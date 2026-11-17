#!/usr/bin/env python3
"""review-loop のレビュー役の構成を、不具合を含む題材で比べる。

    bench.py build <題材> <出力先>                 題材のリポジトリを組み立てる(確認用)
    bench.py run --out <結果の置き場> [--cases a,b] [--configs x,y] [--trials 3] [--jobs 4]

run は、題材ごとに「ベース+差分」の一時リポジトリを作り、構成 × 試行ごとに専用の複製の中で
`claude -p` を起動する。GitHub には触れない(origin はローカルの bare リポジトリ)。
結果は <結果の置き場>/<題材>/<構成>/<試行>/ に置く(result.md、meta.json、stdout.jsonl、stderr.txt)。
既に meta.json がある試行は飛ばすので、途中で止めても同じコマンドで続きから回せる。

採点は score.py。正解の一覧(answers/)は、このスクリプトも子も読まない。
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "../../.."))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import claude_p as rl  # noqa: E402  子を `claude -p` で起動し、stream を読む部品(本番が `claude -p` で起動していた版から写した)

CASES = os.path.join(HERE, "cases")
GIT_ID = ["-c", "user.name=dev", "-c", "user.email=dev@example.com", "-c", "commit.gpgsign=false"]

# --- 構成 --------------------------------------------------------------------
# 実物の PR が無いので、対象と意図の在りかを全構成に同じ文で伝える
TARGET = ("レビューの対象は、ブランチ main から今のブランチ(HEAD)への差分(`git diff main...HEAD`)です。"
          "PR はまだ作っていないので、PR 番号はありません。差分の意図は `git log main..HEAD` のコミットメッセージにあります。")
READ_ONLY = rl.NO_MUTATION + rl.DELEGATE_CONSTRAINT
OWN_COPY = ("あなた専用のリポジトリの複製で実行しています。このディレクトリの中では、ファイルを作り、コマンドを実行して構いません。"
            "このディレクトリの外のファイルは変えないでください。commit と push はしないでください。" + rl.DELEGATE_CONSTRAINT)

PERSPECTIVES_PROMPT = ("main からこのブランチへの差分を、正確性 / セキュリティ / 並行性 / プライバシー / 設計の観点でレビューし、"
                       "具体的な指摘を file:line 付きの箇条書きで出してください。")

PROVE_PROMPT = """\
この変更(main からこのブランチへの差分)を壊してください。

指摘は、実際のコードに対する実行で証明したものだけにします。失敗するテスト、再現スクリプト、誤った挙動を示すコマンドの出力などです。
実行は、このディレクトリと、その下に作る `scratch/` の中だけで行います。

指摘ごとに、次を書きます。
- 題
- 実行したコマンド(そのまま)
- 出力(そのまま)
- 変更の意図に照らして、出るべきだった出力

実行していないものは書きません。書き方、命名、構造、将来の変更があって初めて問題になるものが、これに当たります。
指摘なしも正当な結果です。証明できた指摘が無ければ「証明できた指摘なし」と書きます。
"""

CONFIGS = {
    "code-review": {"prompt": "/code-review high", "system": READ_ONLY},
    "security-review": {"prompt": "/security-review", "system": READ_ONLY},
    "mattpocock": {"prompt": "/mattpocock-skills:code-review main", "system": READ_ONLY},
    "perspectives": {"prompt": PERSPECTIVES_PROMPT, "system": READ_ONLY},
    # 観点を書かない形。観点明示型との差が、観点の一覧の効果になる
    "plain": {"prompt": "main からこのブランチへの差分をレビューし、具体的な指摘を file:line 付きの箇条書きで出してください。",
              "system": READ_ONLY},
    "prove": {"prompt": PROVE_PROMPT, "system": OWN_COPY},
}

# PR ありの形(--pr)。本番が `claude -p` で起動していた版と同じ引数とシステムプロンプトで起動する。{pr} は PR 番号に置き換わる
CONFIGS_PR = {
    "code-review": {"prompt": "/code-review high {pr}", "system": rl.REVIEW_CONSTRAINT},
    "security-review": {"prompt": "/security-review", "system": rl.REVIEW_CONSTRAINT},
    "mattpocock": {"prompt": "/mattpocock-skills:code-review PR #{pr}", "system": rl.REVIEW_CONSTRAINT},
    "perspectives": {"prompt": "PR #{pr} の差分を、正確性 / セキュリティ / 並行性 / プライバシー / 設計の観点でレビューし、"
                               "具体的な指摘を file:line 付きの箇条書きで出してください。", "system": rl.REVIEW_CONSTRAINT},
    "plain": {"prompt": "PR #{pr} の差分をレビューし、具体的な指摘を file:line 付きの箇条書きで出してください。",
              "system": rl.REVIEW_CONSTRAINT},
    "prove": {"prompt": PROVE_PROMPT.replace("この変更(main からこのブランチへの差分)", "この変更(PR #{pr})"),
              "system": OWN_COPY},
}

# 子の PATH の先頭に置く gh の包み。検証用のリポジトリ以外を指す呼び出しを断る(元のリポジトリは公開で、
# PR や issue にレビューで見つかった不具合が書いてある。認証があれば読めてしまう)
GH_SHIM = r"""#!/usr/bin/env python3
import os, re, sys
real, allowed = os.environ["RB_REAL_GH"], os.environ["RB_REPO"].lower()
args = sys.argv[1:]
text = " ".join(args).lower()


def deny():
    sys.stderr.write("GraphQL: Could not resolve to a Repository with the name given. (repository)\n")
    sys.exit(1)


named = [m.group(1) for m in re.finditer(r"(?:-r|--repo)[ =]+(?:https?://)?(?:github\.com/)?([\w.-]+/[\w.-]+)", text)]
named += [m.group(1) for m in re.finditer(r"(?:repos|github\.com)[/:]([\w.-]+/[\w.-]+?)(?:\.git)?(?:[/ ?#]|$)", text)]
named += [m.group(0) for m in re.finditer(r"masahirompp/[\w.-]+", text)]
if any(n not in (allowed, "{owner}/{repo}", ":owner/:repo") for n in named):
    deny()
if args[:1] == ["search"] or args[:2] in (["repo", "list"], ["repo", "clone"], ["repo", "fork"]) or "search/" in text:
    deny()
if args[:2] == ["api", "graphql"] and re.search(r"[\"']?(whatnext|skills)[\"']", text):
    deny()
os.environ.pop("GH_REPO", None)
os.execv(real, [real] + args)
"""

TIMEOUT = rl.REVIEW_TIMEOUT
MODEL = "claude-opus-5-5"  # 子に使わせるモデルの既定。--model で変える
print_lock = threading.Lock()
stop = threading.Event()  # 利用枠の上限に当たったら立てる。残りの試行を始めない
LIMIT_RE = re.compile(r"usage limit|hit your .*limit|rate limit|overloaded", re.I)


def log(msg):
    with print_lock:
        print(time.strftime("%H:%M:%S ") + msg, file=sys.stderr, flush=True)


def sh(args, cwd, input=None, timeout=900):
    r = subprocess.run(args, cwd=cwd, input=input, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"`{' '.join(args[:6])}` が失敗した({r.returncode}): {r.stderr.strip()[-2000:]}")
    return r.stdout


def git(cwd, *args, input=None):
    return sh(["git", *GIT_ID, *args], cwd, input=input)


# --- 題材 --------------------------------------------------------------------
def load_case(case_id):
    d = os.path.join(CASES, case_id)
    with open(os.path.join(d, "case.json"), encoding="utf-8") as f:
        case = json.load(f)
    case["dir"] = d
    gh_path = os.path.join(d, "github.json")
    if os.path.exists(gh_path):
        with open(gh_path, encoding="utf-8") as f:
            case["github"] = json.load(f)
    return case


def attach_github(case, repo):
    """組み立てた題材の origin を、検証用の GitHub のリポジトリに付け替える(gh が PR を引けるようにする)。"""
    info = case["github"]
    shutil.rmtree(os.path.join(os.path.dirname(repo), "origin.git"))
    git(repo, "remote", "set-url", "origin", f"git@github.com:{info['repo']}.git")
    git(repo, "fetch", "-q", "origin")
    # まとめたコミットは、組み立てのたびに時刻が変わって別の SHA になる。中身が同じなら、PR の head に合わせる
    if git(repo, "rev-parse", "HEAD^{tree}").strip() == git(repo, "rev-parse", info["head"] + "^{tree}").strip():
        git(repo, "reset", "-q", "--hard", info["head"])
    if git(repo, "rev-parse", "HEAD").strip() != info["head"]:
        raise RuntimeError(f"{case['id']}: 組み立てた HEAD が、検証用の PR の head と一致しない")


def all_cases():
    return sorted(n for n in os.listdir(CASES) if os.path.isfile(os.path.join(CASES, n, "case.json")))


def build(case, dest):
    """dest の下に <repo_name>/(main にベース、作業ブランチに差分)と origin.git を作り、リポジトリのパスを返す。"""
    os.makedirs(dest)
    repo = os.path.join(dest, case["repo_name"])
    src = case["source"]
    if src["type"] == "skills":
        # このリポジトリの固定した版の写しを土台にする。履歴は持ち込まない(修正後のコミットを見せないため)
        os.makedirs(repo)
        tar = subprocess.run(["git", "archive", src["rev"]], cwd=REPO, capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", repo], input=tar, check=True)
        git(repo, "init", "-q", "-b", "main")
        apply_patch(repo, os.path.join(case["dir"], "base.patch"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "import")
        git(repo, "switch", "-q", "-c", case["branch"])
        apply_patch(repo, os.path.join(case["dir"], "change.patch"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-F", os.path.join(case["dir"], "message.txt"))
    elif src["type"] == "repo":
        # 実際の PR の、レビューを受ける前のコミットまでを取り込む(それより後の修正は取り込まない)
        git(dest, "init", "-q", "-b", "main", repo)
        # path が "." なら、このリポジトリ自身。読むだけで、変えない
        origin_repo = REPO if src["path"] == "." else os.path.expanduser(src["path"])
        head, base = (git(origin_repo, "rev-parse", src[k] + "^{commit}").strip() for k in ("head", "base"))
        git(repo, "fetch", "-q", "--no-tags", origin_repo, head)
        git(repo, "update-ref", "refs/heads/main", base)
        if src.get("squash"):
            # レビューを通った最終形を、1つのコミットにまとめる(「指摘を反映する」というコミットを見せない)
            tree = git(repo, "rev-parse", head + "^{tree}").strip()
            head = git(repo, "commit-tree", tree, "-p", base, "-F", os.path.join(case["dir"], "message.txt")).strip()
        git(repo, "switch", "-q", "-c", case["branch"], head)
        # 取り込みに使った参照と、まとめる前のコミットを残さない
        os.remove(os.path.join(repo, ".git", "FETCH_HEAD"))
        git(repo, "reflog", "expire", "--expire=now", "--all")
        git(repo, "gc", "-q", "--prune=now")
    else:
        raise RuntimeError(f"source.type が不明: {src['type']}")
    origin = os.path.join(dest, "origin.git")
    git(dest, "init", "-q", "--bare", "-b", "main", origin)
    git(repo, "remote", "add", "origin", origin)
    git(repo, "push", "-q", "-u", "origin", "main", case["branch"])
    git(repo, "remote", "set-head", "origin", "main")
    for cmd in case.get("setup", []):
        sh(cmd, repo, timeout=1800)
    if git(repo, "status", "--porcelain").strip():
        raise RuntimeError(f"{case['id']}: 組み立てた直後の作業ツリーがクリーンでない")
    return repo


def apply_patch(repo, path):
    if os.path.exists(path) and os.path.getsize(path):
        git(repo, "apply", "--whitespace=nowarn", path)


def copy_tree(src, dst):
    """題材を試行の場所へ複製する。macOS では clonefile で速く、容量も使わない。"""
    if sys.platform == "darwin" and subprocess.run(["cp", "-Rc", src, dst], capture_output=True).returncode == 0:
        return
    shutil.copytree(src, dst, symlinks=True)


def clone_trial(template, root, case):
    """題材の複製を新しいディレクトリに作り、(試行のディレクトリ, リポジトリ) を返す。
    パスに題材や構成の名前を入れない(子に、何を測っているかの手がかりを与えない)。"""
    trial = os.path.join(root, "w", uuid.uuid4().hex[:10])
    os.makedirs(os.path.dirname(trial), exist_ok=True)
    copy_tree(template, trial)
    repo = os.path.join(trial, case["repo_name"])
    if os.path.isdir(os.path.join(trial, "origin.git")):  # PR ありの形では、origin は GitHub のまま
        git(repo, "remote", "set-url", "origin", os.path.join(trial, "origin.git"))
    return trial, repo


# --- 子の出力の検査 ----------------------------------------------------------
# PR なしの形では gh の呼び出しも拾う(PR が無いので、呼ぶなら元のリポジトリを探している)。PR ありの形では、
# 元のリポジトリの名前だけを拾う
SUSPECT_CMD = re.compile(r"ghq/|masahirompp/(skills|whatnext)\b|\bgh\s+(pr|api|repo|issue|search|run)\b|review-loop/bench|/answers/")
SUSPECT_CMD_PR = re.compile(r"ghq/|masahirompp/(skills|whatnext)\b|review-loop/bench|/answers/")
PATH_KEYS = ("file_path", "path", "notebook_path")


def outside_access(jsonl, trial, root, pr_mode=False):
    """子(とサブエージェント)のツール呼び出しのうち、題材の外にある答えの手がかりを見に行った疑いのあるものを返す。
    見るのは、自分の試行の外のパス(一時ディレクトリと ~/.claude のスキルは除く)、GitHub や手元の clone に
    触れるコマンド、Web の検索と取得。"""
    home_claude = os.path.join(os.path.expanduser("~"), ".claude") + os.sep
    tmp = os.path.realpath(tempfile.gettempdir()) + os.sep
    root = os.path.realpath(root) + os.sep
    trial = os.path.realpath(trial) + os.sep
    found = []

    def ok_path(p):
        p = os.path.realpath(os.path.expanduser(p))
        if (p + os.sep).startswith(trial):
            return True
        if p.startswith(root):  # ほかの試行や題材の雛形
            return False
        if p.startswith(home_claude):
            return "masahirompp" not in p[len(home_claude):]
        return p.startswith((tmp, "/tmp/", "/private/tmp/", "/dev/", "/usr/", "/bin/", "/opt/", "/etc/"))

    with open(jsonl, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("type") != "assistant":
                continue
            for b in (msg.get("message") or {}).get("content") or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                name, inp = b.get("name") or "", b.get("input") or {}
                if name in ("WebFetch", "WebSearch"):
                    found.append(f"{name} {json.dumps(inp, ensure_ascii=False)[:200]}")
                for k in PATH_KEYS:
                    v = inp.get(k)
                    if isinstance(v, str) and os.path.isabs(os.path.expanduser(v)) and not ok_path(v):
                        found.append(f"{name} {k}={v}")
                cmd = inp.get("command")
                if isinstance(cmd, str) and (SUSPECT_CMD_PR if pr_mode else SUSPECT_CMD).search(cmd.replace(trial, "")):
                    found.append(f"{name} {cmd[:300]}")
    return found


# --- 実行 --------------------------------------------------------------------
def child_env(root, case=None):
    if case is not None and "github" in case and PR_MODE:
        # PR ありの形: gh は認証済みのまま、包みを通す
        env = rl.child_env()
        env.pop("GH_REPO", None)
        env["RB_REAL_GH"], env["RB_REPO"] = REAL_GH, case["github"]["repo"]
        env["PATH"] = os.path.join(root, "bin") + os.pathsep + env.get("PATH", "")
        return env
    return child_env_no_gh(root)


def child_env_no_gh(root):
    """子の環境。gh を未認証にする。題材のコードからリポジトリ名が分かるので、認証があると、子が GitHub の issue や
    PR(レビューで見つかった不具合が書いてある)を読みに行ける。"""
    env = rl.child_env()
    for k in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(k, None)
    env["GH_CONFIG_DIR"] = os.path.join(root, "gh")
    os.makedirs(env["GH_CONFIG_DIR"], exist_ok=True)
    return env


def run_trial(case, config, n, template, root, out, keep, model):
    dest = os.path.join(out, case["id"], config, str(n))
    if os.path.exists(os.path.join(dest, "meta.json")) or stop.is_set():
        return
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    spec = CONFIGS_PR[config] if PR_MODE else CONFIGS[config]
    prompt, system = spec["prompt"], spec["system"] + "\n\n" + TARGET
    if PR_MODE:
        prompt, system = prompt.replace("{pr}", str(case["github"]["pr"])), spec["system"]
    trial, repo = clone_trial(template, root, case)
    head = git(repo, "rev-parse", "HEAD").strip()
    base = os.path.join(dest, "review")
    children = rl.Children()
    meta = {"case": case["id"], "kind": case["kind"], "config": config, "trial": n, "model": model, "pr_mode": PR_MODE, "status": "error",
            "tokens": rl.new_tokens(), "cost_usd": None, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    started = time.monotonic()
    log(f"start {case['id']} {config} #{n}")
    try:
        with open(base + ".stdout.jsonl", "w") as o, open(base + ".stderr.txt", "w") as e:
            p = children.spawn(["claude", "-p", "--model", model, "--output-format", "stream-json", "--verbose",
                                "--append-system-prompt", system, prompt],
                               TIMEOUT, cwd=repo, env=child_env(root, case), stdin=subprocess.DEVNULL, stdout=o, stderr=e)
        tail = rl.StreamTail(base + ".stdout.jsonl")
        timed_out = False
        while p.poll() is None:
            tail.poll()
            if time.monotonic() - started > TIMEOUT:
                timed_out = True
                break
            time.sleep(2)
        rc = p.poll()
        children.finish(p)
        tail.poll()
        meta["duration_s"] = round(time.monotonic() - started)
        text = "\n\n".join(tail.texts())
        with open(os.path.join(dest, "result.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        last = tail.results[-1] if tail.results else {}
        rl.add_tokens(meta["tokens"], last)
        meta["cost_usd"] = last.get("total_cost_usd")
        meta["num_turns"] = last.get("num_turns")
        meta["models"] = sorted((last.get("modelUsage") or {}).keys())
        meta["denials_blocking"] = [rl.summarize_denials([d]) for d in tail.blocking_denials()]
        meta["denials_tolerated"] = tail.take_tolerated()
        meta["outside_access"] = outside_access(base + ".stdout.jsonl", trial, root, PR_MODE)
        meta["tree_changed"] = git(repo, "status", "--porcelain", "--untracked-files=all").strip().splitlines()[:50]
        meta["head_changed"] = git(repo, "rev-parse", "HEAD").strip() != head
        if timed_out:
            meta["status"] = "timeout"
        elif not tail.results or rc != 0 or last.get("subtype") != "success" or last.get("is_error"):
            meta["status"] = "child_error"
            meta["detail"] = f"rc={rc} subtype={last.get('subtype')} {str(last.get('result') or '')[:300]}"
        elif not text.strip():
            meta["status"] = "no_output"
        elif meta["denials_blocking"]:
            meta["status"] = "denied"  # 本番が claude -p で起動していた版なら、試行を止めた拒否。出力は残すが、集計では分ける
        else:
            meta["status"] = "ok"
    except Exception as e:  # 1つの試行の失敗で全体を止めない
        meta["detail"] = f"{type(e).__name__}: {e}"
    finally:
        children.kill_all()
        if not keep:
            shutil.rmtree(trial, ignore_errors=True)
    if meta["status"] not in ("ok", "denied") and (LIMIT_RE.search(str(meta.get("detail") or "")) or stop.is_set()):
        # 利用枠の上限などで動けなかった試行は、結果として残さない(次に同じコマンドで回したときにやり直す)
        stop.set()
        shutil.rmtree(dest, ignore_errors=True)
        log(f"stop  {case['id']} {config} #{n}: {str(meta.get('detail') or meta['status'])[:200]}(残りの試行を始めない)")
        return
    with open(os.path.join(dest, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    t = meta["tokens"]
    log(f"done  {case['id']} {config} #{n}: {meta['status']} {meta.get('duration_s', '?')}s "
        f"in={t['input'] / 1e4:.0f}万 out={t['output'] / 1e4:.1f}万 ${meta['cost_usd'] or 0:.2f}"
        + (f" 題材の外へのアクセス {len(meta['outside_access'])} 件" if meta.get("outside_access") else ""))


PR_MODE = False
REAL_GH = shutil.which("gh")


def cmd_run(args):
    global PR_MODE
    PR_MODE = args.pr
    os.environ[rl.GUARD_ENV] = "1"
    cases = [load_case(c) for c in (args.cases.split(",") if args.cases else all_cases())]
    if PR_MODE and not args.cases:  # 元の PR が無く、検証用の PR を作れない題材は外す(publish.py と同じ条件)
        cases = [c for c in cases if "pr" in c]
    configs = args.configs.split(",") if args.configs else list(CONFIGS)
    unknown = [c for c in configs if c not in CONFIGS]
    if unknown:
        sys.exit(f"構成が不明: {', '.join(unknown)}")
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    root = os.path.realpath(tempfile.mkdtemp(prefix="rb-"))
    log(f"一時ディレクトリ: {root}")
    templates = {}
    try:
        if PR_MODE:
            missing = [c["id"] for c in cases if "github" not in c]
            if missing:
                sys.exit(f"検証用の PR が無い題材がある(publish.py create で作る): {', '.join(missing)}")
            os.makedirs(os.path.join(root, "bin"))
            with open(os.path.join(root, "bin", "gh"), "w") as f:
                f.write(GH_SHIM)
            os.chmod(os.path.join(root, "bin", "gh"), 0o755)
        for case in cases:
            repo = build(case, os.path.join(root, "tpl", case["id"]))
            if PR_MODE:
                attach_github(case, repo)
            templates[case["id"]] = os.path.join(root, "tpl", case["id"])
            log(f"built {case['id']}")
        # 同じ構成が続けて並ばないよう、試行 → 題材 → 構成の順に積む
        jobs = [(case, config, n) for n in range(1, args.trials + 1) for case in cases for config in configs]
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as ex:
            futures = [ex.submit(run_trial, case, config, n, templates[case["id"]], root, out, args.keep, args.model)
                       for case, config, n in jobs]
            for f in concurrent.futures.as_completed(futures):
                f.result()
        if PR_MODE:  # 子が検証用の PR に push していないか(禁じている操作)を、最後にまとめて確かめる
            for case in cases:
                info = case["github"]
                r = subprocess.run([REAL_GH, "pr", "view", str(info["pr"]), "-R", info["repo"], "--json",
                                    "headRefOid,comments,reviews", "--jq",
                                    '"\\(.headRefOid) \\(.comments|length) \\(.reviews|length)"'],
                                   capture_output=True, text=True)
                head, _, counts = r.stdout.strip().partition(" ")
                if head != info["head"] or counts != "0 0":
                    log(f"warn: {case['id']}: 検証用の PR が変わった(head {head[:7]}、コメントとレビューの数 {counts})。"
                        "子が push かコメントをした可能性がある")
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
    log(f"結果: {out}" + ("(利用枠の上限で途中まで。同じコマンドで続きから回せる)" if stop.is_set() else ""))
    if stop.is_set():
        sys.exit(3)


def cmd_build(args):
    print(build(load_case(args.case), os.path.abspath(args.dest)))


def main():
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("case")
    b.add_argument("dest")
    b.set_defaults(fn=cmd_build)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--cases")
    r.add_argument("--configs")
    r.add_argument("--trials", type=int, default=3)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--model", default=MODEL, help=f"子のモデル(既定 {MODEL})")
    r.add_argument("--pr", action="store_true",
                   help="PR ありの形で回す(publish.py create で作った検証用の PR を、PR 番号を渡してレビューさせる)")
    r.add_argument("--keep", action="store_true", help="一時ディレクトリ(題材と試行の複製)を残す")
    r.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
