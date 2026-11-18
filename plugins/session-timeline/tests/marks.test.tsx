import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'
import { markRows, marksOf, observed, slotOf } from '../hooks/marks'

// The model the session runs on and its compactions: facts off the engine, drawn among the phases.

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

const at = (clock: string) => Date.parse(`2026-11-17T${clock}Z`)
const row = (o: object) => JSON.stringify(o)
const said = (clock: string, model: string, extra: object = {}) =>
  row({ type: 'assistant', timestamp: `2026-11-17T${clock}Z`, message: { model, content: [] }, ...extra })

/** A transcript: begun on Fable, compacted, then moved to Opus; a subagent's rows and the engine's notices beside. */
const JSONL = [
  row({ type: 'user', timestamp: '2026-11-17T00:00:00Z', message: { content: 'バグを直して' } }),
  said('00:00:05', 'claude-fable-5-2'),
  said('00:01:00', 'claude-haiku-5-5', { isSidechain: true }),
  said('00:02:00', 'claude-fable-5-2'),
  said('00:02:30', '<synthetic>'),
  row({
    type: 'system',
    subtype: 'compact_boundary',
    timestamp: '2026-11-17T00:10:00Z',
    compactMetadata: { trigger: 'auto', preTokens: 218695 },
  }),
  said('00:20:00', 'claude-opus-5-5'),
  'not json "model"',
].join('\n')

test('the transcript gives the model each time it changes, and each compaction', () => {
  expect(marksOf(JSONL)).toEqual([
    { kind: 'model', at: at('00:00:05'), model: 'claude-fable-5-2' },
    { kind: 'compact', at: at('00:10:00'), trigger: 'auto', before: 218695 },
    { kind: 'model', at: at('00:20:00'), model: 'claude-opus-5-5' },
  ])
  expect(marksOf('')).toEqual([])
})

test('the first model is the one the session began on, a later one a change', () => {
  expect(markRows(marksOf(JSONL)).map(r => r.text)).toEqual([
    'モデル fable-5-2(開始時)',
    'compact(自動)  219k トークン',
    'モデル fable-5-2 → opus-5-5',
  ])
  // The same model seen again adds nothing, with or without the suffix the transcript does not carry.
  const seen = observed(marksOf(JSONL), 'claude-opus-5-5[1m]', at('00:30:00'))
  expect(seen.length).toBe(3)
  expect(
    markRows([
      { kind: 'model', at: 1, model: 'claude-opus-5-5' },
      { kind: 'model', at: 2, model: 'claude-opus-5-5[1m]' },
      { kind: 'compact', at: 3, trigger: 'manual', before: 150_000, after: 20_000 },
    ]).map(r => r.text),
  ).toEqual(['モデル opus-5-5(開始時)', 'compact(手動)  150k → 20.0k トークン'])
})

test('a mark is drawn ahead of the first phase that starts after it', () => {
  expect(slotOf([10, 20, 30], 5)).toBe(0)
  expect(slotOf([10, 20, 30], 20)).toBe(1)
  expect(slotOf([10, 20, 30], 25)).toBe(2)
  expect(slotOf([10, 20, 30], 31)).toBe(3)
  // A phase whose time the transcript did not give is passed over.
  expect(slotOf([undefined, 20], 5)).toBe(1)
  expect(slotOf([], 5)).toBe(0)
})

type T = Parameters<TestBody>
const SUMMARY = { role: 'user', text: 'ここまでの要約', toolUses: [] }
const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const NAMES = ['調査', '実装', 'テスト']

/** The engine beneath the plugin: a clock, the session's model, a model that names phases. */
function world(
  $: T[0],
  on: T[1],
  opts: { model: () => string; start: number; jsonl?: string; compact?: () => object },
): void {
  let clock = opts.start
  let judged = 0
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('session.model', () => ({ value: opts.model() }))
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : {
          value: {
            isAnswered: true,
            text: JSON.stringify({ continues: false, label: NAMES[judged++ % NAMES.length], note: '', summary: '' }),
            usage,
          },
        },
  )
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', () => ({ result: {} }))
  on('session.messages', () => ({ value: [] }))
  on('session.id', () => ({ value: 's' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', () => (opts.jsonl === undefined ? ({ deny: 'no transcript here' } as never) : ({ value: opts.jsonl } as never)))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.compact', () => (opts.compact?.() ?? { messages: [SUMMARY], tokensBefore: 180_000, tokensAfter: 30_000 }) as never)
}

async function texts($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out
}

const turn = async ($: T[0], id: string) => {
  await $.turn.start({ text: `${id} をやって`, turnId: id })
  await $.tool.call({ tool: 'Read', file_path: `/w/${id}.ts`, tool_use_id: `tu-${id}` })
  await $.turn.complete({ answer: 'やりました', durationMs: 10, isAborted: false, turnId: id, reason: 'completed' } as never)
  await settle()
}

test('the starting model, a change of model and a compaction stand among the phases, in order', async ($, on) => {
  let model = 'claude-fable-5-2'
  world($, on, { model: () => model, start: Date.UTC(2026, 10, 17, 1, 0, 0) })

  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  // Before any work: the model the session began on is there already.
  expect((await texts($)).some(t => t.includes('◇ モデル fable-5-2(開始時)'))).toBe(true)

  await turn($, 'a')
  model = 'claude-opus-5-5'
  await turn($, 'b')
  // The test stands for the engine: it hands the hook the transcript a session would.
  await $.session.compact({ trigger: 'manual', instructions: '計画を残す', messages: [SUMMARY] } as never)
  await turn($, 'c')
  // The same model on a later turn, and a reload, add nothing.
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })

  const drawn = await texts($)
  const where = (part: string) => drawn.findIndex(t => t.includes(part))
  const order = [
    where('◇ モデル fable-5-2(開始時)'),
    where('調査'),
    where('◇ モデル fable-5-2 → opus-5-5'),
    where('実装'),
    where('◇ compact(手動)  180k → 30.0k トークン'),
    where('テスト'),
    where('いま'),
  ]
  expect(order.every(i => i >= 0)).toBe(true)
  expect([...order].sort((a, b) => a - b)).toEqual(order)
  expect(drawn.filter(t => t.includes('◇')).length).toBe(3)
})

test('a compaction that was skipped leaves no mark', async ($, on) => {
  world($, on, { model: () => 'claude-fable-5-2', start: Date.UTC(2026, 10, 17, 1, 0, 0), compact: () => ({ skip: 'not now' }) })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  expect((await $.session.compact({ trigger: 'manual', messages: [SUMMARY] } as never)).skip).toBe('not now')
  expect((await texts($)).filter(t => t.includes('compact')).length).toBe(0)
})

test('a resumed session reads its marks off the transcript, and a reset reads them again', { options: { autoOpen: false } }, async ($, on) => {
  // Resumed on the model the transcript ended on: no change is drawn at the resume.
  world($, on, { model: () => 'claude-opus-5-5', start: at('01:00:00'), jsonl: JSONL })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  const expected = ['モデル fable-5-2(開始時)', 'compact(自動)  219k トークン', 'モデル fable-5-2 → opus-5-5']
  const marks = async () => (await texts($)).filter(t => t.includes('◇')).map(t => t.replace(/^.*◇ /, ''))
  expect(await marks()).toEqual(expected)

  await $.command.run({ command: 'timeline', args: 'reset' } as never)
  await settle()
  expect(await marks()).toEqual(expected)
})

test('resumed on another model than the transcript ended on, the change is drawn at the resume', { options: { autoOpen: false } }, async ($, on) => {
  world($, on, { model: () => 'claude-sonnet-5-5', start: at('01:00:00'), jsonl: JSONL })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  const drawn = (await texts($)).filter(t => t.includes('◇'))
  expect(drawn.length).toBe(4)
  expect(drawn.at(-1)).toContain('モデル opus-5-5 → sonnet-5-5')
})
