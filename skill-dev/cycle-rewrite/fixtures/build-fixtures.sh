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

rm -rf "$TPL" "$REPOS"
mkdir -p "$TPL"/{init,midcycle,converging,postend} "$REPOS"

# ---------------------------------------------------------------
# 共通: docs/agents/ (setup-matt-pocock-skills 実行済み相当)
# ---------------------------------------------------------------
seed_agents_docs() {
  local dir="$1"
  mkdir -p "$dir/docs/agents"
  cp "$HOME/.claude/skills/setup-matt-pocock-skills/issue-tracker-github.md" "$dir/docs/agents/issue-tracker.md"
  cp "$HOME/.claude/skills/setup-matt-pocock-skills/triage-labels.md" "$dir/docs/agents/triage-labels.md"
  cp "$HOME/.claude/skills/setup-matt-pocock-skills/domain.md" "$dir/docs/agents/domain.md"
}

AGENT_SKILLS_BLOCK='## Agent skills

### Issue tracker

Issues live in this repo'"'"'s GitHub Issues (uses the `gh` CLI). External PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles map 1:1 to label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.'

CYCLE_REWRITE_BLOCK='## サイクル型リライト開発(cycle-rewrite)

このプロジェクトはサイクル型リライト方式で開発する。サイクルの開始・終了・移行判断は cycle-rewrite スキルに従う。

### 層の定義

- 永続層: `docs/`(PRODUCT.md、adr/)、`CONTEXT.md`、`.claude/skills/`、CLAUDE.md、昇格済みモジュール: `lib/` — 厳格に維持する
- 使い捨て層: `src/` とテストコード — サイクル末に全削除する。品質は「動けばOK」

パスは init で確定した値。cycle-end の削除対象はこの定義を正とする。コードは雑に、ドキュメントは厳格に。

仕様が収束したモジュールは、cycle-end で人間の承認を経て `lib/` に昇格し、以後は永続層として厳格に維持する(テストを持ち越し、インターフェース契約を docs に置く)。依存方向は使い捨て層 → 昇格モジュールの一方向のみ。

**使い捨て層の削除は cycle-end の儀式の中でのみ行う**: issue 棚卸しの完了 → `git tag cycle-N` の作成 → 人間の明示的な承認、を必ずこの順で経ること。タグ前・承認前の削除は、学びと復元手段を同時に失う。

### AI の自律判断(3層)

1. **内部設計の変更**(外から見える挙動が変わらない): 自律で進めてよい。ただし判断内容を `decision-log` ラベル付き issue に記録し、確認フェーズで一括報告する。
2. **観測可能な挙動・仕様の変更**: 人間へのエスカレーション必須。質問は「挙動 A と挙動 B のどちらが欲しいか」というドメイン語の二択で行う。コードの理解を要求する質問はしない。二択で表現できない変更は層1として扱う。
3. **不可逆・外部影響**(課金、外部 API 契約、データ破壊等): 常に同期エスカレーション。例外なし。

### 学びの捕捉

実装・確認中に得た学び(エッジケース、想定外挙動、暗黙の要件、ライブラリのハマり)は発見の都度 GitHub issue に起票する。ラベル(`bug` / `learning` / `spec-change` / `decision-log`)+ 現在サイクルのマイルストーンを付ける。issue は受信箱であり、次サイクルのインプットは蒸留済み docs のみ。

### ブランチ・マージ方針

- PR は使わない。短命ブランチ(worktree)で作業し、ローカルチェック(build/lint、テストがあればテスト)通過を条件にローカルで main にマージする
- 不変条件: main は常に起動する

### ADR の基準

「覆すのが難しい判断のみ書く」は本プロジェクトでは「**サイクルを跨いでも覆らないか**」で解釈する。捨てる予定のコードに紐づく実装レベルの判断は ADR にしない(`decision-log` issue でよい)。

### 旧サイクルコードの参照

旧サイクルのコードを作業ツリーに置かない。参照が必要なら `git show cycle-N:src/...` か、作業ツリー外への `git worktree` を使う。'

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
# テンプレート 2: midcycle (Shiori、サイクル1進行中) — cycle-end / capture 用
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

<!-- last updated: cycle 1 -->

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
- 複数端末同期(理由: サイクル1では単一端末で十分)

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
// Chrome / Firefox / Safari の実エクスポートで検証済み(cycle 1)。
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
# テンプレート 3: converging (Shiori、サイクル3進行中・収束期) — transition-check 用
# ---------------------------------------------------------------
C="$TPL/converging"
mkdir -p "$C/docs/adr" "$C/src" "$C/.claude/skills/working-with-dexie"
seed_agents_docs "$C"
cp "$M/README.md" "$C/README.md"
cp "$M/src/db.ts" "$C/src/db.ts"
cp "$M/src/tags.ts" "$C/src/tags.ts"
cp "$M/src/main.ts" "$C/src/main.ts"
cp "$M/package.json" "$C/package.json"
cp "$M/tsconfig.json" "$C/tsconfig.json"
cp "$M/.prettierrc" "$C/.prettierrc"
cp "$M/docs/adr/0001-client-side-only.md" "$C/docs/adr/0001-client-side-only.md"

printf '%s\n\n%s\n\n### プロセスルール(cycle 1 の学び)\n\n- エージェントの並列作業は2並列まで(3並列以上で main が壊れた実績があるため)\n' \
  "$AGENT_SKILLS_BLOCK" "$CYCLE_REWRITE_BLOCK" > "$C/CLAUDE.md"

cat > "$C/CONTEXT.md" <<'EOF'
# CONTEXT

## ブックマーク

保存された URL + タイトル + メモの1件。

## タグ

ブックマークに付ける自由記述の分類ラベル。1件のブックマークに複数付けられる。

## ピン留め

ブックマークを一覧の先頭に固定する印。

## 同期

複数端末間でブックマークを Supabase 経由で一致させること。
EOF

cat > "$C/docs/PRODUCT.md" <<'EOF'
# Shiori

<!-- last updated: cycle 3 -->

## Problem Statement

ブラウザのブックマークが増えすぎて、目的のページを再発見できない。複数端末で使うと分断される。

## Solution

タグとピン留めで整理でき、全文検索で再発見でき、複数端末で同期できるブックマーク管理Webアプリ。

## User Stories

1. As a ブックマーク利用者, I want URLとタイトルを保存できる, so that あとで読み返せる
2. As a ブックマーク利用者, I want ブックマークにタグを付けられる, so that テーマ別に整理できる
3. As a ブックマーク利用者, I want タグで絞り込める, so that 目的のページをすぐ見つけられる
4. As a ブックマーク利用者, I want よく使うブックマークをピン留めできる, so that 一覧の先頭に固定できる
5. As a ブックマーク利用者, I want タイトルとメモを全文検索できる, so that タグを覚えていなくても見つけられる
6. As a 複数端末の利用者, I want 端末間でブックマークが同期される, so that どの端末でも同じ一覧が見られる

## Implementation Decisions

- ローカルファースト: 保存は IndexedDB(dexie.js)、同期は Supabase(ADR-0004)
- 全文検索は事前構築した検索インデックスを IndexedDB に持つ(ADR-0003。Fuse.js 案は ADR-0002 で不採用)
- 同期の競合解決は last-write-wins

## Testing Decisions

- 外部から観測できる振る舞いのみをテストする
- シナリオ:
  - ブックマークを保存すると一覧に表示される
  - タグで絞り込むと該当ブックマークのみ表示される
  - 検索語を入力するとタイトル一致が上位に表示される
  - 端末Aで保存したブックマークが端末Bに反映される
  - オフラインで保存した変更がオンライン復帰後に同期される

## Out of Scope

- ブラウザ拡張(理由: まず Web アプリで価値検証する)
- フォルダ機能(理由: cycle 1 のユーザーテストでタグとの併存が混乱を招いた。タグに一本化)
- CSVインポート(理由: ユーザーはブラウザのブックマークHTMLエクスポートしか使わない)
- リアルタイム共同編集(理由: 個人利用が対象)

## Further Notes

なし
EOF

cat > "$C/docs/adr/0002-fuse-js-for-search.md" <<'EOF'
# ADR-0002: 全文検索は Fuse.js を使う

Status: Superseded by ADR-0003

## Context

クライアントサイドのみのため、検索もブラウザ内で完結する必要がある。

## Decision

Fuse.js によるインメモリのあいまい検索を採用する。

## Consequences

cycle 1 の計測で 5000 件超で UI がブロックすることが判明し、ADR-0003 に置き換えられた。
EOF

cat > "$C/docs/adr/0003-prebuilt-search-index.md" <<'EOF'
# ADR-0003: 全文検索は事前構築インデックスを使う

Status: Accepted

## Context

Fuse.js のインメモリ検索(ADR-0002)は 5000 件超で UI をブロックした。

## Decision

保存時にトークン化した検索インデックスを IndexedDB に持ち、検索はインデックス参照のみで行う。

## Consequences

保存時に若干のコストがかかる。検索は件数に対してほぼ一定時間。
EOF

cat > "$C/docs/adr/0004-supabase-for-sync.md" <<'EOF'
# ADR-0004: 同期バックエンドは Supabase を使う

Status: Accepted

## Context

cycle 2 で複数端末同期が最重要要件と判明した。自前サーバーの運用は避けたい。

## Decision

Supabase(Postgres + RLS)を同期バックエンドに採用する。ローカルファーストは維持し、IndexedDB を正とする。

## Consequences

Supabase の課金・RLS 設計に依存する。本番プロジェクトへの実データ投入以降はスキーマ変更のコストが上がる。
EOF

cat > "$C/.claude/skills/working-with-dexie/SKILL.md" <<'EOF'
---
name: working-with-dexie
description: dexie.js(IndexedDB)を扱うときの注意点。src/db.ts など dexie を使うコードの追加・変更時に必ず読む。
---

# working-with-dexie

- 大量 insert は `put()` のループではなく `bulkPut()` を使う(10倍以上速い)
- Dexie のトランザクション内で外部の Promise を await するとトランザクションが即コミットされる。トランザクション内は Dexie の操作だけにする
- Safari のプライベートブラウズでは IndexedDB が例外を投げる。起動時に検出して localStorage フォールバックに切り替える
EOF

cat > "$C/src/sync.ts" <<'EOF'
import { db } from "./db";

// 動けばOK品質: Supabase 同期のスケッチ
export async function pushChanges() {
  const all = await db.bookmarks.toArray();
  await fetch(import.meta.env.VITE_SUPABASE_URL + "/rest/v1/bookmarks", {
    method: "POST",
    body: JSON.stringify(all),
  });
}
EOF

cat > "$C/src/search.ts" <<'EOF'
import { db, type Bookmark } from "./db";

// 事前構築インデックス(ADR-0003)の雑な実装
export async function search(query: string): Promise<Bookmark[]> {
  const all = await db.bookmarks.toArray();
  return all.filter((b) => b.title.includes(query) || b.note.includes(query));
}
EOF

# ---------------------------------------------------------------
# テンプレート 4: postend (Shiori、サイクル1の儀式完了直後) — cycle-start 用
# 儀式の成果を反映済み: src/tests 削除、CONTEXT.md からフォルダ剪定、
# Out of Scope に CSV/フォルダ、ADR-0002 は Rejected、dexie スキル抽出、並列2ルール
# ---------------------------------------------------------------
P="$TPL/postend"
mkdir -p "$P/docs/adr" "$P/.claude/skills/working-with-dexie"
seed_agents_docs "$P"
cp "$M/README.md" "$P/README.md"
cp "$M/docs/adr/0001-client-side-only.md" "$P/docs/adr/0001-client-side-only.md"
cp "$C/.claude/skills/working-with-dexie/SKILL.md" "$P/.claude/skills/working-with-dexie/SKILL.md"
cp "$M/.prettierrc" "$P/.prettierrc"

printf '%s\n\n%s\n\n### プロセスルール(cycle 1 の学び)\n\n- エージェントの並列作業は2並列まで(3並列以上で main が壊れた実績があるため)\n' \
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

<!-- last updated: cycle 1 -->

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
- 全文検索の方式は未決 — Fuse.js のインメモリ検索は cycle 1 で不採用(ADR-0002 Rejected。5000件超でUIブロック)。次サイクルで再設計する

## Testing Decisions

- 外部から観測できる振る舞いのみをテストする
- シナリオ:
  - ブックマークを保存すると一覧に表示される
  - タグで絞り込むと該当ブックマークのみ表示される
  - 検索語を入力するとタイトル一致が上位に表示される
  - IndexedDB が使えない環境(Safari プライベートブラウズ)では localStorage にフォールバックして保存できる

## Out of Scope

- ブラウザ拡張(理由: まず Web アプリで価値検証する)
- 複数端末同期(理由: サイクル1では単一端末で十分)
- CSVインポート(理由: ユーザーはブラウザのブックマークHTMLエクスポートしか使わない)
- フォルダ機能(理由: cycle 1 のユーザーテストでタグとの併存が混乱を招いた。タグに一本化)

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

cycle 1 の計測で 5000 件超で UI が1秒以上ブロックすることが判明し、不採用となった。代替方式は次サイクルで設計する。
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

create_milestone() { # $1=repo-name $2=title $3=state(optional)
  gh api -X POST "repos/$OWNER/$1/milestones" -f title="$2" ${3:+-f state="$3"} --jq .number
}

issue() { # $1=repo $2=milestone-title $3=label $4=title $5=body
  gh issue create -R "$OWNER/$1" --milestone "$2" --label "$3" --title "$4" --body "$5" >/dev/null
}

seed_midcycle_issues() { # $1=repo-name
  local r="$1"
  issue "$r" cycle-1 spec-change "CSVインポートは不要と判明" \
    "ユーザーテストの結果、全員がブラウザのブックマークHTMLエクスポートを使っており、CSVを持っている人はいなかった。CSVインポートはやらない。"
  issue "$r" cycle-1 learning "SafariプライベートブラウズではIndexedDBが使えない" \
    "Safariのプライベートブラウズで起動時に例外。IndexedDBが使えない環境ではlocalStorageフォールバックが必要、という要件が新たに判明した。"
  issue "$r" cycle-1 learning "dexie.jsのハマり: bulkPut必須・トランザクション内awaitの罠" \
    "put()のループはbulkPut()の10倍以上遅い。また、Dexieのトランザクション内で外部のPromiseをawaitするとトランザクションが即コミットされる。コードを書き直しても次サイクルで同じ罠を踏みそう。"
  issue "$r" cycle-1 learning "Fuse.jsによる全文検索は5000件超で破綻" \
    "計測したところ5000件超でUIが1秒以上ブロックする。Fuse.js案(ADR-0002)は不採用にすべき。次サイクルでは保存時に検索インデックスを別に構築する設計が必要。"
  issue "$r" cycle-1 learning "エージェント3並列でmainが2回壊れた" \
    "エージェントを3並列で走らせたら、マージ順の競合でmainが起動しない状態が2回発生した。並列度は2までに制限すべき。進め方のルールとして残したい。"
  issue "$r" cycle-1 spec-change "フォルダ機能は廃止、タグに一本化" \
    "ユーザーテストでフォルダとタグの併存が混乱を招いた。フォルダはやらない。タグに一本化する。"
  issue "$r" cycle-1 decision-log "日付表示をdate-fnsからIntl.DateTimeFormatに内部変更" \
    "バンドルサイズ削減のためdate-fnsをやめてIntl.DateTimeFormatに内部変更した。外部から見える挙動は変わらない。"
}

seed_converging_issues() { # $1=repo-name
  local r="$1"
  issue "$r" cycle-3 learning "同期の再試行はexponential backoffが必要" \
    "オフライン復帰直後に同期リクエストが連続失敗する。再試行はexponential backoffにする必要がある。"
  issue "$r" cycle-3 decision-log "同期キューをメモリからIndexedDBに内部変更" \
    "タブを閉じると未送信の変更が消えるため、同期キューをIndexedDBに永続化する内部変更を行った。外部から見える挙動は変わらない。"
  issue "$r" cycle-3 learning "Supabase RLSポリシーはローカル環境と挙動差がある" \
    "supabase start のローカル環境では通るRLSポリシーが、リンクした環境では拒否されるケースがあった。ポリシーはリンク環境でも検証が必要。"
}

# --- init 用 (シードは repo のみ。ラベル・マイルストーンは init モードが作るのが期待動作) ---
create_repo init "cycle-rewrite-eval-init-with$SUFFIX"
create_repo init "cycle-rewrite-eval-init-base$SUFFIX"

# --- midcycle 用 (cycle-end / capture) ---
for name in "cycle-rewrite-eval-end-with$SUFFIX" "cycle-rewrite-eval-end-base$SUFFIX" "cycle-rewrite-eval-capture-with$SUFFIX" "cycle-rewrite-eval-capture-base$SUFFIX"; do
  create_repo midcycle "$name"
  seed_workflow_labels "$name"
  create_milestone "$name" cycle-1 >/dev/null
  seed_midcycle_issues "$name"
done

# --- converging 用 (transition-check) ---
for name in "cycle-rewrite-eval-trans-with$SUFFIX" "cycle-rewrite-eval-trans-base$SUFFIX"; do
  create_repo converging "$name"
  cd "$REPOS/$name"
  # cycle-1 / cycle-2 のタグ履歴を再現
  git tag cycle-1
  git commit -q --allow-empty -m "cycle 2 end"
  git tag cycle-2
  git commit -q --allow-empty -m "cycle 3 wip"
  git push -q && git push -q --tags
  seed_workflow_labels "$name"
  create_milestone "$name" cycle-1 closed >/dev/null
  create_milestone "$name" cycle-2 closed >/dev/null
  create_milestone "$name" cycle-3 >/dev/null
  seed_converging_issues "$name"
done

# --- postend 用 (cycle-start) ---
# タグ cycle-1・マイルストーン close・issue 全 close の「儀式完了直後」状態。
# close 済み issue に旧サイクルの情報(検索インデックス案等)を意図的に残し、
# cycle-start が旧 issue を読まない規律を検証できるようにする
for name in "cycle-rewrite-eval-start-with$SUFFIX" "cycle-rewrite-eval-start-base$SUFFIX"; do
  create_repo postend "$name"
  cd "$REPOS/$name"
  git tag cycle-1
  git push -q --tags
  seed_workflow_labels "$name"
  MS_NUM=$(create_milestone "$name" cycle-1)
  seed_midcycle_issues "$name"
  for n in $(gh issue list -R "$OWNER/$name" --json number --jq '.[].number'); do
    gh issue close "$n" -R "$OWNER/$name" >/dev/null
  done
  gh api -X PATCH "repos/$OWNER/$name/milestones/$MS_NUM" -f state=closed --jq .state >/dev/null
done

echo "done"
