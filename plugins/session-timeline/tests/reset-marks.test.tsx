import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'

// /timeline reset loses no mark where the transcript cannot be read, nor one recorded while it runs.

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
const NAMES = ['調査', '実装', 'テスト']

/** The engine beneath the plugin: a clock, the session's model, a model that names phases, a transcript or none. */
function world($: T[0], on: T[1], opts: { model: () => string; start: number; jsonl?: () => string | undefined }): void {
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
  on('fs.read', () => {
    const jsonl = opts.jsonl?.()
    return jsonl === undefined ? ({ deny: 'no transcript here' } as never) : ({ value: jsonl } as never)
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.compact', () => ({ messages: [SUMMARY], tokensBefore: 180_000, tokensAfter: 30_000 }) as never)
}

async function marks($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out.filter(t => t.includes('◇')).map(t => t.replace(/^.*◇ /, ''))
}

const turn = async ($: T[0], id: string) => {
  await $.turn.start({ text: `${id} をやって`, turnId: id })
  await $.tool.call({ tool: 'Read', file_path: `/w/${id}.ts`, tool_use_id: `tu-${id}` })
  await $.turn.complete({ answer: 'やりました', durationMs: 10, isAborted: false, turnId: id, reason: 'completed' } as never)
  await settle()
}

test('a reset where the transcript cannot be read keeps the marks recorded live', async ($, on) => {
  let model = 'claude-fable-5-2'
  world($, on, { model: () => model, start: Date.UTC(2026, 10, 17, 1, 0, 0) })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await turn($, 'a')
  model = 'claude-opus-5-5'
  await turn($, 'b')
  await $.session.compact({ trigger: 'manual', messages: [SUMMARY] } as never)
  const expected = ['モデル fable-5-2(開始時)', 'モデル fable-5-2 → opus-5-5', 'compact(手動)  180k → 30.0k トークン']
  expect(await marks($)).toEqual(expected)

  await $.command.run({ command: 'timeline', args: 'reset' } as never)
  await settle()
  expect(await marks($)).toEqual(expected)
})

test('a mark recorded while a reset is under way is kept', async ($, on) => {
  // The transcript holds the session's first answer alone: the compaction below is newer than the reset's reading point.
  const jsonl = JSON.stringify({
    type: 'assistant',
    isSidechain: false,
    timestamp: '2026-11-17T00:00:05Z',
    message: { model: 'claude-fable-5-2' },
  })
  world($, on, { model: () => 'claude-fable-5-2', start: Date.UTC(2026, 10, 17, 1, 0, 0), jsonl: () => jsonl })
  let isResetting = false
  on('state.set', async (_, e, next) => {
    // The engine compacts as the reset asks for the transcript's marks again.
    if (isResetting && e.key === 'isMarksFilled') {
      isResetting = false
      const set = await next(e)
      await $.session.compact({ trigger: 'auto', messages: [SUMMARY] } as never)
      return set
    }
    return next(e)
  })
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  isResetting = true
  await $.command.run({ command: 'timeline', args: 'reset' } as never)
  await settle()
  expect(await marks($)).toEqual(['モデル fable-5-2(開始時)', 'compact(自動)  180k → 30.0k トークン'])
})
