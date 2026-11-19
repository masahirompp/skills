import type { On, SessionMessage } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'

import { REGROUP_SYSTEM, RECAP_SYSTEM } from '../hooks/group'
import { addLinks, callMentions, linkOf, urlsIn } from '../hooks/links'

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

test('a note in parentheses after a URL is not the URL; parentheses of its own are', () => {
  expect(addLinks([], ['PR を作った: https://github.com/o/r/pull/58(ドラフト)']).map(l => [l.kind, l.href])).toEqual([
    ['PR', 'https://github.com/o/r/pull/58'],
  ])
  expect(addLinks([], ['see https://github.com/o/r/pull/58(#58)']).map(l => [l.kind, l.href])).toEqual([
    ['PR', 'https://github.com/o/r/pull/58'],
  ])
  expect(urlsIn('https://github.com/o/r/commit/e26d750abc(直し)')).toEqual(['https://github.com/o/r/commit/e26d750abc'])
  // The URL's characters stop at the note's Japanese: the opening paren left is cut.
  expect(urlsIn('https://docs.example.com/a(下書き)')).toEqual(['https://docs.example.com/a'])
  expect(urlsIn('(https://example.com/a_(b))')).toEqual(['https://example.com/a_(b)'])
})

test('a Markdown link is the URL in its parentheses, its text a URL too', () => {
  // Claude's answers write a link as `[URL](URL)`.
  const text = '作りました: [https://github.com/o/r/pull/5](https://github.com/o/r/pull/5)。'
  expect(urlsIn(text)).toEqual(['https://github.com/o/r/pull/5'])
  expect(addLinks([], [text]).map(l => [l.kind, l.href])).toEqual([['PR', 'https://github.com/o/r/pull/5']])
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

test('a link said again moves to the front', () => {
  const one = addLinks([], ['https://github.com/o/r/issues/1 と https://docs.example.com/a', 'https://github.com/o/r/pull/2'])
  expect(one.map(l => l.label)).toEqual(['o/r#2', 'docs.example.com/a', 'o/r#1'])
  const two = addLinks(one, ['https://github.com/o/r/issues/1#issuecomment-9'])
  expect(two.map(l => l.label)).toEqual(['o/r#1', 'o/r#2', 'docs.example.com/a'])
})

test("opening the pane lists the history's links alone, dropping those it lacks", { options: { autoOpen: false } }, async ($, on) => {
  engine(on, () => [
    { role: 'user', text: 'https://github.com/o/r/issues/1 を直して', toolUses: [] },
    { role: 'assistant', text: 'https://github.com/o/r/issues/2 も見ました', toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  // Said live, but the history (after /compact, say) does not hold it.
  await $.turn.start({ text: 'https://old.example.com/gone も見て', turnId: 't1' })
  await $.turn.complete({ answer: 'ok', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://github.com/o/r/issues/2', 'https://github.com/o/r/issues/1'])
})

test('a link the history holds past the kept 40 does not come back on top as the pane opens', { options: { autoOpen: false } }, async ($, on) => {
  const many = Array.from({ length: 45 }, (_, i) => `https://github.com/o/r/issues/${i + 1}`).join(' ')
  engine(on, () => [
    { role: 'user', text: many, toolUses: [] },
    { role: 'assistant', text: '見ました', toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'https://github.com/o/r/issues/1 から', turnId: 't1' })
  await $.turn.complete({ answer: 'ok', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect((await listed($))[0]).toBe('https://github.com/o/r/issues/45')
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
  await $.turn.complete({
    answer: 'PR を作りました: https://github.com/o/r/pull/56',
    durationMs: 10,
    isAborted: false,
    turnId: 't1',
    reason: 'completed',
  } as never)
  await settle()

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /^リンク$/ })).toBeTruthy()
  const hrefs = (await ui.findAll({ type: 'Link' })).map(l => l.props.href)
  // Newest first: the PR the answer named, the page fetched, then the issue the history named.
  expect(hrefs).toEqual(['https://github.com/o/r/pull/56', 'https://docs.example.com/mods', 'https://github.com/o/r/issues/44'])
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

test("after /timeline reset the links are the history's alone", async ($, on) => {
  engine(on, () => [
    { role: 'user', text: 'https://github.com/o/r/issues/1 を直して', toolUses: [] },
    { role: 'assistant', text: '直しました', toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'https://old.example.com/gone も見て', turnId: 't1' })
  await $.turn.complete({ answer: 'ok', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toContain('https://old.example.com/gone')
  await $.command.run({ command: 'timeline', args: 'reset' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://github.com/o/r/issues/1'])
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
const TRACKED = '[{"number":3,"url":"https://github.com/o/r/issues/3"}]'
// `gh pr list --json url` as it prints: a read, not a PR this work made.
const PR_LIST =
  '[{"url":"https://github.com/masahirompp/skills/pull/59"},{"url":"https://github.com/masahirompp/skills/pull/58"},{"url":"https://github.com/masahirompp/skills/pull/57"}]\n'
const PR_ANSWER = 'PR を作りました: https://github.com/o/r/pull/56'

test("no tool's output is listed, a command's nor a search's; the PR Claude names in its answer is", async ($, on) => {
  engine(on, () => [])
  on('tool.call', (_, e) => {
    if (e.tool === 'Bash') return { text: 'https://github.com/o/r/pull/56\n', result: {} }
    if (e.tool === 'WebSearch') return { text: SEARCH, result: SEARCH_RESULT }
    if (e.tool === 'WebFetch') return { text: FETCHED, result: {} }
    if (e.tool.startsWith('mcp__')) return { text: TRACKED, result: {} }
    return { text: GREPPED, result: {} }
  })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await $.tool.call({ tool: 'Bash', command: 'gh pr create --fill', tool_use_id: 'b1' })
  await $.tool.call({ tool: 'WebSearch', query: 'ink flicker', mode: 'standard', tool_use_id: 's1' } as never)
  await $.tool.call({ tool: 'WebFetch', url: 'https://docs.example.com/x', prompt: 'read', tool_use_id: 'f1' })
  await $.tool.call({ tool: 'Grep', pattern: 'github', tool_use_id: 'g1' } as never)
  await $.tool.call({ tool: 'mcp__tracker__list', query: 'open', tool_use_id: 'm1' } as never)
  await $.turn.complete({ answer: '調べました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/x'])
  await $.turn.start({ text: '続けて', turnId: 't2' })
  await $.turn.complete({ answer: PR_ANSWER, durationMs: 10, isAborted: false, turnId: 't2', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://github.com/o/r/pull/56', 'https://docs.example.com/x'])
})

test("no output is listed when the history is read again; the answer's PR is", { options: { autoOpen: false } }, async ($, on) => {
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
        { tool_use_id: 'm1', tool: 'mcp__tracker__list', input: { query: 'open' }, text: TRACKED },
      ],
    },
    { role: 'assistant', text: PR_ANSWER, toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://github.com/o/r/pull/56', 'https://docs.example.com/x'])
})

const end = (reason: 'clear' | 'resume') => ({ reason, sessionId: 's', resume: { id: 's' } }) as never
const tick = () => new Promise<void>(r => setTimeout(r, 5))

/** Holds the first read of the links once `isArmed` is set, until `release`: a write still out as the conversation is swapped. */
function holdLinks(on: On): { isArmed: boolean; isHeld: boolean; release: () => void } {
  let release!: () => void
  const gate = new Promise<void>(r => (release = r))
  const h = { isArmed: false, isHeld: false, release: () => release() }
  on('state.get', async (_, e, next) => {
    if (h.isArmed && !h.isHeld && e.key === 'links') {
      h.isHeld = true
      await gate
    }
    return next(e)
  })
  on('session.end', (_, e) => ({ sessionId: (e as { sessionId: string }).sessionId }) as never)
  on('session.cwd', () => ({ value: '/' }))
  return h
}

async function untilHeld(h: { isHeld: boolean }): Promise<void> {
  for (let i = 0; i < 200 && !h.isHeld; i++) await tick()
  expect(h.isHeld).toBe(true)
}

for (const reason of ['clear', 'resume'] as const) {
  test(`a rescan still out as /${reason} comes lists none of the conversation before`, { options: { autoOpen: false } }, async ($, on) => {
    let history: readonly SessionMessage[] = [
      { role: 'user', text: 'https://github.com/o/r/issues/1 を直して', toolUses: [] },
      { role: 'assistant', text: '直しました', toolUses: [] },
    ]
    engine(on, () => history)
    const h = holdLinks(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    h.isArmed = true
    const opening = $.command.run({ command: 'timeline', args: '' } as never)
    await untilHeld(h)
    await $.session.end(end(reason))
    history = reason === 'clear' ? [{ role: 'user', text: '<command-name>/clear</command-name>', toolUses: [] }] : []
    await $.turn.start({ text: '新しい話', turnId: 't2' })
    h.release()
    await opening
    await settle()
    expect(await listed($)).toEqual([])
  })

  test(`a tool call's links still out as /${reason} comes are not listed in the next`, { options: { autoOpen: false } }, async ($, on) => {
    let history: readonly SessionMessage[] = []
    engine(on, () => history)
    const h = holdLinks(on)
    on('tool.call', () => ({ text: 'page', result: {} }))
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await $.command.run({ command: 'timeline', args: '' } as never)
    await $.turn.start({ text: 'ページを読んで', turnId: 't1' })
    h.isArmed = true
    // A URL argument: still listed, so the write is one the switch could catch out.
    const calling = $.tool.call({ tool: 'WebFetch', url: 'https://docs.example.com/mods', prompt: 'read', tool_use_id: 'f1' })
    await untilHeld(h)
    await $.session.end(end(reason))
    history = reason === 'clear' ? [{ role: 'user', text: '<command-name>/clear</command-name>', toolUses: [] }] : []
    await $.turn.start({ text: '新しい話', turnId: 't2' })
    h.release()
    await calling
    await settle()
    expect(await listed($)).toEqual([])
  })
}

test('the PRs a read-only command lists are not listed, live or read again', async ($, on) => {
  const history: SessionMessage[] = []
  engine(on, () => history)
  on('tool.call', () => ({ text: PR_LIST, result: {} }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'PR を見て', turnId: 't1' })
  await $.tool.call({ tool: 'Bash', command: 'gh pr list --state all --json url --limit 3', tool_use_id: 'b1' })
  await $.turn.complete({ answer: '見ました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual([])
  history.push(
    { role: 'user', text: 'PR を見て', toolUses: [] },
    {
      role: 'assistant',
      text: '',
      toolUses: [{ tool_use_id: 'b1', tool: 'Bash', input: { command: 'gh pr list --state all --json url --limit 3' }, text: PR_LIST }],
    },
    { role: 'assistant', text: '見ました', toolUses: [] },
  )
  await $.command.run({ command: 'timeline', args: 'reset' } as never)
  await settle()
  expect(await listed($)).toEqual([])
})

test('of a call\'s arguments, only one that is a URL and nothing more is listed; a list or an object is not looked into', () => {
  expect(
    callMentions('WebFetch', {
      url: ' https://docs.example.com/mods\n',
      prompt: 'https://docs.example.com/other を読んで',
      edits: [{ old_string: 'a', new_string: 'https://nested.example.com/x' }],
      meta: { url: 'https://nested.example.com/y' },
    }),
  ).toEqual(['https://docs.example.com/mods'])
  // What an Edit writes, though a URL alone, is the file's text.
  expect(callMentions('Edit', { file_path: '/w/README.md', old_string: 'https://old.example.com/a', new_string: 'https://new.example.com/b' })).toEqual([])
})

// A commit as Claude runs it: the trailer's session URL rides in the command.
const COMMIT =
  'git commit -m "$(cat <<\'EOF\'\nsession-timeline: 直す\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_013k9798cevtHJTL3NQNrLus\nEOF\n)"'
const PR_CREATE = 'gh pr create --title "x" --body "本文 https://github.com/o/r/issues/44 を直す"'
const AGENT = { description: 'review', prompt: 'https://github.com/o/r/pull/58 を見て' }
const FETCH = { url: 'https://docs.example.com/mods', prompt: 'read' }

test('a URL inside a command or a prompt is not listed as the call goes; a URL argument is', async ($, on) => {
  engine(on, () => [])
  on('tool.call', () => ({ text: 'ok', result: {} }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '続けて', turnId: 't1' })
  await $.tool.call({ tool: 'Bash', command: COMMIT, tool_use_id: 'b1' })
  await $.tool.call({ tool: 'Bash', command: PR_CREATE, tool_use_id: 'b2' })
  await $.tool.call({ tool: 'Agent', ...AGENT, tool_use_id: 'a1' } as never)
  await $.tool.call({ tool: 'WebFetch', ...FETCH, tool_use_id: 'f1' })
  await $.turn.complete({ answer: 'できました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/mods'])
})

test('a URL inside a command or a prompt is not listed when the history is read again', { options: { autoOpen: false } }, async ($, on) => {
  engine(on, () => [
    { role: 'user', text: '続けて', toolUses: [] },
    {
      role: 'assistant',
      text: '',
      toolUses: [
        { tool_use_id: 'b1', tool: 'Bash', input: { command: COMMIT }, text: 'ok' },
        { tool_use_id: 'b2', tool: 'Bash', input: { command: PR_CREATE }, text: 'ok' },
        { tool_use_id: 'a1', tool: 'Agent', input: AGENT, text: 'ok' },
        { tool_use_id: 'f1', tool: 'WebFetch', input: FETCH, text: 'page' },
      ],
    },
    { role: 'assistant', text: 'できました', toolUses: [] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await listed($)).toEqual(['https://docs.example.com/mods'])
})

test('a prompt said while the pane reads the history is kept, though the history read lacks it', { options: { autoOpen: false } }, async ($, on) => {
  engine(on, () => [
    { role: 'user', text: 'https://github.com/o/r/issues/1 を直して', toolUses: [] },
    { role: 'assistant', text: '直しました', toolUses: [] },
  ])
  // Held at the rescan's write, its read of the messages done.
  const h = holdLinks(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  h.isArmed = true
  const opening = $.command.run({ command: 'timeline', args: '' } as never)
  await untilHeld(h)
  await $.turn.start({ text: 'https://github.com/o/r/issues/9 も', turnId: 't1' })
  h.release()
  await opening
  await settle()
  expect(await listed($)).toEqual(['https://github.com/o/r/issues/9', 'https://github.com/o/r/issues/1'])
})

const TOKYO = 'https://ja.wikipedia.org/wiki/東京'
const TOKYO_HREF = 'https://ja.wikipedia.org/wiki/%E6%9D%B1%E4%BA%AC'

test('a URL argument holding Japanese is listed whole as the call goes, not cut as a sentence is', async ($, on) => {
  engine(on, () => [])
  on('tool.call', () => ({ text: 'page', result: {} }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: '調べて', turnId: 't1' })
  await $.tool.call({ tool: 'WebFetch', url: TOKYO, prompt: 'read', tool_use_id: 'f1' })
  await settle()
  expect(await listed($)).toEqual([TOKYO_HREF])
})

test('a URL argument holding Japanese is listed whole when the history is read again', { options: { autoOpen: false } }, async ($, on) => {
  engine(on, () => [
    { role: 'user', text: '調べて', toolUses: [] },
    { role: 'assistant', text: '', toolUses: [{ tool_use_id: 'f1', tool: 'WebFetch', input: { url: TOKYO, prompt: 'read' }, text: 'page' }] },
  ])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(await listed($)).toEqual([TOKYO_HREF])
})
