import type { SessionMessage } from 'claude-code'

import type { FoundLink } from '../types'

/** How many links the pane keeps; the oldest mentioned drop off. */
export const MAX_LINKS = 40

const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+/g

/**
 * A Markdown link, `[text](URL)`, its URL the group: tried before a bare URL,
 * so a link whose text is the URL itself (`[https://…](https://…)`) is one URL,
 * not the two run together. The URL may hold balanced parentheses.
 */
const MD_LINK_RE = /\[[^\]\n]*\]\((https?:\/\/[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)\)/g

const TOKEN_RE = new RegExp(`${MD_LINK_RE.source}|${URL_RE.source}`, 'g')

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
  for (const m of text.matchAll(TOKEN_RE)) {
    const u = m[1] ?? trimEnd(m[0])
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

/** The keys `tool.call`'s input carries beside the tool's own arguments. */
export const NOT_ARGUMENTS: readonly string[] = ['tool', 'tool_use_id', 'agentId', 'consent', 'requestMeta']

/**
 * The arguments that hold what a tool writes into a file, not a target it
 * names: an Edit that swaps one URL for another in a README is nobody's pick.
 */
const CONTENT_ARGS: Readonly<Record<string, readonly string[]>> = {
  Write: ['content'],
  Edit: ['old_string', 'new_string'],
  MultiEdit: ['edits'],
  NotebookEdit: ['new_source'],
}

/**
 * The URLs a tool call names: its arguments whose value is a URL and nothing
 * more (WebFetch's `url`), less what it writes into a file. A URL inside a
 * command, a prompt or a file's text (a commit's trailer, a PR's body) rides
 * along, nobody's pick; an argument holding a list or an object is not looked
 * into. Never the call's output: a listing, a search or a page shows URLs
 * nobody chose, and what the work made (a PR) Claude names in its answer.
 */
export function callMentions(tool: string, args: Readonly<Record<string, unknown>>): string[] {
  const skip = CONTENT_ARGS[tool] ?? []
  const out: string[] = []
  for (const [key, value] of Object.entries(args)) {
    if (typeof value !== 'string' || skip.includes(key)) continue
    const url = value.trim()
    if (/^https?:\/\/\S+$/.test(url)) out.push(url)
  }
  return out
}

/** Every text a URL can be said in, in order: the messages' words and their tool calls' arguments. */
export function mentionsOf(messages: readonly SessionMessage[]): string[] {
  const out: string[] = []
  for (const m of messages) {
    if (m.text) out.push(m.text)
    for (const u of m.toolUses ?? []) out.push(...callMentions(u.tool, u.input ?? {}))
  }
  return out
}

/**
 * The links found in `mentions`, put ahead of `known`: a link said again moves
 * to the front, its `seen` raised. Newest first, at most MAX_LINKS.
 */
export function addLinks(known: readonly FoundLink[], mentions: readonly string[]): FoundLink[] {
  const byKey = new Map(known.map(l => [l.key, l]))
  let seen = Math.max(0, ...known.map(l => l.seen))
  for (const text of mentions) {
    for (const url of urlsIn(text)) {
      const link = linkOf(url)
      if (!link) continue
      seen += 1
      byKey.set(link.key, { ...link, seen })
    }
  }
  return [...byKey.values()].sort((a, b) => b.seen - a.seen).slice(0, MAX_LINKS)
}
