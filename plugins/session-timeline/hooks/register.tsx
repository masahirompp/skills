import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Backfill, Group, Live, Phase, Recap } from '../types'
import { stretchesOf, timed, timesOf, transcriptPathOf } from './backfill'
import type { Times } from './backfill'
import { BOUNDARY_TOOLS, MAX_STEPS, SYSTEM, briefOf, fold, outcomeOf, parseVerdict, promptOf } from './classify'
import type { Step, Stretch, Verdict } from './classify'
import { RECAP_SYSTEM, REGROUP_SYSTEM, groupsByKind, mergeSameKind, parseGroups, parseRecap, recapPrompt, regroupPrompt } from './group'
import { cells, clockOf, colorOf, durationOf, padCells } from './view'

const PANE = 'session-timeline'
const TITLE = 'Session timeline'

const phases = atom({ plugin: 'session-timeline', key: 'phases' } as const, [] as Phase[], { shape: 'phases-2' })
const groups = atom({ plugin: 'session-timeline', key: 'groups' } as const, [] as Group[], { shape: 'groups-1' })
const expanded = atom({ plugin: 'session-timeline', key: 'expanded' } as const, [] as string[], { shape: 'expanded-1' })
const recap = atom({ plugin: 'session-timeline', key: 'recap' } as const, null as Recap, { shape: 'recap-1' })
const savedLatest = atom({ plugin: 'session-timeline', key: 'latestRow' } as const, '')
const live = atom({ plugin: 'session-timeline', key: 'live' } as const, null as Live, { shape: 'live-1' })
const backfill = atom({ plugin: 'session-timeline', key: 'backfill' } as const, null as Backfill, { shape: 'backfill-1' })
const isBackfilled = atom({ plugin: 'session-timeline', key: 'isBackfilled' } as const, false)
const cwd = atom({ plugin: 'session-timeline', key: 'cwd' } as const, '')
const transcriptPath = atom({ plugin: 'session-timeline', key: 'transcriptPath' } as const, '')

// The stretch being gathered and the classifications in flight: a reload drops
// them, and the next stretch starts afresh.
let stretch: Stretch | undefined
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
  const next = r.isAnswered ? parseRecap(r.text) : null
  if (next) await update($, recap, () => next)
}

async function gather($: EngineInterface): Promise<Stretch> {
  if (!stretch) {
    const s: Stretch = { start: await $.clock.now(), steps: [], subSteps: 0 }
    stretch = s
    await update($, live, l => ({ since: s.start ?? 0, steps: 0, isClassifying: l?.isClassifying ?? false }))
  }
  return stretch
}

async function countStep($: EngineInterface): Promise<void> {
  await update($, live, l => (l ? { ...l, steps: l.steps + 1 } : l))
}

/** Closes the stretch and classifies it after the ones before it. */
function close($: EngineInterface): void {
  const done = stretch
  stretch = undefined
  if (!done || (done.steps.length === 0 && !done.prompt && !done.answer)) return
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
async function fillHistory($: EngineInterface): Promise<void> {
  const messages = await $.session.messages()
  if (!Array.isArray(messages)) return
  const existing = await read($, phases)
  const known = new Set([...existing.flatMap(p => p.toolIds), ...(stretch?.steps.map(s => s.id) ?? [])])
  const liveStarts = [...existing.map(p => p.start), stretch?.start].filter((n): n is number => n !== undefined)
  const liveFrom = liveStarts.length > 0 ? Math.min(...liveStarts) : undefined
  const past = timed(stretchesOf(messages, known), await readTimes($), liveFrom)
  if (past.length === 0) return

  let done: Phase[] = []

  await update($, backfill, () => ({ done: 0, total: past.length }))
  for (const s of past) {
    const verdict = await judge($, s, done.slice(-6))
    done = fold(done, s, verdict, 'past')
    const now = done
    await update($, phases, list => [...now, ...list.filter(p => !p.id.startsWith('past-'))])
    await update($, backfill, b => (b ? { ...b, done: b.done + 1 } : b))
  }
}

async function openPane($: EngineInterface): Promise<boolean> {
  const { isPlaced } = await $.ui.open({ id: PANE, title: TITLE })
  if (!(await read($, isBackfilled))) {
    await update($, isBackfilled, () => true)
    enqueue(async () => {
      try {
        await fillHistory($)
      } finally {
        await update($, backfill, () => null)
        isRecapWanted = true
        scheduleRegroup($)
      }
    })
  } else if ((await read($, phases)).length > 0) {
    // Phases recorded before regrouping or the recap existed: make them now.
    const isMissingRecap = (await read($, recap)) === null
    if (isMissingRecap) isRecapWanted = true
    if (isMissingRecap || (await read($, groups)).length === 0) scheduleRegroup($)
  }
  return isPlaced
}

/** Forgets every phase, the grouping and the recap, so the next open rebuilds them from the history. */
async function reset($: EngineInterface): Promise<void> {
  await update($, phases, () => [])
  await update($, groups, () => [])
  await update($, expanded, () => [])
  await update($, recap, () => null)
  await update($, isBackfilled, () => false)
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
  await countStep($)
  if (stretch === s && (BOUNDARY_TOOLS.has(step.tool) || s.steps.length >= MAX_STEPS)) close($)
}

export const register: Register = on => {
  loadedAt = Date.now()

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'timeline',
      description: 'Show what this session is doing, phase by phase (reset: rebuild from the history)',
    })
    await update($, cwd, c => c || e.cwd)
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

  on('tool.call', async ($, e, next) => {
    // An Agent or Skill call (a review, a plan) is a stretch of its own: close what came before it.
    if (!e.agentId && BOUNDARY_TOOLS.has(e.tool)) close($)
    const s = e.agentId ? undefined : await gather($).catch(() => undefined)
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

    if (list.length === 0 && !current) {
      return (
        <Box flexDirection="column">
          {progress}
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
      </Box>
    )
  })
}
