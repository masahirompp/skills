import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'

// The races code review found: calls that overlap, and a backfill that a
// reload, a reset or a second open lands in the middle of.

declare function setTimeout(fn: () => void, ms: number): unknown
const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

const PANE = {
  plugin: 'session-timeline',
  component: 'Pane',
  requestId: 'session-timeline',
  props: {
    title: 'Session timeline',
    isFocused: false,
    bodyColumns: 70,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 60 },
    view: {},
  },
} as const

const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const msg = (role: 'user' | 'assistant', text: string, toolUses: object[] = []) => ({ role, text, toolUses }) as never

/** Kinds that never merge into one another, so each judged stretch stays its own row. */
const NAMES = ['調査', '実装', 'レビュー', '修正', 'テスト']

type T = Parameters<TestBody>
type World = {
  /** Each phase judgment's prompt, in order. */
  judged: string[]
  /** How often the history was read: once per backfill. */
  historyReads: number
}

/** The engine beneath the plugin: a clock, a model that names phases, a history, and no transcript file. */
function world(
  $: T[0],
  on: T[1],
  opts: { label?: (n: number) => string; isModelDown?: boolean; history?: unknown[] | (() => unknown[]); modelDelay?: number; openDelay?: number; toolDelay?: number } = {},
): World {
  const w: World = { judged: [], historyReads: 0 }
  let clock = Date.UTC(2026, 10, 17, 1, 0, 0)
  on('clock.now', () => ({ value: (clock += 1000) }))
  on('model.complete', async (_, e) => {
    if (opts.isModelDown) return { deny: 'cut off' } as never
    // Named as the call is asked, so a call asked before a reset keeps the name it was asked under.
    const isJudge = e.system !== REGROUP_SYSTEM && e.system !== RECAP_SYSTEM
    if (isJudge) w.judged.push(e.prompt)
    const label = opts.label?.(w.judged.length) ?? NAMES[(w.judged.length - 1) % NAMES.length]!
    if (opts.modelDelay) await sleep(opts.modelDelay)
    if (!isJudge) {
      return { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
    }
    return { value: { isAnswered: true, text: JSON.stringify({ continues: false, label, note: '', summary: '', topic: label }), usage } }
  })
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', async (_, e) => {
    if (opts.toolDelay) await sleep(opts.toolDelay)
    return { result: { content: `${e.tool_use_id} の結果` } }
  })
  on('session.messages', () => {
    w.historyReads += 1
    const h = opts.history
    return { value: (typeof h === 'function' ? h() : (h ?? [])) as never }
  })
  on('session.id', () => ({ value: 's' }))
  on('env.get', () => ({ value: undefined }) as never)
  on('fs.read', () => ({ deny: 'no transcript here' }) as never)
  on('ui.open', async () => {
    if (opts.openDelay) await sleep(opts.openDelay)
    return { value: { isPlaced: true } }
  })
  return w
}

async function labels($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const texts = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return texts
}

test('two Agent calls in parallel: both reviews reach a phase judgment', async ($, on) => {
  const w = world($, on, { toolDelay: 50 })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '並列でレビューして', turnId: 't1' })
  await Promise.all([
    $.tool.call({ tool: 'Agent', description: 'a', prompt: 'a', subagent_type: 'x', tool_use_id: 'review-a' }),
    $.tool.call({ tool: 'Agent', description: 'b', prompt: 'b', subagent_type: 'x', tool_use_id: 'review-b' }),
  ])
  await $.turn.complete({ answer: '終わり', durationMs: 1, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await sleep(400)
  const all = w.judged.join('\n')
  expect(all).toContain('review-a の結果')
  expect(all).toContain('review-b の結果')
})

test('a text-only turn recorded live is not judged again by the backfill', { options: { autoOpen: false } }, async ($, on) => {
  // The history grows as the session goes: empty when it starts, the turn in it once the turn is done.
  let history: unknown[] = []
  const w = world($, on, { history: () => history })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '質問です', turnId: 't1' })
  history = [msg('user', '質問です'), msg('assistant', '答えです')]
  await $.turn.complete({ answer: '答えです', durationMs: 1, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await sleep(300)
  expect(w.judged.length).toBe(1)
  await $.command.run({ command: 'timeline', args: '' } as never)
  await sleep(300)
  expect(w.judged.length).toBe(1)
})

// The kit cannot reload the module mid-backfill. What a reload needs is the mark: a backfill
// that does not finish must leave it unset, so the next module's open runs it again.
test('a backfill that does not finish is not marked done', { options: { autoOpen: false } }, async ($, on) => {
  const marks: unknown[] = []
  on('state.set', (_, e, next) => {
    if (e.key === 'isBackfilled') marks.push(e.value)
    return next(e)
  })
  world($, on, { isModelDown: true, history: [msg('user', '古い作業'), msg('assistant', '済みました')] })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await sleep(300)
  expect(marks).toEqual([])
  expect((await labels($)).some(t => t.includes('過去分を判定中'))).toBe(false)
})

test('a reset in the middle of a backfill keeps none of the phases from before it', { options: { autoOpen: false } }, async ($, on) => {
  const history = [
    msg('user', 'A をやって'),
    msg('assistant', '', [{ tool_use_id: 'ha', tool: 'Edit', input: { file_path: '/a' } }]),
    msg('user', 'B をやって'),
    msg('assistant', '', [{ tool_use_id: 'hb', tool: 'Edit', input: { file_path: '/b' } }]),
  ]
  let isReset = false
  const w = world($, on, { history, modelDelay: 40, label: () => (isReset ? '新' : '旧') })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await sleep(60)
  isReset = true
  await $.command.run({ command: 'timeline', args: 'reset' } as never)
  await sleep(600)
  const texts = await labels($)
  expect(texts.some(t => t.startsWith('旧'))).toBe(false)
  expect(texts.some(t => t.startsWith('新'))).toBe(true)
  expect(w.judged.length).toBeGreaterThan(0)
})

test('opening twice at once backfills the history once', async ($, on) => {
  // autoOpen opens the pane as the session starts; the person types /timeline before that open has settled.
  const history = [msg('user', 'A をやって'), msg('assistant', 'A 済み'), msg('user', 'B をやって'), msg('assistant', 'B 済み')]
  const w = world($, on, { history, openDelay: 30 })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await sleep(400)
  expect(w.judged.length).toBe(2)
  expect((await labels($)).filter(t => /^(調査|実装)\s/.test(t)).length).toBe(2)
})
