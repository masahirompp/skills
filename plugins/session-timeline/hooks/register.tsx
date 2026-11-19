import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelCompleteResult, Register } from 'claude-code'

import type { Backfill, FoundLink, Group, Live, Phase, Recap, Usage } from '../types'
import { stretchesOf, timed, timesOf, transcriptPathOf } from './backfill'
import type { Times } from './backfill'
import { BOUNDARY_TOOLS, MAX_STEPS, SYSTEM, briefOf, fold, outcomeOf, parseVerdict, promptOf } from './classify'
import type { Step, Stretch, Verdict } from './classify'
import { RECAP_SYSTEM, REGROUP_SYSTEM, groupsByKind, mergeSameKind, parseGroups, parseRecap, recapPrompt, regroupPrompt } from './group'
import { addLinks, callMentions, mentionsOf, NOT_ARGUMENTS, rescanLinks } from './links'
import { cells, clockOf, colorOf, durationOf, padCells, usageLine } from './view'

const PANE = 'session-timeline'
const TITLE = 'Session timeline'

const phases = atom({ plugin: 'session-timeline', key: 'phases' } as const, [] as Phase[], { shape: 'phases-2' })
const groups = atom({ plugin: 'session-timeline', key: 'groups' } as const, [] as Group[], { shape: 'groups-1' })
const expanded = atom({ plugin: 'session-timeline', key: 'expanded' } as const, [] as string[], { shape: 'expanded-1' })
const recap = atom({ plugin: 'session-timeline', key: 'recap' } as const, null as Recap, { shape: 'recap-1' })
const savedLatest = atom({ plugin: 'session-timeline', key: 'latestRow' } as const, '')
const usage = atom({ plugin: 'session-timeline', key: 'usage' } as const, { calls: 0, input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } as Usage, { shape: 'usage-1' })
const live = atom({ plugin: 'session-timeline', key: 'live' } as const, null as Live, { shape: 'live-1' })
const backfill = atom({ plugin: 'session-timeline', key: 'backfill' } as const, null as Backfill, { shape: 'backfill-1' })
const isBackfilled = atom({ plugin: 'session-timeline', key: 'isBackfilled' } as const, false)
const cwd = atom({ plugin: 'session-timeline', key: 'cwd' } as const, '')
const transcriptPath = atom({ plugin: 'session-timeline', key: 'transcriptPath' } as const, '')
const links = atom({ plugin: 'session-timeline', key: 'links' } as const, [] as FoundLink[], { shape: 'links-1' })
/** How many links the pane shows; the rest are counted. */
const SHOWN_LINKS = 8
/** How many messages the conversation held when the live recording began: the backfill covers those alone. -1 unknown. */
const liveFromIndex = atom({ plugin: 'session-timeline', key: 'liveFromIndex' } as const, -1)

// The stretch being gathered and the classifications in flight: a reload drops
// them, and the next stretch starts afresh.
let stretch: Stretch | undefined
/** Calls of a stretch still running: a stretch is classified once it is closed and none is left. */
const running = new Map<Stretch, number>()
const closed = new WeakSet<Stretch>()
/** Whether this module has asked for the backfill yet: set before any await, so two opens ask once. */
let isFillAsked = false
/** Bumped by a reset: a backfill begun under an older epoch writes nothing more. */
let epoch = 0
let queue: Promise<void> = Promise.resolve()
let isRegroupQueued = false
/**
 * The conversation's newest row, to come back to. The transcript draws only the
 * rows on screen, so a row drawn for the first time is new only while a reply
 * runs or just after it ends; one drawn when the person scrolls back is old.
 */
let latestRow: string | undefined
let latestTool: string | undefined
let isReplying = false
let repliedAt = 0
/**
 * When this module loaded or the conversation was switched: the rows drawn just
 * after it are the ones on screen, the bottom as a rule.
 */
let loadedAt = 0
const seenRows = new Set<string>()
const FRESH_MS = 5000
/** A turn ended (or the history came in) since the recap was last written. */
let isRecapWanted = false
/**
 * Bumped as /clear or /resume swaps the conversation in this process: a live
 * stretch of the one before writes nothing into the next.
 */
let conversation = 0
/**
 * How the conversation was swapped (/clear or /resume), until the next one's
 * first event takes it up: no `session.start` comes for it.
 */
let switched: 'clear' | 'resume' | undefined
let adopting: Promise<void> = Promise.resolve()
/**
 * Whether this module has opened the pane: it stays up through /clear and /resume,
 * so the conversation moved to fills in as it is taken up.
 */
let isPaneOpened = false

function enqueue(job: () => Promise<void>): void {
  queue = queue.then(job).catch(() => undefined)
}

/**
 * Adds a model call's tokens to the running total, answered or not: a failed call can still cost.
 * `mine` is the conversation that asked: a call answered after /clear or /resume adds nothing to the next.
 */
async function track($: EngineInterface, r: ModelCompleteResult, mine: number): Promise<void> {
  if (conversation !== mine) return
  const u = r.usage
  await update($, usage, t => ({
    calls: t.calls + 1,
    input: t.input + (u.input_tokens ?? 0),
    output: t.output + (u.output_tokens ?? 0),
    cacheRead: t.cacheRead + (u.cache_read_input_tokens ?? 0),
    cacheWrite: t.cacheWrite + (u.cache_creation_input_tokens ?? 0),
  }))
}

/** Regroups once the work queued before it is done; one waiting regroup covers any number of asks. */
function scheduleRegroup($: EngineInterface): void {
  if (isRegroupQueued) return
  isRegroupQueued = true
  enqueue(async () => {
    isRegroupQueued = false
    // Of the conversation it runs in: one swapped in under it writes nothing more.
    const mine = conversation
    await regroup($, mine)
    if (isRecapWanted && conversation === mine) {
      isRecapWanted = false
      await writeRecap($, mine)
    }
  })
}

/** The whole session's fine phases, cut again into the phases a person would name. */
async function regroup($: EngineInterface, mine: number): Promise<void> {
  const list = await read($, phases)
  if (conversation !== mine) return
  if (list.length <= 2) {
    await update($, groups, () => groupsByKind(list))
    return
  }
  const previous = await read($, groups)
  const r = await $.model.complete({
    model: 'haiku',
    system: REGROUP_SYSTEM,
    prompt: regroupPrompt(list, previous),
    maxTokens: 1500,
    effort: 'low',
    timeoutMs: 45000,
  })
  await track($, r, mine)
  if (conversation !== mine) return
  const parsed = r.isAnswered ? parseGroups(r.text, list) : undefined
  // A failed regroup keeps the last good one; new phases show as not yet grouped.
  if (!parsed && previous.length > 0) return
  await update($, groups, () => mergeSameKind(parsed ?? groupsByKind(list)))
}

/** Where the session stands, from the phases, the person's prompts and the last answer. */
async function writeRecap($: EngineInterface, mine: number): Promise<void> {
  const grouped = await read($, groups)
  if (grouped.length === 0) return
  const messages = await $.session.messages()
  if (!Array.isArray(messages)) return
  const prompts = messages
    .filter(m => m.role === 'user' && (m.toolResults?.length ?? 0) === 0 && m.text.trim() !== '')
    .map(m => m.text)
    .slice(-15)
  const answer = [...messages].reverse().find(m => m.role === 'assistant' && m.text.trim() !== '')?.text ?? ''
  const r = await $.model.complete({
    model: 'haiku',
    system: RECAP_SYSTEM,
    prompt: recapPrompt(grouped, prompts, answer),
    maxTokens: 800,
    effort: 'low',
    timeoutMs: 45000,
  })
  await track($, r, mine)
  const next = r.isAnswered ? parseRecap(r.text) : null
  if (next && conversation === mine) await update($, recap, () => next)
}

/** The URLs said in the conversation `mine` as it goes: a prompt, an answer, a tool call's arguments. */
async function noteLinks($: EngineInterface, mentions: readonly string[], mine: number): Promise<void> {
  if (conversation !== mine) return
  // Checked again as the change applies: the read beneath `update` (and its retry) can outlast a switch,
  // whose clearing the change would otherwise fill with the last conversation's links.
  await update($, links, known => (conversation === mine ? addLinks(known, mentions) : known))
}

/** The links of the whole conversation, read again from its messages: the history before the mod loaded, or /resume's. */
async function rescan($: EngineInterface): Promise<void> {
  const mine = conversation
  const messages = await $.session.messages().catch(() => undefined)
  if (!Array.isArray(messages) || conversation !== mine) return
  await update($, links, known => (conversation === mine ? rescanLinks(known, mentionsOf(messages)) : known))
}

async function gather($: EngineInterface): Promise<Stretch> {
  if (!stretch) {
    // Set before the first await: two calls arriving together share one stretch.
    const s: Stretch = { steps: [], subSteps: 0 }
    stretch = s
    s.start = await $.clock.now()
    await update($, live, l => ({ since: s.start ?? 0, steps: 0, isClassifying: l?.isClassifying ?? false }))
  }
  return stretch
}

async function countStep($: EngineInterface): Promise<void> {
  await update($, live, l => (l ? { ...l, steps: l.steps + 1 } : l))
}

/** Closes the stretch; it is classified once its running calls are back. */
function close($: EngineInterface): void {
  const done = stretch
  stretch = undefined
  if (!done) return
  closed.add(done)
  if (!running.get(done)) finish($, done)
}

/** Classifies a closed stretch with nothing left running, after the ones before it. */
function finish($: EngineInterface, done: Stretch): void {
  running.delete(done)
  if (done.steps.length === 0 && !done.prompt && !done.answer) return
  const mine = conversation
  enqueue(() => classifyLive($, done, mine))
}

async function judge($: EngineInterface, done: Stretch, recent: readonly Phase[], mine: number): Promise<Verdict> {
  const r = await $.model.complete({
    model: 'haiku',
    system: SYSTEM,
    prompt: promptOf(done, recent),
    maxTokens: 400,
    effort: 'low',
    timeoutMs: 30000,
  })
  await track($, r, mine)
  return (
    (r.isAnswered ? parseVerdict(r.text) : undefined) ?? {
      continues: recent.length > 0,
      label: recent[recent.length - 1]?.label ?? '作業',
      note: '',
      summary: '',
    }
  )
}

async function classifyLive($: EngineInterface, done: Stretch, mine: number): Promise<void> {
  if (conversation !== mine) return
  const ended: Stretch = { ...done, end: await $.clock.now() }
  await update($, live, l => (l ? { ...l, isClassifying: true } : { since: done.start ?? 0, steps: 0, isClassifying: true }))
  const verdict = await judge($, ended, (await read($, phases)).slice(-6), mine)
  if (conversation !== mine) return
  await update($, phases, list => fold(list, ended, verdict, 'live'))
  scheduleRegroup($)
  const isGathering = stretch !== undefined
  await update($, live, l => (isGathering && l ? { ...l, isClassifying: false } : null))
}

/** Each tool call's times from the transcript file, or none where it cannot be read. */
async function readTimes($: EngineInterface): Promise<Times> {
  try {
    let path = await read($, transcriptPath)
    if (!path) {
      const configDir = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${(await $.env.get('HOME')) ?? ''}/.claude`
      path = transcriptPathOf(configDir, await read($, cwd), await $.session.id())
    }
    return timesOf(await $.fs.read(path))
  } catch {
    return new Map()
  }
}

/** Classifies the history before the mod loaded and puts it ahead of the live phases. */
/** The conversation's messages, or none where the session cannot give them. */
async function messageCount($: EngineInterface): Promise<number> {
  const messages = await $.session.messages().catch(() => undefined)
  return Array.isArray(messages) ? messages.length : -1
}

/**
 * Classifies the history before the live recording began and puts it ahead of the
 * live phases. Returns false where a reset made it stale before it finished.
 */
async function fillHistory($: EngineInterface, mine: number, talk: number): Promise<boolean> {
  const all = await $.session.messages()
  if (!Array.isArray(all)) return true
  // Only what came before the live recording: a turn it saw, text alone included, is its own.
  const until = await read($, liveFromIndex)
  const messages = until >= 0 ? all.slice(0, until) : all
  // A backfill cut short left past- phases: they are this backfill's to redo, not known.
  const existing = (await read($, phases)).filter(p => !p.id.startsWith('past-'))
  const known = new Set([...existing.flatMap(p => p.toolIds), ...(stretch?.steps.map(s => s.id) ?? [])])
  const liveStarts = [...existing.map(p => p.start), stretch?.start].filter((n): n is number => n !== undefined)
  const liveFrom = liveStarts.length > 0 ? Math.min(...liveStarts) : undefined
  const past = timed(stretchesOf(messages, known), await readTimes($), liveFrom)
  if (past.length === 0) return epoch === mine

  let done: Phase[] = []
  if (epoch !== mine) return false
  await update($, backfill, () => ({ done: 0, total: past.length }))
  for (const s of past) {
    const verdict = await judge($, s, done.slice(-6), talk)
    if (epoch !== mine) return false
    done = fold(done, s, verdict, 'past')
    const now = done
    await update($, phases, list => [...now, ...list.filter(p => !p.id.startsWith('past-'))])
    await update($, backfill, b => (b ? { ...b, done: b.done + 1 } : b))
  }
  return epoch === mine
}

async function openPane($: EngineInterface): Promise<boolean> {
  isPaneOpened = true
  const { isPlaced } = await $.ui.open({ id: PANE, title: TITLE })
  await rescan($)
  await askFill($)
  return isPlaced
}

/** Asks for the backfill once per conversation; where it is done, makes the grouping or recap still missing. */
async function askFill($: EngineInterface): Promise<void> {
  // Read and set with no await between: of two opens at once, one asks.
  const isFirstAsk = !isFillAsked
  isFillAsked = true
  if (isFirstAsk && !(await read($, isBackfilled))) {
    const mine = epoch
    const talk = conversation
    enqueue(async () => {
      try {
        // Marked done only once it is: a backfill a reload cuts short runs again on the next open.
        if (await fillHistory($, mine, talk)) await update($, isBackfilled, () => true)
      } finally {
        if (epoch === mine) {
          await update($, backfill, () => null)
          isRecapWanted = true
          scheduleRegroup($)
        }
      }
    })
  } else if ((await read($, phases)).length > 0) {
    // Phases recorded before regrouping or the recap existed: make them now.
    const isMissingRecap = (await read($, recap)) === null
    if (isMissingRecap) isRecapWanted = true
    if (isMissingRecap || (await read($, groups)).length === 0) scheduleRegroup($)
  }
}

/** Forgets every phase, the grouping, the recap and the links, so the next open rebuilds them from the history. */
async function reset($: EngineInterface): Promise<void> {
  // A backfill under way stops writing; the open after this asks for a new one over the whole history.
  epoch += 1
  isFillAsked = false
  const count = await messageCount($)
  await update($, liveFromIndex, () => count)
  await update($, backfill, () => null)
  await update($, phases, () => [])
  await update($, groups, () => [])
  await update($, expanded, () => [])
  await update($, recap, () => null)
  // Read again from the history as the pane opens after this, none of the old kept ahead.
  await update($, links, () => [])
  await update($, isBackfilled, () => false)
}

/**
 * Drops what this module holds of the conversation ending under /clear or
 * /resume. The process goes on under another, whose first event takes it up.
 */
function forget(reason: 'clear' | 'resume'): void {
  epoch += 1
  conversation += 1
  isFillAsked = false
  stretch = undefined
  running.clear()
  isRecapWanted = false
  latestRow = undefined
  latestTool = undefined
  isReplying = false
  repliedAt = 0
  seenRows.clear()
  loadedAt = Date.now()
  switched = reason
}

/**
 * Takes up the conversation /clear or /resume swapped in, once, at its first
 * event: no `session.start` comes for it. Where the live recording begins is set
 * here; `prompt` is the turn that brought it, which the history may hold already.
 * Waits for one taking it up already.
 */
function adopt($: EngineInterface, isFilled: boolean, prompt?: string): Promise<void> {
  const reason = switched
  if (!reason) return adopting
  switched = undefined
  adopting = (async () => {
    const all = await $.session.messages().catch(() => undefined)
    let count = Array.isArray(all) ? all.length : -1
    const last = Array.isArray(all) ? all[all.length - 1] : undefined
    if (prompt !== undefined && last?.role === 'user' && (last.toolResults?.length ?? 0) === 0 && last.text === prompt) {
      count -= 1
    }
    // The engine starts the state afresh for the next conversation; cleared here too, so none of the last is kept.
    await update($, liveFromIndex, () => count)
    await update($, backfill, () => null)
    await update($, live, () => null)
    await update($, phases, () => [])
    await update($, groups, () => [])
    await update($, expanded, () => [])
    await update($, recap, () => null)
    await update($, savedLatest, () => '')
    await update($, links, () => [])
    await update($, usage, () => ({ calls: 0, input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }))
    const here = await $.session.cwd().catch(() => '')
    if (here) await update($, cwd, () => here)
    // After /clear there is nothing to fill: the one message before is the record of the command.
    await update($, isBackfilled, () => reason === 'clear')
    if (reason === 'resume' && isFilled) {
      await rescan($)
      await askFill($)
    }
  })().catch(() => undefined)
  return adopting
}

async function startTurn($: EngineInterface, text: string): Promise<void> {
  close($)
  const s = await gather($)
  s.prompt = text
}

async function endTurn($: EngineInterface, answer: string): Promise<void> {
  const s = await gather($)
  s.answer = answer
  close($)
  // Asked once the turn's last stretch is classified, so the recap reads the regroup that takes it in.
  const mine = conversation
  enqueue(async () => {
    if (conversation !== mine) return
    isRecapWanted = true
    scheduleRegroup($)
  })
}

/** A finished tool call: into its stretch, or counted as a subagent's step when `s` is none. */
async function record($: EngineInterface, s: Stretch | undefined, step: Step): Promise<void> {
  if (!s) {
    if (stretch) stretch.subSteps += 1
    await countStep($)
    return
  }
  // The call may have outlived its stretch: it still belongs to the one it began in.
  s.steps.push(step)
  const left = (running.get(s) ?? 1) - 1
  running.set(s, left)
  await countStep($)
  if (closed.has(s)) {
    if (left === 0) finish($, s)
  } else if (stretch === s && (BOUNDARY_TOOLS.has(step.tool) || s.steps.length >= MAX_STEPS)) close($)
}

export const register: Register = (on, options) => {
  loadedAt = Date.now()
  // userConfig: open the pane as the session starts, so it is there without /timeline.
  const isAutoOpen = options.autoOpen !== false

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'timeline',
      description: 'Show what this session is doing, phase by phase (reset: rebuild from the history)',
    })
    await update($, cwd, c => c || e.cwd)
    // A fresh module has no backfill running: progress left by one a reload cut short is stale.
    await update($, backfill, () => null)
    // Where the live recording begins, once per session: the backfill covers the messages before it.
    if ((await read($, liveFromIndex)) < 0) {
      const count = await messageCount($)
      if (count >= 0) await update($, liveFromIndex, () => count)
    }
    // Unasked, the pane waits undrawn until the terminal is wide enough or the person opens it.
    if (isAutoOpen) void openPane($).catch(() => undefined)
    return next(e)
  })

  // /clear and /resume go on in this process under another conversation, and no session.start comes for it.
  on('session.end', ($, e, next) => {
    if (e.reason === 'clear' || e.reason === 'resume') forget(e.reason)
    return next(e)
  })

  // The transcript's own path, from the settings hooks' input, where they run.
  on('classic.UserPromptSubmit', async ($, e, next) => {
    await update($, transcriptPath, () => e.transcript_path).catch(() => undefined)
    return next(e)
  })

  on('command.run', { command: 'timeline' }, async ($, e) => {
    await adopt($, false)
    if (e.args.trim() === 'reset') await reset($)
    const isPlaced = await openPane($)
    return { text: isPlaced ? 'Timeline pane opened.' : 'Timeline pane is waiting for room (widen the terminal).' }
  })

  // Rows drawn for the first time are the newest; a row scrolled back into view is not new.
  on(
    'ui.render',
    { component: ['UserMessage', 'AssistantMessage', 'ToolUse', 'ToolGroup', 'CommandOutput', 'TurnDuration'] },
    ($, e, next) => {
      if (!seenRows.has(e.requestId)) {
        seenRows.add(e.requestId)
        const now = Date.now()
        if (isReplying || now - repliedAt < FRESH_MS || now - loadedAt < FRESH_MS) latestRow = e.requestId
      }
      return next(e)
    },
  )

  on('turn.start', async ($, e, next) => {
    if (!e.agentId) {
      // Where the pane stands (autoOpen, or /timeline before the switch), the history /resume brought fills in as the turn begins.
      await adopt($, isAutoOpen || isPaneOpened, e.text)
      isReplying = true
      await noteLinks($, [e.text], conversation).catch(() => undefined)
      await startTurn($, e.text).catch(() => undefined)
    }
    return next(e)
  })

  // What Claude writes mid-turn, before a tool call, is said as each response ends: the turn's last words are not all of it.
  on('turn.step', async function* ($, e, next) {
    const mine = conversation
    const r = yield* next(e)
    if (!e.agentId && r.answer) await noteLinks($, [r.answer], mine).catch(() => undefined)
    return r
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (!e.agentId) {
      isReplying = false
      repliedAt = Date.now()
      await noteLinks($, [e.answer], conversation).catch(() => undefined)
      await endTurn($, e.answer).catch(() => undefined)
      // Kept past a reload: the rows the reply drew may not be drawn again before the person asks.
      const row = latestRow ?? latestTool
      if (row) await update($, savedLatest, () => row).catch(() => undefined)
    }
    return done
  })

  on('tool.call', async ($, e, next) => {
    // An Agent or Skill call (a review, a plan) is a stretch of its own: close what came before it,
    // unless that holds nothing yet but the prompt, which the call then shares.
    const before = stretch
    if (!e.agentId && BOUNDARY_TOOLS.has(e.tool) && before && (before.steps.length > 0 || running.get(before))) close($)
    const s = e.agentId ? undefined : await gather($).catch(() => undefined)
    if (s) running.set(s, (running.get(s) ?? 0) + 1)
    if (!e.agentId) latestTool = e.tool_use_id
    const mine = conversation
    const ran = await next(e)
    if (!e.agentId) {
      // The tool's arguments alone: what rides beside them (consent, requestMeta) is no one's pick.
      const args = Object.fromEntries(Object.entries(e).filter(([k]) => !NOT_ARGUMENTS.includes(k)))
      await noteLinks($, callMentions(e.tool, args), mine).catch(() => undefined)
    }
    const outcome = outcomeOf(e.tool, ran.result ?? ran.text)
    const step: Step = {
      id: e.tool_use_id,
      tool: e.tool,
      brief: briefOf(e as unknown as Record<string, unknown>),
      isError: ran.isError === true,
      ...(outcome !== undefined ? { outcome } : {}),
    }
    await record($, s, step).catch(() => undefined)
    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Link } = $.ui.resolve(e)
    const list = await read($, phases)
    const grouped = await read($, groups)
    const open = new Set(await read($, expanded))
    const now = await $.clock.now()
    const current = await read($, live)
    const filling = await read($, backfill)

    const progress = filling ? (
      <Text color="suggestion">
        過去分を判定中… {filling.done}/{filling.total}
      </Text>
    ) : null

    const found = await read($, links)
    const linkW = Math.max(20, (e.props.bodyColumns ?? 70) - 8)
    const linkRows = found.slice(0, SHOWN_LINKS).map(l => (
      <Box key={'link-' + l.key} flexDirection="row">
        <Text dimColor>{padCells(l.kind, 7)}</Text>
        <Link href={l.href} label={cells(l.label) > linkW ? padCells(l.label, linkW - 1) + '…' : l.label} />
      </Box>
    ))
    const linkSection =
      linkRows.length > 0 ? (
        <Box flexDirection="column" marginTop={1}>
          <Text bold>リンク</Text>
          {linkRows}
          {found.length > SHOWN_LINKS ? <Text dimColor>ほか {found.length - SHOWN_LINKS} 件</Text> : null}
        </Box>
      ) : null

    if (list.length === 0 && !current) {
      return (
        <Box flexDirection="column">
          {progress}
          <Text dimColor>まだ工程がありません。作業が進むと、区切りごとに工程名が付きます。</Text>
          {linkSection}
        </Box>
      )
    }

    const byId = new Map(list.map(p => [p.id, p]))
    const covered = new Set(grouped.flatMap(g => g.phaseIds))
    // Fine phases newer than the last regroup show alone until the next one takes them in.
    const rows: { group: Group; members: Phase[]; isPending: boolean }[] = [
      ...grouped
        .map(g => ({ group: g, members: g.phaseIds.map(id => byId.get(id)).filter((p): p is Phase => !!p), isPending: false }))
        .filter(r => r.members.length > 0),
      ...list
        .filter(p => !covered.has(p.id))
        .map(p => ({
          group: { id: 'g-' + p.id, label: p.label, note: p.note, summary: p.summary, phaseIds: [p.id] },
          members: [p],
          isPending: true,
        })),
    ]

    const labelW =
      Math.min(24, Math.max(6, ...rows.map(r => cells(r.group.label) + (r.group.isSide ? 6 : 0)))) + 1
    const spent = (ps: readonly Phase[]) =>
      ps.reduce((sum, p) => sum + (p.start !== undefined && p.end !== undefined ? p.end - p.start : 0), 0)
    const jump = async (anchor: string) => {
      const r = await $.ui.scroll({ to: { requestId: anchor }, block: 'start' })
      if (r.deny) await $.ui.toast(`その位置へ移動できませんでした: ${r.deny}`)
    }
    const saved = await read($, savedLatest)
    const lastKnownTool = [...list].reverse().find(p => p.toolIds.length > 0)?.toolIds.at(-1)
    const toLatest = async () => {
      const target = latestRow ?? latestTool ?? (saved || undefined) ?? lastKnownTool
      const r = target ? await $.ui.scroll({ to: { requestId: target }, block: 'end' }) : { deny: '最新の行が分かりません' }
      if (r.deny) await $.ui.toast(`最新の会話へ移動できませんでした: ${r.deny}`)
    }

    const drawn = rows.map(({ group: g, members, isPending }, i) => {
      const isOpen = open.has(g.id)
      const ms = spent(members)
      const anchor = members.find(p => p.anchor)?.anchor
      const canOpen = members.length > 1
      const isSide = g.isSide === true
      const line = [
        <Text dimColor>{clockOf(members[0]?.start)}  </Text>,
        isSide ? <Text dimColor>↳ </Text> : <Text color={colorOf(g.label)}>{isPending ? '○ ' : '● '}</Text>,
        <Text bold={!isPending && !isSide} dimColor={isPending || isSide}>
          {padCells(isSide ? `脇道: ${g.label}` : g.label, labelW)}
        </Text>,
        <Text dimColor={isSide}>{padCells(ms > 0 ? durationOf(ms) : '', 8)}</Text>,
        g.note ? isSide ? <Text dimColor>{g.note}</Text> : <Text color="warning">{g.note}</Text> : null,
        canOpen ? <Text dimColor>  {isOpen ? '▾' : '▸'}{members.length}</Text> : null,
      ]
      const press = async () => {
        if (canOpen) await update($, expanded, ids => (ids.includes(g.id) ? ids.filter(id => id !== g.id) : [...ids, g.id]))
        if (anchor) await jump(anchor)
      }
      return (
        <Box key={g.id} flexDirection="column">
          <Button key={'go-' + g.id} plain onPress={press}>
            {line}
          </Button>
          {g.summary ? (
            <Text dimColor wrap="truncate-end">
              {'       │  '}
              {g.summary}
            </Text>
          ) : null}
          {isOpen
            ? members.map((p, k) => {
                const at = p.anchor
                const child = [
                  <Text dimColor>
                    {'       '}
                    {k === members.length - 1 ? '└ ' : '├ '}
                    {clockOf(p.start)}{' '}
                  </Text>,
                  isSide ? (
                    <Text dimColor>{padCells(p.label, labelW)}</Text>
                  ) : (
                    <Text color={colorOf(p.label)}>{padCells(p.label, labelW)}</Text>
                  ),
                  <Text dimColor>
                    {padCells(p.start !== undefined && p.end !== undefined ? durationOf(p.end - p.start) : '', 8)}
                  </Text>,
                  <Text dimColor wrap="truncate-end">{p.note || p.summary}</Text>,
                ]
                return at ? (
                  <Button key={'go-' + p.id} plain onPress={() => jump(at)}>
                    {child}
                  </Button>
                ) : (
                  <Box key={p.id} flexDirection="row">
                    {child}
                  </Box>
                )
              })
            : null}
          <Text dimColor>{'       │'}</Text>
        </Box>
      )
    })

    const summary = await read($, recap)
    const tokens = await read($, usage)
    const recapRows = summary
      ? (
          [
            ['目的', summary.goal],
            ['現状', summary.status],
            ['次', summary.next],
          ] as const
        )
          .filter(([, text]) => text !== '')
          .map(([head, text]) => (
            <Box flexDirection="row">
              <Text dimColor>{padCells(head, 6)}</Text>
              <Text wrap="wrap">{text}</Text>
            </Box>
          ))
      : null

    return (
      <Box flexDirection="column">
        {progress}
        {drawn}
        <Button key="now" plain onPress={toLatest}>
          <Text dimColor>{current ? clockOf(current.since) : clockOf(now)}  </Text>
          <Text color="suggestion">◉ </Text>
          <Text bold>{padCells('いま', labelW)}</Text>
          <Text dimColor>
            {current
              ? `${current.isClassifying ? '判定中…' : '進行中'}  ${durationOf(now - current.since)} · ${current.steps}手`
              : '待機中'}
          </Text>
        </Button>
        {recapRows ? (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>まとめ</Text>
            {recapRows}
          </Box>
        ) : null}
        {linkSection}
        {tokens.calls > 0 ? (
          <Box marginTop={1}>
            <Text dimColor wrap="truncate-end">
              {usageLine(tokens)}
            </Text>
          </Box>
        ) : null}
      </Box>
    )
  })
}
