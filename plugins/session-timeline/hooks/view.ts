import { kindOf } from './classify'

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
