import { atom, read, update } from 'claude-code'
import type { EngineInterface, ModelCompleteResult, Register } from 'claude-code'

import type { Backfill, Group, Live, Mark, Phase, Recap, Usage } from '../types'
import { stretchesOf, timeReader, timed, transcriptPathOf } from './backfill'
import type { Times } from './backfill'
import { BOUNDARY_TOOLS, MAX_STEPS, SYSTEM, briefOf, fold, outcomeOf, parseVerdict, promptOf } from './classify'
import type { Step, Stretch, Verdict } from './classify'
import { RECAP_SYSTEM, REGROUP_SYSTEM, groupsByKind, mergeSameKind, parseGroups, parseRecap, recapPrompt, regroupPrompt } from './group'
import { capped, isNewModel, joined, markReader, markRows, observed, placeOf } from './marks'
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
/** How many messages the conversation held when the live recording began: the backfill covers those alone. -1 unknown. */
const liveFromIndex = atom({ plugin: 'session-timeline', key: 'liveFromIndex' } as const, -1)
/** The model changes and compactions, oldest first: those before `liveSince` read off the transcript, the rest seen live. */
const marks = atom({ plugin: 'session-timeline', key: 'marks' } as const, [] as Mark[], { shape: 'marks-1' })
/**
 * When the live recording began, a reset leaving it be: the transcript's marks from before it are the backfill's.
 * 0 not settled yet: `liveStart` settles it where it is first needed.
 */
const liveSince = atom({ plugin: 'session-timeline', key: 'liveSince' } as const, 0)
/**
 * Whether the transcript's marks from before `liveSince` are in. Apart from `isBackfilled`: the phases
 * can be filled in without the transcript, and were by versions that kept no marks.
 */
const isMarksFilled = atom({ plugin: 'session-timeline', key: 'isMarksFilled' } as const, false)

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
/** When this module loaded: the rows drawn just after it are the ones on screen, the bottom as a rule. */
let loadedAt = 0
const seenRows = new Set<string>()
const FRESH_MS = 5000
/** A turn ended (or the history came in) since the recap was last written. */
let isRecapWanted = false

function enqueue(job: () => Promise<void>): void {
  queue = queue.then(job).catch(() => undefined)
}

/** Adds a model call's tokens to the running total, answered or not: a failed call can still cost. */
async function track($: EngineInterface, r: ModelCompleteResult): Promise<void> {
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
    await regroup($)
    if (isRecapWanted) {
      isRecapWanted = false
      await writeRecap($)
    }
  })
}

/** The whole session's fine phases, cut again into the phases a person would name. */
async function regroup($: EngineInterface): Promise<void> {
  const list = await read($, phases)
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
  await track($, r)
  const parsed = r.isAnswered ? parseGroups(r.text, list) : undefined
  // A failed regroup keeps the last good one; new phases show as not yet grouped.
  if (!parsed && previous.length > 0) return
  await update($, groups, () => mergeSameKind(parsed ?? groupsByKind(list)))
}

/** Where the session stands, from the phases, the person's prompts and the last answer. */
async function writeRecap($: EngineInterface): Promise<void> {
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
  await track($, r)
  const next = r.isAnswered ? parseRecap(r.text) : null
  if (next) await update($, recap, () => next)
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
  enqueue(() => classifyLive($, done))
}

async function judge($: EngineInterface, done: Stretch, recent: readonly Phase[]): Promise<Verdict> {
  const r = await $.model.complete({
    model: 'haiku',
    system: SYSTEM,
    prompt: promptOf(done, recent),
    maxTokens: 400,
    effort: 'low',
    timeoutMs: 30000,
  })
  await track($, r)
  return (
    (r.isAnswered ? parseVerdict(r.text) : undefined) ?? {
      continues: recent.length > 0,
      label: recent[recent.length - 1]?.label ?? '作業',
      note: '',
      summary: '',
    }
  )
}

async function classifyLive($: EngineInterface, done: Stretch): Promise<void> {
  const ended: Stretch = { ...done, end: await $.clock.now() }
  await update($, live, l => (l ? { ...l, isClassifying: true } : { since: done.start ?? 0, steps: 0, isClassifying: true }))
  const verdict = await judge($, ended, (await read($, phases)).slice(-6))
  // The marks so far: a change of model or a compaction since the last phase's work began starts a new phase.
  const breaks = (await read($, marks)).map(m => m.at)
  await update($, phases, list => fold(list, ended, verdict, 'live', breaks))
  scheduleRegroup($)
  const isGathering = stretch !== undefined
  await update($, live, l => (isGathering && l ? { ...l, isClassifying: false } : null))
}

/**
 * When the live recording began, settled as now where nothing has settled it; 0 where the clock cannot be read.
 * Not `session.start`'s alone to settle: a process that moves to another conversation (/clear, /resume)
 * goes on with an empty state and no `session.start`.
 */
async function liveStart($: EngineInterface): Promise<number> {
  const known = await read($, liveSince)
  if (known > 0) return known
  const now = await $.clock.now().catch(() => 0)
  if (now <= 0) return 0
  await update($, liveSince, at => (at > 0 ? at : now))
  return read($, liveSince)
}

/**
 * Notes the model the main conversation runs on, where it is another than the one last seen.
 * `isStart`: the session is beginning, so a first sighting is the model it began on.
 */
async function noteModel($: EngineInterface, isStart = false): Promise<void> {
  // Before the sighting's own time: what is seen live is never earlier than where the live recording began.
  await liveStart($)
  const model = await $.session.model().catch(() => undefined)
  if (typeof model !== 'string' || model === '') return
  if (!isNewModel(await read($, marks), model)) return
  const at = await $.clock.now()
  await update($, marks, list => observed(list, model, at, !isStart))
}

/** What the timeline takes from the transcript file: the marks, and each tool call's times. */
type Transcript = { marks: Mark[]; times: Times }

/** How much of the transcript file one ranged read asks for: `$.fs.read` answers 4 MiB at most. */
const RANGE_BYTES = 2 * 1024 * 1024
/** Ranged reads of one file, at most: a read that never comes back empty is given up on. */
const MAX_RANGES = 4096

/**
 * Reads the transcript file; undefined where it cannot be read. A file over the 4 MiB one
 * read may answer is read by ranges, its lines taken in as they come: transcripts grow well past that.
 */
async function readTranscript($: EngineInterface): Promise<Transcript | undefined> {
  try {
    // Neither the path nor the directory need be in the state: no prompt may have come yet, and after a
    // /clear or a /resume no `session.start` has. The session tells both.
    let path = await read($, transcriptPath)
    if (!path) path = (await $.session.info().catch(() => undefined))?.transcriptPath ?? ''
    if (!path) {
      const configDir = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${(await $.env.get('HOME')) ?? ''}/.claude`
      const dir = (await read($, cwd)) || (await $.session.cwd().catch(() => ''))
      path = transcriptPathOf(configDir, dir, await $.session.id())
    }
    const marks = markReader()
    const times = timeReader()
    const take = (line: string) => {
      marks.take(line)
      times.take(line)
    }
    // Whole where it fits. The read is refused for a file too large as for one missing: the ranges tell which.
    const whole = await $.fs.read(path).catch(() => undefined)
    if (whole !== undefined) {
      for (const line of whole.split('\n')) take(line)
    } else {
      // A range's edge may cut a line, or a character in it (U+FFFD there, inside a string: the row still parses).
      let rest = ''
      let n = 0
      for (;;) {
        if (n >= MAX_RANGES) return undefined
        const text = await $.fs.read(path, { offset: n * RANGE_BYTES, length: RANGE_BYTES })
        // Past the file's end the read is empty.
        if (text === '') break
        n += 1
        const lines = (rest + text).split('\n')
        rest = lines.pop() ?? ''
        for (const line of lines) take(line)
      }
      take(rest)
    }
    return { marks: marks.marks(), times: times.times }
  } catch {
    return undefined
  }
}

/**
 * Puts the transcript's marks from before the live recording ahead of the ones it saw, which it leaves as they are
 * (but that a first sighting with no model before it in the transcript is the model the conversation began on).
 * Only a transcript that was read is given here: the earlier reading's marks it replaces are lost to it.
 */
async function fillMarks($: EngineInterface, mine: number, found: readonly Mark[]): Promise<void> {
  const since = await liveStart($)
  // With no time to part the transcript's marks from the live ones, they are owed still.
  if (since <= 0) return
  const past = found.filter(m => m.at < since)
  if (epoch !== mine) return
  await update($, marks, list => joined(past, list.filter(m => m.at >= since)))
  if (epoch !== mine) return
  await update($, isMarksFilled, () => true)
}

/**
 * Asks for the transcript's marks again where they are not in yet: the transcript
 * could not be read the last time, or the phases were filled in with no marks kept.
 */
function retryMarks($: EngineInterface): void {
  const mine = epoch
  enqueue(async () => {
    if (epoch !== mine || (await read($, isMarksFilled))) return
    const transcript = await readTranscript($)
    if (transcript) await fillMarks($, mine, transcript.marks)
  })
}

/** The conversation's messages, or none where the session cannot give them. */
async function messageCount($: EngineInterface): Promise<number> {
  const messages = await $.session.messages().catch(() => undefined)
  return Array.isArray(messages) ? messages.length : -1
}

/**
 * Classifies the history before the live recording began and puts it ahead of the
 * live phases. Returns false where a reset made it stale before it finished.
 */
async function fillHistory($: EngineInterface, mine: number, times: Times): Promise<boolean> {
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
  const past = timed(stretchesOf(messages, known), times, liveFrom)
  if (past.length === 0) return epoch === mine

  let done: Phase[] = []
  // The marks are in before the phases are judged: a phase ends where a mark stands.
  const breaks = (await read($, marks)).map(m => m.at)
  if (epoch !== mine) return false
  await update($, backfill, () => ({ done: 0, total: past.length }))
  for (const s of past) {
    const verdict = await judge($, s, done.slice(-6))
    if (epoch !== mine) return false
    done = fold(done, s, verdict, 'past', breaks)
    const now = done
    await update($, phases, list => [...now, ...list.filter(p => !p.id.startsWith('past-'))])
    await update($, backfill, b => (b ? { ...b, done: b.done + 1 } : b))
  }
  return epoch === mine
}

async function openPane($: EngineInterface): Promise<boolean> {
  const { isPlaced } = await $.ui.open({ id: PANE, title: TITLE })
  // Read and set with no await between: of two opens at once, one asks.
  const isFirstAsk = !isFillAsked
  isFillAsked = true
  if (isFirstAsk && !(await read($, isBackfilled))) {
    const mine = epoch
    enqueue(async () => {
      try {
        // Marked done only once it is: a backfill a reload cuts short runs again on the next open.
        const transcript = await readTranscript($)
        // The marks first: they cost no model call, and stand while the phases are judged.
        // Where the transcript cannot be read, the marks recorded so far stand as they are.
        if (transcript) await fillMarks($, mine, transcript.marks)
        if (await fillHistory($, mine, transcript?.times ?? new Map())) await update($, isBackfilled, () => true)
      } finally {
        if (epoch === mine) {
          await update($, backfill, () => null)
          isRecapWanted = true
          scheduleRegroup($)
        }
      }
    })
  } else {
    // The marks are owed whatever became of the phases' backfill: asked for on every open until they are in.
    retryMarks($)
    if ((await read($, phases)).length > 0) {
      // Phases recorded before regrouping or the recap existed: make them now.
      const isMissingRecap = (await read($, recap)) === null
      if (isMissingRecap) isRecapWanted = true
      if (isMissingRecap || (await read($, groups)).length === 0) scheduleRegroup($)
    }
  }
  return isPlaced
}

/** Forgets every phase, the grouping and the recap, so the next open rebuilds them from the history. */
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
  await update($, isBackfilled, () => false)
  // The marks seen live stand as they are: the engine told them, and the transcript holds less (no model
  // that answered nothing, not always a compaction's tokens after). `liveSince` stays where it is, so the
  // open after this reads again off the transcript only the marks from before the live recording began.
  await update($, isMarksFilled, () => false)
  await noteModel($).catch(() => undefined)
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
  enqueue(async () => {
    isRecapWanted = true
    scheduleRegroup($)
  })
  // The transcript's path may be known only since this turn's prompt, the file there only since its answer: marks
  // it could not give before, it may now. Asked whether or not this module opened the pane: after a /clear or
  // a /resume the pane stays open with no open asked of this conversation.
  retryMarks($)
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
    // The session itself begins here only where this is the first start the state has seen, with nothing said yet.
    let isSessionStart = false
    if ((await read($, liveFromIndex)) < 0) {
      const count = await messageCount($)
      if (count >= 0) await update($, liveFromIndex, () => count)
      isSessionStart = count === 0
    }
    await liveStart($)
    // The model the session begins on; after a reload, the same one adds nothing. Loaded into a session
    // under way, the model is not the one it began on: the transcript's marks tell what came before.
    await noteModel($, isSessionStart).catch(() => undefined)
    // Unasked, the pane waits undrawn until the terminal is wide enough or the person opens it.
    if (isAutoOpen) void openPane($).catch(() => undefined)
    return next(e)
  })

  // The transcript's own path, from the settings hooks' input, where they run.
  on('classic.UserPromptSubmit', async ($, e, next) => {
    await update($, transcriptPath, () => e.transcript_path).catch(() => undefined)
    return next(e)
  })

  on('command.run', { command: 'timeline' }, async ($, e) => {
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
      isReplying = true
      // A change of model is noted where the first turn runs on it.
      await noteModel($).catch(() => undefined)
      await startTurn($, e.text).catch(() => undefined)
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (!e.agentId) {
      isReplying = false
      repliedAt = Date.now()
      await endTurn($, e.answer).catch(() => undefined)
      // Kept past a reload: the rows the reply drew may not be drawn again before the person asks.
      const row = latestRow ?? latestTool
      if (row) await update($, savedLatest, () => row).catch(() => undefined)
    }
    return done
  })

  on('session.compact', async ($, e, next) => {
    const done = await next(e)
    // The main conversation's own, installed: a precompute changes nothing yet, a skip nothing at all.
    if (!e.agentId && e.trigger !== 'precompute' && done.skip === undefined) {
      const { tokensBefore: before, tokensAfter: after } = done
      const record = async () => {
        await liveStart($)
        const at = await $.clock.now()
        const mark: Mark = {
          kind: 'compact',
          at,
          trigger: e.trigger,
          ...(before !== undefined ? { before } : {}),
          ...(after !== undefined ? { after } : {}),
        }
        await update($, marks, list => capped([...list, mark]))
      }
      await record().catch(() => undefined)
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
    const ran = await next(e)
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
    const { Box, Text, Button } = $.ui.resolve(e)
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

    const noted = markRows(await read($, marks))
    const markLine = (m: (typeof noted)[number]) => (
      <Box key={m.key} flexDirection="column">
        <Text dimColor wrap="truncate-end">
          {clockOf(m.at)}  ◇ {m.text}
        </Text>
        <Text dimColor>{'       │'}</Text>
      </Box>
    )

    if (list.length === 0 && !current) {
      return (
        <Box flexDirection="column">
          {progress}
          {noted.map(markLine)}
          <Text dimColor>まだ工程がありません。作業が進むと、区切りごとに工程名が付きます。</Text>
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

    // Each mark goes ahead of the first phase that starts after it; one after them all, ahead of "now".
    // One that falls among a row's phases parts the row there: the work begun before it stays above it.
    const places = noted.map(m => placeOf(rows.map(r => r.members.map(p => p.start)), m.at))
    const marksAt = (row: number, member: number) =>
      noted.filter((_, k) => places[k]?.row === row && places[k]?.member === member).map(markLine)

    const drawn = rows.flatMap(({ group: g, members: all, isPending }, i) => {
      const cuts = [...new Set(places.filter(p => p.row === i && p.member > 0).map(p => p.member))].sort((a, b) => a - b)
      const edges = [0, ...cuts, all.length]
      return edges.slice(0, -1).map((from, n) => drawPart(g, all.slice(from, edges[n + 1]), isPending, i, from, n === cuts.length))
    })

    /** A row, or the part of one between two marks: the row's name on each part, what it came to on the last. */
    function drawPart(g: Group, members: Phase[], isPending: boolean, i: number, from: number, isLast: boolean) {
      const isOpen = open.has(g.id)
      const ms = spent(members)
      const anchor = members.find(p => p.anchor)?.anchor
      const canOpen = members.length > 1
      const isSide = g.isSide === true
      const key = from === 0 ? g.id : `${g.id}@${from}`
      const line = [
        <Text dimColor>{clockOf(members[0]?.start)}  </Text>,
        isSide ? <Text dimColor>↳ </Text> : <Text color={colorOf(g.label)}>{isPending ? '○ ' : '● '}</Text>,
        <Text bold={!isPending && !isSide} dimColor={isPending || isSide}>
          {padCells(isSide ? `脇道: ${g.label}` : g.label, labelW)}
        </Text>,
        <Text dimColor={isSide}>{padCells(ms > 0 ? durationOf(ms) : '', 8)}</Text>,
        g.note && isLast ? isSide ? <Text dimColor>{g.note}</Text> : <Text color="warning">{g.note}</Text> : null,
        canOpen ? <Text dimColor>  {isOpen ? '▾' : '▸'}{members.length}</Text> : null,
      ]
      const press = async () => {
        if (canOpen) await update($, expanded, ids => (ids.includes(g.id) ? ids.filter(id => id !== g.id) : [...ids, g.id]))
        if (anchor) await jump(anchor)
      }
      return (
        <Box key={key} flexDirection="column">
          {marksAt(i, from)}
          <Button key={'go-' + key} plain onPress={press}>
            {line}
          </Button>
          {g.summary && isLast ? (
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
    }

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
        {marksAt(rows.length, 0)}
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
