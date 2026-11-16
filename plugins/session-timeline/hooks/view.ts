import type { Usage } from '../types'
import { kindOf } from './classify'

/**
 * Claude Haiku 5.5's API prices per 1M tokens (prompts up to 100K tokens), as of 2026-11:
 * input $0.10, output $0.50; a cache write at 1.25x input, a cache read at 0.1x.
 */
const PRICE = { input: 0.1, output: 0.5, cacheWrite: 0.125, cacheRead: 0.01 }

/** What the tokens would cost at API prices, in dollars. */
export function costOf(u: Usage): number {
  return (
    (u.input * PRICE.input + u.output * PRICE.output + u.cacheWrite * PRICE.cacheWrite + u.cacheRead * PRICE.cacheRead) /
    1_000_000
  )
}

function kilo(n: number): string {
  return n < 1000 ? String(n) : n < 100_000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n / 1000)}k`
}

/** One faint line under the timeline: how many calls, how many tokens, roughly what they cost. */
export function usageLine(u: Usage): string {
  const input = u.input + u.cacheRead + u.cacheWrite
  const cost = costOf(u)
  const dollars = cost < 0.01 ? cost.toFixed(4) : cost < 1 ? cost.toFixed(3) : cost.toFixed(2)
  return `Haiku ${u.calls}回 · 入力 ${kilo(input)} / 出力 ${kilo(u.output)} トークン · 約 $${dollars}(API 料金換算)`
}

const WIDE = /[ᄀ-ᅟ⺀-〾ぁ-㏿㐀-䶿一-鿿ꀀ-꓏가-힣豈-﫿︰-﹏＀-｠￠-￦]/

/** Terminal cells a string takes: CJK and full-width as two. */
export function cells(text: string): number {
  let n = 0
  for (const ch of text) n += WIDE.test(ch) ? 2 : 1
  return n
}

export function padCells(text: string, width: number): string {
  let out = ''
  let n = 0
  for (const ch of text) {
    const w = WIDE.test(ch) ? 2 : 1
    if (n + w > width) break
    out += ch
    n += w
  }
  return out + ' '.repeat(Math.max(0, width - n))
}

export function clockOf(t: number | undefined): string {
  if (t === undefined) return '--:--'
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function durationOf(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 60) return `${s}秒`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}分`
  return `${Math.floor(m / 60)}時間${m % 60}分`
}

const PALETTE = ['#4e9de0', '#e0a03a', '#9a7fe0', '#3fb68b', '#e06c75', '#56b6c2', '#c678dd', '#98c379']

/** One color per kind of phase: レビュー 1回目 and レビュー 2回目 share one. */
export function colorOf(label: string): string {
  let h = 0
  for (const ch of kindOf(label)) h = (h * 31 + (ch.codePointAt(0) ?? 0)) >>> 0
  return PALETTE[h % PALETTE.length] ?? '#4e9de0'
}
