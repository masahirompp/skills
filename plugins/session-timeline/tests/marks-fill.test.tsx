import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'
import type { Phase } from '../types'

// The marks are filled in off the transcript until that works, whatever became of the phases'
// backfill; and only the model a session began on is called the starting one.

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
const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const msg = (role: 'user' | 'assistant', text: string) => ({ role, text, toolUses: [] }) as never
const HISTORY = [msg('user', 'バグを直して'), msg('assistant', '直しました')]

const at = (clock: string) => Date.parse(`2026-11-17T${clock}Z`)
const said = (timestamp: string, model: string) =>
  JSON.stringify({ type: 'assistant', isSidechain: false, timestamp, message: { model } })

/** A transcript: begun on Fable, compacted, then moved to Opus. */
const JSONL = [
  said('2026-11-17T00:00:05Z', 'claude-fable-5-2'),
  JSON.stringify({
    type: 'system',
    subtype: 'compact_boundary',
    timestamp: '2026-11-17T00:10:00Z',
    compactMetadata: { trigger: 'auto', preTokens: 218695 },
  }),
  said('2026-11-17T00:20:00Z', 'claude-opus-5-5'),
].join('\n')
const EXPECTED = ['モデル fable-5-2(開始時)', 'compact(自動)  219k トークン', 'モデル fable-5-2 → opus-5-5']

/** The engine beneath the plugin: a session resumed an hour on, with a history and a transcript or none. */
function world($: T[0], on: T[1], opts: { model: string; jsonl: () => string | undefined }): void {
  let clock = at('01:00:00')
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('session.model', () => ({ value: opts.model }))
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '調査', note: '', summary: '' }), usage } },
  )
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('session.messages', () => ({ value: HISTORY }))
  on('session.id', () => ({ value: 's' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', () => {
    const jsonl = opts.jsonl()
    return jsonl === undefined ? ({ deny: 'no transcript here' } as never) : ({ value: jsonl } as never)
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
}

async function texts($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out
}
const marks = async ($: T[0]) => (await texts($)).filter(t => t.includes('◇')).map(t => t.replace(/^.*◇ /, ''))

test('a session whose phases 0.4.0 backfilled still gets its marks off the transcript', async ($, on) => {
  // What 0.4.0 left in the state: the phases filled in and marked so, no marks, no time the live recording began.
  const past: Phase = { id: 'past-1', label: '設計', note: '', summary: '', toolIds: [], steps: 1, errors: 0 }
  const left: Record<string, unknown> = {
    phases: { shape: 'phases-2', value: [past] },
    isBackfilled: true,
    liveFromIndex: HISTORY.length,
  }
  on('state.set', (_, e, next) => {
    delete left[e.key]
    return next(e)
  })
  on('state.get', (_, e, next) => (e.key in left ? ({ value: { value: left[e.key], version: 0 } } as never) : next(e)))

  world($, on, { model: 'claude-opus-5-5', jsonl: () => JSONL })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  const seen = await texts($)
  expect(seen.some(t => t.includes('設計'))).toBe(true)
  expect(await marks($)).toEqual(EXPECTED)
})

test('marks the transcript could not give are asked for again once it can', async ($, on) => {
  let jsonl: string | undefined
  world($, on, { model: 'claude-opus-5-5', jsonl: () => jsonl })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  // The phases' backfill is done, without the transcript.
  expect((await texts($)).some(t => t.includes('調査'))).toBe(true)
  // Loaded into a session with a history: the model seen is not called the one it began on.
  expect(await marks($)).toEqual(['モデル opus-5-5'])

  jsonl = JSONL
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await marks($)).toEqual(EXPECTED)
})

test('with the pane open, the marks are asked for again as a turn ends', async ($, on) => {
  let jsonl: string | undefined
  world($, on, { model: 'claude-opus-5-5', jsonl: () => jsonl })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  jsonl = JSONL
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await $.turn.complete({ answer: '続けました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await marks($)).toEqual(EXPECTED)
})

test('past the most marks kept, the oldest left is still drawn as the change it was', async ($, on) => {
  // 205 changes of model, a minute apart, ending on Fable, and resumed on Opus: the oldest give way.
  const day = Date.parse('2026-11-16T00:00:00Z')
  const rows = Array.from({ length: 205 }, (_, i) =>
    said(new Date(day + i * 60_000).toISOString(), i % 2 === 0 ? 'claude-fable-5-2' : 'claude-opus-5-5'),
  )
  world($, on, { model: 'claude-opus-5-5', jsonl: () => rows.join('\n') })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  const drawn = await marks($)
  expect(drawn.length).toBe(200)
  expect(drawn.filter(t => t.includes('(開始時)'))).toEqual([])
  expect(drawn[0]).toBe('モデル opus-5-5 → fable-5-2')
})
