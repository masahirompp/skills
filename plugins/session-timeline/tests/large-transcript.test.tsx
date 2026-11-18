import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

import { RECAP_SYSTEM, REGROUP_SYSTEM } from '../hooks/group'

// The marks from before the mod loaded are filled in whatever the transcript file's size.

declare function setTimeout(fn: () => void, ms: number): unknown
declare const TextEncoder: new () => { encode(text: string): Uint8Array }
declare const TextDecoder: new () => { decode(bytes: Uint8Array): string }
const settle = () => new Promise<void>(r => setTimeout(r, 500))

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
const MIB = 1024 * 1024

/**
 * `$.fs.read` as the engine answers it: the range of bytes asked for, as text
 * (a cut character U+FFFD at that edge), empty past the end, and a refusal
 * where the answer would be over 4 MiB.
 */
function fileRead(bytes: Uint8Array, e: { offset?: number; length?: number }): object {
  const offset = e.offset ?? 0
  const end = e.length === undefined ? bytes.length : Math.min(bytes.length, offset + e.length)
  if ((e.length ?? 0) > 4 * MIB || end - offset > 4 * MIB) return { deny: 'over 4 MiB' }
  return { value: new TextDecoder().decode(bytes.subarray(Math.min(offset, bytes.length), Math.max(offset, end))) }
}

/** The engine beneath the plugin: a session resumed on Opus, over a transcript file of these bytes. */
function world($: T[0], on: T[1], bytes: Uint8Array): { reads: number } {
  const seen = { reads: 0 }
  let clock = Date.parse('2026-11-17T01:00:00Z')
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '調査', note: '', summary: '' }), usage } },
  )
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.messages', () => ({ value: [] }))
  on('session.id', () => ({ value: 's' }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  on('fs.read', (_, e) => {
    seen.reads += 1
    return fileRead(bytes, e) as never
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  return seen
}

async function marks($: T[0]): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Text' })).map(t => t.text ?? '')
  await ui.unmount()
  return out.filter(t => t.includes('◇')).map(t => t.replace(/^.*◇ /, ''))
}

const said = (timestamp: string, model: string, text: string) =>
  JSON.stringify({ type: 'assistant', isSidechain: false, timestamp, message: { model, text } })

/**
 * A transcript of `mib` MiB and more: begun on Fable, compacted by hand, then
 * moved to Opus, each a long way into the file from the one before. The rows
 * between are Fable's and then Opus's answers, of lengths that vary: a range's
 * edge falls inside a row, and inside a character of it.
 */
function transcript(mib: number): Uint8Array {
  const day = Date.parse('2026-11-17T00:00:00Z')
  const lines: string[] = []
  let size = 0
  let n = 0
  const add = (line: string) => {
    lines.push(line)
    size += line.length * 3
  }
  const pad = (model: string, until: number) => {
    while (size < until) add(said(new Date(day + (n += 1) * 10).toISOString(), model, 'あいうえお'.repeat(40 + (n % 7)) + 'x'.repeat(n % 5)))
  }
  add(said(new Date(day).toISOString(), 'claude-fable-5-2', '始めます'))
  pad('claude-fable-5-2', mib * MIB * 1.5)
  add(
    JSON.stringify({
      type: 'system',
      subtype: 'compact_boundary',
      timestamp: new Date(day + (n += 1) * 10).toISOString(),
      compactMetadata: { trigger: 'manual', preTokens: 51700, postTokens: 11498 },
    }),
  )
  pad('claude-fable-5-2', mib * MIB * 3)
  pad('claude-opus-5-5', mib * MIB * 3.3)
  return new TextEncoder().encode(lines.join('\n'))
}

const EXPECTED = ['モデル fable-5-2(開始時)', 'compact(手動)  51.7k → 11.5k トークン', 'モデル fable-5-2 → opus-5-5']

test('a transcript file over 4 MiB still gives the marks from before the mod loaded', { timeoutMs: 30000 }, async ($, on) => {
  const bytes = transcript(5)
  expect(bytes.length).toBeGreaterThan(4 * MIB)
  world($, on, bytes)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  expect(await marks($)).toEqual(EXPECTED)
})

test('a transcript file under 4 MiB is read in one call', async ($, on) => {
  const text = [
    said('2026-11-17T00:00:00Z', 'claude-fable-5-2', '始めます'),
    JSON.stringify({
      type: 'system',
      subtype: 'compact_boundary',
      timestamp: '2026-11-17T00:10:00Z',
      compactMetadata: { trigger: 'manual', preTokens: 51700, postTokens: 11498 },
    }),
    said('2026-11-17T00:20:00Z', 'claude-opus-5-5', '続けます'),
  ].join('\n')
  const seen = world($, on, new TextEncoder().encode(text))
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true })
  await settle()
  expect(await marks($)).toEqual(EXPECTED)
  expect(seen.reads).toBe(1)
})
