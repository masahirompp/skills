import { expect, test } from 'claude-code/testing'

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
