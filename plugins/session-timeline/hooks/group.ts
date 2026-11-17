import type { Group, Phase, Recap } from '../types'
import { clip, kindOf } from './classify'

export const REGROUP_SYSTEM = `あなたはコーディングエージェントの作業記録を、人が進捗を一言で語る粒度の「大きな工程」にまとめる係です。
入力は時系列に番号の付いた細かい工程の列です。これを連続した範囲に区切り、各範囲に工程名を付けます。
- 目安は作業 1 時間あたり 4〜6 工程。全体で多くても 8 工程。細かく分けすぎないこと。
- 工程名は 調査, 設計, 実装, テスト, レビュー, 修正, PR作成 のような一般的な語を使い、同じ種類が繰り返されたら回数を付ける(例: レビュー 2回目)。
- 「実装→レビュー→修正→レビュー 2回目」のような流れが見えるように区切る。
- 〈〉内は話題、「」内はその工程を始めたユーザーの指示。話題が変わる所では必ず区切る。
- セッションの本題(最初の依頼や、最も時間を使った話題)と関係ない質問・雑談・別件の作業は、1 工程だけの短い範囲でも独立させて side: true を付ける。本題を進めるための調べものや、本題についての質問は本題に含める。
- 前回の区切りが与えられたら、明らかに良くなる場合を除いてそれを保ち、新しく増えた分だけを扱う。
- note には所要時間以外で中身が掴める結果を短く(例: 指摘4件, 3ファイル変更)。summary は 40 字以内。
次の JSON 配列だけを返します。範囲は 1 から最後の番号までを漏れなく重複なく覆います。
[{"from": 1, "to": 4, "label": "12字以内", "note": "20字以内", "summary": "40字以内", "side": false}]`

function hm(t: number | undefined): string {
  if (t === undefined) return '--:--'
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function took(p: Phase): string {
  if (p.start === undefined || p.end === undefined) return ''
  return ` ${Math.max(0, Math.round((p.end - p.start) / 60000))}分`
}

export function regroupPrompt(phases: readonly Phase[], previous: readonly Group[]): string {
  const index = new Map(phases.map((p, i) => [p.id, i + 1]))
  const lines = ['## 細かい工程(時系列)']
  phases.forEach((p, i) => {
    const extra = [p.note && `[${p.note}]`, p.errors > 0 && `(失敗${p.errors})`].filter(Boolean).join(' ')
    const topic = p.topic ? ` 〈${p.topic}〉` : ''
    const asked = p.prompt ? ` 「${clip(p.prompt, 80)}」` : ''
    lines.push(`${i + 1}. ${hm(p.start)}${took(p)} ${p.label}${topic}${extra ? ' ' + extra : ''}: ${clip(p.summary, 60)}${asked}`)
  })
  const prev = previous
    .map(g => {
      const at = g.phaseIds.map(id => index.get(id)).filter((n): n is number => n !== undefined)
      return at.length > 0 ? `${Math.min(...at)}-${Math.max(...at)} ${g.label}${g.isSide ? ' (脇道)' : ''}` : undefined
    })
    .filter(Boolean)
  if (prev.length > 0) lines.push('', '## 前回の区切り', ...(prev as string[]))
  return lines.join('\n')
}

/** Reads the ranges out of a reply and mends them into a cover of 1..n; undefined when unusable. */
export function parseGroups(text: string, phases: readonly Phase[]): Group[] | undefined {
  const m = text.match(/\[[\s\S]*\]/)
  if (!m) return undefined
  let raw: unknown
  try {
    raw = JSON.parse(m[0])
  } catch {
    return undefined
  }
  if (!Array.isArray(raw)) return undefined
  const n = phases.length
  const ranges = raw
    .map(r => r as Record<string, unknown>)
    .filter(r => Number.isInteger(r.from) && typeof r.label === 'string' && r.label.trim() !== '')
    .map(r => ({
      from: Math.max(1, Math.min(n, r.from as number)),
      label: clip((r.label as string).trim(), 16),
      note: typeof r.note === 'string' ? clip(r.note.trim(), 24) : '',
      summary: typeof r.summary === 'string' ? clip(r.summary.trim(), 60) : '',
      isSide: r.side === true,
    }))
    .sort((a, b) => a.from - b.from)
  if (ranges.length === 0) return undefined
  // Each range runs to the one after it: gaps close up, overlaps give way to the later.
  const groups: Group[] = []
  ranges.forEach((r, i) => {
    const from = i === 0 ? 1 : r.from
    const to = (ranges[i + 1]?.from ?? n + 1) - 1
    if (to < from) return
    const ids = phases.slice(from - 1, to).map(p => p.id)
    groups.push({
      id: 'g-' + ids[0],
      label: r.label,
      note: r.note,
      summary: r.summary,
      phaseIds: ids,
      ...(r.isSide ? { isSide: true } : {}),
    })
  })
  return groups.length > 0 ? groups : undefined
}

/** Merges neighbours of one kind: the first's label, the later note and summary where given. */
export function mergeSameKind(groups: readonly Group[]): Group[] {
  const out: Group[] = []
  for (const g of groups) {
    const last = out[out.length - 1]
    if (last && kindOf(last.label) === kindOf(g.label) && !last.isSide === !g.isSide) {
      out[out.length - 1] = {
        ...last,
        note: g.note || last.note,
        summary: g.summary || last.summary,
        phaseIds: [...last.phaseIds, ...g.phaseIds],
      }
    } else {
      out.push(g)
    }
  }
  return out
}

/** The grouping without a model: each fine phase alone, then neighbours of one kind merged. */
export function groupsByKind(phases: readonly Phase[]): Group[] {
  return mergeSameKind(
    phases.map(p => ({ id: 'g-' + p.id, label: p.label, note: p.note, summary: p.summary, phaseIds: [p.id] })),
  )
}

export const RECAP_SYSTEM = `あなたはコーディングエージェントのセッションを、席を外していた人向けに短くまとめる係です。
入力は、工程の一覧(脇道の印付き)、ユーザーの指示の履歴、エージェントの最後の応答です。脇道は扱わず、本題だけをまとめます。
- goal: このセッションの本題(何を達成しようとしているか)
- status: 本題が今どこまで進んだか。決まったこと・できたことを具体的に
- next: 次にやること、またはユーザーの判断を待っていること。なければ空文字
次の JSON だけを返します。
{"goal": "40字以内", "status": "100字以内", "next": "60字以内"}`

export function recapPrompt(groups: readonly Group[], prompts: readonly string[], answer: string): string {
  const lines = ['## 工程']
  for (const g of groups) {
    lines.push(`- ${g.isSide ? '(脇道) ' : ''}${g.label}${g.note ? ` [${g.note}]` : ''}: ${g.summary}`)
  }
  lines.push('', '## ユーザーの指示(古い順)')
  for (const p of prompts) lines.push(`- ${clip(p.replace(/\s+/g, ' '), 200)}`)
  if (answer) lines.push('', '## エージェントの最後の応答', clip(answer, 1500))
  return lines.join('\n')
}

export function parseRecap(text: string): Recap {
  const m = text.match(/\{[\s\S]*\}/)
  if (!m) return null
  try {
    const v = JSON.parse(m[0]) as Record<string, unknown>
    const str = (x: unknown, n: number) => (typeof x === 'string' ? clip(x.trim(), n) : '')
    const goal = str(v.goal, 60)
    if (!goal) return null
    const sides = Array.isArray(v.sides) ? v.sides.map(x => str(x, 40)).filter(Boolean).slice(0, 4) : []
    return { goal, status: str(v.status, 140), next: str(v.next, 80), sides }
  } catch {
    return null
  }
}
