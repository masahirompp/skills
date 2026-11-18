#!/usr/bin/env python3
"""review-loop を、本番と同じ呼び方(導入済みのプラグインのスキル)で、通しで1回まわして記録する。

    run.py run <題材> [--keep] [--plugin-dir DIR] [--model M] [--max-minutes N] [--work-root DIR] [--slot s1]
    run.py analyze <結果のディレクトリ>          集計だけをやり直す(別セッションは起動しない)

run は、次を順に行う。
  1. 検証用のリポジトリ(bench/cases/<題材>/github.json)に、題材の head から、試し用のブランチ(e2e-<時刻>)と PR を作る。
     PR の本文は、題材の PR の本文を写す。題材の PR と、そのブランチには書き込まない
  2. リポジトリを <work-root>/<枠> に取り出し、PR のブランチの worktree(<枠>/.claude/worktrees/pr)を作って、
     その中で `claude --bg` を起動して、依頼文を渡す
  3. 別セッションのターンが終わるたびに、最後の出力を cases.json の答え方に照らし、答えて続ける(`--resume --bg`)か、終える
  4. 終わったら、手順から外れた箇所を別セッションに尋ね(自己申告)、セッションを止めて、記録を結果のディレクトリに写す
  5. analyze.py で集計する
  6. 試し用の PR を閉じ、ブランチと取り出した写しを消す(--keep で残す)

結果は <work-root>/runs/<題材>-<時刻>/ に置く(リポジトリの外。コミットしない)。

別セッションを実際に起動するので、費用がかかる(1回 3〜7 ドルほど)。取り出す先の枠(既定は ~/rlbench-e2e/s1)は、
あらかじめ信頼済みにしておく(そこで一度 `claude` を起動して、信頼のダイアログで承認する)。`--bg` は、信頼済みの
ディレクトリでしか起動できず、git リポジトリには、親のディレクトリの信頼が引き継がれない。そのため、取り出す先を
実行ごとに変えず、固定の枠を使い回す。並行に回すときは、枠を分ける(--slot s2)。
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(os.path.dirname(HERE), "bench")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PLUGIN_ID = "masahirompp-skills@masahirompp"
BRANCH_PREFIX = "e2e-"
REPO_PREFIX = "rlbench-"
STRIP_ENV = ("CLAUDE_JOB_DIR", "CLAUDE_CODE_SESSION_KIND", "CLAUDE_CODE_SESSION_ID")
POLL = 15
sys.dont_write_bytecode = True


def sh(args, cwd=None, input=None, check=True, env=None):
    r = subprocess.run(args, cwd=cwd, input=input, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:5])} が失敗した(終了コード {r.returncode}): {r.stderr.strip()[-800:]}")
    return r.stdout


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def child_env():
    return {k: v for k, v in os.environ.items() if k not in STRIP_ENV}


def load_config(case_id):
    with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
        conf = json.load(f)
    if case_id not in conf["cases"]:
        raise SystemExit(f"cases.json に {case_id} が無い")
    return {**conf["defaults"], **conf["cases"][case_id]}


def plugin_info(plugin_dir):
    """どの版の SKILL.md を読ませるかを記録する。"""
    def digest(path):
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]

    installed = [p for p in json.loads(sh(["claude", "plugin", "list", "--json"])) if p["id"] == PLUGIN_ID and p.get("enabled")]
    info = {"mode": "plugin-dir" if plugin_dir else "installed",
            "repo_head": sh(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).strip(),
            "repo_skill_sha256": digest(os.path.join(REPO_ROOT, "skills", "review-loop", "SKILL.md"))}
    if installed:
        p = installed[0]
        info["installed_version"] = p["version"]
        info["installed_skill_sha256"] = digest(os.path.join(p["installPath"], "skills", "review-loop", "SKILL.md"))
    if plugin_dir:
        info["plugin_dir"] = os.path.abspath(plugin_dir)
        info["used_skill_sha256"] = digest(os.path.join(plugin_dir, "skills", "review-loop", "SKILL.md"))
    elif not installed:
        raise SystemExit(f"{PLUGIN_ID} が導入されていない(または無効)。--plugin-dir を使う")
    else:
        info["used_skill_sha256"] = info["installed_skill_sha256"]
    return info


# ---- GitHub ----

def create_trial_pr(gj, branch):
    repo = gj["repo"]
    if not repo.split("/")[1].startswith(REPO_PREFIX):
        raise SystemExit(f"{repo} は検証用のリポジトリの名前ではない")
    src = json.loads(sh(["gh", "pr", "view", str(gj["pr"]), "-R", repo, "--json", "title,body,baseRefName,headRefName"]))
    if branch == src["headRefName"] or not branch.startswith(BRANCH_PREFIX):
        raise SystemExit("試し用のブランチの名前が、題材のブランチと重なる")
    body = src["body"].replace("\r\n", "\n")
    if "## レビューループの経緯" in body:  # 題材の PR に経緯が書かれていたら、写さない
        body = body.split("## レビューループの経緯")[0].rstrip() + "\n"
    sh(["gh", "api", f"repos/{repo}/git/refs", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={gj['head']}"])
    url = sh(["gh", "pr", "create", "-R", repo, "--base", src["baseRefName"], "--head", branch,
              "--title", src["title"], "--body-file", "-"], input=body).strip()
    return int(url.rsplit("/", 1)[1]), url


def close_trial_pr(repo, number, branch):
    if not branch.startswith(BRANCH_PREFIX) or not repo.split("/")[1].startswith(REPO_PREFIX):
        raise RuntimeError("試し用でないものを消そうとした")
    sh(["gh", "pr", "close", str(number), "-R", repo], check=False)
    sh(["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch}"], check=False)


# ---- 別セッション ----

def agents():
    return json.loads(sh(["claude", "agents", "--json", "--all"]))


def agent(short_id):
    for a in agents():
        if a.get("id") == short_id:
            return a
    return None


def start(workdir, args, prompt):
    out = sh(["claude", "--bg", *args, "--", prompt], cwd=workdir, env=child_env())
    m = re.search(r"backgrounded · (\w+)", out)
    if not m:
        raise RuntimeError(f"別セッションを起動できなかった: {out[-600:]}")
    short = m.group(1)
    for _ in range(20):
        a = agent(short)
        if a and a.get("sessionId"):
            return short, a["sessionId"]
        time.sleep(1)
    raise RuntimeError(f"起動したセッション {short} が一覧に出ない")


def jsonl_path(session_id):
    """セッションの記録の場所。記録は、セッションの作業ディレクトリの名前の下に置かれる。別セッションが
    自分で worktree に移ると、置き場も変わるので、セッション ID で探す。まだ無ければ、空の文字列。"""
    found = glob.glob(os.path.join(os.path.expanduser("~/.claude/projects"), "*", session_id + ".jsonl"))
    return max(found, key=os.path.getmtime) if found else ""


def session_cwd(short, fallback):
    """別セッションの、いまの作業ディレクトリ(自分で worktree に移っていれば、その先)。続きは、そこで起動する。"""
    a = agent(short)
    cwd = a and a.get("cwd")
    return cwd if cwd and os.path.isdir(cwd) else fallback


def turn_state(path, sent):
    """記録から、sent(最後に渡した文)へのターンが終わったかと、最後の出力を読む。(終わったか, 最後の出力)

    続きのセッションの記録は、前のセッションの履歴の写しから始まる。写しの末尾を「終わった」と読み違えないように、
    渡した文が記録に現れたあとの終わりだけを数える。"""
    if not path or not os.path.exists(path):
        return False, ""
    done, texts, seen = False, [], False
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("isSidechain"):
                continue
            t = e.get("type")
            if t == "system" and e.get("subtype") == "turn_duration":
                done = not e.get("pendingBackgroundAgentCount")
            elif t == "user":
                done = False
                c = (e.get("message") or {}).get("content")
                if isinstance(c, str) or (isinstance(c, list) and any(x.get("type") == "text" for x in c)):
                    texts = []
                if isinstance(c, str) and c.strip() == sent.strip():
                    seen = True
            elif t == "assistant":
                done = False
                c = (e.get("message") or {}).get("content") or []
                if any(x.get("type") == "tool_use" for x in c):
                    texts = []
                texts += [x["text"] for x in c if x.get("type") == "text"]
    return done and seen, "\n".join(texts).strip()


def wait_turn(short, sid, deadline, sent):
    """ターンの終わりを待つ。('done' | 'waiting' | 'timeout' | 'gone', 最後の出力)"""
    while True:
        a = agent(short)
        path = jsonl_path(sid)
        if a is None:
            return "gone", turn_state(path, sent)[1]
        status = a.get("status")
        done, text = turn_state(path, sent)
        if status == "waiting":
            return "waiting", text
        if status != "busy" and done:
            return "done", text
        if a.get("state") in ("stopped", "done") and status != "busy":
            return ("done" if done else "gone"), text
        if time.time() > deadline:
            return "timeout", text
        time.sleep(POLL)


def stop(short):
    sh(["claude", "stop", short], check=False)


def drive(conf, workdir, base_args, out_dir, pr, prior=None):
    """別セッションを起動し、答えながら終わりまで回す。やりとりの記録を返す。

    prior(前の実行の drive.json)を渡すと、起動せずに、最後のセッションの続きから回す(仕組みの側だけが
    途中で止まったときのため)。"""
    deadline = time.time() + conf["max_minutes"] * 60
    turns, replies, final_next, outcome = [], 0, False, None
    if prior:
        sessions = prior["sessions"]
        turns = [t for t in prior.get("turns", []) if t.get("state") == "done" and t.get("decision") == "reply"]
        replies = len(turns)
        short, sid = sessions[-1]["id"], sessions[-1]["session_id"]
        sent = turns[-1]["reply"] if turns else conf["prompt"].format(pr=pr)
        log(f"続きから回す: {short}({sid})")
    else:
        sent = conf["prompt"].format(pr=pr)
        short, sid = start(workdir, base_args, sent)
        sessions = [{"id": short, "session_id": sid}]
        log(f"起動した: {short}({sid})。`claude logs {short}` で様子を見られる")
    while outcome is None:
        state, text = wait_turn(short, sid, deadline, sent)
        turn = {"sent": sent, "state": state, "at": datetime.datetime.now().isoformat(timespec="seconds"),
                "session": short, "output": text}
        turns.append(turn)
        save(out_dir, "drive.json", {"sessions": sessions, "turns": turns})
        if state != "done":
            outcome = state
            log(f"ターンが終わらずに止まった: {state}")
            break
        rule = None
        # 判断を仰ぐ出力にも「最後にレビューした SHA」が入ることがある(2026-11-18 の sk-12)。仰いでいれば、終了と読まない
        asking = bool(conf.get("ask_match") and re.search(conf["ask_match"], text))
        if final_next or (re.search(conf["end_match"], text) and not asking):
            turn["decision"] = "end"
            outcome = "ended"
            break
        for r in conf.get("answers", []):
            if re.search(r["match"], text):
                rule = r
                break
        if replies >= conf["max_replies"]:
            turn["decision"] = "max_replies"
            outcome = "max_replies"
            break
        reply = rule["reply"] if rule else conf["default_reply"]
        turn["decision"] = "reply"
        turn["reply"] = reply
        turn["rule"] = rule["label"] if rule else "(想定に無い質問。default_reply)"
        final_next = bool(rule and rule.get("final"))
        replies += 1
        log(f"判断を仰がれた({turn['rule']})。答えて続ける")
        cwd = session_cwd(short, workdir)
        stop(short)
        short, sid = start(cwd, ["--resume", sid, *base_args], reply)
        sessions.append({"id": short, "session_id": sid, "cwd": cwd})
        sent = reply
    # 終わったあとに、手順から外れた箇所を尋ねる(自己申告。ループの結果には影響しない)
    debrief = None
    if outcome in ("ended", "max_replies") and conf.get("debrief"):
        cwd = session_cwd(short, workdir)
        stop(short)
        short, sid = start(cwd, ["--resume", sid, *base_args], conf["debrief"])
        sessions.append({"id": short, "session_id": sid, "cwd": cwd, "debrief": True})
        state, debrief = wait_turn(short, sid, time.time() + 5 * 60, conf["debrief"])
    for s in sessions:
        stop(s["id"])
    time.sleep(3)  # 止めたときに、費用の記録が書かれる
    result = {"outcome": outcome, "sessions": sessions, "turns": turns, "debrief": debrief}
    save(out_dir, "drive.json", result)
    return result


def save(out_dir, name, data):
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")


def collect_records(sessions, out_dir):
    """セッションとサブエージェントの記録を、結果のディレクトリに写す(大きいので、コミットしない)。"""
    dst = os.path.join(out_dir, "records")
    os.makedirs(dst, exist_ok=True)
    for i, s in enumerate(sessions):
        src = jsonl_path(s["session_id"])
        if not src:
            continue
        shutil.copy(src, os.path.join(dst, f"{i:02d}-{s['session_id']}.jsonl"))
        sub = os.path.join(os.path.dirname(src), s["session_id"], "subagents")
        if os.path.isdir(sub):
            shutil.copytree(sub, os.path.join(dst, f"{i:02d}-subagents"), dirs_exist_ok=True)


def empty(workdir):
    """枠の中身を消す(枠そのものは、信頼の設定がパスに付いているので残す)。"""
    for name in os.listdir(workdir):
        path = os.path.join(workdir, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)


def run(args):
    conf = load_config(args.case)
    if args.max_minutes:
        conf["max_minutes"] = args.max_minutes
    with open(os.path.join(BENCH, "cases", args.case, "github.json"), encoding="utf-8") as f:
        gj = json.load(f)
    with open(os.path.join(BENCH, "cases", args.case, "case.json"), encoding="utf-8") as f:
        repo_name = json.load(f).get("repo_name", "repo")
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = secrets.token_hex(4)
    # 結果は、リポジトリの外に置く。別セッションの出力や依頼文には、利用者の計算機のパスやセッションの URL が入るので、
    # コミットしない(このリポジトリは公開)
    out_dir = os.path.abspath(args.out or os.path.join(os.path.expanduser(args.work_root), "runs", f"{args.case}-{stamp}"))
    os.makedirs(out_dir)
    slot_dir = os.path.join(os.path.expanduser(args.work_root), args.slot)
    lock = slot_dir + ".lock"
    if not os.path.isdir(slot_dir):
        raise SystemExit(f"枠 {slot_dir} が無い。作って、そこで一度 claude を起動し、信頼のダイアログで承認する")
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        raise SystemExit(f"枠 {slot_dir} は、ほかの実行が使っている({lock})。--slot で別の枠を選ぶ")
    branch = f"{BRANCH_PREFIX}{stamp.lower()}"
    # 別セッションは、枠に取り出したリポジトリの、PR のブランチの worktree で起動する。バックグラウンドのセッションは
    # 「編集の前に worktree に隔離する」指示を受けるので、枠のトップで起動すると、自分で detached の worktree を作って移る
    # (2026-11-18 の2回で起きた)。作業ディレクトリが初めから .claude/worktrees/ の下なら、移らない
    workdir = os.path.join(slot_dir, ".claude", "worktrees", "pr")
    plugin = plugin_info(args.plugin_dir)
    base_args = ["--model", args.model, "--permission-mode", "auto", "--disallowedTools", "AskUserQuestion"]
    if args.plugin_dir:  # 作業ツリーの版を読ませるときは、導入済みの版を無効にする
        base_args += ["--plugin-dir", os.path.abspath(args.plugin_dir),
                      "--settings", json.dumps({"enabledPlugins": {PLUGIN_ID: False}})]
    meta = {"case": args.case, "expect": conf.get("expect"), "run_id": run_id, "started": stamp, "repo": gj["repo"],
            "base_head": gj["head"], "branch": branch, "slot_dir": slot_dir, "workdir": workdir, "model": args.model,
            "launch": "claude --bg " + " ".join(base_args), "plugin": plugin,
            "claude_version": sh(["claude", "--version"]).strip()}
    if not args.plugin_dir and plugin["installed_skill_sha256"] != plugin["repo_skill_sha256"]:
        log("注意: 導入済みの SKILL.md が、このリポジトリの作業ツリーの SKILL.md と違う")
    pr = None
    try:
        pr, url = create_trial_pr(gj, branch)
        meta.update(pr=pr, pr_url=url, base_args=base_args, keep=args.keep)
        save(out_dir, "meta.json", meta)
        log(f"試し用の PR を作った: {url}")
        empty(slot_dir)
        sh(["git", "clone", "-q", f"git@github.com:{gj['repo']}.git", slot_dir])
        sh(["git", "worktree", "add", "-q", workdir, branch], cwd=slot_dir)
        drive_and_collect(conf, meta, out_dir)
    finally:
        finish(meta, out_dir)


def drive_and_collect(conf, meta, out_dir, prior=None):
    t0 = time.time()
    result = drive(conf, meta["workdir"], meta["base_args"], out_dir, meta["pr"], prior)
    meta["wall_seconds"] = round(time.time() - t0) + (meta.get("wall_seconds") or 0)
    meta["outcome"] = result["outcome"]
    collect_records(result["sessions"], out_dir)
    for s in result["sessions"]:  # 記録を写したら、別セッションを一覧から外す(会話の記録は残る。`claude --resume` で開ける)
        sh(["claude", "rm", s["id"]], check=False)
    view = json.loads(sh(["gh", "pr", "view", str(meta["pr"]), "-R", meta["repo"], "--json", "body,headRefOid,commits,state"]))
    save(out_dir, "pr-body.md", view["body"].replace("\r\n", "\n"))
    meta["final_head"] = view["headRefOid"]
    meta["commits"] = [{"sha": c["oid"][:7], "title": c["messageHeadline"]} for c in view["commits"]]
    save(out_dir, "pr.diff", sh(["gh", "api", f"repos/{meta['repo']}/compare/{meta['base_head']}...{view['headRefOid']}",
                                 "-H", "Accept: application/vnd.github.diff"], check=False))


def finish(meta, out_dir):
    """結果を書き、後片付けをして、集計する。"""
    save(out_dir, "meta.json", meta)
    slot_dir = meta.get("slot_dir") or meta["workdir"]
    lock = slot_dir + ".lock"
    if os.path.exists(lock):
        os.remove(lock)
    if meta.get("pr") and not meta.get("keep"):
        close_trial_pr(meta["repo"], meta["pr"], meta["branch"])
        empty(slot_dir)
        log("試し用の PR を閉じ、ブランチと写しを消した")
    elif meta.get("pr"):
        log(f"残した: PR #{meta['pr']}、ブランチ {meta['branch']}、写し {meta['workdir']}")
    subprocess.run([sys.executable, os.path.join(HERE, "analyze.py"), out_dir], check=False)
    log(f"結果: {out_dir}")


def cont(args):
    """仕組みの側だけが途中で止まった実行を、別セッションの続きから回す。"""
    out_dir = os.path.abspath(args.dir)
    with open(os.path.join(out_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(out_dir, "drive.json"), encoding="utf-8") as f:
        prior = json.load(f)
    meta.setdefault("base_args", ["--model", meta["model"], "--permission-mode", "auto", "--disallowedTools", "AskUserQuestion"])
    meta["continued"] = True
    try:
        drive_and_collect(load_config(meta["case"]), meta, out_dir, prior)
    finally:
        finish(meta, out_dir)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("case")
    r.add_argument("--keep", action="store_true", help="試し用の PR、ブランチ、写しを残す")
    r.add_argument("--plugin-dir", help="導入済みの版の代わりに、このディレクトリのプラグインを読ませる(例: リポジトリのルート)")
    r.add_argument("--model", default="claude-opus-5-5")
    r.add_argument("--max-minutes", type=int)
    r.add_argument("--work-root", default="~/rlbench-e2e")
    r.add_argument("--slot", default="s1", help="取り出す先の枠(<work-root> の下の、信頼済みのディレクトリ)")
    r.add_argument("--out")
    c = sub.add_parser("continue", help="仕組みの側だけが途中で止まった実行を、別セッションの続きから回す")
    c.add_argument("dir")
    a = sub.add_parser("analyze")
    a.add_argument("dir")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args)
    elif args.cmd == "continue":
        cont(args)
    else:
        sys.exit(subprocess.run([sys.executable, os.path.join(HERE, "analyze.py"), args.dir]).returncode)


if __name__ == "__main__":
    main()
