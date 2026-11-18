import type { Mark } from '../types'
import { kilo } from './view'

/** Marks kept: the oldest give way past this many. */
export const MAX_MARKS = 200

/** A model id without what the transcript file does not carry (`[1m]`), to compare one sighting with another. */
function bare(model: string): string {
  return model.replace(/\[[^\]]*\]$/, '')
}

export function shortModel(model: string): string {
  return model.replace(/^claude-/, '')
}

/** Whether `model` is another than the one the marks last saw. */
export function isNewModel(marks: readonly Mark[], model: string): boolean {
  const last = marks.findLast(m => m.kind === 'model')
  return !(last?.kind === 'model' && bare(last.model) === bare(model))
}

/** The marks with the model seen at `at` added, unless it is the model last seen. */
export function observed(marks: readonly Mark[], model: string, at: number): Mark[] {
  if (!isNewModel(marks, model)) return [...marks]
  return [...marks, { kind: 'model' as const, at, model }].slice(-MAX_MARKS)
}

/**
 * The model changes and compactions of the main conversation, read off the
 * transcript file's lines: the model of each assistant row where it differs
 * from the row before, and each compaction boundary.
 */
export function marksOf(jsonl: string): Mark[] {
  let out: Mark[] = []
  for (const line of jsonl.split('\n')) {
    if (!line.includes('"model"') && !line.includes('compact_boundary')) continue
    let row: {
      type?: string
      subtype?: string
      isSidechain?: boolean
      timestamp?: string
      message?: { model?: unknown }
      compactMetadata?: { trigger?: unknown; preTokens?: unknown; postTokens?: unknown }
    }
    try {
      row = JSON.parse(line)
    } catch {
      continue
    }
    const at = row.timestamp ? Date.parse(row.timestamp) : NaN
    if (Number.isNaN(at) || row.isSidechain === true) continue
    if (row.type === 'system' && row.subtype === 'compact_boundary') {
      const meta = row.compactMetadata
      out.push({
        kind: 'compact',
        at,
        trigger: typeof meta?.trigger === 'string' ? meta.trigger : '',
        ...(typeof meta?.preTokens === 'number' ? { before: meta.preTokens } : {}),
        ...(typeof meta?.postTokens === 'number' ? { after: meta.postTokens } : {}),
      })
    } else if (row.type === 'assistant') {
      const model = row.message?.model
      // `<synthetic>` rows are the engine's own notices, not a model's answer.
      if (typeof model === 'string' && model !== '' && !model.startsWith('<')) out = observed(out, model, at)
    }
  }
  return out.slice(-MAX_MARKS)
}

const TRIGGERS: Record<string, string> = { auto: '自動', manual: '手動', plugin: 'プラグイン' }

export type MarkRow = { key: string; at: number; text: string }

/** The marks as lines to draw, oldest first: the first model as the one the session began on, later ones as changes. */
export function markRows(marks: readonly Mark[]): MarkRow[] {
  const rows: MarkRow[] = []
  let model: string | undefined
  for (const m of [...marks].sort((a, b) => a.at - b.at)) {
    if (m.kind === 'model') {
      if (model !== undefined && bare(model) === bare(m.model)) continue
      const text =
        model === undefined ? `モデル ${shortModel(m.model)}(開始時)` : `モデル ${shortModel(model)} → ${shortModel(m.model)}`
      model = m.model
      rows.push({ key: `mark-model-${m.at}`, at: m.at, text })
    } else {
      const how = TRIGGERS[m.trigger]
      const size =
        m.before !== undefined ? `  ${kilo(m.before)}${m.after !== undefined ? ` → ${kilo(m.after)}` : ''} トークン` : ''
      rows.push({ key: `mark-compact-${m.at}`, at: m.at, text: `compact${how ? `(${how})` : ''}${size}` })
    }
  }
  return rows
}

/**
 * Before which of the timeline's rows a mark at `at` is drawn: the first that
 * starts at or after it, or past the last. A row whose start is unknown is never the one.
 */
export function slotOf(starts: readonly (number | undefined)[], at: number): number {
  const i = starts.findIndex(s => s !== undefined && s >= at)
  return i < 0 ? starts.length : i
}
