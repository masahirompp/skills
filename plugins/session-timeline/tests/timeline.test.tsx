import { expect, test } from 'claude-code/testing'

import type { Phase } from '../types'

import { SYSTEM, fold, kindOf, parseVerdict } from '../hooks/classify'
import { RECAP_SYSTEM, REGROUP_SYSTEM, groupsByKind, mergeSameKind, parseGroups, parseRecap, regroupPrompt } from '../hooks/group'
import { stretchesOf, timed, timesOf, transcriptPathOf } from '../hooks/backfill'
import { colorOf, durationOf, padCells } from '../hooks/view'

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

test('turns and a review become phases, each a row to press', async ($, on) => {
  let clock = Date.UTC(2026, 10, 17, 1, 0, 0)
  const asked: string[] = []
  // The classifier answers by what the stretch holds, as Haiku would.
  const verdicts = [
    { continues: false, label: '実装', note: '2ファイル変更', summary: 'timeline mod を実装' },
    { continues: false, label: 'レビュー 1回目', note: '指摘4件', summary: 'サブエージェントでレビュー' },
    { continues: false, label: '修正', note: '指摘4件を反映', summary: '指摘を直した' },
    { continues: true, label: '修正', note: '指摘4件を反映、テスト通過', summary: '指摘を直しテストを通した' },
  ]
  const regroups: string[] = []
  let markSide = false
  const recaps: string[] = []
  on('session.messages', () => ({
    value: [
      { role: 'user', text: 'timeline mod を作って、レビューして直して', toolUses: [] },
      { role: 'assistant', text: '4件の指摘を直しました', toolUses: [] },
    ],
  }))
  on('model.complete', (_, e) => {
    const u = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
    if (e.system === REGROUP_SYSTEM) {
      regroups.push(e.prompt)
      // Over the whole session: the review and the fix it led to read as one.
      const ranges = [
        { from: 1, to: 1, label: '実装', note: '2ファイル変更', summary: '' },
        { from: 2, to: 3, label: 'レビューと修正', note: '指摘4件→反映', summary: 'レビュー指摘を直した', side: markSide },
      ]
      return { value: { isAnswered: true, text: JSON.stringify(ranges), usage: u } }
    }
    if (e.system === RECAP_SYSTEM) {
      recaps.push(e.prompt)
      const r = { goal: 'timeline mod を作る', status: '実装とレビュー対応まで済んだ', next: '' }
      return { value: { isAnswered: true, text: JSON.stringify(r), usage: u } }
    }
    expect(e.system).toBe(SYSTEM)
    asked.push(e.prompt)
    return { value: { isAnswered: true, text: JSON.stringify(verdicts[asked.length - 1]), usage: u } }
  })
  on('clock.now', () => ({ value: (clock += 60_000) }))
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', (_, e) =>
    e.tool === 'Agent' ? { result: { content: 'Findings: 1. … 2. … 3. … 4. …' } } : { result: {} },
  )

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.turn.start({ text: 'timeline mod を作って、レビューして直して', turnId: 't1' })
  await $.tool.call({ tool: 'Write', file_path: '/m/register.tsx', content: 'x', tool_use_id: 'tu-write' })
  await $.tool.call({ tool: 'Edit', file_path: '/m/view.ts', old_string: 'a', new_string: 'b', tool_use_id: 'tu-edit' })
  // A review by a subagent closes the stretch before it.
  await $.tool.call({ tool: 'Agent', description: 'review', prompt: 'review it', subagent_type: 'claude', tool_use_id: 'tu-review' })
  await $.tool.call({ tool: 'Edit', file_path: '/m/view.ts', old_string: 'b', new_string: 'c', tool_use_id: 'tu-fix' })
  await $.turn.complete({ answer: '4件の指摘を直しました', durationMs: 10, isAborted: false, turnId: 't1', reason: 'completed' } as never)
  await settle()

  expect(asked.length).toBe(3)
  expect(asked[0]).toContain('Write /m/register.tsx')
  expect(asked[0]).not.toContain('Agent')
  expect(asked[1]).toContain('Findings')
  expect(asked[1]).not.toContain('Edit')
  // The earlier phases ride along, so the classifier can count rounds.
  expect(asked[2]).toContain('レビュー 1回目 [指摘4件]')

  // Regrouped after the last phase, with every fine phase numbered and the instruction that opened it.
  expect(regroups.at(-1)).toContain('3. ')
  expect(regroups.at(-1)).toContain('「timeline mod を作って、レビューして直して」')
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  // Two phases, and the "now" row at the bottom that takes you to the newest of the conversation.
  const keys = (await ui.findAll({ type: 'Button' })).map(b => b.key)
  expect(keys.length).toBe(3)
  expect(keys.at(-1)).toBe('now')
  expect(await ui.find({ type: 'Text', text: /^待機中$/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /^レビューと修正/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /指摘4件→反映/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /▸2/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /█/ })).toBeFalsy()
  expect(await ui.find({ type: 'Text', text: /失敗/ })).toBeFalsy()
  // The recap comes after the regroup, from the phases and the person's prompts.
  expect(recaps.length).toBe(1)
  expect(recaps[0]).toContain('レビューと修正')
  expect(recaps[0]).toContain('timeline mod を作って')
  expect(await ui.find({ type: 'Text', text: /^実装とレビュー対応まで済んだ$/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /脇道/ })).toBeFalsy()
  await ui.unmount()

  // A range the regroup calls a digression is drawn faint and marked in the timeline itself.
  markSide = true
  await $.turn.start({ text: 'ところで git の rebase って何？', turnId: 't2' })
  await $.turn.complete({ answer: '説明しました', durationMs: 10, isAborted: false, turnId: 't2', reason: 'completed' } as never)
  await settle()
  const ui2 = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui2.find({ type: 'Text', text: /^脇道: レビューと修正/ })).toBeTruthy()
  expect(await ui2.find({ type: 'Text', text: /^↳ $/ })).toBeTruthy()
  await ui2.unmount()
})

test('a continuing verdict extends the last phase', () => {
  const stretch = { start: 0, steps: [{ id: 'a', tool: 'Edit', brief: '', isError: true }], subSteps: 2 }
  const one = fold([], { ...stretch, end: 100 }, { continues: false, label: '実装', note: '', summary: 's' }, 'live')
  const two = fold(one, { ...stretch, start: 100, end: 300 }, { continues: true, label: '実装', note: '3ファイル', summary: '' }, 'live')
  expect(two.length).toBe(1)
  expect(two[0]).toMatchObject({ start: 0, end: 300, steps: 6, errors: 2, note: '3ファイル', summary: 's', anchor: 'a' })
})

test('the verdict is read out of a chatty reply, and junk is refused', () => {
  expect(parseVerdict('はい。\n{"continues": false, "label": "調査", "note": "", "summary": "x"}')?.label).toBe('調査')
  expect(parseVerdict('no json here')).toBeUndefined()
  expect(parseVerdict('{"label": ""}')).toBeUndefined()
})

test('drawing helpers', () => {
  expect(padCells('レビュー', 10)).toBe('レビュー  ')
  expect(durationOf(28_000)).toBe('28秒')
  expect(durationOf(18 * 60_000)).toBe('18分')
  expect(colorOf('レビュー 1回目')).toBe(colorOf('レビュー 2回目'))
})

const usage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }
const msg = (role: 'user' | 'assistant', text: string, toolUses: object[] = [], toolResults?: object[]) =>
  ({ role, text, toolUses, ...(toolResults ? { toolResults } : {}) }) as never

const HISTORY = [
  msg('user', 'バグを調べて'),
  msg('assistant', '', [{ tool_use_id: 'h1', tool: 'Grep', input: { pattern: 'bug' } }]),
  msg('user', '', [], [{ tool_use_id: 'h1', text: '', isError: false }]),
  msg('assistant', '', [{ tool_use_id: 'h2', tool: 'Agent', input: { description: 'review' }, result: 'Findings: 1. 2.' }]),
  msg('user', '', [], [{ tool_use_id: 'h2', text: '', isError: false }]),
  msg('assistant', '直しました'),
  msg('user', '次はこれ'),
  msg('assistant', '', [{ tool_use_id: 'seen', tool: 'Edit', input: { file_path: '/a' } }]),
]

const JSONL = [
  '{"type":"mode"}',
  '{"type":"assistant","timestamp":"2026-11-17T00:00:00.000Z","message":{"content":[{"type":"tool_use","id":"h1"}]}}',
  '{"type":"user","timestamp":"2026-11-17T00:00:28.000Z","message":{"content":[{"type":"tool_result","tool_use_id":"h1"}]}}',
  '{"type":"assistant","timestamp":"2026-11-17T00:01:00.000Z","message":{"content":[{"type":"tool_use","id":"h2"}]}}',
  '{"type":"user","timestamp":"2026-11-17T00:07:00.000Z","message":{"content":[{"type":"tool_result","tool_use_id":"h2"}]}}',
  'not json "tool_use',
].join('\n')

test('history is cut like the live recording, skipping what it saw', () => {
  const parts = stretchesOf(HISTORY, new Set(['seen']))
  expect(parts.map(p => p.steps.map(s => s.tool))).toEqual([['Grep'], ['Agent'], []])
  expect(parts[0]?.prompt).toBe('バグを調べて')
  expect(parts[1]?.steps[0]?.outcome).toContain('Findings')
  expect(parts[2]?.answer).toBe('直しました')
  // The turn whose tool calls were recorded live is left to the live phases.
  expect(parts.some(p => p.prompt === '次はこれ')).toBe(false)
})

test('times come from the transcript file, and a stretch without calls borrows the one before', () => {
  const times = timesOf(JSONL)
  expect(times.get('h1')).toEqual({ start: Date.parse('2026-11-17T00:00:00Z'), end: Date.parse('2026-11-17T00:00:28Z') })
  const parts = timed(stretchesOf(HISTORY, new Set(['seen'])), times, undefined)
  expect(parts.map(p => (p.end ?? 0) - (p.start ?? 0))).toEqual([28_000, 360_000, 0])
  expect(timed(stretchesOf(HISTORY, new Set()), new Map(), undefined)[0]?.start).toBeUndefined()
  expect(transcriptPathOf('/h/.claude', '/home/me/work/x.y', 'abc')).toBe('/h/.claude/projects/-home-me-work-x-y/abc.jsonl')
})

test('opening the pane fills in the history before the live phases', async ($, on) => {
  const verdicts = [
    { continues: false, label: '調査', note: '', summary: 'バグ調査' },
    { continues: false, label: 'レビュー 1回目', note: '指摘2件', summary: '' },
    { continues: false, label: '修正', note: '', summary: '' },
  ]
  let asked = 0
  on('model.complete', (_, e) =>
    e.system === REGROUP_SYSTEM || e.system === RECAP_SYSTEM
      ? { value: { isAnswered: false, reason: 'api-error', status: 529, error: 'overloaded', usage } as never }
      : { value: { isAnswered: true, text: JSON.stringify(verdicts[asked++]), usage } },
  )
  on('session.messages', () => ({ value: HISTORY.slice(0, 6) }))
  on('session.id', () => ({ value: 'abc' }))
  on('clock.now', () => ({ value: Date.parse('2026-11-17T01:00:00Z') }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/h' : undefined }) as never)
  const paths: string[] = []
  on('fs.read', (_, e) => {
    paths.push(e.path)
    return { value: JSONL } as never
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/w/p', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()

  expect(paths).toEqual(['/h/.claude/projects/-w-p/abc.jsonl'])
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /^調査/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /^28秒/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /^6分/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /過去分を判定中/ })).toBeFalsy()
  await ui.unmount()

  // Opening it again does not classify the history twice.
  await $.command.run({ command: 'timeline', args: '' } as never)
  await settle()
  expect(asked).toBe(3)
})

const P = (id: string, label: string): Phase => ({ id, label, note: '', summary: '', steps: 1, errors: 0, toolIds: [] })

test('a kind is a label without its round', () => {
  expect(kindOf('レビュー 2回目')).toBe('レビュー')
  expect(kindOf('レビュー（第3回）')).toBe('レビュー')
  expect(kindOf('修正#2')).toBe('修正')
  expect(kindOf('PR作成')).toBe('PR作成')
})

test('a fine phase of the same kind folds into the last', () => {
  const s = { start: 0, end: 10, steps: [], subSteps: 0 }
  const one = fold([], s, { continues: false, label: 'レビュー 1回目', note: '', summary: '' }, 'live')
  const two = fold(one, s, { continues: false, label: 'レビュー 2回目', note: '指摘1件', summary: '' }, 'live')
  expect(two.map(p => [p.label, p.note])).toEqual([['レビュー 1回目', '指摘1件']])
})

test('ranges are mended into a cover of every phase', () => {
  const ps = ['a', 'b', 'c', 'd', 'e'].map(id => P(id, id))
  // A gap (3), an overlap (4 in both) and a range past the end.
  const text = 'ok: [{"from":1,"to":2,"label":"調査"},{"from":4,"to":9,"label":"実装"},{"from":3,"to":4,"label":"設計"}]'
  expect(parseGroups(text, ps)?.map(g => [g.label, g.phaseIds.join('')])).toEqual([
    ['調査', 'ab'],
    ['設計', 'c'],
    ['実装', 'de'],
  ])
  expect(parseGroups('none', ps)).toBeUndefined()
  expect(parseGroups('[{"from":1}]', ps)).toBeUndefined()
})

test('neighbours of one kind merge, and the model is told the last cut', () => {
  const ps = [P('a', '実装'), P('b', 'レビュー 1回目'), P('c', 'レビュー 2回目'), P('d', '修正')]
  expect(groupsByKind(ps).map(g => g.phaseIds.join(''))).toEqual(['a', 'bc', 'd'])
  const merged = mergeSameKind([
    { id: 'g-a', label: '実装', note: '', summary: '', phaseIds: ['a'] },
    { id: 'g-b', label: '実装 2回目', note: 'n', summary: '', phaseIds: ['b'] },
  ])
  expect(merged).toEqual([{ id: 'g-a', label: '実装', note: 'n', summary: '', phaseIds: ['a', 'b'] }])
  const prompt = regroupPrompt(ps, [{ id: 'g-a', label: '実装', note: '', summary: '', phaseIds: ['a', 'b'] }])
  expect(prompt).toContain('## 前回の区切り\n1-2 実装')
})

test('a side range is marked and never merged into the main subject', () => {
  const ps = [P('a', '実装'), P('b', '実装'), P('c', '実装')]
  const text = '[{"from":1,"to":1,"label":"実装"},{"from":2,"to":2,"label":"実装","side":true},{"from":3,"to":3,"label":"実装"}]'
  const gs = mergeSameKind(parseGroups(text, ps) ?? [])
  expect(gs.map(g => [g.phaseIds.join(''), g.isSide === true])).toEqual([
    ['a', false],
    ['b', true],
    ['c', false],
  ])
})

test('phases on different topics do not fold together', () => {
  const s = { start: 0, end: 10, steps: [], subSteps: 0 }
  const one = fold([], s, { continues: false, label: '調査', note: '', summary: '', topic: 'timeline mod' }, 'live')
  const two = fold(one, s, { continues: true, label: '調査', note: '', summary: '', topic: 'git' }, 'live')
  expect(two.map(p => p.topic)).toEqual(['timeline mod', 'git'])
})

test('a recap without a goal is dropped', () => {
  expect(parseRecap('{"goal":"","status":"x"}')).toBeNull()
  expect(parseRecap('{"goal":"g","status":"s","next":"n","sides":["a",3]}')).toEqual({ goal: 'g', status: 's', next: 'n', sides: ['a'] })
})

test('the pane opens as the session starts, by default', async ($, on) => {
  const opened: string[] = []
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.messages', () => ({ value: [] }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await settle()
  expect(opened).toEqual(['session-timeline'])
})

test('with autoOpen off, the pane waits for /timeline', { options: { autoOpen: false } }, async ($, on) => {
  const opened: string[] = []
  on('ui.open', (_, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('command.register', () => ({ value: { command: 'timeline' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.messages', () => ({ value: [] }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await settle()
  expect(opened).toEqual([])
  await $.command.run({ command: 'timeline', args: '' } as never)
  expect(opened).toEqual(['session-timeline'])
})
