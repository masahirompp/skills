import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'

// /timeline reset keeps the marks recorded live as they are: the transcript, which holds less
// than the engine told, only gives the marks from before the live recording began.

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
 * A session the plugin sees from its start, and the transcript file the engine writes beside it:
 * an assistant row with the model each turn ran on, a boundary row with no `postTokens` for an automatic compaction.
 */
function session($: T[0], on: T[1]) {
  const s = { model: 'claude-haiku-5-5', clock: Date.UTC(2026, 10, 17, 1, 0, 0), lines: [] as string[] }
  const stamp = () => new Date((s.clock += 1000)).toISOString()
  on('clock.now', () => ({ value: (s.clock += 1000) }))
  on('session.model', () => ({ value: s.model }))
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '調査', note: '', summary: '' }), usage } },
  )
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', () => ({ result: {} }))
  on('session.messages', () => ({ value: [] }))
  on('session.id', () => ({ value: 's' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', () => ({ value: s.lines.join('\n') }) as never)
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.compact', () => ({ messages: [SUMMARY], tokensBefore: 182_000, tokensAfter: 31_000 }) as never)
  return {
    start: async () => {
      await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
      await settle()
    },
    switchTo: (model: string) => {
      s.model = model
    },
    turn: async (id: string) => {
      s.clock += 60_000
      await $.turn.start({ text: `${id} をやって`, turnId: id })
      s.lines.push(JSON.stringify({ type: 'assistant', isSidechain: false, timestamp: stamp(), message: { model: s.model } }))
      await $.turn.complete({ answer: 'やりました', durationMs: 10, isAborted: false, turnId: id, reason: 'completed' } as never)
      await settle()
    },
    autoCompact: async () => {
      s.clock += 60_000
      s.lines.push(
        JSON.stringify({ type: 'system', subtype: 'compact_boundary', timestamp: stamp(), compactMetadata: { trigger: 'auto', preTokens: 182_000 } }),
      )
      await $.session.compact({ trigger: 'auto', messages: [SUMMARY] } as never)
    },
    reset: async () => {
      s.clock += 60_000
      await $.command.run({ command: 'timeline', args: 'reset' } as never)
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

test('a reset keeps the model the session began on, though no answer in the transcript ran on it', async ($, on) => {
  const s = session($, on)
  await s.start()
  // Switched before the first turn: the transcript's answers know the second model alone.
  s.switchTo('claude-sonnet-5-5')
  await s.turn('a')
  const expected = ['モデル haiku-5-5(開始時)', 'モデル haiku-5-5 → sonnet-5-5']
  expect(await marks($)).toEqual(expected)

  await s.reset()
  expect(await marks($)).toEqual(expected)
})

test('a reset before the first answer keeps the model the session began on', async ($, on) => {
  const s = session($, on)
  await s.start()
  const expected = ['モデル haiku-5-5(開始時)']
  expect(await marks($)).toEqual(expected)

  // The transcript is read, and holds no answer yet.
  await s.reset()
  expect(await marks($)).toEqual(expected)
  await s.turn('a')
  expect(await marks($)).toEqual(expected)
})

test('a reset keeps the tokens after a compaction, which the transcript does not hold', async ($, on) => {
  const s = session($, on)
  await s.start()
  await s.turn('a')
  await s.autoCompact()
  await s.turn('b')
  const expected = ['モデル haiku-5-5(開始時)', 'compact(自動)  182k → 31.0k トークン']
  expect(await marks($)).toEqual(expected)

  await s.reset()
  expect(await marks($)).toEqual(expected)
})
