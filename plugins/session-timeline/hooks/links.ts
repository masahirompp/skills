import type { SessionMessage } from 'claude-code'

import type { FoundLink } from '../types'

/** How many links the pane keeps; the oldest mentioned drop off. */
export const MAX_LINKS = 40

const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+/g

/** Cuts what text around a URL leaves on its end: a sentence's stop, a Markdown link's closing paren. */
function trimEnd(url: string): string {
  let u = url
  for (;;) {
    const last = u.at(-1)
    if (last === undefined) return u
    if ('.,;:!?\'"*'.includes(last)) {
      u = u.slice(0, -1)
      continue
    }
    if (last === ')' || last === ']') {
      const open = last === ')' ? '(' : '['
      const opens = u.split(open).length - 1
      const closes = u.split(last).length - 1
      if (closes > opens) {
        u = u.slice(0, -1)
        continue
      }
    }
    return u
  }
}

/** The URLs a text holds, in order, as written. */
export function urlsIn(text: string): string[] {
  const out: string[] = []
  for (const m of text.matchAll(URL_RE)) {
    const u = trimEnd(m[0])
    if (/^https?:\/\/[^/?#]+\.[^/?#]+|^https?:\/\/localhost/.test(u)) out.push(u)
  }
  return out
}

/**
 * A URL as the pane lists it: GitHub's issues, pull requests and commits by
 * their number, one entry however the URL went on (`/files`, `#issuecomment-…`).
 */
export function linkOf(url: string): Omit<FoundLink, 'seen'> | undefined {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return undefined
  }
  if (parsed.hostname === 'github.com') {
    const [owner, repo, kind, id] = parsed.pathname.split('/').filter(Boolean)
    const base = `https://github.com/${owner}/${repo}`
    if (owner && repo && kind === 'pull' && id && /^\d+$/.test(id)) {
      return { key: `${base}/pull/${id}`, href: `${base}/pull/${id}`, kind: 'PR', label: `${owner}/${repo}#${id}` }
    }
    if (owner && repo && kind === 'issues' && id && /^\d+$/.test(id)) {
      return { key: `${base}/issues/${id}`, href: `${base}/issues/${id}`, kind: 'Issue', label: `${owner}/${repo}#${id}` }
    }
    if (owner && repo && kind === 'commit' && id && /^[0-9a-f]{7,40}$/.test(id)) {
      return { key: `${base}/commit/${id}`, href: `${base}/commit/${id}`, kind: 'Commit', label: `${owner}/${repo}@${id.slice(0, 7)}` }
    }
  }
  const href = parsed.href
  const label = `${parsed.host}${parsed.pathname === '/' ? '' : parsed.pathname}${parsed.search}${parsed.hash}`
  return { key: href.replace(/\/$/, ''), href, kind: 'URL', label }
}

/**
 * Whether a URL found in a tool's output is listed: only what work makes and
 * names (an issue, a PR, a commit). A fetched page or a search answer holds
 * dozens of other URLs nobody chose.
 */
export function isNamedKind(link: Omit<FoundLink, 'seen'>): boolean {
  return link.kind !== 'URL'
}

/** Where the URLs of a conversation's messages are said: chosen (prompts, answers, tool arguments) or only seen in output. */
export type Mention = { text: string; isOutput: boolean }

/** Every place a URL can be said in the messages, in order. */
export function mentionsOf(messages: readonly SessionMessage[]): Mention[] {
  const out: Mention[] = []
  for (const m of messages) {
    if (m.text) out.push({ text: m.text, isOutput: false })
    for (const u of m.toolUses ?? []) {
      out.push({ text: JSON.stringify(u.input ?? {}), isOutput: false })
      if (u.text) out.push({ text: u.text, isOutput: true })
    }
  }
  return out
}

/**
 * The links found in `mentions`, put ahead of `known`: a link said again moves
 * to the front, its `seen` raised. Newest first, at most MAX_LINKS.
 */
export function addLinks(known: readonly FoundLink[], mentions: readonly Mention[]): FoundLink[] {
  const byKey = new Map(known.map(l => [l.key, l]))
  let seen = Math.max(0, ...known.map(l => l.seen))
  for (const { text, isOutput } of mentions) {
    for (const url of urlsIn(text)) {
      const link = linkOf(url)
      if (!link || (isOutput && !isNamedKind(link))) continue
      seen += 1
      byKey.set(link.key, { ...link, seen })
    }
  }
  return [...byKey.values()].sort((a, b) => b.seen - a.seen).slice(0, MAX_LINKS)
}

/**
 * The links of the whole conversation, read afresh from its messages; those
 * `known` holds and the messages do not yet (a turn still being written) stay
 * ahead, newest.
 */
export function rescanLinks(known: readonly FoundLink[], mentions: readonly Mention[]): FoundLink[] {
  const fresh = addLinks([], mentions)
  const keys = new Set(fresh.map(l => l.key))
  const missing = known.filter(l => !keys.has(l.key)).sort((a, b) => a.seen - b.seen)
  const top = Math.max(0, ...fresh.map(l => l.seen))
  return [...missing.map((l, i) => ({ ...l, seen: top + i + 1 })), ...fresh]
    .sort((a, b) => b.seen - a.seen)
    .slice(0, MAX_LINKS)
}
