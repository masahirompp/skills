#!/bin/bash
# cycle-rewrite スキル eval 用フィクスチャ生成スクリプト
# 使い捨て私有リポ cycle-rewrite-eval-* を GitHub に作成しシードする
set -euo pipefail

# ワークスペースは CYCLE_REWRITE_WS で上書き可能(既定: ~/.claude/skill-dev/cycle-rewrite-workspace)
WS="${CYCLE_REWRITE_WS:-$HOME/.claude/skill-dev/cycle-rewrite-workspace}/fixtures"
TPL="$WS/templates"
REPOS="$WS/repos"
OWNER="masahirompp"
SUFFIX="${1:-}"   # 例: -i2 (イテレーションごとに新しい使い捨てリポを作る)
# ONLY で作る種類を絞れる(init inbox capture goal impl clean の空白区切り)。既定は全部。
# GitHub はリポジトリの連続作成を制限するので、一部の eval だけ回すときに使う
ONLY="${ONLY:-}"
want() { [ -z "$ONLY" ] || [[ " $ONLY " == *" $1 "* ]]; }

rm -rf "$TPL"
[ -z "$ONLY" ] && rm -rf "$REPOS"
mkdir -p "$TPL"/{init,midcycle,postend} "$REPOS"

# ---------------------------------------------------------------
# 共通: docs/agents/ (setup-matt-pocock-skills 実行済み相当)
# ---------------------------------------------------------------
seed_agents_docs() {
  local dir="$1"
  # setup-matt-pocock-skills はプラグイン配布に移行済み — キャッシュ内の最新バージョンを使う
  local mps
  mps="$(ls -d "$HOME/.claude/plugins/cache/mattpocock/mattpocock-skills"/*/skills/engineering/setup-matt-pocock-skills 2>/dev/null | sort -V | tail -1 || true)"
  [ -n "$mps" ] || { echo "setup-matt-pocock-skills が見つからない (mattpocock-skills プラグインをインストールすること)" >&2; exit 1; }
  mkdir -p "$dir/docs/agents"
  cp "$mps/issue-tracker-github.md" "$dir/docs/agents/issue-tracker.md"
  cp "$mps/triage-labels.md" "$dir/docs/agents/triage-labels.md"
  cp "$mps/domain.md" "$dir/docs/agents/domain.md"
}

AGENT_SKILLS_BLOCK='## Agent skills

### Issue tracker

Issues live in this repo'"'"'s GitHub Issues (uses the `gh` CLI). External PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles map 1:1 to label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.'

# init が CLAUDE.md に追記する規約ブロック。スキルの references/init.md から取り出すので、文言はスキルと常に一致する
SKILL_DIR="$(cd "$(dirname "$0")/../../../plugins/cycle-rewrite/skills/cycle-rewrite" && pwd)"
CYCLE_REWRITE_BLOCK="$(awk '/^```markdown$/{f=1;next} /^```$/{if(f)exit} f' "$SKILL_DIR/references/init.md")"
[ -n "$CYCLE_REWRITE_BLOCK" ] || { echo "references/init.md から規約ブロックを取り出せない" >&2; exit 1; }

# ---------------------------------------------------------------
# テンプレート 1: init (グリーンフィールド)
# ---------------------------------------------------------------
cat > "$TPL/init/README.md" <<'EOF'
# habitto

毎日の習慣を記録するWebアプリ(構想段階)。
EOF
seed_agents_docs "$TPL/init"
printf '%s\n' "$AGENT_SKILLS_BLOCK" > "$TPL/init/CLAUDE.md"

# ---------------------------------------------------------------
# テンプレート 2: midcycle (Shiori、実装の途中) — inbox / capture / impl / clean 用
# ---------------------------------------------------------------
M="$TPL/midcycle"
mkdir -p "$M/docs/adr" "$M/src/import" "$M/tests"
seed_agents_docs "$M"

cat > "$M/README.md" <<'EOF'
# Shiori

タグとピン留めで整理するクライアントサイドのブックマーク管理Webアプリ。
EOF

printf '%s\n\n%s\n' "$AGENT_SKILLS_BLOCK" "$CYCLE_REWRITE_BLOCK" > "$M/CLAUDE.md"

cat > "$M/CONTEXT.md" <<'EOF'
# CONTEXT

## ブックマーク

保存された URL + タイトル + メモの1件。

## タグ

ブックマークに付ける自由記述の分類ラベル。1件のブックマークに複数付けられる。

## フォルダ

ブックマークを入れる階層構造。タグと併存する。

## ピン留め

ブックマークを一覧の先頭に固定する印。
EOF

cat > "$M/docs/PRODUCT.md" <<'EOF'
# Shiori

## Problem Statement

ブラウザのブックマークが増えすぎて、目的のページを再発見できない。

## Solution

タグとピン留めで整理でき、全文検索で再発見できるクライアントサイドのブックマーク管理Webアプリ。

## User Stories

1. As a ブックマーク利用者, I want URLとタイトルを保存できる, so that あとで読み返せる
2. As a ブックマーク利用者, I want ブックマークにタグを付けられる, so that テーマ別に整理できる
3. As a ブックマーク利用者, I want タグで絞り込める, so that 目的のページをすぐ見つけられる
4. As a ブックマーク利用者, I want ブックマークをフォルダに整理できる, so that 階層で管理できる
5. As a ブックマーク利用者, I want よく使うブックマークをピン留めできる, so that 一覧の先頭に固定できる
6. As a ブックマーク利用者, I want タイトルとメモを全文検索できる, so that タグを覚えていなくても見つけられる
7. As a ブックマーク利用者, I want ブラウザからエクスポートしたブックマークHTMLをインポートできる, so that 既存のブックマークを一括で移行できる

## Implementation Decisions

- クライアントサイドのみ、サーバーなし(ADR-0001)
- 保存は IndexedDB(dexie.js)
- 全文検索は Fuse.js のインメモリ検索(ADR-0002)
- ブックマークHTMLのパーサーは自前実装。Chrome / Firefox / Safari の実エクスポートで検証済み

## Testing Decisions

- 外部から観測できる振る舞いのみをテストする
- シナリオ:
  - ブックマークを保存すると一覧に表示される
  - タグで絞り込むと該当ブックマークのみ表示される
  - 検索語を入力するとタイトル一致が上位に表示される
  - ChromeからエクスポートしたブックマークHTMLをインポートすると、全ブックマークが一覧に表示される

## Out of Scope

- ブラウザ拡張(理由: まず Web アプリで価値検証する)
- 複数端末同期(理由: まず単一端末で価値検証する)

## Further Notes

なし
EOF

cat > "$M/docs/adr/0001-client-side-only.md" <<'EOF'
# ADR-0001: クライアントサイドのみで構成する

Status: Accepted

## Context

価値検証段階であり、サーバーの運用コスト・認証実装を避けたい。

## Decision

サーバーを持たず、データは IndexedDB(dexie.js)に保存する。

## Consequences

複数端末同期はできない。エクスポート/インポートで代替する。
EOF

cat > "$M/docs/adr/0002-fuse-js-for-search.md" <<'EOF'
# ADR-0002: 全文検索は Fuse.js を使う

Status: Accepted

## Context

クライアントサイドのみ(ADR-0001)のため、検索もブラウザ内で完結する必要がある。

## Decision

Fuse.js によるインメモリのあいまい検索を採用する。

## Consequences

データ全件をメモリに載せる。件数が増えた場合の性能は未検証。
EOF

cat > "$M/src/db.ts" <<'EOF'
import Dexie, { type Table } from "dexie";

export interface Bookmark {
  id?: number;
  url: string;
  title: string;
  note: string;
  tags: string[];
  pinned: boolean;
}

export class ShioriDB extends Dexie {
  bookmarks!: Table<Bookmark>;
  constructor() {
    super("shiori");
    this.version(1).stores({ bookmarks: "++id, title, *tags, pinned" });
  }
}

export const db = new ShioriDB();
EOF

cat > "$M/src/tags.ts" <<'EOF'
import { db, type Bookmark } from "./db";

// 動けばOK品質
export async function addTag(bookmark: Bookmark, tag: string) {
  bookmark.tags.push(tag);
  await db.bookmarks.put(bookmark);
}

export async function listTags(): Promise<string[]> {
  const all = await db.bookmarks.toArray();
  return all.flatMap((b) => b.tags);
}
EOF

cat > "$M/src/search.ts" <<'EOF'
import Fuse from "fuse.js";
import { db, type Bookmark } from "./db";

export async function search(query: string): Promise<Bookmark[]> {
  const all = await db.bookmarks.toArray();
  const fuse = new Fuse(all, { keys: ["title", "note"] });
  return fuse.search(query).map((r) => r.item);
}
EOF

cat > "$M/src/import/bookmark-html.ts" <<'EOF'
// ブラウザのブックマークエクスポート(Netscape Bookmark File Format)のパーサー。
// Chrome / Firefox / Safari の実エクスポートで検証済み。
// 使い捨て層に依存しない純関数。db やアプリの型を import しないこと。

export interface ParsedBookmark {
  url: string;
  title: string;
  addedAt?: Date;
}

export function parseBookmarkHtml(html: string): ParsedBookmark[] {
  const results: ParsedBookmark[] = [];
  const anchor = /<DT><A[^>]*HREF="([^"]*)"(?:[^>]*ADD_DATE="(\d+)")?[^>]*>([\s\S]*?)<\/A>/gi;
  let m: RegExpExecArray | null;
  while ((m = anchor.exec(html)) !== null) {
    const [, url, addDate, rawTitle] = m;
    if (!url || url.startsWith("place:")) continue; // Firefox の内部エントリ(place:)を除外
    results.push({
      url,
      title: decodeEntities(rawTitle.trim()) || url,
      addedAt: addDate ? new Date(Number(addDate) * 1000) : undefined,
    });
  }
  return results;
}

function decodeEntities(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}
EOF

cat > "$M/tests/bookmark-html.test.ts" <<'EOF'
import { describe, it, expect } from "vitest";
import { parseBookmarkHtml } from "../src/import/bookmark-html";

describe("parseBookmarkHtml", () => {
  it("parses a Chrome export anchor", () => {
    const html =
      '<DT><A HREF="https://example.com" ADD_DATE="1700000000">Example &amp; Co</A>';
    const [b] = parseBookmarkHtml(html);
    expect(b.url).toBe("https://example.com");
    expect(b.title).toBe("Example & Co");
  });

  it("skips Firefox place: entries", () => {
    expect(parseBookmarkHtml('<DT><A HREF="place:type=6">Recent</A>')).toEqual([]);
  });
});
EOF

cat > "$M/src/main.ts" <<'EOF'
import { db } from "./db";
import { search } from "./search";
import { parseBookmarkHtml } from "./import/bookmark-html";

async function render() {
  const list = await db.bookmarks.orderBy("pinned").reverse().toArray();
  const ul = document.querySelector("#list")!;
  ul.innerHTML = list.map((b) => `<li>${b.title}</li>`).join("");
}

document.querySelector("#q")?.addEventListener("input", async (e) => {
  const hits = await search((e.target as HTMLInputElement).value);
  console.log(hits);
});

document.querySelector("#import")?.addEventListener("change", async (e) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const parsed = parseBookmarkHtml(await file.text());
  await db.bookmarks.bulkPut(
    parsed.map((p) => ({ url: p.url, title: p.title, note: "", tags: [], pinned: false })),
  );
  render();
});

render();
EOF

cat > "$M/tests/search.test.ts" <<'EOF'
import { describe, it, expect } from "vitest";
import { search } from "../src/search";

describe("search", () => {
  it("returns empty for empty db", async () => {
    expect(await search("foo")).toEqual([]);
  });
});
EOF

cat > "$M/package.json" <<'EOF'
{
  "name": "shiori",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "echo 'build ok'",
    "lint": "echo 'lint ok'",
    "test": "echo 'tests ok'"
  },
  "dependencies": {
    "dexie": "^4.0.0",
    "fuse.js": "^7.0.0"
  }
}
EOF

cat > "$M/tsconfig.json" <<'EOF'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true
  },
  "include": ["src", "tests"]
}
EOF

cat > "$M/.prettierrc" <<'EOF'
{ "semi": true, "singleQuote": false }
EOF

# ---------------------------------------------------------------
# テンプレート 3: postend (Shiori、棚卸しを済ませて使い捨て層を消した直後) — goal 用
# 反映済み: src/tests 削除、CONTEXT.md からフォルダ剪定、
# Out of Scope に CSV/フォルダ、ADR-0002 は Rejected、dexie スキル抽出、並列2ルール
# ---------------------------------------------------------------
P="$TPL/postend"
mkdir -p "$P/docs/adr" "$P/.claude/skills/working-with-dexie"
seed_agents_docs "$P"
cp "$M/README.md" "$P/README.md"
cp "$M/docs/adr/0001-client-side-only.md" "$P/docs/adr/0001-client-side-only.md"
cat > "$P/.claude/skills/working-with-dexie/SKILL.md" <<'EOF'
---
name: working-with-dexie
description: dexie.js(IndexedDB)を扱うときの注意点。src/db.ts など dexie を使うコードの追加・変更時に必ず読む。
---

# working-with-dexie

- 大量 insert は `put()` のループではなく `bulkPut()` を使う(10倍以上速い)
- Dexie のトランザクション内で外部の Promise を await するとトランザクションが即コミットされる。トランザクション内は Dexie の操作だけにする
- Safari のプライベートブラウズでは IndexedDB が例外を投げる。起動時に検出して localStorage フォールバックに切り替える
EOF
cp "$M/.prettierrc" "$P/.prettierrc"

printf '%s\n\n%s\n\n### プロセスルール\n\n- エージェントの並列作業は2並列まで(3並列以上で main が壊れた実績があるため)\n' \
  "$AGENT_SKILLS_BLOCK" "$CYCLE_REWRITE_BLOCK" > "$P/CLAUDE.md"

cat > "$P/CONTEXT.md" <<'EOF'
# CONTEXT

## ブックマーク

保存された URL + タイトル + メモの1件。

## タグ

ブックマークに付ける自由記述の分類ラベル。1件のブックマークに複数付けられる。

## ピン留め

ブックマークを一覧の先頭に固定する印。
EOF

cat > "$P/docs/PRODUCT.md" <<'EOF'
# Shiori

## Problem Statement

ブラウザのブックマークが増えすぎて、目的のページを再発見できない。

## Solution

タグとピン留めで整理でき、全文検索で再発見できるクライアントサイドのブックマーク管理Webアプリ。

## User Stories

1. As a ブックマーク利用者, I want URLとタイトルを保存できる, so that あとで読み返せる
2. As a ブックマーク利用者, I want ブックマークにタグを付けられる, so that テーマ別に整理できる
3. As a ブックマーク利用者, I want タグで絞り込める, so that 目的のページをすぐ見つけられる
4. As a ブックマーク利用者, I want よく使うブックマークをピン留めできる, so that 一覧の先頭に固定できる
5. As a ブックマーク利用者, I want タイトルとメモを全文検索できる, so that タグを覚えていなくても見つけられる

## Implementation Decisions

- クライアントサイドのみ、サーバーなし(ADR-0001)
- 保存は IndexedDB(dexie.js)
- 全文検索の方式は未決 — Fuse.js のインメモリ検索は不採用(ADR-0002 Rejected。5000件超でUIブロック)。次の作り直しで再設計する

## Testing Decisions

- 外部から観測できる振る舞いのみをテストする
- シナリオ:
  - ブックマークを保存すると一覧に表示される
  - タグで絞り込むと該当ブックマークのみ表示される
  - 検索語を入力するとタイトル一致が上位に表示される
  - IndexedDB が使えない環境(Safari プライベートブラウズ)では localStorage にフォールバックして保存できる

## Out of Scope

- ブラウザ拡張(理由: まず Web アプリで価値検証する)
- 複数端末同期(理由: まず単一端末で価値検証する)
- CSVインポート(理由: ユーザーはブラウザのブックマークHTMLエクスポートしか使わない)
- フォルダ機能(理由: ユーザーテストでタグとの併存が混乱を招いた。タグに一本化)

## Further Notes

なし
EOF

cat > "$P/docs/adr/0002-fuse-js-for-search.md" <<'EOF'
# ADR-0002: 全文検索は Fuse.js を使う

Status: Rejected

## Context

クライアントサイドのみ(ADR-0001)のため、検索もブラウザ内で完結する必要がある。

## Decision

Fuse.js によるインメモリのあいまい検索を採用する。

## Consequences

計測で 5000 件超で UI が1秒以上ブロックすることが判明し、不採用となった。代替方式は次の作り直しで設計する。
EOF

# ---------------------------------------------------------------
# リポジトリ生成
# ---------------------------------------------------------------
create_repo() { # $1=template $2=repo-name
  local dir="$REPOS/$2"
  rm -rf "$dir"
  cp -R "$TPL/$1" "$dir"
  cd "$dir"
  git init -q -b main
  git add -A
  git commit -qm "initial state"
  gh repo create "$OWNER/$2" --private --source . --push >/dev/null
  echo "created $OWNER/$2"
}

seed_workflow_labels() { # $1=repo-name
  local r="$OWNER/$1"
  gh label create learning --color FBCA04 --description "実装・確認で得た学び" -R "$r" >/dev/null
  gh label create spec-change --color D93F0B --description "仕様変更・要件の判明" -R "$r" >/dev/null
  gh label create decision-log --color 0E8A16 --description "AI の内部設計判断の記録(自律判断 層1)" -R "$r" >/dev/null
  for l in needs-triage needs-info ready-for-agent ready-for-human; do
    gh label create "$l" --color CCCCCC -R "$r" >/dev/null
  done
}

# 受信箱の issue は、本文の最後に起票したときの作業ブランチを `branch: <名前>` の1行で持つ
issue() { # $1=repo $2=label $3=title $4=body $5=branch(省略時 main。"-" なら branch: の行を付けない)
  local body="$4" b="${5:-main}"
  [ "$b" = "-" ] || body="$body

branch: $b"
  gh issue create -R "$OWNER/$1" --label "$2" --title "$3" --body "$body" >/dev/null
}

# issue list は作成直後に反映が遅れることがあるため、closed が期待の件数になるまで再試行する
# (open が空かどうかで終えると、一覧にまだ出ていないだけの issue を閉じ残す)
close_all_issues() { # $1=repo-name $2=comment $3=期待する件数
  local nums closed
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    nums=$(gh issue list -R "$OWNER/$1" --state open --json number --jq '.[].number')
    [ -z "$nums" ] || echo "$nums" | xargs -I{} gh issue close {} -R "$OWNER/$1" -c "$2" >/dev/null
    closed=$(gh issue list -R "$OWNER/$1" --state closed --json number --jq 'length')
    [ "${closed:-0}" -ge "$3" ] && return 0
    sleep 2
  done
  echo "close_all_issues: $1 の closed が $3 件に届かない(${closed:-0} 件)" >&2
  return 1
}

# 番号は起票順(#1〜#7)。eval の assertion がこの番号を参照する
seed_midcycle_issues() { # $1=repo-name
  local r="$1"
  issue "$r" spec-change "CSVインポートは不要と判明" \
    "ユーザーテストの結果、全員がブラウザのブックマークHTMLエクスポートを使っており、CSVを持っている人はいなかった。CSVインポートはやらない。"
  issue "$r" learning "SafariプライベートブラウズではIndexedDBが使えない" \
    "Safariのプライベートブラウズで起動時に例外。IndexedDBが使えない環境ではlocalStorageフォールバックが必要、という要件が新たに判明した。"
  issue "$r" learning "dexie.jsのハマり: bulkPut必須・トランザクション内awaitの罠" \
    "put()のループはbulkPut()の10倍以上遅い。また、Dexieのトランザクション内で外部のPromiseをawaitするとトランザクションが即コミットされる。コードを書き直しても同じ罠を踏みそう。"
  issue "$r" learning "Fuse.jsによる全文検索は5000件超で破綻" \
    "計測したところ5000件超でUIが1秒以上ブロックする。Fuse.js案(ADR-0002)は不採用にすべき。保存時に検索インデックスを別に構築する設計が必要。"
  issue "$r" learning "エージェント3並列でmainが2回壊れた" \
    "エージェントを3並列で走らせたら、マージ順の競合でmainが起動しない状態が2回発生した。並列度は2までに制限すべき。進め方のルールとして残したい。"
  issue "$r" spec-change "フォルダ機能は廃止、タグに一本化" \
    "ユーザーテストでフォルダとタグの併存が混乱を招いた。フォルダはやらない。タグに一本化する。"
  issue "$r" decision-log "日付表示をdate-fnsからIntl.DateTimeFormatに内部変更" \
    "バンドルサイズ削減のためdate-fnsをやめてIntl.DateTimeFormatに内部変更した。外部から見える挙動は変わらない。"
}

# --- init 用 (シードは repo のみ。ラベルは init モードが作るのが期待動作) ---
if want init; then
  create_repo init "cycle-rewrite-eval-init-with$SUFFIX"
  create_repo init "cycle-rewrite-eval-init-base$SUFFIX"
fi

# --- midcycle を使う4種 ---
#   inbox:   受信箱に8件(うち1件は暫定)が残ったまま、作り直しを頼まれる
#   capture: 受信箱は空。動作確認で見つけたバグを起票する
#   impl:    実装して完了報告の前に棚卸しをする。別のブランチの issue が1件ある
#   clean:   受信箱は空。今の仕様のまま作り直しを頼まれる。受信箱ではない普通の issue が1件ある
for kind in inbox capture impl clean; do
  want "$kind" || continue
  for cfg in with base; do
    name="cycle-rewrite-eval-$kind-$cfg$SUFFIX"
    create_repo midcycle "$name"
    seed_workflow_labels "$name"
    case "$kind" in
      inbox)
        seed_midcycle_issues "$name"
        # 実装セッションが層2で暫定の挙動を採った記録(#8)。確定を人間に聞くかを見る
        issue "$name" spec-change "暫定: ブックマークHTMLの再インポートで、同じURLは重複して追加する" \
          "実装中に、保存済みと同じURLを含むHTMLをインポートしたときの挙動が PRODUCT.md・ADR・CONTEXT.md のどこにも定められていないと判明した(暗黙の要件の発覚)。

選択肢:
- 案A: 既存を残して、同じURLはスキップする
- 案B: 既存のタイトルを、インポートした内容で上書きする
- 案C: 重複して追加する

暫定で案C(今の実装のまま)を採った。確定は人間が行う。"
        ;;
      impl)
        # 並行して動く別の作業の issue(#1)。完了報告の前の棚卸しが触らないことを見る
        issue "$name" learning "同期の再試行はexponential backoffが必要" \
          "同期の試作で、オフライン復帰直後に同期リクエストが連続失敗した。再試行はexponential backoffにする必要がある。" \
          spike/sync
        ;;
      clean)
        # 受信箱のラベルが無い普通の issue(#1)。作り直しを止めず、閉じられもしないことを見る
        gh label create bug --color D73A4A --force -R "$OWNER/$name" >/dev/null
        issue "$name" bug "ピン留めしたブックマークが一覧の先頭に来ないことがある" \
          "再現条件は未調査。あとで直す。" -
        ;;
    esac
  done
done

# --- postend 用 (goal: 目的のある作り直し) ---
# 使い捨て層は消してあり、受信箱は空。旧構成のタグ cycle-1 が残っている(既存プロジェクトの移行後を再現)。
# close 済みの issue に以前の情報(検索インデックス案等)を意図的に残し、閉じた issue を仕様のインプットにしないことを見る
for name in "cycle-rewrite-eval-goal-with$SUFFIX" "cycle-rewrite-eval-goal-base$SUFFIX"; do
  want goal || continue
  create_repo postend "$name"
  cd "$REPOS/$name"
  git tag cycle-1
  git push -q --tags
  seed_workflow_labels "$name"
  seed_midcycle_issues "$name"
  close_all_issues "$name" "棚卸し済み" 7
done

echo "done"
