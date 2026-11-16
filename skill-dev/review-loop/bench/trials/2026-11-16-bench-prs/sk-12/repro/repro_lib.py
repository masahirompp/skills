"""再現の共通部分。対象のルートの review_loop.py を読み込み(バイトコードは書かない)、偽の claude で子を動かす。"""
import json, os, subprocess, sys, tempfile
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def load(root):
    scripts = os.path.join(root, "skills/review-loop/scripts")
    if not os.path.isfile(os.path.join(scripts, "review_loop.py")):
        print(f"前提のファイルがない: {scripts}/review_loop.py"); sys.exit(2)
    sys.path.insert(0, scripts)
    import review_loop as r
    r.POLL_SECONDS = 0.05
    r.log = lambda msg: None  # 進捗の行で結果が読みにくくなるので出さない
    r.watched = lambda args, timeout: args  # 見張り役(1秒ごとに確かめる)を挟まず、再現を速くする
    return r


def result(text, **extra):
    d = {"type": "result", "subtype": "success", "is_error": False, "result": text, "permission_denials": [],
         "modelUsage": {"m": {"inputTokens": 1, "outputTokens": 1}}}
    d.update(extra)
    return {"emit": d}


class Case:
    def __init__(self, r, files):
        self.r = r
        self.dir = tempfile.mkdtemp(prefix="case.", dir=os.path.join(HERE, "out"))
        self.workdir = os.path.join(self.dir, "wd"); os.makedirs(self.workdir)
        self.casedir = os.path.join(self.dir, "case"); os.makedirs(self.casedir)
        for name, steps in files.items():
            with open(os.path.join(self.casedir, name + ".json"), "w") as f:
                json.dump(steps, f, ensure_ascii=False)
        self.env = dict(os.environ, PATH=os.path.join(HERE, "fake") + os.pathsep + os.environ["PATH"],
                        REPRO_CASE=self.casedir)
        self.children = r.Children()
        self.attempt = {"tokens": r.new_tokens()}

    def reviews(self):
        try:
            return self.r.run_reviews(self.dir, self.env, {"number": 7}, self.workdir, self.children, self.attempt)
        finally:
            self.children.kill_all()

    def judge(self, reviews=None):
        if reviews is None:  # 判定役への入力は、本物の run_reviews で作る(形を再現の側で決めない)
            reviews = self.reviews()
        try:
            return self.r.run_judge(self.dir, self.env, 7, reviews, self.workdir,
                                    self.children, self.attempt)
        finally:
            self.children.kill_all()

    def read(self, name):
        p = os.path.join(self.workdir, name)
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


class Report:
    def __init__(self):
        self.bad = 0

    def __call__(self, label, ok, seen=""):
        print(("守られている  " if ok else "症状を見た    ") + label + ("" if ok else f"\n    見たもの: {seen!r}"))
        self.bad += not ok

    def run(self, f):
        """f を実行し、症状と関係のない例外で落ちたら、実行できなかったとして終了コード2で終わる。"""
        try:
            f()
        except Exception:
            import traceback; traceback.print_exc()
            print("実行できなかった"); sys.exit(2)
        self.exit()

    def exit(self):
        sys.exit(1 if self.bad else 0)
