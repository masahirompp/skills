import type { SessionMessage } from 'claude-code'

import type { FoundLink } from '../types'

/** How many links the pane keeps; the oldest mentioned drop off. */
export const MAX_LINKS = 40

const URL_RE = /https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+/g

/**
 * A Markdown link, `[text](URL)`, its text and URL the groups: tried before a bare URL,
 * so a link whose text is the URL itself (`[https://…](https://…)`) is one URL,
 * not the two run together. The URL may hold balanced parentheses.
 */
const MD_LINK_RE = /\[([^\]\n]*)\]\((https?:\/\/[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)\)/g

const TOKEN_RE = new RegExp(`${MD_LINK_RE.source}|${URL_RE.source}`, 'g')

/**
 * A GitHub issue, pull request or commit up to its number, a parenthesis right after:
 * the number ends the page, so `(` there begins a note (`…/pull/58(#58)`), not the URL.
 */
const GITHUB_NOTE_RE = /^(https?:\/\/github\.com\/[^/\s]+\/[^/\s]+\/(?:(?:pull|issues)\/\d+|commit\/[0-9a-f]{7,40}))\(.*$/

/**
 * Cuts what text around a URL leaves on its end: a sentence's stop, a Markdown link's closing paren,
 * an opening paren or bracket whose note the URL's characters stop short of (`…/a(ドラフト)`).
 */
function trimEnd(url: string): string {
  let u = url.replace(GITHUB_NOTE_RE, '$1')
  for (;;) {
    const last = u.at(-1)
    if (last === undefined) return u
    if ('.,;:!?\'"*(['.includes(last)) {
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

/** A host to open: not a template (`https://${host}/x`) nor a bare word (`https://foo`). */
const OPENABLE_RE = /^https?:\/\/[^/?#]+\.[^/?#]+|^https?:\/\/localhost/

/** A URL said in a text, with the words a Markdown link gives it (`[PR #58](…)`), where it has them. */
export type Said = { url: string; text?: string }

/**
 * The words of a Markdown link, kept as written to name the link: none where
 * they are blank or the URL itself (`[https://…](https://…)`), which say no more than it.
 */
function wordsOf(text: string | undefined): string | undefined {
  const words = text?.replace(/\s+/g, ' ').trim()
  return words && !/^https?:\/\//.test(words) ? words : undefined
}

/** The URLs a text holds, in order, each with its Markdown link's words where it has them. */
export function saidIn(text: string): Said[] {
  const out: Said[] = []
  for (const m of text.matchAll(TOKEN_RE)) {
    const url = m[2] ?? trimEnd(m[0])
    if (!OPENABLE_RE.test(url)) continue
    const words = m[2] !== undefined ? wordsOf(m[1]) : undefined
    out.push(words ? { url, text: words } : { url })
  }
  return out
}

/** The URLs a text holds, in order, as written. */
export function urlsIn(text: string): string[] {
  return saidIn(text).map(s => s.url)
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

/**
 * Where a URL is said: a text, whose URLs are cut where the words around them
 * begin, or a whole URL (a tool call's argument), its ends known, taken as it is.
 */
export type Mention = string | { readonly url: string }

/** A tool call's URL arguments, each a whole URL: none is cut short as a URL in a sentence is (`…/wiki/東京`). */
export function toolMentions(tool: string, args: Readonly<Record<string, unknown>>): Mention[] {
  return callMentions(tool, args).map(url => ({ url }))
}

/** Everything a URL can be said in, in order: the messages' words and their tool calls' arguments. */
export function mentionsOf(messages: readonly SessionMessage[]): Mention[] {
  const out: Mention[] = []
  for (const m of messages) {
    if (m.text) out.push(m.text)
    for (const u of m.toolUses ?? []) out.push(...toolMentions(u.tool, u.input ?? {}))
  }
  return out
}

/**
 * Whether `url` goes to the row `link` itself, not a part within it: GitHub's
 * rows drop what follows their number (`#issuecomment-…`, `/files`), which a
 * link's words then name (`[このコメント](…)`), not the PR. Only a trailing `/` is the same page.
 */
function isWhole(url: string, link: Omit<FoundLink, 'seen'>): boolean {
  return new URL(url).href.replace(/\/$/, '') === link.key
}

function saidOf(mention: Mention): Said[] {
  if (typeof mention === 'string') return saidIn(mention)
  return OPENABLE_RE.test(mention.url) ? [{ url: mention.url }] : []
}

/**
 * The links found in `mentions`, put ahead of `known`: a link said again moves
 * to the front, its `seen` raised. A Markdown link's words name it where the
 * link goes to it whole, the latest kept when it is said again bare or by a
 * link to a part of it. Newest first, at most MAX_LINKS.
 */
export function addLinks(known: readonly FoundLink[], mentions: readonly Mention[]): FoundLink[] {
  const byKey = new Map(known.map(l => [l.key, l]))
  let seen = Math.max(0, ...known.map(l => l.seen))
  for (const mention of mentions) {
    for (const { url, text } of saidOf(mention)) {
      const link = linkOf(url)
      if (!link) continue
      seen += 1
      const words = (text !== undefined && isWhole(url, link) ? text : undefined) ?? byKey.get(link.key)?.text
      byKey.set(link.key, words ? { ...link, text: words, seen } : { ...link, seen })
    }
  }
  return [...byKey.values()].sort((a, b) => b.seen - a.seen).slice(0, MAX_LINKS)
}
