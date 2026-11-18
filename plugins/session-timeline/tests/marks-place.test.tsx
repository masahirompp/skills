import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'

// A mark stands between the work begun before it and the work begun after it,
// also where both are of one kind and would be one row.

declare function setTimeout(fn: () => void, ms: number): unknown
const settle = () => new Promise<void>(r => setTimeout(r, 300))

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

type T = Parameters<TestBody>
const SUMMARY = { role: 'user', text: 'ここまでの要約', toolUses: [] }
const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }

/**
 * The engine beneath the plugin. Every stretch is judged 実装, and a regroup
 * puts every phase into one 実装: nothing but a mark can part the rows.
 */
function world(
  $: T[0],
  on: T[1],
  opts: { model: () => string; start: number; history?: unknown[]; jsonl?: string },
): void {
  let clock = opts.start
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('session.model', () => ({ value: opts.model() }))
  on('model.complete', (_, e) => {
    if (e.system === RECAP_SYSTEM) {
      return { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
    }
    const text =
      e.system === REGROUP_SYSTEM
        ? JSON.stringify([{ from: 1, label: '実装', note: '', summary: '', side: false }])
        : JSON.stringify({ continues: false, label: '実装', note: '', summary: '' })
    return { value: { isAnswered: true, text, usage } }
  })
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', () => ({ result: {} }))
  on('session.messages', () => ({ value: (opts.history ?? []) as never }))
  on('session.id', () => ({ value: 's' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', () => (opts.jsonl === undefined ? ({ deny: 'no transcript here' } as never) : ({ value: opts.jsonl } as never)))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.compact', () => ({ messages: [SUMMARY], tokensBefore: 180_000, tokensAfter: 30_000 }) as never)
}

/** The timeline's rows in the order drawn: a phase's row as its name, a mark as its text. */
async function rows($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out
    .map(t => (t.includes('◇') ? t.replace(/^.*◇ /, '') : t.trim()))
    .filter(t => t === '実装' || t === 'いま' || t.startsWith('モデル') || t.startsWith('compact'))
}

const turn = async ($: T[0], id: string) => {
  await $.turn.start({ text: `${id} をやって`, turnId: id })
  await $.tool.call({ tool: 'Edit', file_path: `/w/${id}.ts`, old_string: 'a', new_string: 'b', tool_use_id: `tu-${id}` })
  await $.turn.complete({ answer: 'やりました', durationMs: 10, isAborted: false, turnId: id, reason: 'completed' } as never)
  await settle()
}

test('a change of model stands between the turns of one kind before it and after it', async ($, on) => {
  let model = 'claude-fable-5-2'
  world($, on, { model: () => model, start: Date.UTC(2026, 10, 17, 1, 0, 0) })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await turn($, 'a')
  model = 'claude-opus-5-5'
  await turn($, 'b')
  expect(await rows($)).toEqual(['モデル fable-5-2(開始時)', '実装', 'モデル fable-5-2 → opus-5-5', '実装', 'いま'])

  // A compaction too, and with the three phases regrouped into one.
  await $.session.compact({ trigger: 'manual', messages: [SUMMARY] } as never)
  await turn($, 'c')
  await turn($, 'd')
  expect(await rows($)).toEqual([
    'モデル fable-5-2(開始時)',
    '実装',
    'モデル fable-5-2 → opus-5-5',
    '実装',
    'compact(手動)  180k → 30.0k トークン',
    '実装',
    'いま',
  ])
})

test('a compaction in the middle of a turn stands after the work it interrupted, ahead of the next', async ($, on) => {
  world($, on, { model: () => 'claude-fable-5-2', start: Date.UTC(2026, 10, 17, 1, 0, 0) })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'a をやって', turnId: 'a' })
  await $.tool.call({ tool: 'Edit', file_path: '/w/a.ts', old_string: 'a', new_string: 'b', tool_use_id: 'tu-a1' })
  await $.session.compact({ trigger: 'auto', messages: [SUMMARY] } as never)
  await $.tool.call({ tool: 'Edit', file_path: '/w/a.ts', old_string: 'b', new_string: 'c', tool_use_id: 'tu-a2' })
  await $.turn.complete({ answer: 'やりました', durationMs: 10, isAborted: false, turnId: 'a', reason: 'completed' } as never)
  await settle()
  await turn($, 'b')
  expect(await rows($)).toEqual(['モデル fable-5-2(開始時)', '実装', 'compact(自動)  180k → 30.0k トークン', '実装', 'いま'])
})

test('in the history filled in, a change of model parts the tool calls before it from those after it', { options: { autoOpen: false } }, async ($, on) => {
  const use = (id: string) => ({ role: 'assistant', text: '', toolUses: [{ tool_use_id: id, tool: 'Edit', input: { file_path: '/a' } }] })
  const history = [
    { role: 'user', text: 'A をやって', toolUses: [] },
    use('h1'),
    { role: 'user', text: 'B をやって', toolUses: [] },
    use('h2'),
  ]
  const said = (clock: string, model: string, id: string) =>
    JSON.stringify({
      type: 'assistant',
      isSidechain: false,
      timestamp: `2026-11-17T${clock}Z`,
      message: { model, content: [{ type: 'tool_use', id }] },
    })
  const jsonl = [said('00:00:05', 'claude-fable-5-2', 'h1'), said('00:20:00', 'claude-opus-5-5', 'h2')].join('\n')
  world($, on, { model: () => 'claude-opus-5-5', start: Date.parse('2026-11-17T01:00:00Z'), history, jsonl })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await rows($)).toEqual(['モデル fable-5-2(開始時)', '実装', 'モデル fable-5-2 → opus-5-5', '実装', 'いま'])
})
