import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'

// After /clear or an in-process /resume the plugin's state is empty and no `session.start` fires:
// where the live recording begins is settled where it is first needed, the conversation's earlier
// marks come off its transcript, and a conversation with no answer before is one just begun.

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
const said = (timestamp: string, model: string) =>
  JSON.stringify({ type: 'assistant', isSidechain: false, timestamp, message: { model } })

const PATH = '/h/.claude/projects/-w/s.jsonl'

/**
 * The engine beneath the plugin in a process that has moved to another conversation: no `session.start`
 * is sent, the state is empty. The transcript is the one file at the conversation's own path.
 */
function world($: T[0], on: T[1], opts: { model: string; lines: string[]; messages: () => unknown[] }) {
  const s = { clock: Date.parse('2026-11-17T01:00:00Z') }
  on('clock.now', () => ({ value: (s.clock += 1000) }))
  on('session.model', () => ({ value: opts.model }))
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '調査', note: '', summary: '' }), usage } },
  )
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('session.messages', () => ({ value: opts.messages() }) as never)
  on('session.id', () => ({ value: 's' }))
  on('session.cwd', () => ({ value: '/w' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', (_, e) =>
    e.path === PATH && opts.lines.length > 0 ? ({ value: opts.lines.join('\n') } as never) : ({ deny: 'no such file' } as never),
  )
  on('ui.open', () => ({ value: { isPlaced: true } }))
  return {
    turn: async (id: string) => {
      s.clock += 60_000
      await $.turn.start({ text: `${id} をやって`, turnId: id })
      opts.lines.push(said(new Date((s.clock += 1000)).toISOString(), opts.model))
      await $.turn.complete({ answer: 'やりました', durationMs: 10, isAborted: false, turnId: id, reason: 'completed' } as never)
      await settle()
    },
    command: async (args: string) => {
      await $.command.run({ command: 'timeline', args } as never)
      await settle()
    },
  }
}

async function marks($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out.filter(t => t.includes('◇')).map(t => t.replace(/^.*◇ /, ''))
}

/** The conversation moved to: begun on Haiku, compacted, a day before. */
const resumed = () => [
  said('2026-11-16T00:00:05Z', 'claude-haiku-5-5'),
  JSON.stringify({
    type: 'system',
    subtype: 'compact_boundary',
    timestamp: '2026-11-16T00:10:00Z',
    compactMetadata: { trigger: 'auto', preTokens: 218695 },
  }),
]
const HISTORY = [msg('user', 'バグを直して'), msg('assistant', '直しました')]
const PAST = ['モデル haiku-5-5(開始時)', 'compact(自動)  219k トークン']

// (b) /clear: whether the conversation's messages hold the turn's own prompt as the turn starts is not relied on.
for (const [name, atStart] of [
  ['no message yet', []],
  ['the prompt alone', [msg('user', 'a をやって')]],
] as const) {
  test(`after /clear, the first model seen is the one the conversation began on (as the turn starts: ${name})`, async ($, on) => {
    const lines: string[] = []
    const w = world($, on, { model: 'claude-haiku-5-5', lines, messages: () => (lines.length === 0 ? [...atStart] : HISTORY) })
    await w.turn('a')
    expect(await marks($)).toEqual(['モデル haiku-5-5(開始時)'])
    await w.turn('b')
    expect(await marks($)).toEqual(['モデル haiku-5-5(開始時)'])
  })
}

// (a) /resume: the marks of the conversation moved to come off its transcript.
test('after /resume, /timeline reset fills in the marks of the conversation moved to', async ($, on) => {
  const w = world($, on, { model: 'claude-sonnet-5-5', lines: resumed(), messages: () => HISTORY })
  await w.command('reset')
  expect(await marks($)).toEqual([...PAST, 'モデル haiku-5-5 → sonnet-5-5'])
})

test('after /resume, /timeline fills in the marks of the conversation moved to', async ($, on) => {
  const w = world($, on, { model: 'claude-sonnet-5-5', lines: resumed(), messages: () => HISTORY })
  await w.command('')
  expect(await marks($)).toEqual(PAST)
  // The model now is seen as the next turn starts: a change from the last the transcript knew.
  await w.turn('a')
  expect(await marks($)).toEqual([...PAST, 'モデル haiku-5-5 → sonnet-5-5'])
})

test('after /resume, a turn fills in the marks of the conversation moved to', async ($, on) => {
  const w = world($, on, { model: 'claude-haiku-5-5', lines: resumed(), messages: () => HISTORY })
  await w.turn('a')
  expect(await marks($)).toEqual(PAST)
})
