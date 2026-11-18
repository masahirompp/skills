#!/usr/bin/env python3
"""run.py が残した記録(records/*.jsonl)から、1回分の数字を集める。別セッションは起動しない。

    analyze.py <結果のディレクトリ>

書き出すもの:
  result.json   数字と、機械的な照合の結果。どの行で確かめたかを `at`(記録のファイルと行番号)で持つ
  summary.md    人が読む要約
  timeline.md   親のセッションの流れ(1操作1行)
  agents.md     親が起動したサブエージェント(security-review のサブタスク、修正役)への依頼文と、返ったものの先頭
  bash.md       親が流したコマンドのうち、再現、テスト、push、PR 本文の書き換えに関わるものと、その出力

数字は、記録の中の操作と出力から拾う。別セッションの報告(最後の出力、PR 本文の経緯、自己申告)は、
「報告」として分けて載せ、数字の根拠にしない。機械的な照合は見落としも誤検知もあるので、
`at` の行を読んで確かめる。
"""
import glob
import json
import os
import re
import sys

REVIEW_SKILLS = ("code-review", "security-review")
LOOP_SKILL = "review-loop"


def ts(e):
    return e.get("timestamp") or ""


def secs(a, b):
    import datetime
    if not a or not b:
        return None
    f = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return round((f(b) - f(a)).total_seconds())


def load(run_dir):
    """親のセッションの記録を、続きの写しをまたいで1本にする(写しは履歴を含むので、uuid で重なりを除く)。"""
    events, seen, costs = [], set(), []
    for path in sorted(glob.glob(os.path.join(run_dir, "records", "*.jsonl"))):
        name = os.path.basename(path)
        last_cost = None
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") == "cost-state":
                    last_cost = e
                    continue
                u = e.get("uuid")
                if e.get("isSidechain") or (u and u in seen):
                    continue
                if u:
                    seen.add(u)
                e["_at"] = f"{name}:{n}"
                events.append(e)
        if last_cost:
            costs.append(last_cost)
    return events, costs


def text_of(content):
    if isinstance(content, str):
        return content
    out = []
    for x in content or []:
        if isinstance(x, dict):
            if x.get("type") == "text":
                out.append(x.get("text", ""))
            elif x.get("type") == "tool_result":
                out.append(text_of(x.get("content")))
    return "\n".join(out)


def exit_code(result_text, is_error):
    m = re.match(r"\s*Exit code (\d+)", result_text or "")
    if m:
        return int(m.group(1))
    return 1 if is_error else 0


def walk(events):
    """記録を、操作(tool_use と、その結果)、発言、通知に分ける。"""
    calls, by_id, items = [], {}, []
    for e in events:
        t = e.get("type")
        m = e.get("message") or {}
        c = m.get("content")
        if t == "assistant":
            for x in c or []:
                if x.get("type") == "tool_use":
                    call = {"kind": "call", "name": x["name"], "input": x.get("input") or {}, "id": x["id"],
                            "ts": ts(e), "at": e["_at"], "msg": m.get("id"), "usage": m.get("usage")}
                    calls.append(call)
                    by_id[x["id"]] = call
                    items.append(call)
                elif x.get("type") == "text" and x.get("text", "").strip():
                    items.append({"kind": "say", "text": x["text"], "ts": ts(e), "at": e["_at"], "usage": m.get("usage")})
        elif t == "user":
            if isinstance(c, str):
                if c.lstrip().startswith("<task-notification>"):
                    tid = re.search(r"<tool-use-id>(.*?)</tool-use-id>", c)
                    note = {"kind": "notify", "text": c, "ts": ts(e), "at": e["_at"], "tool_use_id": tid and tid.group(1)}
                    items.append(note)
                    call = by_id.get(note["tool_use_id"])
                    if call is not None and "notified" not in call:
                        call["notified"] = note
                elif not c.lstrip().startswith("<"):
                    items.append({"kind": "prompt", "text": c, "ts": ts(e), "at": e["_at"]})
                else:
                    items.append({"kind": "inject", "text": c, "ts": ts(e), "at": e["_at"]})
                continue
            for x in c or []:
                if x.get("type") == "tool_result":
                    call = by_id.get(x.get("tool_use_id"))
                    if call is not None:
                        call["result"] = text_of(x.get("content"))
                        call["is_error"] = bool(x.get("is_error"))
                        call["result_ts"] = ts(e)
                        call["result_at"] = e["_at"]
                elif x.get("type") == "text":
                    items.append({"kind": "inject", "text": x.get("text", ""), "ts": ts(e), "at": e["_at"]})
    return calls, items


def skill_name(call):
    return str(call["input"].get("skill", ""))


def returned(call):
    """Skill の返り方。"""
    r = call.get("result") or ""
    if "running in the background" in r:
        return "background"
    if "completed (forked execution)" in r:
        return "inline-fork"
    if r.startswith("Launching skill"):
        return "loaded-into-context"
    return "error" if call.get("is_error") else "other"


def done_ts(call):
    """呼び出しの結果が親に届いた時刻(バックグラウンドなら、完了の通知)。"""
    if call.get("notified"):
        return call["notified"]["ts"]
    return call.get("result_ts")


def usage_tokens(text):
    m = re.search(r"<subagent_tokens>(\d+)</subagent_tokens>", text or "")
    return int(m.group(1)) if m else None


def context_size(usage):
    if not usage:
        return None
    return (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0)


def analyze(run_dir):
    meta = json.load(open(os.path.join(run_dir, "meta.json"), encoding="utf-8"))
    drive = json.load(open(os.path.join(run_dir, "drive.json"), encoding="utf-8")) if os.path.exists(os.path.join(run_dir, "drive.json")) else {}
    events, costs = load(run_dir)
    calls, items = walk(events)
    workdir = meta.get("workdir", "")
    pr = str(meta.get("pr", ""))

    # ---- スキルとして呼ばれたか ----
    loop_calls = [c for c in calls if c["name"] == "Skill" and skill_name(c).endswith(LOOP_SKILL)]
    read_skill_md = [c for c in calls if c["name"] == "Read" and "review-loop/SKILL.md" in str(c["input"].get("file_path", ""))]

    # ---- 反復: レビュー役の Skill の呼び出しを、同じ応答(msg)ごとにまとめる ----
    reviews = [c for c in calls if c["name"] == "Skill" and skill_name(c) in REVIEW_SKILLS]
    groups = []
    for c in reviews:
        if groups and (c["msg"] == groups[-1][-1]["msg"] or (secs(groups[-1][0]["ts"], c["ts"]) or 0) < 120):
            groups[-1].append(c)
        else:
            groups.append([c])
    agent_calls = [c for c in calls if c["name"] in ("Agent", "Task")]
    bash = [c for c in calls if c["name"] == "Bash"]

    def is_fixer(c):
        p = str(c["input"].get("prompt", ""))
        return "/before" in p and "/work" in p

    iterations = []
    for i, g in enumerate(groups):
        start = g[0]["ts"]
        end = groups[i + 1][0]["ts"] if i + 1 < len(groups) else "9"
        inside = lambda c: start <= c["ts"] < end
        it_agents = [c for c in agent_calls if inside(c)]
        fixers = [c for c in it_agents if is_fixer(c)]
        sec_tasks = [c for c in it_agents if not is_fixer(c)]
        # レビューの終わり: レビュー役の結果と、修正役でないサブタスクの結果のうち、最後に届いたもの
        ends = [done_ts(c) for c in g + sec_tasks if done_ts(c)]
        review_end = max(ends) if ends else None
        pushes = [c for c in bash if inside(c) and re.search(r"\bgit\b[^|;&]*\bpush\b", c["input"].get("command", ""))]
        fix_start = fixers[0]["ts"] if fixers else None
        fix_end = max([done_ts(c) for c in fixers if done_ts(c)], default=None)
        same_turn = len({c["msg"] for c in g}) == 1
        iterations.append({
            "n": i + 1,
            "review": {
                "start": start, "end": review_end, "seconds": secs(start, review_end),
                "same_turn": same_turn, "at": g[0]["at"],
                "skills": [{"skill": skill_name(c), "args": c["input"].get("args", ""), "returned": returned(c),
                            "seconds": secs(c["ts"], done_ts(c)), "tokens": usage_tokens((c.get("notified") or {}).get("text")),
                            "at": c["at"], "result_at": (c.get("notified") or {}).get("at") or c.get("result_at"),
                            "result_head": ((c.get("notified") or {}).get("text") or c.get("result") or "")[:300]} for c in g],
                "subtasks": [{"description": c["input"].get("description"), "prompt_chars": len(str(c["input"].get("prompt", ""))),
                              "seconds": secs(c["ts"], done_ts(c)), "at": c["at"]} for c in sec_tasks],
            },
            "select_seconds": secs(review_end, fix_start) if fix_start else None,
            "fixers": [{"description": c["input"].get("description"), "seconds": secs(c["ts"], done_ts(c)),
                        "background": bool(c["input"].get("run_in_background")) or "notified" in c,
                        "tokens": usage_tokens((c.get("notified") or {}).get("text") or c.get("result")),
                        "mentions_diagnosing_bugs": "diagnosing-bugs" in str(c["input"].get("prompt", "")),
                        "prompt_chars": len(str(c["input"].get("prompt", ""))), "at": c["at"]} for c in fixers],
            "fix_seconds": secs(fix_start, fix_end),
            "verify_seconds": secs(fix_end, pushes[-1]["ts"]) if fix_end and pushes and pushes[-1]["ts"] > fix_end else None,
            "pushes": [{"command": c["input"]["command"][:200], "exit": exit_code(c.get("result"), c.get("is_error")), "at": c["at"]} for c in pushes],
        })

    # ---- 再現: 親が、修正前の写しと作業ツリーに流したコマンド ----
    tmp_roots = set()
    for c in bash:
        for m in re.finditer(r"(/(?:private/)?(?:var/folders|tmp)/[\w./-]*?tmp\.[A-Za-z0-9]+)", (c.get("result") or "") + " " + c["input"].get("command", "")):
            tmp_roots.add(m.group(1))
    fixer_done = min([done_ts(c) for c in agent_calls if is_fixer(c) and done_ts(c)], default=None)
    setup = re.compile(r"^\s*(mktemp|mkdir|git archive|tar )")
    repro_cmds = []
    for c in bash:
        cmd = c["input"].get("command", "")
        touches = "/before" in cmd or any(r in cmd for r in tmp_roots)
        if not touches or all(setup.match(part) for part in re.split(r"\s*(?:&&|;|\n)\s*", cmd) if part.strip()):
            continue
        out = c.get("result") or ""
        codes = re.findall(r"(?im)^(.*?(?:before|修正前|wt|worktree|after|修正後|作業ツリー|rc|exit|終了コード)[^\n]*?)[:=]\s*(\d+)\s*$", out)
        repro_cmds.append({"at": c["at"], "ts": c["ts"], "after_fixer": bool(fixer_done and c["ts"] > fixer_done),
                           "command": cmd, "exit": exit_code(out, c.get("is_error")),
                           "codes_in_output": [f"{a.strip()}={b}" for a, b in codes][:20], "output_head": out[:1500]})

    # ---- 確認の操作(手順1の1と4、手順4) ----
    def has(c, pat):
        return re.search(pat, c["input"].get("command", "")) is not None

    checks = []
    for it in iterations:
        g_start, r_end = it["review"]["start"], it["review"]["end"] or "9"
        nxt = iterations[it["n"]]["review"]["start"] if it["n"] < len(iterations) else "9"
        prev = iterations[it["n"] - 2]["review"]["start"] if it["n"] > 1 else ""
        before = [c for c in bash if prev <= c["ts"] <= g_start]
        after = [c for c in bash if r_end <= c["ts"] < nxt]
        checks.append({
            "iteration": it["n"],
            "status_before_review": [c["at"] for c in before if has(c, r"git status")][-1:],
            "pr_head_before_review": [c["at"] for c in before if has(c, r"gh pr view")][-1:],
            "status_after_review": [c["at"] for c in after if has(c, r"git status")][:1],
            "head_after_review": [c["at"] for c in after if has(c, r"git (rev-parse|log)")][:1],
            "tests_after_fix": [c["at"] for c in after if has(c, r"test\.py|pytest|unittest|npm test|pnpm test")][:3],
            "pr_body_edit": [c["at"] for c in after if has(c, r"gh pr edit|gh api[^\n]*pulls")][:3],
        })

    # ---- 作業ディレクトリの外への参照(機械的な照合。誤検知がある) ----
    outside = []
    for c in calls:
        blob = json.dumps(c["input"], ensure_ascii=False)
        hits = set(re.findall(r"(?<![\w/.-])masahirompp/(?!rlbench-)[\w.-]+", blob))  # GitHub の、題材でないリポジトリ
        hits |= set(re.findall(r"/Users/[\w.-]+/(?:ghq|\.claude/(?:projects|jobs))[\w./-]*", blob))
        hits = {h for h in hits if workdir not in h}
        if hits:
            outside.append({"at": c["at"], "tool": c["name"], "hits": sorted(hits)[:5], "input": blob[:300]})

    # ---- 文脈の大きさ、費用 ----
    # 終了後の自己申告のターンは、ループの外なので数えない
    loop_items = items
    if drive.get("debrief") is not None:
        last_prompt = max((i for i, x in enumerate(items) if x["kind"] == "prompt"), default=len(items))
        loop_items = items[:last_prompt]
    sizes = [(context_size(x.get("usage")), x["at"]) for x in loop_items if x.get("usage")]
    sizes = [s for s in sizes if s[0]]
    model_usage, total_cost, api_ms = {}, 0.0, 0
    for c in costs:
        total_cost += c.get("totalCostUSD") or 0
        api_ms += c.get("totalAPIDuration") or 0
        for mname, u in (c.get("modelUsage") or {}).items():
            agg = model_usage.setdefault(mname, {})
            for k, v in u.items():
                if isinstance(v, (int, float)):
                    agg[k] = agg.get(k, 0) + v

    prompts = [x for x in items if x["kind"] == "prompt"]
    first, last = (events[0], events[-1]) if events else ({}, {})
    all_ts = [ts(e) for e in events if ts(e)]

    # ---- 報告(別セッションが書いたもの。数字の根拠にしない) ----
    body_path = os.path.join(run_dir, "pr-body.md")
    body = open(body_path, encoding="utf-8").read() if os.path.exists(body_path) else ""
    hist = body.split("## レビューループの経緯", 1)[1] if "## レビューループの経緯" in body else ""
    details = "\n".join(re.findall(r"<details>.*?</details>", hist, flags=re.S))
    main_hist = re.sub(r"<details>.*?</details>", "", hist, flags=re.S)
    reported = {
        "iterations": len(re.findall(r"(?m)^### 反復", hist)),
        "fixed": len(re.findall(r"(?m)^- 直した:", main_hist)),
        "not_fixed": len(re.findall(r"(?m)^- 直さなかった:", main_hist)),
        "not_fixed_did_not_occur": len(re.findall(r"(?m)^- 直さなかった:.*起きなかった", main_hist)),
        "not_fixed_no_repro": len(re.findall(r"(?m)^- 直さなかった:.*再現を作れなかった", main_hist)),
        "pending": len(re.findall(r"(?m)^- 未決:", main_hist)),
        "not_target": len(re.findall(r"(?m)^- ", details)),
    }

    result = {
        "case": meta.get("case"), "outcome": meta.get("outcome"), "plugin": meta.get("plugin"), "launch": meta.get("launch"),
        "skill_invocation": {"via_skill_tool": [c["at"] for c in loop_calls], "read_skill_md_by_path": [c["at"] for c in read_skill_md]},
        "wall_seconds": meta.get("wall_seconds"), "session_seconds": secs(min(all_ts), max(all_ts)) if all_ts else None,
        "cost_usd": round(total_cost, 4), "api_seconds": round(api_ms / 1000), "model_usage": model_usage,
        "iterations": iterations, "checks": checks,
        "questions": [{"sent": t.get("sent", "")[:200], "decision": t.get("decision"), "rule": t.get("rule"),
                       "output_head": t.get("output", "")[:600]} for t in drive.get("turns", [])],
        "asked_for_judgement": sum(1 for t in drive.get("turns", []) if t.get("decision") == "reply"),
        "repro_commands": repro_cmds,
        "commits_added": [c for c in meta.get("commits", [])][1:] if meta.get("commits") else [],
        "context_tokens": {"at_end": sizes[-1] if sizes else None, "max": max(sizes) if sizes else None},
        "outside_access": outside,
        "reported": {"pr_body_history": reported, "debrief": drive.get("debrief")},
        "prompts": [{"at": p["at"], "text": p["text"][:200]} for p in prompts],
    }
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    write_timeline(run_dir, items)
    write_agents(run_dir, agent_calls, is_fixer)
    write_bash(run_dir, repro_cmds, bash)
    write_summary(run_dir, meta, result)
    return result


def short(s, n=200):
    return re.sub(r"\s+", " ", str(s))[:n]


def write_timeline(run_dir, items):
    with open(os.path.join(run_dir, "timeline.md"), "w", encoding="utf-8") as f:
        for x in items:
            t = x["ts"][11:19]
            if x["kind"] == "call":
                inp = x["input"]
                arg = inp.get("command") or inp.get("description") or inp.get("file_path") or json.dumps(inp, ensure_ascii=False)
                rc = ""
                if "result" in x:
                    rc = f" → exit {exit_code(x['result'], x.get('is_error'))}" if x["name"] == "Bash" else f" → {short(x['result'], 80)}"
                f.write(f"{t} {x['at']} {x['name']}: {short(arg, 240)}{rc}\n")
            elif x["kind"] == "say":
                f.write(f"{t} {x['at']} 発言: {short(x['text'], 300)}\n")
            elif x["kind"] == "prompt":
                f.write(f"{t} {x['at']} 利用者: {short(x['text'], 300)}\n")
            elif x["kind"] == "notify":
                f.write(f"{t} {x['at']} 完了の通知: {short(re.sub(r'<output-file>.*?</output-file>|<note>.*?</note>', '', x['text'], flags=re.S), 300)}\n")


def write_agents(run_dir, agent_calls, is_fixer):
    with open(os.path.join(run_dir, "agents.md"), "w", encoding="utf-8") as f:
        for c in agent_calls:
            role = "修正役" if is_fixer(c) else "サブタスク"
            inp = c["input"]
            f.write(f"## {role}: {inp.get('description')}({c['at']}、{c['ts'][11:19]})\n\n")
            f.write(f"- subagent_type: {inp.get('subagent_type')}、run_in_background: {inp.get('run_in_background')}、依頼文 {len(str(inp.get('prompt', '')))} 文字\n\n")
            f.write("### 依頼文\n\n````\n" + str(inp.get("prompt", "")) + "\n````\n\n")
            back = (c.get("notified") or {}).get("text") or c.get("result") or ""
            f.write("### 返ったもの(先頭)\n\n````\n" + back[:3000] + "\n````\n\n")


def write_bash(run_dir, repro_cmds, bash):
    with open(os.path.join(run_dir, "bash.md"), "w", encoding="utf-8") as f:
        f.write("# 親が、修正前の写しや一時ディレクトリに触れたコマンド\n\n")
        for r in repro_cmds:
            f.write(f"## {r['at']}({r['ts'][11:19]}、修正役のあと: {r['after_fixer']}、終了コード {r['exit']})\n\n````\n{r['command']}\n````\n\n出力:\n\n````\n{r['output_head']}\n````\n\n")
        f.write("# push と、PR 本文の書き換え\n\n")
        for c in bash:
            cmd = c["input"].get("command", "")
            if re.search(r"git\b[^|;&\n]*\bpush\b|gh pr edit|gh api[^\n]*pulls", cmd):
                f.write(f"## {c['at']}({c['ts'][11:19]}、終了コード {exit_code(c.get('result'), c.get('is_error'))})\n\n````\n{cmd[:1500]}\n````\n\n出力:\n\n````\n{(c.get('result') or '')[:600]}\n````\n\n")


def write_summary(run_dir, meta, r):
    def mmss(s):
        return "—" if s is None else f"{s // 60}:{s % 60:02d}"

    L = []
    L.append(f"# {r['case']}({meta.get('started')})\n")
    L.append(f"- 見込み: {meta.get('expect')}")
    L.append(f"- 終わり方: {r['outcome']}。判断を仰いだ回数(答えて続けた回数): {r['asked_for_judgement']}")
    p = r.get("plugin") or {}
    L.append(f"- プラグイン: {p.get('mode')}(導入済みの版 {p.get('installed_version')}、読ませた SKILL.md の sha256 {p.get('used_skill_sha256')}、リポジトリの SKILL.md {p.get('repo_skill_sha256')})")
    L.append(f"- 起動: `{r.get('launch')}`、{meta.get('claude_version')}")
    inv = r["skill_invocation"]
    L.append(f"- スキルとして呼ばれたか: Skill ツールで {len(inv['via_skill_tool'])} 回({', '.join(inv['via_skill_tool']) or '無い'})。SKILL.md をパスで読んだ: {len(inv['read_skill_md_by_path'])} 回")
    L.append(f"- 所要: {mmss(r['wall_seconds'])}(起動から終了まで。答えるまでの待ちと自己申告を含む)。費用: ${r['cost_usd']}(cost-state の合計。自己申告のターンを含む)")
    ce = r["context_tokens"]
    L.append(f"- 親の文脈: 終了時 {ce['at_end'][0] if ce['at_end'] else '—'} トークン({ce['at_end'][1] if ce['at_end'] else ''})、最大 {ce['max'][0] if ce['max'] else '—'}({ce['max'][1] if ce['max'] else ''})")
    L.append(f"- 足されたコミット: {len(r['commits_added'])}({', '.join(c['sha'] for c in r['commits_added'])})\n")
    L.append("## 反復\n")
    L.append("| 反復 | レビュー | 同じ応答で呼んだか | レビュー役(返り方、所要) | サブタスク | 対象を選ぶ | 修正役 | 親の確かめ(修正役の返りから push まで) | push |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for it in r["iterations"]:
        rv = it["review"]
        sk = "<br>".join(f"{s['skill']} `{s['args']}`: {s['returned']}、{mmss(s['seconds'])}({s['at']})" for s in rv["skills"])
        st = "<br>".join(f"{s['description']}({s['prompt_chars']} 文字、{mmss(s['seconds'])})" for s in rv["subtasks"]) or "無い"
        fx = "<br>".join(f"{mmss(x['seconds'])}({x['at']}、依頼文 {x['prompt_chars']} 文字)" for x in it["fixers"]) or "無い"
        ps = "<br>".join(f"exit {x['exit']}({x['at']})" for x in it["pushes"]) or "無い"
        L.append(f"| {it['n']} | {mmss(rv['seconds'])} | {'はい' if rv['same_turn'] else 'いいえ'} | {sk} | {st} | {mmss(it['select_seconds'])} | {fx} | {mmss(it['verify_seconds'])} | {ps} |")
    L.append("\n## 確認の操作(記録の行。空は、見つからなかった)\n")
    L.append("| 反復 | レビュー前の git status | レビュー前の gh pr view | レビュー後の git status | レビュー後の HEAD | 修正後のテスト | PR 本文の書き換え |")
    L.append("|---|---|---|---|---|---|---|")
    for c in r["checks"]:
        g = lambda k: ", ".join(c[k]) or "—"
        L.append(f"| {c['iteration']} | {g('status_before_review')} | {g('pr_head_before_review')} | {g('status_after_review')} | {g('head_after_review')} | {g('tests_after_fix')} | {g('pr_body_edit')} |")
    L.append("\n## 親が流した再現(bash.md に全文)\n")
    for x in r["repro_commands"]:
        L.append(f"- {x['at']}(修正役のあと: {x['after_fixer']}): 終了コード {x['exit']}、出力の中の数字 {x['codes_in_output'] or '無い'} — `{short(x['command'], 160)}`")
    if not r["repro_commands"]:
        L.append("- 無い")
    L.append("\n## 判断を仰いだやりとり\n")
    for q in r["questions"]:
        L.append(f"- 渡した文: {short(q['sent'], 100)} → 判定: {q['decision']}({q.get('rule') or ''})\n  - 最後の出力(先頭): {short(q['output_head'], 400)}")
    L.append("\n## 作業ディレクトリの外への参照(機械的な照合)\n")
    for o in r["outside_access"][:30]:
        L.append(f"- {o['at']} {o['tool']}: {o['hits']} — `{short(o['input'], 160)}`")
    if not r["outside_access"]:
        L.append("- 無い")
    rp = r["reported"]["pr_body_history"]
    L.append("\n## 報告(別セッションが書いたもの。数字の根拠にしない)\n")
    L.append(f"- PR 本文の経緯: 反復 {rp['iterations']}、直した {rp['fixed']}、直さなかった {rp['not_fixed']}(起きなかった {rp['not_fixed_did_not_occur']}、再現を作れなかった {rp['not_fixed_no_repro']})、未決 {rp['pending']}、対象でない指摘 {rp['not_target']}")
    L.append(f"- 自己申告(終了後に尋ねた):\n\n{r['reported']['debrief'] or '(無い)'}\n")
    with open(os.path.join(run_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    res = analyze(sys.argv[1])
    print(open(os.path.join(sys.argv[1], "summary.md"), encoding="utf-8").read())
