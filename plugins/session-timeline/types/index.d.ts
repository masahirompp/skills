export type Phase = {
  id: string
  /** The phase's name as the classifier gave it: 実装, レビュー 2回目, ... */
  label: string
  /** A short figure of what it came to: 指摘4件, 3ファイル変更, ... */
  note: string
  summary: string
  /** What it is about, as the classifier named it: the session's main subject or a side one. */
  topic?: string
  /** The person's instruction that opened it, cut short: where a digression shows plainest. */
  prompt?: string
  /** Absent for a past phase whose times the transcript file did not give. */
  start?: number
  end?: number
  /** A tool_use_id of the main conversation inside the phase, to scroll to. */
  anchor?: string
  /** The main conversation's tool calls it holds: what a backfill skips. */
  toolIds: string[]
  steps: number
  errors: number
}

/** A phase as a person tells progress: a run of the fine phases, regrouped over the whole session. */
export type Group = {
  id: string
  label: string
  note: string
  summary: string
  /** The fine phases it holds, in order. */
  phaseIds: string[]
  /** A digression from the session's main subject. */
  isSide?: boolean
}

/** Where the session stands, in a few lines a person reads at a glance. */
export type Recap = { goal: string; status: string; next: string; sides: string[] } | null

/** The stretch not yet classified: since when, and how many steps. */
export type Live = { since: number; steps: number; isClassifying: boolean } | null

/** What the model calls behind the timeline have used, all told. */
export type Usage = { calls: number; input: number; output: number; cacheRead: number; cacheWrite: number }

/** How far filling in the history before the mod loaded has got. */
export type Backfill = { done: number; total: number } | null

declare module 'claude-code' {
  interface PluginState {
    'session-timeline': {
      phases: Shaped<Phase[]>
      groups: Shaped<Group[]>
      expanded: Shaped<string[]>
      recap: Shaped<Recap>
      latestRow: string
      usage: Shaped<Usage>
      liveFromIndex: number
      live: Shaped<Live>
      backfill: Shaped<Backfill>
      isBackfilled: boolean
      cwd: string
      transcriptPath: string
    }
  }
}
