import type { On, SessionMessage } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import { REGROUP_SYSTEM, RECAP_SYSTEM } from '../hooks/group'
import { addLinks, linkOf, rescanLinks, urlsIn } from '../hooks/links'

const PANE = {
  plugin: 'session-timeline',
  component: 'Pane',
  requestId: 'session-timeline',
  props: {
    title: 'Session timeline',
    isFocused: false,
    bodyColumns: 70,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

declare function setTimeout(fn: () => void, ms: number): unknown
const settle = () => new Promise<void>(r => setTimeout(r, 300))

test('URLs are cut where the text around them begins', () => {
  expect(urlsIn('PR は https://github.com/o/r/pull/51 です。')).toEqual(['https://github.com/o/r/pull/51'])
  expect(urlsIn('see [#44](https://github.com/o/r/issues/44).')).toEqual(['https://github.com/o/r/issues/44'])
  expect(urlsIn('(https://example.com/a_(b))')).toEqual(['https://example.com/a_(b)'])
  expect(urlsIn('"https://example.com/x",')).toEqual(['https://example.com/x'])
  expect(urlsIn('http://localhost:3000/ok')).toEqual(['http://localhost:3000/ok'])
  // No host to open: a template, not a page.
  expect(urlsIn('https://${host}/x and https://foo')).toEqual([])
})

test('a Markdown link is the URL in its parentheses, its text a URL too', () => {
  // Claude's answers write a link as `[URL](URL)`.
  const text = '作りました: [https://github.com/o/r/pull/5](https://github.com/o/r/pull/5)。'
  expect(urlsIn(text)).toEqual(['https://github.com/o/r/pull/5'])
  expect(addLinks([], [{ text, isOutput: false }]).map(l => [l.kind, l.href])).toEqual([['PR', 'https://github.com/o/r/pull/5']])
  expect(urlsIn('[docs](https://example.com/a_(b)) と [https://x.example.com/p](https://x.example.com/p)')).toEqual([
    'https://example.com/a_(b)',
    'https://x.example.com/p',
  ])
})

test('GitHub issues, PRs and commits are named by number however the URL goes on', () => {
  expect(linkOf('https://github.com/o/r/pull/51/files#diff-1')).toEqual({
    key: 'https://github.com/o/r/pull/51',
    href: 'https://github.com/o/r/pull/51',
    kind: 'PR',
    label: 'o/r#51',
  })
  expect(linkOf('https://github.com/o/r/issues/44#issuecomment-1')?.label).toBe('o/r#44')
  expect(linkOf('https://github.com/o/r/issues/44#issuecomment-1')?.kind).toBe('Issue')
  expect(linkOf('https://github.com/o/r/commit/e26d750abc')?.label).toBe('o/r@e26d750')
  expect(linkOf('https://github.com/o/r')?.kind).toBe('URL')
  expect(linkOf('https://claude.ai/code/artifact/abc')?.label).toBe('claude.ai/code/artifact/abc')
})

test('a link said again moves to the front; a page only seen in output is left out', () => {
  const one = addLinks(
    [],
    [
      { text: 'https://github.com/o/r/issues/1 と https://docs.example.com/a', isOutput: false },
      // A search answer's pages: nobody chose them.
      { text: 'https://blog.example.com/x https://github.com/o/r/pull/2', isOutput: true },
    ],
  )
  expect(one.map(l => l.label)).toEqual(['o/r#2', 'docs.example.com/a', 'o/r#1'])
  const two = addLinks(one, [{ text: 'https://github.com/o/r/issues/1#issuecomment-9', isOutput: false }])
  expect(two.map(l => l.label)).toEqual(['o/r#1', 'o/r#2', 'docs.example.com/a'])
})

test('a rescan reads the order off the messages and keeps what they lack yet ahead', () => {
  const live = addLinks([], [{ text: 'https://github.com/o/r/pull/9', isOutput: false }])
  const again = rescanLinks(live, [
    { text: 'https://github.com/o/r/issues/1', isOutput: false },
    { text: 'https://github.com/o/r/issues/2', isOutput: false },
  ])
  expect(again.map(l => l.label)).toEqual(['o/r#9', 'o/r#2', 'o/r#1'])
})

test('the pane lists the links of the history and of the live turns, each one to open', async ($, on) => {
  let clock = Date.UTC(2026, 10, 19, 1, 0, 0)
  const u = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
  on('session.messages', () => ({
    value: [
      { role: 'user', text: 'https://github.com/o/r/issues/44 を直して', toolUses: [] },
      {
        role: 'assistant',
        text: '',
        toolUses: [
          {
            tool_use_id: 'old-search',
            tool: 'WebSearch',
            input: { query: 'x' },
            text: 'https://random.example.com/a https://random.example.com/b',
          },
        ],
      },
      { role: 'assistant', text: '調べました', toolUses: [] },
    ],
  }))
  on('model.complete', (_, e) => {
    if (e.system === REGROUP_SYSTEM) return { value: { isAnswered: true, text: '[]', usage: u } }
    if (e.system === RECAP_SYSTEM) return { value: { isAnswered: false, reason: 'aborted', usage: u } }
    return { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '実装', note: '', summary: '' }), usage: u } }
  })
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', (_, e) =>
    e.tool === 'Bash' ? { text: 'https://github.com/o/r/pull/56\n', result: {} } : { text: 'https://noise.example.com/z', result: {} },
  )

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await $.tool.call({ tool: 'Bash', command: 'gh pr create --fill', tool_use_id: 'tu-pr' })
  await $.tool.call({ tool: 'WebFetch', url: 'https://docs.example.com/mods', prompt: 'read', tool_use_id: 'tu-fetch' })
  await $.turn.complete({ answer: 'PR を作りました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /^リンク$/ })).toBeTruthy()
  const hrefs = (await ui.findAll({ type: 'Link' })).map(l => l.props.href)
  // Newest first: the page fetched, the PR made, then the issue the history named.
  expect(hrefs).toEqual(['https://docs.example.com/mods', 'https://github.com/o/r/pull/56', 'https://github.com/o/r/issues/44'])
  expect(await ui.find({ type: 'Text', text: /^PR / })).toBeTruthy()
  await ui.unmount()
})

/** The engine beneath the mod, with `history` as the conversation's messages. */
function engine(on: On, history: () => readonly SessionMessage[]): void {
  let clock = Date.UTC(2026, 10, 19, 1, 0, 0)
  const u = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
  on('session.messages', () => ({ value: history() as SessionMessage[] }))
  on('model.complete', (_, e) => {
    if (e.system === REGROUP_SYSTEM) return { value: { isAnswered: true, text: '[]', usage: u } }
    if (e.system === RECAP_SYSTEM) return { value: { isAnswered: false, reason: 'aborted', usage: u } }
    return { value: { isAnswered: true, text: JSON.stringify({ continues: false, label: '実装', note: '', summary: '' }), usage: u } }
  })
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
}

/** The pages the pane's links open, top first. */
async function listed($: Engine): Promise<string[]> {
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const out = (await ui.findAll({ type: 'Link' })).map(l => String(l.props.href))
  await ui.unmount()
  return out
}

const HTML = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>\n<!-- see https://www.chartjs.org/docs -->'

test('what a tool writes into a file, and what rides beside its arguments, is not listed', async ($, on) => {
  engine(on, () => [])
  on('tool.call', () => ({ text: 'ok', result: {} }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'https://github.com/o/r/issues/44 を直して', turnId: 't1' })
  await $.tool.call({ tool: 'Write', file_path: '/w/index.html', content: HTML, tool_use_id: 'w1' })
  await $.tool.call({
    tool: 'Edit',
    file_path: '/w/README.md',
    old_string: 'https://old.example.com/a',
    new_string: 'https://new.example.com/b',
    tool_use_id: 'e1',
  })
  await $.tool.call({ tool: 'NotebookEdit', notebook_path: '/w/n.ipynb', new_source: 'https://nb.example.com/c', tool_use_id: 'n1' } as never)
  // Not the tool's arguments: the person's words for a press, a hook's request meta.
  await $.tool.call({
    tool: 'Bash',
    command: 'ls',
    tool_use_id: 'b1',
    consent: 'The user pressed "1: Yes" on https://consent.example.com/prompt',
  } as never)
  await $.tool.call({
    tool: 'mcp__docs__search',
    query: 'x',
    tool_use_id: 'm1',
    requestMeta: { 'anthropic/sources': JSON.stringify([{ url: 'https://sources.example.com/a' }]) },
  } as never)
  await $.tool.call({ tool: 'WebFetch', url: 'https://docs.example.com/mods', prompt: 'read', tool_use_id: 'f1' })
  await $.turn.complete({ answer: 'できました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/mods', 'https://github.com/o/r/issues/44'])
})

test('what a tool wrote into a file is not listed when the history is read again', { options: { autoOpen: false } }, async ($, on) => {
  engine(on, () => [
    { role: 'user', text: 'https://github.com/o/r/issues/44 を直して', toolUses: [] },
    {
      role: 'assistant',
      text: '',
      toolUses: [
        { tool_use_id: 'w1', tool: 'Write', input: { file_path: '/w/index.html', content: HTML }, text: 'ok' },
        {
          tool_use_id: 'e1',
          tool: 'Edit',
          input: { file_path: '/w/README.md', old_string: 'https://old.example.com/a', new_string: 'https://new.example.com/b' },
          text: 'ok',
        },
        { tool_use_id: 'n1', tool: 'NotebookEdit', input: { notebook_path: '/w/n.ipynb', new_source: 'https://nb.example.com/c' }, text: 'ok' },
        { tool_use_id: 'f1', tool: 'WebFetch', input: { url: 'https://docs.example.com/mods', prompt: 'read' }, text: 'page' },
      ],
    },
    { role: 'assistant', text: 'できました', toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/mods', 'https://github.com/o/r/issues/44'])
})

test('a URL Claude writes mid-turn is listed as the turn goes, though the turn ends on other words', async ($, on) => {
  engine(on, () => [])
  const answers = ['issue https://github.com/o/r/issues/44 を見ます', '完了しました']
  on('turn.step', async function* (_, e) {
    const answer = e.agentId ? 'https://sub.example.com/a' : (answers[e.index] ?? '')
    return { turnId: e.turnId, index: e.index, answer, toolUses: [], stopReason: 'end_turn', usage: null }
  })
  on('tool.call', () => ({ text: 'a.ts\n', result: {} }))
  const step = async (index: number, agentId?: string) => {
    for await (const _ of $.turn.step({ turnId: 't1', index, model: 'claude-opus-5-5', messageCount: 1 + index * 2, agentId })) void _
  }
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await step(0)
  await $.tool.call({ tool: 'Bash', command: 'ls', tool_use_id: 'b1' })
  // A subagent's steps are its own conversation's.
  await step(0, 'sub-1')
  await step(1)
  await $.turn.complete({ answer: '完了しました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://github.com/o/r/issues/44'])
})

// A search answer as the model reads it: other repositories' issues among the hits.
const SEARCH =
  'Web search results for query: "ink flicker"\n\nLinks: [{"title":"Flicker on resize","url":"https://github.com/x/y/issues/7"},{"title":"Fix flicker","url":"https://github.com/x/y/pull/8"}]'
const SEARCH_RESULT = {
  query: 'ink flicker',
  results: [
    {
      tool_use_id: 'srv-1',
      content: [
        { title: 'Flicker on resize', url: 'https://github.com/x/y/issues/7' },
        { title: 'Fix flicker', url: 'https://github.com/x/y/pull/8' },
      ],
    },
  ],
  durationSeconds: 1,
}
const FETCHED = 'See https://github.com/x/z/issues/9 for the bug.'
const GREPPED = '/w/a.ts:3: // https://github.com/x/w/commit/abcdef1'

test('GitHub issues a search, a fetched page or a file shows are not listed; the PR gh made is', async ($, on) => {
  engine(on, () => [])
  on('tool.call', (_, e) => {
    if (e.tool === 'Bash') return { text: 'https://github.com/o/r/pull/56\n', result: {} }
    if (e.tool === 'WebSearch') return { text: SEARCH, result: SEARCH_RESULT }
    if (e.tool === 'WebFetch') return { text: FETCHED, result: {} }
    return { text: GREPPED, result: {} }
  })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await $.tool.call({ tool: 'Bash', command: 'gh pr create --fill', tool_use_id: 'b1' })
  await $.tool.call({ tool: 'WebSearch', query: 'ink flicker', mode: 'standard', tool_use_id: 's1' } as never)
  await $.tool.call({ tool: 'WebFetch', url: 'https://docs.example.com/x', prompt: 'read', tool_use_id: 'f1' })
  await $.tool.call({ tool: 'Grep', pattern: 'github', tool_use_id: 'g1' } as never)
  await $.turn.complete({ answer: '調べました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/x', 'https://github.com/o/r/pull/56'])
})

test('the same outputs read again from the history are not listed either', { options: { autoOpen: false } }, async ($, on) => {
  engine(on, () => [
    { role: 'user', text: '続けて', toolUses: [] },
    {
      role: 'assistant',
      text: '',
      toolUses: [
        { tool_use_id: 'b1', tool: 'Bash', input: { command: 'gh pr create --fill' }, text: 'https://github.com/o/r/pull/56\n' },
        { tool_use_id: 's1', tool: 'WebSearch', input: { query: 'ink flicker', mode: 'standard' }, text: SEARCH, result: SEARCH_RESULT },
        { tool_use_id: 'f1', tool: 'WebFetch', input: { url: 'https://docs.example.com/x', prompt: 'read' }, text: FETCHED },
        { tool_use_id: 'g1', tool: 'Grep', input: { pattern: 'github' }, text: GREPPED },
      ],
    },
    { role: 'assistant', text: '調べました', toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/x', 'https://github.com/o/r/pull/56'])
})
