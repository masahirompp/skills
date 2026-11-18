import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'
import { markRows, marksOf } from '../hooks/marks'

// A transcript that carries on a compacted conversation starts at the compaction boundary: what came
// before is in another file. The first model it shows is not the one the conversation began on.

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

const row = (o: object) => JSON.stringify(o)
const said = (timestamp: string, model: string) =>
  row({ type: 'assistant', isSidechain: false, timestamp, message: { model, content: [] } })

/** Rows with no time ahead of the conversation's own, as every transcript has. */
const HEAD = [
  row({ type: 'ai-title', aiTitle: 'バグを直す', sessionId: 's' }),
  row({ type: 'agent-name', agentName: 'main', sessionId: 's' }),
  row({ type: 'mode', mode: 'default', sessionId: 's' }),
  row({ type: 'permission-mode', permissionMode: 'default', sessionId: 's' }),
  row({ type: 'file-history-snapshot', messageId: 'm', snapshot: {} }),
]

/**
 * The head of a transcript carrying on a compacted conversation, as seen in one: the boundary, the
 * summary, then an answer the compaction kept (older than the boundary), and the answers after.
 */
const CARRIED = [
  ...HEAD,
  row({
    type: 'system',
    subtype: 'compact_boundary',
    timestamp: '2026-10-16T02:19:27.839Z',
    parentUuid: null,
    compactMetadata: { trigger: 'auto', preTokens: 218695, postTokens: 9615 },
  }),
  row({ type: 'user', timestamp: '2026-10-16T02:19:27.836Z', message: { role: 'user', content: 'ここまでの要約' } }),
  said('2026-10-16T01:24:36.052Z', 'claude-opus-5-5'),
  row({ type: 'system', subtype: 'stop_hook_summary', timestamp: '2026-10-16T01:24:36.118Z' }),
  said('2026-10-16T02:35:02.436Z', 'claude-opus-5-5'),
].join('\n')

/** A transcript from the conversation's first row on. */
const WHOLE = [
  ...HEAD,
  row({ type: 'user', timestamp: '2026-10-15T23:43:36.000Z', message: { role: 'user', content: 'バグを直して' } }),
  said('2026-10-15T23:43:41.000Z', 'claude-opus-5-5'),
].join('\n')

const DRAWN = ['モデル opus-5-5', 'compact(自動)  219k → 9.6k トークン']

test('a transcript that starts at a compaction boundary does not call its first model the starting one', () => {
  const rows = markRows(marksOf(CARRIED))
  expect(rows.map(r => r.text)).toEqual(DRAWN)
  // Drawn by time: the answer the compaction kept, ahead of the boundary it is written behind.
  expect(rows.map(r => r.at)).toEqual([Date.parse('2026-10-16T01:24:36.052Z'), Date.parse('2026-10-16T02:19:27.839Z')])
})

test('a transcript from the first row on still calls its first model the starting one', () => {
  expect(markRows(marksOf(WHOLE)).map(r => r.text)).toEqual(['モデル opus-5-5(開始時)'])
})

type T = Parameters<TestBody>
const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const msg = (role: 'user' | 'assistant', text: string) => ({ role, text, toolUses: [] }) as never

/** The engine beneath the plugin: a session resumed at `start` on Opus, with a history and the transcript. */
function world($: T[0], on: T[1], start: string): void {
  let clock = Date.parse(start)
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('session.model', () => ({ value: 'claude-opus-5-5[1m]' }))
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '調査', note: '', summary: '' }), usage } },
  )
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('session.messages', () => ({ value: [msg('user', 'ここまでの要約'), msg('assistant', '直しました')] }))
  on('session.id', () => ({ value: 's' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', () => ({ value: CARRIED }) as never)
  on('ui.open', () => ({ value: { isPlaced: true } }))
}

async function marks($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out.filter(t => t.includes('◇')).map(t => t.replace(/^.*◇ /, ''))
}

test('loaded into the carried-on conversation, the pane calls no model the starting one', async ($, on) => {
  world($, on, '2026-10-16T03:00:00Z')
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  expect(await marks($)).toEqual(DRAWN)
  // The model seen live is the one the transcript last knew: no mark, and none made the starting one.
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await $.turn.complete({ answer: '続けました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await marks($)).toEqual(DRAWN)
})
