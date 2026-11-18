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

/**
 * The newest MAX_MARKS of the marks. The model before the oldest sighting kept is
 * written on it where the mark that told it is dropped: it stays the change it was.
 */
export function capped(marks: readonly Mark[]): Mark[] {
  if (marks.length <= MAX_MARKS) return [...marks]
  const kept = marks.slice(-MAX_MARKS)
  const dropped = marks.slice(0, -MAX_MARKS).findLast(m => m.kind === 'model')
  const i = kept.findIndex(m => m.kind === 'model')
  const first = kept[i]
  if (dropped?.kind === 'model' && first?.kind === 'model') kept[i] = { ...first, prev: dropped.model }
  return kept
}

/**
 * The marks with the model seen at `at` added, unless it is the model last seen.
 * `isMidway`: the sighting is not known to be the session's first, where the marks hold none before it.
 */
export function observed(marks: readonly Mark[], model: string, at: number, isMidway = false): Mark[] {
  if (!isNewModel(marks, model)) return [...marks]
  const isFirst = !marks.some(m => m.kind === 'model')
  return capped([...marks, { kind: 'model' as const, at, model, ...(isFirst && isMidway ? { isMidway } : {}) }])
}

/**
 * The marks seen live, behind the transcript's from before them. Where the transcript holds no model
 * before them, the first seen live is the model the conversation began on, midway no more.
 */
export function joined(past: readonly Mark[], seen: readonly Mark[]): Mark[] {
  if (past.some(m => m.kind === 'model')) return capped([...past, ...seen])
  const begun = seen.map((m): Mark => {
    if (m.kind !== 'model' || !m.isMidway) return m
    const { isMidway: _, ...rest } = m
    return rest
  })
  return capped([...past, ...begun])
}

/**
 * The model changes and compactions of the main conversation, read off the
 * transcript file's lines: the model of each assistant row where it differs
 * from the row before, and each compaction boundary. The first model is the one the
 * conversation began on, unless a boundary is written ahead of it: by the file's order, not by time.
 */
export function marksOf(jsonl: string): Mark[] {
  const reader = markReader()
  for (const line of jsonl.split('\n')) reader.take(line)
  return reader.marks()
}

/** `marksOf`, a line at a time: a transcript file too large for one read is taken in as it comes, never held whole. */
export function markReader(): { take: (line: string) => void; marks: () => Mark[] } {
  let out: Mark[] = []
  const take = (line: string): void => {
    if (!line.includes('"model"') && !line.includes('compact_boundary')) return
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
      return
    }
    const at = row.timestamp ? Date.parse(row.timestamp) : NaN
    if (Number.isNaN(at) || row.isSidechain === true) return
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
      // A boundary written ahead of the first answer: the file carries on a compacted conversation, whose
      // earlier rows are in another. Its first model is midway, not the one the conversation began on.
      const isCarried = out.some(m => m.kind === 'compact')
      if (typeof model === 'string' && model !== '' && !model.startsWith('<')) out = observed(out, model, at, isCarried)
    }
  }
  return { take, marks: () => capped(out) }
}

const TRIGGERS: Record<string, string> = { auto: '自動', manual: '手動', plugin: 'プラグイン' }

export type MarkRow = { key: string; at: number; text: string }

/**
 * The marks as lines to draw, oldest first: a model as a change from the one before it, or as the one
 * the session began on where none was before it. A sighting with no known past is the model alone.
 */
export function markRows(marks: readonly Mark[]): MarkRow[] {
  const rows: MarkRow[] = []
  let model: string | undefined
  for (const m of [...marks].sort((a, b) => a.at - b.at)) {
    if (m.kind === 'model') {
      const before = model ?? m.prev
      model = m.model
      if (before !== undefined && bare(before) === bare(m.model)) continue
      const text =
        before !== undefined
          ? `モデル ${shortModel(before)} → ${shortModel(m.model)}`
          : `モデル ${shortModel(m.model)}${m.isMidway ? '' : '(開始時)'}`
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

/**
 * Where a mark at `at` is drawn among the timeline's rows, each given as the starts of the phases it
 * holds: ahead of phase `member` of row `row`, the first phase of them all that starts at or after it.
 * A `member` past 0 parts the row in two there. Past the last phase: `row` is the number of rows.
 */
export function placeOf(rows: readonly (readonly (number | undefined)[])[], at: number): { row: number; member: number } {
  const flat = rows.flatMap((starts, row) => starts.map((start, member) => ({ row, member, start })))
  const found = flat[slotOf(flat.map(u => u.start), at)]
  return found ? { row: found.row, member: found.member } : { row: rows.length, member: 0 }
}
