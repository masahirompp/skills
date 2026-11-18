import type { Phase } from '../types'

/** One step of a stretch: a tool call of the main conversation. */
export type Step = {
  id: string
  tool: string
  brief: string
  isError: boolean
  /** What an Agent or Skill call came back with, cut short: review findings live here. */
  outcome?: string
}

/** A run of work classified as one: a turn, or a part of one. */
export type Stretch = {
  start?: number
  end?: number
  prompt?: string
  steps: Step[]
  subSteps: number
  answer?: string
}

export type Verdict = { continues: boolean; label: string; note: string; summary: string; topic?: string }

/** A stretch is classified at a turn's end, around an Agent or Skill call, or at this many steps. */
export const MAX_STEPS = 15
export const BOUNDARY_TOOLS: ReadonlySet<string> = new Set(['Agent', 'Task', 'Skill'])

export const SYSTEM = `あなたはコーディングエージェントの作業ログを「工程」に分ける係です。
工程とは、人が進捗を一言で言うときの単位です(例: 調査, 設計, 実装, テスト, レビュー, 修正, PR作成)。
同じ種類の工程が繰り返されたら回数を付けます(例: レビュー 2回目)。
直前の工程の続きなら continues を true にし、label は直前と同じにします。
note には所要時間以外で作業の中身が掴める結果を短く書きます(例: 指摘4件, 3ファイル変更, テスト全通過)。分からなければ空文字。
topic にはこの区間が扱う話題を短く書きます(例: timeline mod, CI 設定, git の使い方)。同じ話題なら直前と同じ語を使います。
必ず次の JSON だけを返します。
{"continues": boolean, "label": "12字以内", "note": "20字以内", "summary": "40字以内", "topic": "16字以内"}`

const KEYS = ['file_path', 'command', 'pattern', 'description', 'skill', 'url', 'query', 'subagent_type', 'prompt'] as const

/** A tool call's argument worth a line of the log: a path, a command, a query. */
export function briefOf(input: Record<string, unknown>): string {
  for (const key of KEYS) {
    const v = input[key]
    if (typeof v === 'string' && v.length > 0) return clip(v.replace(/\s+/g, ' '), 80)
  }
  return ''
}

/** A phase's kind: its label without a round count, so レビュー 1回目 and レビュー 2回目 are one kind. */
export function kindOf(label: string): string {
  return (
    label
      .replace(/[\s(（]*(第?[\d０-９]+\s*(回目|周目|巡目|回)|[#＃]\s*[\d０-９]+|[\d０-９]+)[)）]?\s*$/u, '')
      .trim() || label
  )
}

export function clip(text: string, n: number): string {
  return text.length > n ? text.slice(0, n - 1) + '…' : text
}

export function outcomeOf(tool: string, result: unknown): string | undefined {
  return BOUNDARY_TOOLS.has(tool) ? clip(JSON.stringify(result ?? ''), 1500) : undefined
}

export function promptOf(stretch: Stretch, recent: readonly Phase[]): string {
  const lines: string[] = []
  lines.push('## これまでの工程(古い順)')
  if (recent.length === 0) lines.push('(なし)')
  for (const p of recent) lines.push(`- ${p.label}${p.topic ? ` 〈${p.topic}〉` : ''}${p.note ? ` [${p.note}]` : ''}: ${p.summary}`)
  lines.push('', '## 今回の区間')
  if (stretch.prompt) lines.push(`ユーザーの指示: ${clip(stretch.prompt, 400)}`)
  for (const s of stretch.steps) {
    lines.push(`- ${s.tool}${s.brief ? ` ${s.brief}` : ''}${s.isError ? ' (失敗)' : ''}`)
    if (s.outcome) lines.push(`  結果: ${clip(s.outcome, 1200)}`)
  }
  if (stretch.subSteps > 0) lines.push(`(サブエージェント内のツール呼び出し ${stretch.subSteps} 回)`)
  if (stretch.answer) lines.push(`エージェントの応答: ${clip(stretch.answer, 800)}`)
  return lines.join('\n')
}

export function parseVerdict(text: string): Verdict | undefined {
  const m = text.match(/\{[\s\S]*\}/)
  if (!m) return undefined
  try {
    const v = JSON.parse(m[0]) as Record<string, unknown>
    if (typeof v.label !== 'string' || v.label.trim() === '') return undefined
    return {
      continues: v.continues === true,
      label: clip(v.label.trim(), 16),
      note: typeof v.note === 'string' ? clip(v.note.trim(), 24) : '',
      summary: typeof v.summary === 'string' ? clip(v.summary.trim(), 60) : '',
      ...(typeof v.topic === 'string' && v.topic.trim() !== '' ? { topic: clip(v.topic.trim(), 20) } : {}),
    }
  } catch {
    return undefined
  }
}

/**
 * Folds a classified stretch into the phases: extends the last, or starts one named `prefix-n`.
 * `breaks` are the times of the marks (a change of model, a compaction): a stretch begun after one
 * never extends a phase whose work began before it, so the mark has a place between the two.
 */
export function fold(
  phases: readonly Phase[],
  stretch: Stretch,
  v: Verdict,
  prefix: string,
  breaks: readonly number[] = [],
): Phase[] {
  const errors = stretch.steps.filter(s => s.isError).length
  const steps = stretch.steps.length + stretch.subSteps
  const ids = stretch.steps.map(s => s.id)
  const anchor = ids[0]
  const end = stretch.end
  const last = phases[phases.length - 1]
  // Same kind as the last (レビュー 2回目 after レビュー 1回目 too) on the same topic folds in: the last keeps its label.
  const isSameTopic = !v.topic || !last?.topic || v.topic === last.topic
  const from = last?.lastStart ?? last?.start
  const to = stretch.start
  const isParted = from !== undefined && to !== undefined && breaks.some(at => from < at && at <= to)
  if (last && isSameTopic && !isParted && (v.continues || kindOf(v.label) === kindOf(last.label))) {
    const merged: Phase = {
      ...last,
      note: v.note || last.note,
      summary: v.summary || last.summary,
      ...(last.topic === undefined && v.topic !== undefined ? { topic: v.topic } : {}),
      ...(last.prompt === undefined && stretch.prompt ? { prompt: clip(stretch.prompt.replace(/\s+/g, ' '), 120) } : {}),
      steps: last.steps + steps,
      errors: last.errors + errors,
      toolIds: [...last.toolIds, ...ids].slice(-300),
      ...(end !== undefined ? { end } : {}),
      ...(last.start === undefined && stretch.start !== undefined ? { start: stretch.start } : {}),
      ...(stretch.start !== undefined ? { lastStart: stretch.start } : {}),
      ...(last.anchor === undefined && anchor !== undefined ? { anchor } : {}),
    }
    return [...phases.slice(0, -1), merged]
  }
  const phase: Phase = {
    id: `${prefix}-${phases.length + 1}`,
    label: v.label,
    note: v.note,
    summary: v.summary,
    ...(v.topic !== undefined ? { topic: v.topic } : {}),
    ...(stretch.prompt ? { prompt: clip(stretch.prompt.replace(/\s+/g, ' '), 120) } : {}),
    steps,
    errors,
    toolIds: ids.slice(-300),
    ...(stretch.start !== undefined ? { start: stretch.start } : {}),
    ...(end !== undefined ? { end } : {}),
    ...(anchor !== undefined ? { anchor } : {}),
  }
  return [...phases, phase]
}
