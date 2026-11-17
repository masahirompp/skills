import type { SessionMessage } from 'claude-code'

import { BOUNDARY_TOOLS, MAX_STEPS, briefOf, outcomeOf } from './classify'
import type { Stretch } from './classify'

export type Times = ReadonlyMap<string, { start?: number; end?: number }>

/**
 * The history as stretches, cut as the live recording cuts: at each prompt the
 * person typed, around Agent and Skill calls, and every MAX_STEPS calls.
 * Tool calls in `known` are left out; a stretch left empty by that is dropped.
 */
export function stretchesOf(messages: readonly SessionMessage[], known: ReadonlySet<string>): Stretch[] {
  const out: Stretch[] = []
  let cur: Stretch | undefined
  let isKnownTurn = false
  const flush = () => {
    if (cur && (cur.steps.length > 0 || (!isKnownTurn && (cur.prompt || cur.answer)))) out.push(cur)
    cur = undefined
  }
  for (const m of messages) {
    if (m.role === 'user') {
      if ((m.toolResults?.length ?? 0) === 0 && m.text.trim() !== '') {
        flush()
        isKnownTurn = false
        cur = { prompt: m.text, steps: [], subSteps: 0 }
      }
      continue
    }
    if (m.text.trim() !== '') (cur ??= { steps: [], subSteps: 0 }).answer = m.text
    for (const u of m.toolUses) {
      if (known.has(u.tool_use_id)) {
        // A turn the live recording saw: its prompt and answer are in a phase already.
        isKnownTurn = true
        continue
      }
      const isBoundary = BOUNDARY_TOOLS.has(u.tool)
      if (isBoundary) flush()
      cur ??= { steps: [], subSteps: 0 }
      const outcome = outcomeOf(u.tool, u.result ?? u.text)
      cur.steps.push({
        id: u.tool_use_id,
        tool: u.tool,
        brief: briefOf(u.input),
        isError: u.isError === true,
        ...(outcome !== undefined ? { outcome } : {}),
      })
      if (isBoundary || cur.steps.length >= MAX_STEPS) flush()
    }
  }
  flush()
  return out
}

/** Each tool call's start and end, read off the transcript file's lines. */
export function timesOf(jsonl: string): Map<string, { start?: number; end?: number }> {
  const times = new Map<string, { start?: number; end?: number }>()
  for (const line of jsonl.split('\n')) {
    if (!line.includes('"tool_use') && !line.includes('"tool_result')) continue
    let row: { type?: string; timestamp?: string; message?: { content?: unknown } }
    try {
      row = JSON.parse(line)
    } catch {
      continue
    }
    const t = row.timestamp ? Date.parse(row.timestamp) : NaN
    const content = row.message?.content
    if (Number.isNaN(t) || !Array.isArray(content)) continue
    for (const b of content as { type?: string; id?: string; tool_use_id?: string }[]) {
      if (b.type === 'tool_use' && b.id) times.set(b.id, { ...times.get(b.id), start: t })
      if (b.type === 'tool_result' && b.tool_use_id) times.set(b.tool_use_id, { ...times.get(b.tool_use_id), end: t })
    }
  }
  return times
}

/**
 * Gives each stretch the span of its tool calls; one with none takes the end of
 * the one before. A stretch with no tool calls that starts at or after
 * `liveFrom` (the live recording's start) is dropped: the live phases hold it.
 * One with tool calls is kept: those the live recording saw are left out
 * earlier, by their ids.
 */
export function timed(stretches: readonly Stretch[], times: Times, liveFrom: number | undefined): Stretch[] {
  const out: Stretch[] = []
  let prev: number | undefined
  for (const s of stretches) {
    const marks = s.steps.map(st => times.get(st.id)).filter(t => t !== undefined)
    const starts = marks.map(t => t.start).filter((n): n is number => n !== undefined)
    const ends = marks.map(t => t.end ?? t.start).filter((n): n is number => n !== undefined)
    const start = starts.length > 0 ? Math.min(...starts) : prev
    const end = ends.length > 0 ? Math.max(...ends) : start
    if (s.steps.length === 0 && liveFrom !== undefined && start !== undefined && start >= liveFrom) continue
    out.push({ ...s, ...(start !== undefined ? { start } : {}), ...(end !== undefined ? { end } : {}) })
    prev = end ?? prev
  }
  return out
}

/** Where Claude Code keeps this session's transcript, when no hook named it. */
export function transcriptPathOf(configDir: string, cwd: string, sessionId: string): string {
  return `${configDir}/projects/${cwd.replace(/[^A-Za-z0-9]/g, '-')}/${sessionId}.jsonl`
}
