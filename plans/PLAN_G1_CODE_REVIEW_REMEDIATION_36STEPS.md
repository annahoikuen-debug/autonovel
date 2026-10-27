# AutoNovel コードレビュー整改計画書【G1 / 36 ステップ・2 サブエージェント分割】

## ── 「緑だが意味が無いテスト」を根絶し、本番を壊す 4 件の S1 を潰す ──

- **文書ID**: `PLAN_G1_CODE_REVIEW_REMEDIATION_36STEPS`
- **作成日**: 2026-10-01
- **起点**: F2 整改（`c7512099`）完了後のコードレビュー
- **対象**: AutoNovel v6.0.0 / ブランチ `fix/f2-review-remediation` 以降
- **総合判定（レビュー時）**: **条件付き不可**。基準テストは全て緑だが **S1 が 4 件**、**空虚なテストが 3 件**
- **構成**: **TRACK-A（Python 中核 + Python テスト網）= 23 ステップ** ／ **TRACK-B（FE + CI + ツール）= 13 ステップ** ＝ **計 36 ステップ**

### レビュー時の実測ベースライン（重要）

```
pytest tests/regression tests/contract tests/unit/story_spine tests/unit/story_spine_wiring
  → 1024 passed, 17 skipped (163.71s)
npm run typecheck   → 0 errors
npm run lint        → 0 errors, 316 warnings
npm run test:ci     → 48 files / 238 tests passed
ruff check src tests config scripts → 983 errors (F821=36, F811=38)
ruff format --check src tests config scripts → 1641 files would be reformatted
pytest tests/regression/test_status_md_counts_match_reality.py → 3 passed in 68.85s
```

**この绿は「テストが機能している」証明ではない。** 以下の 4 つの S1 はすべてこの绿の中で静かに残っている。

---

## 0. 本計画書の位置づけ

F2 整改（13 ステップ）は「壊れているもの」を直したが、**3 つのテストが空振りした**。

| 空振りしたテスト | 場所 | なぜ空振りか |
|---|:---|:---|
| `test_hard_includes_tension_and_artifact` | `tests/contract/test_spine_prompt_injection.py:95` | `assert str(x) in s or "テンション" in s` の第 2 項が format 文字列の**無条件ラベル**で常に成立。値の注入が壊れても緑 |
| `test_finale_appears_whenever_there_is_room` | `tests/regression/test_pacing_graph_relative.py` | `room` が空のとき `assert` に到達しない（eps<20 で必ず空） |
| `test_status_md_test_counts_match_reality` | `tests/regression/test_status_md_counts_match_reality.py:27` | ループ内の `pytest.skip` により、参照パスが壊れると**失敗ではなくガード全体が消える** |

本計画は **「欠陥の修正」＋「その欠陥を 2 度と検出できないテストの追加」** を 1 ステップに必ず対でセットする（P5）。**テストのない修正ステップは存在してはならない。**

---

## 0.1 分割原則

| 原則 | 内容 |
|:---|:---|
| **P1 ファイル排他所有** | **1 ファイルは 1 サブエージェントのみ**が触る（§0.2 の表に無いファイルを触ってはいけない） |
| **P2 完了判定は 1 行** | 「緑か赤か」のみ。数値の解釈を LLM にさせない |
| **P3 修正とテストは同一コミット** | テストのない修正を残さない |
| **P4 反証テストを 1 本ずつ** | 修正前にそのテストが**実際に赤くなる**ことを確認する。**赤を確認できないテストは書かない** |
| **P5 猜测禁止** | 対象ファイルの行番号・関数名を必ず grep / Get-Content で確認してから編集する。**この文書の行番号は 2026-10-01 実測値** |
| **P6 1 ステップ = 1 コミット** | 失敗したら `git reset --hard HEAD~1` して次へ |
| **P7 環境隔離** | 並列 pytest のため DB を分ける（`$env:DATABASE_URL`） |
| **P8 ステップの粒度** | 1 ステップ = 30 分以内。**36 ステップに分けたのは、各ステップが独立して revert できるようにするため** |

### P4 の実行手順（両トラック共通・省略不可）

```powershell
# 1) 反証テストだけを書く（実装には触らない）
# 2) 赤になることを確認する ← ここを飛ばすとステップG无效
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_XXX.py -v
# 3) 実測値を記録する（例: 203 failed / 112 failed）
# 4) 実装を直す
# 5) 緑になることを確認する
# 6) 「修正前 N 件赤 → 修正後 0 件」をコミットメッセージに書く
```

---

## 0.2 ★ ファイル排他所有表（この表に無いファイルを触ってはいけない）

| ファイル / ディレクトリ | 所有者 | 担当ステップ |
|---|:---:|:---:|
| `src/services/spine_resolver.py` | **A** | A4 / A6 / A8 |
| `config/story_spine/loader.py` | **A** | A3 |
| `config/story_spine/beat.py` | **A**（読むだけ） | A9 |
| `config/story_spine/windows.py`（新規） | **A** | A10 |
| `config/story_spine/__init__.py` | **A** | A10 |
| `src/backend/engine_narrative.py` | **A** | A11 |
| `src/backend/routers/structure.py` | **A** | A14 |
| `src/services/structure_validator.py` | **A** | A15 / A16 / A17 / A19 |
| `src/backend/workflows/reverse_plot_workflow.py` | **A** | A20 / A21 |
| `src/backend/routers/misc.py` | **A** | A22 |
| `config/archetypes_new.py` / `config/data/archetypes.json` | **A** | A23 |
| `tests/unit/story_spine/**` | **A** | A4-A19 |
| `tests/unit/story_spine_wiring/**` | **A** | A20 / A21 |
| `tests/contract/**` | **A** | A13 / A17 |
| `tests/regression/test_pacing_graph_relative.py` | **A** | A12 |
| `tests/regression/test_spine/**`（新規） | **A** | A3 / A6 / A8 |
| `frontend/src/**` | **B** | B1-B9 |
| `frontend/tests/**` | **B** | B1-B9 / B12 |
| `frontend/tests/fixtures/planning_options.snapshot.json` | **B** | B12 |
| `scripts/export_planning_options.py` | **B** | B12 |
| `tests/unit/scripts/**` | **B** | B12 |
| `.github/workflows/ci.yml` | **B** | B11 |
| `Makefile` | **B** | B10 |
| `tests/regression/test_status_md_counts_match_reality.py` | **B** | B13 |
| `docs/STATUS.md` | **統合** | 読むだけ。A/B どちらも触らない |
| `plans/PLAN_G1_CODE_REVIEW_REMEDIATION_36STEPS.md` | **統合** | 本書。読むだけ |

### 衝突の事前計算（重要）

| 競合 | 判定 |
|:---|:---|
| `src/backend/routers/misc.py` | **A22 のみ**が触る。B12 は `misc.py` を**読むだけ**（スナップショット生成に import する）。競合なし |
| `tests/contract/**` | A13 / A17 が触る。B は `tests/contract/` を触らない |
| `tests/unit/scripts/test_planning_options_snapshot.py` | **B12 のみ**。A は触らない |
| `src/services/structure_validator.py` の `validate()` 応答 | A17 で Python 側を変え、B3 で FE 型を合わせる。**A → B の順（Gate HB1）** |
| `config/story_spine/windows.py` | A10 が新規作成。B は触らない |
| `docs/STATUS.md` | **統合担当のみ**が最後に 1 回だけ追記する。A/B は触らない |

---

## 0.3 依存関係グラフとゲート

```
        ┌──────────────────────────────────────────────────────┐
        │ A1 ベースライン採取・ブランチ作成（TRACK-A 起点）       │ ← 最優先
        └───────────────────────┬──────────────────────────────┘
                                │ Gate HA0（マージ不要・前提のみ）
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
┌───────────────────────────────┐   ┌──────────────────────────────┐
│ TRACK-A: Python 中核 23 steps │   │ TRACK-B: FE + CI 13 steps    │
│                               │   │                              │
│ A2  Spine の解決キー追跡      │   │ B1  Wizard の bookId 除去    │ ← S1-3
│ A3  loader fallback の可視化  │   │ B2  patternKey の経路是正    │
│ A4  _strict_starts 不変条件   │   │ B3  BeatSheetViewer 型追随   │
│ A5  web hook が close を殺す  │   │ B4  style_key 名前空間不一致 │ ← S2-4
│     【反証テスト】            │   │ B5  styleKey 死んだ制御      │
│ A6  web hook の close 守護    │   │ B6  入力欄二重描画の解消    │
│ A7  _merge_duty 損失【反証】  │   │ B7  card_id 欠落時の key 破綻│
│ A8  _merge_duty の切断明示    │   │ B8  ラベル htmlFor/id        │
│ A9  span 重複の可視化        │   │ B9  警告判定の単一源化       │
│ A10 windows.py 新規           │   │ B10 lint ゲート実行可能性    │
│ A11 PacingGraph 置換         │   │ B11 ci.yml ratchet 実効化   │
│ A12 PacingGraph 網羅テスト    │   │ B12 snapshot の射影化        │
│ A13 契約テスト95行目の空虚さ  │   │ B13 STATUS.md ガード 69秒    │
│ A14 章キー契約統一           │   │                              │
│ A15 check_required_beats 改造 │   │                              │
│ A16 validator 短編域テスト    │   │                              │
│ A17 validate() spine 除去     │──►│（A17 の完了後に B3 へ）      │
│ A18 validate() 応答契約テスト  │   │                              │
│ A19 climax tension=None 防御  │   │                              │
│ A20 reverse_plot spine 受け渡し│  │                              │
│ A21 catharsis 判定の重複排除  │   │                              │
│ A22 misc.py card_id/growth    │   │                              │
│ A23 STORY_ARCHETYPES SSOT     │   │                              │
└───────────────┬───────────────┘   └──────────────┬───────────────┘
                │                                  │
                └──────────────┬───────────────────┘
                               ▼
                  ┌──────────────────────────────┐
                  │ I1 統合（統合担当）           │
                  │ ・ベースライン比較            │
                  │ ・docs/STATUS.md 差分反映     │
                  │ ・「完成形」判定              │
                  └──────────────────────────────┘
```

| ゲート | 条件 | 誰 | 判定方法 |
|:---|:---|:---:|:---|
| **HA0** | `git status --short` が空。ブランチ `fix/g1-review-36` 作成済み | A1 | 1 行 |
| **HA1** | `pytest tests/unit/story_spine tests/unit/story_spine_wiring tests/contract tests/regression -q` が緑 | A | 1 行 |
| **HB1** | `cd frontend; npx tsc --noEmit` が 0 errors、`npm run lint` 0 errors、`npm run test:ci` failed 0 | B | 1 行 |
| **HG1** | **新規/変更テストが全て「修正前に赤」を記録している**（§0.1 P4） | 統合 | コミットメッセージの件数記録 |
| **HG2** | **`ruff check src tests config scripts --select F821,F811` が 0 errors** | B10 | 1 行 |
| **HG3** | **`pytest tests/regression -q` が 300 秒以内に完了する**（現状 164 秒） | 統合 | 1 行 |
| **HG4** | **`make lint` / `make format-check` が通る**（現状は両方赤） | B10 | 1 行 |

---

## 0.4 作業開始前の必須事項

```powershell
cd E:\ssssad\autonovel

# F1 計画の教訓。**未コミット変更がある状態で比較ベースラインを取ると全部が「回帰」になる**
git status --short          # 現状: クリーン（0 件）
git log --oneline -1        # c7512099 であること

# ベースラインライン assuring
C:\Python314\python.exe -m pytest tests\regression -q --timeout=300 2>&1 | Tee-Object baseline_regression.log
cd frontend; npm run test:ci 2>&1 | Tee-Object ../baseline_frontend.log; cd ..

git checkout -b fix/g1-review-36
```

---

## 1. 変更ファイル総覧

### 1.1 新規（12 ファイル）

| ファイル | 担当 | ステップ |
|---|:---:|:---:|
| `config/story_spine/windows.py` | A | A10 |
| `tests/regression/test_spine/test_loader_fallback_is_visible.py` | A | A3 |
| `tests/regression/test_spine/test_web_hook_preserves_close_beat.py` | A | A6 |
| `tests/regression/test_spine/test_merge_duty_no_silent_loss.py` | A | A8 |
| `tests/unit/story_spine/test_span_overlap_report.py` | A | A9 |
| `tests/unit/story_spine/test_validator_short_lengths.py` | A | A16 |
| `tests/unit/story_spine/test_validator_response_contract.py` | A | A18 |
| `tests/unit/story_spine_wiring/test_reverse_plot_spine_wiring.py` | A | A20 / A21 |
| `tests/unit/test_story_archetypes_ssot.py` | A | A23 |
| `frontend/src/pages/WizardWorkflowPage.test.tsx` | B | B1 / B2 |
| `frontend/src/constants/manuscript.fallback.test.ts` | B | B4 |
| `tests/unit/scripts/test_planning_options_projection.py` | B | B12 |

### 1.2 改修（15 ファイル）

| ファイル | 担当 | 変更内容 |
|---|:---:|:---|
| `config/story_spine/beat.py` | A | （読むだけ。変更は A10 の windows.py 側で行う） |
| `config/story_spine/loader.py` | A | `_resolve` の `logger.debug` → `logger.warning` ＋ 戻り値に解決済みキーを持たせる |
| `config/story_spine/__init__.py` | A | `windows.py` の公開 |
| `config/story_spine/beat.py` の `Spine` | A | `resolved_pattern` / `resolved_length` / `resolved_market` フィールド追加 |
| `src/services/spine_resolver.py` | A | web hook の close 守護・`_merge_duty` の切断明示・`Spine` の解決キー埋め込み |
| `src/backend/engine_narrative.py` | A | `PacingGraph` を重複 span 耐性のウィンドウ表方式へ |
| `src/backend/routers/structure.py` | A | `ep_num` → `chapter_number` の契約統一 |
| `src/services/structure_validator.py` | A | `check_required_beats` を話数非依存化、`validate()` から `spine` 除去、`structure_key` 修正、`tension=None` 防御 |
| `src/backend/workflows/reverse_plot_workflow.py` | A | `_spine_for` の length/market 受け渡し、catharsis 判定の重複排除、ハードコード除去、`Spine` import |
| `src/backend/routers/misc.py` | A | `card_id` の辞書展開順序、`growth_curves` の truthiness |
| `config/archetypes_new.py` / `config/data/archetypes.json` | A | 二重 SSOT の解消（JSON を正とする） |
| `frontend/src/pages/WizardWorkflowPage.tsx` | B | `bookId ?? 1` 除去、`patternKey` の経路是正 |
| `frontend/src/components/planning/BeatSheetViewer.tsx` | B | `structure_key` 表示の修正、未使用フィールドの整理 |
| `frontend/src/components/generate/SimpleModePanel.tsx` | B | `style_key` 名前空間、`styleKey` 配線、二重描画、`card_id` フォールバック、ラベル |
| `frontend/src/components/editor/ManuscriptTargetIndicator.tsx` | B | 警告判定の単一源化 |
| `Makefile` | B | lint/format ゲートの実行可能性 |
| `.github/workflows/ci.yml` | B | 静的解析の ratchet 実効化 |
| `tests/regression/test_status_md_counts_match_reality.py` | B | 69 秒問題・skip 自己消滅・壊れた文言 |
| `scripts/export_planning_options.py` | B | スナップショットの射影化 |
| `tests/contract/test_spine_prompt_injection.py` | A | 95 行目の空虚さを解消 |

---

## 2. TRACK-A：Python 中核 + Python テスト網（23 ステップ）

### A1. ベースライン採取とブランチ作成
- **対象**: コマンドのみ（ファイル変更なし）
- **依存**: なし（**全作業の起点**）
- **推定所要**: 15 分

**作業内容**

1. `git status --short` がクリーンであることを確認。
2. ベースラインを 2 つ採取する（`baseline_regression.log` / `baseline_frontend.log`）。
3. `git checkout -b fix/g1-review-36`。

**検証コマンド**
```powershell
git status --short
C:\Python314\python.exe -m pytest tests\regression -q --timeout=300 2>&1 | Tee-Object baseline_regression.log
```

**完了判定**: `git status --short` が空、かつ `baseline_regression.log` に `passed` が記録されている。

---

### A2. `Spine` が「実際に使った設定」を報告しない問題の反証
- **対象ファイル**: `tests/regression/test_spine/test_spine_resolved_keys.py`（新規）
- **依存**: A1
- **推定所要**: 20 分

**背景（レビュー時実測）**

`config/story_spine/loader.py:53-60` の `_resolve` は未知キーを `logger.debug` だけで `exile_rise`/`novella`/`general` にフォールバックする。
`src/services/spine_resolver.py:363-369` は **要求されたキー** を `Spine` に詰める。

実測:
```
Spine reported : nope bogus_len bogus_market 5
Spine actual   : exile_rise novella general 5
identical beats : True
```

つまり `resolve_spine("nope", ...)` は「`nope` を使った Spine」と嘘をつくが、中身は `exile_rise`。
`structure_validator.load_pattern_beats` はこれを `resolved_pattern_key` で回避しているが、`resolve_spine` 自体に情報が無いため、
**プロンプト・UI「適用パターン」・`validate_spine` の全てが使っていないキーを表示する**。

**回帰テスト（先に作る）** — `tests/regression/test_spine/test_spine_resolved_keys.py`

```python
"""**Spine が実際に使用した pattern/length/market を報告すること**の回帰テスト。

レビュー実測:
  resolve_spine("nope","bogus_len","bogus_market",5).pattern == "nope"
  だが beats は resolve_spine("exile_rise","novella","general",5) と完全一致

このテストは修正前に **3 件赤** になる（Spine に解決済みフィールドが無い）。
"""
from __future__ import annotations

import pytest

from config.story_spine import LENGTHS, MARKETS, PATTERNS, resolve_spine

UNKNOWN = ("__no_such_pattern__", "__no_such_length__", "__no_such_market__")


def test_spine_reports_resolved_keys_when_input_is_valid():
    spine = resolve_spine("exile_rise", "novella", "general", 8)
    assert spine.resolved_pattern == "exile_rise"
    assert spine.resolved_length == "novella"
    assert spine.resolved_market == "general"


@pytest.mark.parametrize("field", ["resolved_pattern", "resolved_length", "resolved_market"])
def test_spine_reports_fallback_key_when_input_is_unknown(field: str):
    """未知キーを渡したとき、**実際に使われたキー**が報告されること。"""
    spine = resolve_spine(*UNKNOWN, 8)
    value = getattr(spine, field)
    assert value in {"exile_rise", "novella", "general"}, (
        f"{field}={value!r} がフォールバック先の実キーを示していない"
    )


def test_unknown_and_fallback_resolution_produce_identical_beats():
    """未知キーの解決と、フォールバックキーを明示指定した解決が同一であること。"""
    unknown = resolve_spine(*UNKNOWN, 8)
    explicit = resolve_spine("exile_rise", "novella", "general", 8)
    assert [(b.key, b.ep_start, b.ep_end) for b in unknown.beats] == [
        (b.key, b.ep_start, b.ep_end) for b in explicit.beats
    ]


def test_resolved_keys_are_not_silently_downgraded():
    """解決済みキーが.Patterns に実在すること（存在しないキーを渡していない）。"""
    spine = resolve_spine(*UNKNOWN, 8)
    assert spine.resolved_pattern in PATTERNS
    assert spine.resolved_length in LENGTHS
    assert spine.resolved_market in MARKETS
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_spine_resolved_keys.py -v
```

**完了判定**: 上記 4 テスト緑。**修正前に 3 件赤**（`resolved_*` 属性が `Spine` に無い）を記録すること（P4）。

---

### A3. `loader._resolve` のフォールバックが無可視である問題の修正
- **対象ファイル**: `config/story_spine/loader.py`（`:53-60`）、`tests/regression/test_spine/test_loader_fallback_is_visible.py`（新規）
- **依存**: A1
- **推定所要**: 30 分

**背景**

`_resolve` は未知キーで `logger.debug` のみ。本番のログレベル（INFO）では**完全に不可視**。
計画書の原則「黙って諦めない」に反する。
また `get_pattern` / `get_length` / `get_market` の 3  函数が同じ `_resolve` を共有しているため、
 어느 1 つがotal フォールバックしても他の呼び出し元は察觉できない。

**回帰テスト（先に作る）** — `tests/regression/test_spine/test_loader_fallback_is_visible.py`

```python
"""**未知キーのフォールバックがログで可視化されること**の回帰テスト。

修正前: `logger.debug` のみ → 実運用（INFO）では見えない
修正後: `logger.warning` があり、caplog で捕捉できること
"""
from __future__ import annotations

import logging

import pytest

from config.story_spine import loader

BAD_KEY = "__definitely_not_a_real_key__"


@pytest.mark.parametrize(
    "getter,kind", [(loader.get_pattern, "pattern"), (loader.get_length, "length"), (loader.get_market, "market")]
)
def test_unknown_key_is_logged_at_warning_or_above(getter, kind, caplog):
    """未知キーは **WARNING 以上** で記録されること（debug は不可視なので不可）。"""
    with caplog.at_level(logging.DEBUG, logger="config.story_spine.loader"):
        getter(BAD_KEY)
    records = [r for r in caplog.records if BAD_KEY in r.getMessage()]
    assert records, f"{kind} の未知キーがログに記録されなかった（logger.debug  では実運用で見えない）"
    assert any(r.levelno >= logging.WARNING for r in records), (
        f"{kind} の未知キーが DEBUG レベル。它は本番ログに出ない。"
        "「黙って諦めない」原則に反する"
    )


def test_fallback_message_states_the_substituted_key(caplog):
    """**どのキーに置き換えたか**がメッセージに含まれること。"""
    with caplog.at_level(logging.DEBUG, logger="config.story_spine.loader"):
        loader.get_pattern(BAD_KEY)
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "exile_rise" in msg, f"置換先キーがログに無い: {msg!r}"
```

**修正内容**（`loader.py:53-60`）

```python
def _resolve(table: dict[str, Any], key: str, kind: str) -> Any:
    """未知キーは既定値へフォールバックする。None は決して返さない。

    **フォールバックは WARNING で必ず可視化する**（debug では本番ログに出ず、
    「使っていないパターンを使用したことに気づけない」ため）。
    """
    hit = table.get(key)
    if hit is not None:
        return hit
    fallback = _FALLBACKS[kind]
    logger.warning(
        "未知の %s '%s' を既定 '%s' にフォールバック（要求キーはそのまま結果に含まれる）",
        kind, key, fallback,
    )
    return table.get(fallback)
```

さらに A2 のテストが green になるよう、`resolve_spine` 側で実際に使われたキーを判別できるようにする
（`_FALLBACKS` を `loader` から import して判定し、`Spine` に詰める）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_loader_fallback_is_visible.py -v
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_spine_resolved_keys.py -v
```

**完了判定**: 上記 2 ファイル合計 7 テスト緑。`test_unknown_key_is_logged_at_warning_or_above` が **修正前に 3 件赤**（DEBUG 判定）を記録。

---

### A4. `_strict_starts` の不変条件テスト（到達不能分岐の明示的記録）
- **対象ファイル**: `src/services/spine_resolver.py`（`:185-201`、読むだけ）、`tests/unit/story_spine/test_strict_starts_invariant.py`（新規）
- **依存**: A1
- **推定所要**: 25 分

**背景**

`src/services/spine_resolver.py:198-200` に
```python
if starts[0] < 1:
    # n > eps（1 話短編の重なり許容段）。_to_instances 側で全部 1..eps に広げる
    starts = [1] * n
```
という **到達不能 believed 分岐** がある。`_to_instances:207` が `n > eps` を先に `return` するため、
`_strict_starts` に渡る `n` は必ず `n <= eps`。よって `starts[0] < 1` は成立しない。

到達不能コードは「ingeering した人のために残不应该的东西」であり、
**将来 `_to_instances` のガードが変わった瞬間に `ep_start=1, ep_end=0` という空区間ifluorished BeatInstance を生む**。

**回帰テスト（先に作る）** — `tests/unit/story_spine/test_strict_starts_invariant.py`

```python
"""`_strict_starts` の不変条件と、到達不能 believed 分岐の明示的記録。

レビュー所見: `spine_resolver.py:198-200` の `starts = [1] * n` は到達不能。
放置すると `_to_instances:207` のガードが変わった時に
`ep_start=1, ep_end=0` という**空区間**の BeatInstance を生む。
"""
from __future__ import annotations

import pytest

from config.story_spine import PATTERNS, resolve_spine
from src.services.spine_resolver import _strict_starts


@pytest.mark.parametrize("eps", [3, 5, 8, 12, 20, 40, 100, 300])
def test_strict_starts_is_strictly_increasing_and_in_range(eps: int):
    """境界列は **strictly increasing** かつ **[1, eps] に収まる**こと。"""
    bounds = [i / 10 for i in range(11)]  # 0.0 .. 1.0
    starts = _strict_starts(bounds, len(bounds) - 1, eps)
    assert starts == sorted(starts), f"単調増加でない: {starts}"
    assert len(set(starts)) == len(starts), f"重複がある: {starts}"
    assert all(1 <= s <= eps for s in starts), f"[1,{eps}] の外: {starts}"


@pytest.mark.parametrize("pattern", ["exile_rise", "detective_mystery", "dungeon_conqueror"])
@pytest.mark.parametrize("eps", [3, 4, 5, 6, 8, 10, 20, 40])
def test_no_beat_gets_an_empty_episode_range(pattern: str, eps: int):
    """**空区間（ep_end < ep_start）が 1 つも無いこと**（空区間の混入検出）。"""
    spine = resolve_spine(pattern, "short", "general", eps)
    empty = [b for b in spine.beats if b.ep_end < b.ep_start]
    assert not empty, (
        f"{pattern}@{eps}: 空区間の beat が {[b.key for b in empty]}。"
        "これは `_strict_starts` の `starts=[1]*n` フォールバックが到達した結果"
    )


def test_overlapping_is_only_allowed_when_beats_exceed_episodes():
    """**重なりは n > eps のときだけ**許されること（1話短篇の仕様）。"""
    for eps in (1, 2, 3):
        spine = resolve_spine("exile_rise", "short", "general", eps)
        covered = [e for b in spine.beats for e in range(b.ep_start, b.ep_end + 1)]
        # eps より多い beat がある = 重なり許可の域。それ以外は厳密に 1 回ずつ。
        if len(spine.beats) <= eps:
            assert covered == list(range(1, eps + 1)), (
                f"eps={eps}: 重なり許可の域ではないのに被覆が重複/欠落: {covered}"
            )
```

**作業内容**

1. 上記テストを書く。
2. `src/services/spine_resolver.py:198-200` の到達不能 believed 分岐を、`assert` 化して**到達不能であることをコードで示す**:
   ```python
   assert starts[0] >= 1, (
       f"starts[0]={starts[0]} が 1 未満。n={n} > eps={eps} は `_to_instances:207` で"
       "処理済みのはず。ガードが変更されている可能性がある"
   )
   ```
   （`starts = [1] * n` の削除は**後続ステップ A6** で併せて行う。単独で消すと本ステップのテストが赤になるため）

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_strict_starts_invariant.py -v
```

**完了判定**: 6 テスト緑。**修正前（`assert` 化前）も緑であることを確認し、assert 化後は緑のまま**（＝-believed 分岐が到達しないことの証明）。

---

### A5. web hook が close-role beat を殺す問題の反証テスト
- **対象ファイル**: `tests/regression/test_spine/test_web_hook_preserves_close_beat.py`（新規・**まだ緑になることを確認してはいけない**）
- **依存**: A1
- **推定所持**: 25 分

**背景（レビュー時実測・最も危険)**

`src/services/spine_resolver.py:279-284`:
```python
last = instances[-1]
if last.key not in _ALWAYS_KEEP:
    if last.ep_start >= eps:
        instances[-1] = _as(last, hook_def)      # ← ここ。key/role/duty を丸ごと上書き
```

`_as` は `ep_start`/`ep_end` を保持しつつ `key`/`label`/`role`/`duty`/`tension`/`artifact` を
volume\_hook のものへ**全て置き換える**。つまり **最終 beat が close role だった場合、その存在そのものが消える**。
`_ALWAYS_KEEP`（`:38`）は `("midpoint_reversal", "climax")` しか守らない。

実測（web 市場, 全 38 パターン × eps 3,4,5,6,8,10,12,20,40）:
```
close-role 全滅: 203 ケース
  academy_cinderella@3  YAML['coda','payoff'] → ['inciting','midpoint_reversal','climax','volume_hook']
  army_rational@3       YAML['aftermath']   → ['inciting','midpoint_reversal','climax','volume_hook']
```

**既存テスト `tests/unit/story_spine/test_resolver_no_silent_drop.py:20-31` が緑なのは、**
`resolve_spine(pattern, "single_volume", "general", eps)` と **非 web 市場・eps≥6 しか見ていない**ため。

**回帰テスト（先に作る）** — `tests/regression/test_spine/test_web_hook_preserves_close_beat.py`

```python
"""**web 市場でも close-role beat が消えないこと**の回帰テスト。

レビュー実測: 203 ケースで close-role が全滅（無言・ログなし）。
既存テスト `test_resolver_no_silent_drop.py:20` は
`single_volume`/`general`/eps>=6 しか見ておらず、web 経路を丸ごと避けている。

**このファイルは A6 の修正まで必ず赤になる。** 修正前の失敗数を記録すること。
"""
from __future__ import annotations

import pytest

from config.story_spine import BEAT_VOCABULARY, PATTERNS, resolve_spine

CLOSE_ROLE_KEYS = {k for k, b in BEAT_VOCABULARY.items() if b.role == "close"}

WEB_EPS_LIST = (3, 4, 5, 6, 8, 10, 12, 20, 40)


def _expected_close_keys(pattern_key: str) -> set[str]:
    return {b["key"] for b in PATTERNS[pattern_key]["beats"] if b["key"] in CLOSE_ROLE_KEYS}


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
@pytest.mark.parametrize("eps", WEB_EPS_LIST)
def test_web_keeps_at_least_one_close_role_beat(pattern: str, eps: int):
    """**web でも YAML に close role があるなら 1 つは残る**こと。

    YAML 側は single_volume 用の設計なので web で全部は残らないが、
    「締めが 1 つも無い」は構造破綻である。
    """
    expected = _expected_close_keys(pattern)
    if not expected:
        pytest.skip(f"{pattern} に close role の beat が無い（patterns.yaml 側の定義）")

    keys = set(resolve_spine(pattern, "short", "web", eps).keys)
    surviving = keys & expected
    assert surviving, (
        f"{pattern}@{eps} web: close role が全滅。期待 {sorted(expected)} / 実際 {sorted(keys)}。"
        "volume_hook が最終 beat を上書きしている（spine_resolver.py:281 の `_as(last, hook_def)`）"
    )


@pytest.mark.parametrize("eps", WEB_EPS_LIST)
def test_close_beat_keeps_its_own_duty_and_role(eps: int):
    """**残る close beat は自分の duty / role を保持すること**（上書きでないこと）。"""
    for pattern in ("exile_rise", "army_rational", "academy_cinderella", "gourmet_conqueror"):
        expected = _expected_close_keys(pattern)
        if not expected:
            continue
        spine = resolve_spine(pattern, "short", "web", eps)
        survivors = [b for b in spine.beats if b.key in expected]
        if not survivors:
            continue  # 上記テストが担当
        for b in survivors:
            vocab = BEAT_VOCABULARY[b.key]
            assert b.role == vocab.role, (
                f"{pattern}@{eps}: {b.key} の role が {b.role!r}（期待 {vocab.role!r}）。"
                "別 beat の role が貼り付いている"
            )


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
def test_web_volume_hook_still_lands_on_the_final_episode(pattern: str):
    """**修正で web の ending_contract を壊さないこと**（逆方向の保証）。"""
    for eps in WEB_EPS_LIST:
        spine = resolve_spine(pattern, "short", "web", eps)
        tail = spine.at(eps)
        assert tail is not None and tail.key == "volume_hook", (
            f"{pattern}@{eps}: 最終話(ep={eps}) が {tail.key if tail else None!r}（ending_contract 違反）"
        )


@pytest.mark.parametrize("eps", WEB_EPS_LIST)
def test_closing_beat_is_not_rewritten_into_volume_hook(eps: int):
    """**volume_hook と close beat が同一 beats 里有면 1 つも無い**こと（上書きの直接検出）。"""
    for pattern in sorted(PATTERNS):
        expected = _expected_close_keys(pattern)
        if not expected:
            continue
        keys = resolve_spine(pattern, "short", "web", eps).keys
        overlap = set(keys) & expected
        if not overlap:
            # 消滅は上のテストが検出する。ここでは「上書き」を検出する。
            pytest.fail(
                f"{pattern}@{eps}: close beat が 1 つも無い。"
                f"YAML は {sorted(expected)} を持つのに結果は {keys}"
            )
        break
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_web_hook_preserves_close_beat.py -v
```

**完了判定**: **203 件赤であることを記録し、赤のまま A6 へ進む**（P4）。緑にしようとしてテストを弱めないこと。

---

### A6. web hook が close-role beat を殺す問題の修正
- **対象ファイル**: `src/services/spine_resolver.py`（`:254-326` の `_enforce_invariants`、`:198-200`）
- **依存**: A5（**A5 が赤であることを確認済みであること**）
- **推定所持**: 45 分

**作業内容**

1. `_enforce_invariants` に「**close role の beacon をvolume\_hook に食わせない**」規則を追加する。

   方針: **hook を「消費」させる前に、末尾から close role の beat を探す**。
   - 末尾 beat が close role ではなく、`volume_hook` が末尾に既に居る → 何もしない（正常）
   - 末尾 beat が close role → **1 話手前の非 INVARIANT beat を volume\_hook に差し替える**。
     そのような beat が無い場合のみ、`_as(last, hook_def)` による上書きを許すが、
     **その場合は `logger.warning` で「締（N字）が volume\_hook へ置換された」と必ず可視化する**。

   ```python
   def _is_close(inst: BeatInstance) -> bool:
       return inst.key in _CLOSE_ROLE_KEYS or inst.role == "close"
   ```

   （`_CLOSE_ROLE_KEYS = frozenset(k for k, v in BEAT_VOCABULARY.items() if v.role == "close")` を
   `:38` の `_ALWAYS_KEEP` の近くに定義する）

2. `:279-284` の分岐を上記方針で置き換える。

   ```python
   if last.key not in _ALWAYS_KEEP:
       donor_idx = next(
           (j for j in range(len(instances) - 2, -1, -1)
            if instances[j].key not in _ALWAYS_KEEP and instances[j].key != hook_def.key),
           None,
       )
       if donor_idx is not None and instances[donor_idx].ep_start >= eps:
           # 手前の 1 話幅 beat を volume_hook に譲る（締めは残る）
           instances[donor_idx] = _as(instances[donor_idx], hook_def)
           logger.info(
               "web: 第%d话を volume_hook へ差し替え（%s を譲った）",
               instances[donor_idx].ep_start, instances[donor_idx].key,
           )
       elif last.ep_start >= eps:
           # 譲る話が無い。**黙って上書きしない**（既存ログの明確化）
           logger.warning(
               "web: 譲れる話が無いため最終話(%s, role=%s)を volume_hook へ置換した。"
               "締（N字）が消える。eps を増やすか EPS パターン側で解決すること",
               last.key, last.role,
           )
           instances[-1] = _as(last, hook_def)
       else:
           instances[-1] = replace(last, ep_end=eps - 1)
           instances.append(hook)
   ```

3. `:198-200` の到達不能 believed 分岐を削除する（A4 で assert 化したので安全）。

4. **剩下的な** 重複排除ロジック（`:313-324`）はそのままとする（A8 の対象）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_web_hook_preserves_close_beat.py -v
C:\Python314\python.exe -m pytest tests\unit\story_spine tests\regression -q
```

**完了判定**: 新規 4 テスト緑。**修正前 203 件赤 → 修正後 0 件**をコミットに記録。かつ `test_web_volume_hook_still_lands_on_the_final_episode` が緑（ending_contract を壊していない）。

---

### A7. `_merge_duty` が 3 成员目以降を黙って捨てる問題の反証テスト
- **対象ファイル**: `tests/regression/test_spine/test_merge_duty_no_silent_loss.py`（新規・**修正まで赤**）
- **依存**: A1
- **推定所持**: 25 分

**背景**

`src/services/spine_resolver.py:54-61`:
```python
def _merge_duty(a: str, b: str) -> str:
    head = a.rstrip("。")
    merged = f"{head}、続けて{b.rstrip('。')}。"
    if len(merged) <= 60:
        return merged
    truncated = merged[:58].rstrip("、。")
    return f"{truncated}…。"
```
`:229-230` で `node.members` の 2 個目以降を**順次**この関数に食わせている。
つまり `inciting + cold_open + revelation + humiliation`（4 個）を吸収した beat の duty は、
1 回目の統合で既に 58 字に切られ、2 回目以降は**新しい内容が丸ごと捨てられる**。

実測（`exile_rise` short/general）:
```
eps=1..8 の inciting duty が 58 字 + "…。"
```

**duty は LLM プロンプトに注入される値**（`src/services/llm/prompts.py` の `build_spine_section`）なので、
**切られた指示がモデルに渡る**。かつ `BeatInstance` に「何 beat を吸収したか」の記録が無い。

**回帰テスト（先に作る）**

```python
"""**duty 統合で情報が黙って消えないこと**の回帰テスト。

レビュー実測: `_merge_duty`（spine_resolver.py:54-61）が 58 字で切り、
`_build`（:229-230）が順次適用するため、3 成员目以降は丸ごと捨てられる。

**このファイルは A8 の修正まで必ず赤になる。**
"""
from __future__ import annotations

import pytest

from config.story_spine import BEAT_VOCABULARY, PATTERNS, resolve_spine


def _merged_patterns() -> list[str]:
    """4つ以上の beat を 1 話に吸収するパターン（統合が起きる条件を満たすもの）。"""
    out = []
    for pk, p in PATTERNS.items():
        keys = [b["key"] for b in p["beats"]]
        # 隣接マージグループが 3 個以上連続するパターンを探す
        for grp in (("inciting", "cold_open", "revelation", "humiliation"),
                    ("aftermath", "payoff", "residue"),
                    ("deepening", "comic_relief", "interlude", "promise")):
            if all(k in keys for k in grp):
                out.append(pk)
                break
    return out


@pytest.mark.parametrize("pattern", _merged_patterns())
@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5, 8])
def test_merged_duty_declares_its_own_truncation(pattern: str, eps: int):
    """**切断された beat は必ず省略記号で明示されること**。

    切り詰められたのに句点で終わって「全部入りだ」と騙さないこと。
    """
    for b in resolve_spine(pattern, "short", "general", eps).beats:
        assert b.duty.endswith("。"), f"{pattern}@{eps}/{b.key}: 句点で終わらない {b.duty!r}"
        if len(b.duty) >= 58:
            assert "…" in b.duty, (
                f"{pattern}@{eps}/{b.key}: {len(b.duty)} 字だが省略記号が無い。"
                "途中で切れたことを隠している"
            )


@pytest.mark.parametrize("pattern", _merged_patterns())
@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5, 8])
def test_merge_reports_which_beats_were_absorbed(pattern: str, eps: int):
    """**吸収した beat の key が追跡可能であること**（cannot 追踪 = 情報が消える）。"""
    spine = resolve_spine(pattern, "short", "general", eps)
    spine_keys = set(spine.keys)
    yaml_keys = {b["key"] for b in PATTERNS[pattern]["beats"]}

    # 1 話に複数 beat を吸収した結果なら、その痕跡が clé として残っていること
    absorbed = yaml_keys - spine_keys
    if not absorbed:
        pytest.skip(f"{pattern}@{eps}: 吸収が発生していない")

    for b in spine.beats:
        if b.members and len(b.members) > 1:
            assert set(b.members) <= yaml_keys | spine_keys, (
                f"{pattern}@{eps}/{b.key}: members に架空の key がある {b.members}"
            )


@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5, 8])
def test_absorbed_members_are_at_least_visible_in_the_duty_text(eps: int):
    """**吸収された beat の識別子が duty か members に残る**こと。

    何も残らない = プロンプトに「何 Olson 犬」が渡らない。
    """
    import re

    for pattern in _merged_patterns():
        for b in resolve_spine(pattern, "short", "general", eps).beats:
            absorbed = [m for m in (b.members or ()) if m != b.key]
            if not absorbed:
                continue
            has_members_field = len(b.members or ()) > 1
            has_marker = any(m in b.duty for m in absorbed)
            assert has_members_field or has_marker, (
                f"{pattern}@{eps}/{b.key}: {absorbed} を吸収したが"
                "members にも duty にも痕跡が無い（情報が消えた）"
            )
            assert len(b.duty) <= 60, f"{pattern}@{eps}/{b.key}: duty が 60 字契約を超過 {len(b.duty)}"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_merge_duty_no_silent_loss.py -v
```

**完了判定**: **`members` 属性が無いことで複数件赤**であることを記録し、赤のまま A8 へ。

---

### A8. `_merge_duty` の情報損失の修正
- **対象ファイル**: `src/services/spine_resolver.py`（`:54-61`, `:223-243`）、`tests/regression/test_spine/test_merge_duty_no_silent_loss.py`
- **依存**: A7
- **推定所持**: 40 分

**作業内容**

1. `BeatInstance` に `members: tuple[str, ...] = ()` を追加する
   （`config/story_spine/beat.py:30-41` は A の所有だが、A9 で読むだけと约定済み。
   **変更が必要なら A9 の前に単独コミットで追加し、A9 の所有表を本案実際HON守すること**）

2. `_build`（`:223-243`）で `members=node.members` を渡す。

3. `_merge_duty` を「**全部入れる不是为了、1 個目の duties を明确に要約 + 残りは省略記号**」に変更する:

   ```python
   def _merge_duty(a: str, b: str) -> str:
       """結合した beat の duty。60字以内・句点で終える。

       ** 여러 beat を吸収した場合は、何を吸収したかを省略記号で明示する**
       （黙って切る 프로ンプトに「全部入り」と嘘をつくtructured data を渡さない）。
       """
       head = a.rstrip("。").rstrip("、")
       tail = b.rstrip("。").rstrip("、")
       merged = f"{head}、続けて{tail}。"
       if len(merged) <= 60:
           return merged
       # 明示的に省略する。人間と LLM の双方に「続きがある」ことを伝える。
       keep = max(1, 57 - len(head))
       clipped = f"{head}、{tail[:keep]}"
       return f"{clipped}…。"
   ```

   **要点**: 現在の `merged[:58]` は「2 つ目を切ってから足す」ため、1 個目が既に長ければ 2 個目が丸ごと消える。
   上記は「1 個目を必ず残し、2 個目の残りは何文字か明示」する。

4. `_build` で **3 個目以降の members を duty に食わせない**（二重に切るのを避ける）:
   ```python
   members = node.members
   duty = primary.duty
   if len(members) > 1:
       others = "＋".join(members[1:])
       duty = _merge_duty(primary.duty, f"{others} 等")
   ```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_spine\test_merge_duty_no_silent_loss.py -v
C:\Python314\python.exe -m pytest tests\contract\test_spine_prompt_injection.py tests\unit\story_spine -q
```

**完了判定**: 新規 4 テスト緑。**修正前 N 件赤 → 修正後 0 件**。かつ **既存の byte 一致契約テスト `test_off_produces_legacy_prompt_exactly` が緑のまま**（プロンプト無変更の保証）。

---

### A9. `beat.py` の span 重複・順序逆転の可視化
- **対象ファイル**: `tests/unit/story_spine/test_span_overlap_report.py`（新規）、`config/story_spine/beat.py`（**読むだけ**）
- **依存**: A1
- **推定所持**: 25 分

**背景（レビュー時実測）**

`config/story_spine/beat.py` の span は**重複が設計意図**だが、コード上は以下が実在する:

```
=== span order violations (beat i の終端 > beat i+1 の終端) ===
  rising_tension(0.28,0.44) -> foreshadow(0.2,0.4)
  deepening(0.3,0.48)    -> comic_relief(0.34,0.42)
  failure(0.38,0.47)     -> daily_loop(0.25,0.4)
  daily_loop(0.25,0.4)   -> training(0.22,0.38)
  midpoint_reversal(0.48,0.56) -> stakes_raise(0.44,0.54)
  last_stand(0.74,0.84)  -> truth_reveal(0.75,0.83)
  coda(0.97,1.0)         -> interlude(0.4,0.5)     ← 役割順と時系列順のズレ

=== overlapping spans: 31/32 組が overlap ===
  climax(0.82,0.94) overlaps aftermath(0.88,0.94)   ← ★ これが S1-4 の根因
```

**これが A10/A11（windows.py / PacingGraph）の前提**。
「重複は許すDisposedBounds」という意思決定を**コードとして固定**しておかないと、
誰かが「整列させよう」と rectifying して別のバグを作る。

**回帰テスト（先に作る）**

```python
"""**beat span の重複・順序逆転は「設計上のKNOWN」であることを固定する。

レビュー実測:
  - 隣接 32 組中 31 組が overlap
  - 7 組が終端順序逆転
  - climax(0.82,0.94) が aftermath(0.88,0.94) を包含 → PacingGraph のフィナーレが死んだ

本テストは「重複を壊さない」ことを保証し、
重複前提の処理（PacingGraph のウィンドウ表化）を可能にする。
"""
from __future__ import annotations

import pytest

from config.story_spine import BEAT_VOCABULARY

_KEYS = list(BEAT_VOCABULARY)


def test_all_spans_are_within_unit_interval():
    """全 span が [0.0, 1.0] に収まること。"""
    for k, v in BEAT_VOCABULARY.items():
        lo, hi = v.span
        assert 0.0 <= lo < hi <= 1.0, f"{k}: span={v.span} が [0,1] の外"


def test_overlap_is_known_and_documented_not_accidental():
    """**重複を「 accident」としてFIXしない**ことの固定。

    重複を消すと PacingGraph / validator の位置意味が変わる。
    (vec3 には「重複は設計意図」と明記する)
    """
    overlaps = [
        (k, BEAT_VOCABULARY[k].span, _KEYS[i + 1], BEAT_VOCABULARY[_KEYS[i + 1]].span)
        for i, k in enumerate(_KEYS[:-1])
        if BEAT_VOCABULARY[k].span[1] > BEAT_VOCABULARY[_KEYS[i + 1]].span[0] + 1e-9
    ]
    assert len(overlaps) >= 25, (
        f"重複が {len(overlaps)} 組しか無い。設計変更の可能性がある。"
        "重複前提のコード（PacingGraph のウィンドウ表）を一并レビューすること"
    )


def test_climax_contains_aftermath_is_a_known_trap():
    """**climax が aftermath を包含する**ことを明示的に記録する。

    PacingGraph が `_FINALE_START = aftermath.span[0]` を使うと
    フィナーレ区間がクライマックス区間に飲まれる（S1-4）。
    この関係をコードに残，才能未来の再発を防ぐ。
    """
    climax = BEAT_VOCABULARY["climax"].span
    aftermath = BEAT_VOCABULARY["aftermath"].span
    assert climax[1] > aftermath[0], (
        f"climax={climax} が aftermath={aftermath} を包含しない。"
        "PacingGraph のフィナーレ窓が تضم定的に诘まる想定が崩れている"
    )


def test_every_role_has_at_least_one_beat():
    """全 role に最低 1 つ beat が存在すること（役割の欠落防止）。"""
    roles = {v.role for v in BEAT_VOCABULARY.values()}
    assert {"hook", "engine", "reversal", "climax", "close"} <= roles, f"不足 role: {roles}"
```

**作業内容**

1. 上記テストを書く（**全て緑になるはず** — これは測定であり修正ではない）。
2. **重複を「 accident」として扱わない**旨を `config/story_spine/beat.py` の docstring に追記する。
   （docstring のみの変更なので A の所有表に反しない）

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_span_overlap_report.py -v
```

**完了判定**: 4 テスト緑。**このステップは測定のみ**（修正は A10/A11 で行う）。P4 の適用対象外（修正therapy 無い）。

---

### A10. 非重複ウィンドウ表の導出ユーティリティ
- **対象ファイル**: `config/story_spine/windows.py`（新規）、`config/story_spine/__init__.py`
- **依存**: A9
- **推定所持**: 40 分

**背景**

`PacingGraph`（`src/backend/engine_narrative.py:56-127`）は**重複する span を if チェーンで first-match-win 判定**している。
結果として最後の区間（フィナーレ）が短すぎる／到達不能になる（S1-4）。

正しい方法は「重複 span から **相互排他的な区間表**を導出」すること。
導出規則:
1. span を**開始位置でソート**する。
2. 各区間の開始を `max(自身の開始, 直前の区間の終端)` に**右に詰める**。
3. 境界：`pos = (ep_num - 1) / total_eps` なので `pos ∈ [0, 1)` に収まる。**1.0 は到達不能**。

**新規ファイル** — `config/story_spine/windows.py`

```python
"""**重複する beat span から相互排他的な区間表を導出する**ユーティリティ。

背景（レビュー S1-4）:
  `beat.py` の span は設計意図で重複している（隣接 32 組中 31 組）。
  そのため「span 値をそのまま if チェーンで比較する」実装では
  必ず区間が飲まれ、**最後の区間が短すぎ거나到達不能になる**。

実測:
  climax(0.82, 0.94) が aftermath(0.88, 0.94) を包含
  → _FINALE_START = aftermath.span[0] = 0.88 だと 0.88-0.94 はクライマックスに食われる
  → フィナーレは pos > 0.94 のみ。pos の最大は (eps-1)/eps なので eps<20 では到達不能

本モジュールは「重複を削除する」のではなく、
**「重複を aware したうえで、判定順序を確定させる」** 責務を持つ。
"""
from __future__ import annotations

from dataclasses import dataclass

from config.story_spine.beat import BEAT_VOCABULARY

#: pos = (ep - 1) / eps は 1.0 に到達しない（ep は 1..eps）
POS_MAX_EXCLUSIVE = 1.0


@dataclass(frozen=True)
class Window:
    """相互排他的な1区間。`lo` を含み `hi` を含まない（半開区間）。"""

    key: str
    lo: float
    hi: float

    def contains(self, pos: float) -> bool:
        return self.lo <= pos < self.hi


def exclusive_windows(
    ordered_specs: list[tuple[str, float, float]],
) -> list[Window]:
    """`(key, lo, hi)` の列を**半開区間の非重複表**に変換する。

    `ordered_specs` は**判定優先順**（上の行が先に評価される）。
    区間は右に詰める: `lo_i = max(lo_i, hi_{i-1})`。

    区間の末端が `hi_i <= lo_i` になったら**区間を落とさない**。
    （落とすと「到達不能の死んだ区間」が生まれ、A11 で検出もされないまま潜伏する）
    幅が 0 になった場合は `hi` を `max(lo, hi)` に補正し、**幅 0 の区間**として
    「到達する pos が 1 つもない」ことを明示的に表現する。
    """
    out: list[Window] = []
    prev_hi = 0.0
    for key, lo, hi in ordered_specs:
        adj_lo = max(lo, prev_hi)
        adj_hi = max(hi, adj_lo)
        out.append(Window(key, adj_lo, adj_hi))
        prev_hi = adj_hi
    return out


def classify(pos: float, windows: list[Window]) -> Window | None:
    """`pos` が属する最初の区間を返す（無ければ None）。"""
    for w in windows:
        if w.contains(pos):
            return w
    return None


def available_positions(key: str, windows: list[Window], eps: int) -> list[float]:
    """指定区間に属する `pos` を全 eps から列挙する（到達可能性の検証用）。"""
    return [
        (ep - 1) / eps
        for ep in range(1, eps + 1)
        if (w := classify((ep - 1) / eps, windows)) is not None and w.key == key
    ]
```

**作業内容**

1. 上記を新規作成する。
2. `config/story_spine/__init__.py` に `Window`, `exclusive_windows`, `classify`, `available_positions` を export する。
3. **Unity テストを `tests/unit/story_spine/` に 1 本だけ書く**（A12 で本格テストする）:
   ```python
   def test_windows_are_mutually_exclusive():
       ws = exclusive_windows([("a", 0.0, 0.18), ("b", 0.18, 0.30), ("c", 0.74, 0.94), ("d", 0.88, 0.94)])
       for i in range(len(ws) - 1):
           assert ws[i].hi <= ws[i + 1].lo, f"{ws[i]} と {ws[i+1]} が重複"
   ```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine -q -k "window"
C:\Python314\python.exe -c "from config.story_spine import exclusive_windows; print(exclusive_windows([('a',0.0,0.18),('b',0.18,0.30),('c',0.74,0.94),('d',0.88,0.94)]))"
```

**完了判定**: `exclusive_windows` が 4 区間を非重複に導出することを確認し、輸出テストが緑。

---

### A11. `PacingGraph` を重複 span 耐性のウィンドウ表方式へ置換
- **対象ファイル**: `src/backend/engine_narrative.py`（`:34-127`）
- **依存**: A10
- **推定所持**: 45 分

**背景（レビュー時実測・S1-4）**

実測（`PacingGraph.get_instruction` を全 eps で走査）:
```
eps= 3 maxpos=0.667 finale=None climax=[3]
eps= 5 maxpos=0.800 finale=None climax=[5]
eps= 8 maxpos=0.875 finale=None climax=[7,8]
eps=10 maxpos=0.900 finale=None climax=[9,10]
eps=12 maxpos=0.917 finale=None climax=[10,11,12]
eps=16 maxpos=0.938 finale=None climax=[13,14,15,16]
eps=20 maxpos=0.950 finale=[20] climax=[16,17,18,19]
eps=40 maxpos=0.975 finale=[39,40] climax=[31..38]
```

**`グランドフィナーレ` は eps<20 で完全に到達不能。**

さらに:
- `_HOOK_END = revelation.span[1] = 0.18` と `_FIRST_EXPLOSION_START = first_win.span[0] = 0.18` が同値。
  `pos <= _HOOK_END` が先に評価されるため `pos == 0.18` は「導入」に属し、「第1の爆発」の窓が境界 1 つ分欠ける。
- `pos` は `(ep-1)/eps` なので **1.0 に到達しない**。`coda(0.97, 1.0)` はどの話数でも到達不能。

**作業内容**

`:45-54` のハードコード定数を削除し、`windows.py` ベースの表に置き換える:

```python
from config.story_spine.windows import exclusive_windows, classify
from config.story_spine.beat import BEAT_VOCABULARY as _V

def _derive_windows() -> list:
    """**重複 span から非重複区間表を導出する**（判定優先順がここ 1 箇所に集約される）。"""
    return exclusive_windows([
        ("light_open",      0.0,                     _V["cold_open"].span[1]),
        ("hook",            _V["cold_open"].span[1], _V["revelation"].span[1]),
        ("first_explosion", _V["first_win"].span[0], _V["first_win"].span[1]),
        ("rise",            0.30,                    0.50),
        ("twist",           0.50,                    _V["last_stand"].span[0]),
        ("climax",          _V["last_stand"].span[0], _V["climax"].span[1]),
        # ★ ここが問題の核心。0.88 ではなく 0.94（クライマックスの終端）から開始する
        ("finale",          max(_V["aftermath"].span[0], _V["climax"].span[1]), 1.0),
    ])


class PacingGraph:
    WINDOWS = _derive_windows()
```

`get_instruction`（`:84-127`）の if チェーンを `classify(pos, PacingGraph.WINDOWS)` による分岐に変更する。

**注意**: 旧 API の`_HOOK_END` / `_CLIMAX_START` などは
`tests/regression/test_pacing_graph_relative.py::test_bounds_are_derived_from_story_spine_spans` が参照しているため、
**その参照を `WINDOWS` へ書き換える（A12 で 함께）**。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_pacing_graph_relative.py -v
```

**完了判定**: **`test_finale_appears_whenever_there_is_room` が eps=3..16 で緑になる**（それまでは空振り）。A12 で全 eps を網羅する。

---

### A12. `PacingGraph` の順序・到達性の網羅テスト
- **対象ファイル**: `tests/regression/test_pacing_graph_relative.py`（改修）
- **依存**: A11
- **推定所持**: 35 分

**背景**

既存テストの 2 つが空振り:
- `test_finale_appears_whenever_there_is_room` — `room` が空なら `assert` に到達しない
- `test_bounds_are_derived_from_story_spine_spans` — 旧定数を参照;A11 で消える

**作業内容**

1. `test_finale_appears_whenever_there_is_room` を**空振りしない形**に書き換える:

```python
@pytest.mark.parametrize("eps", EPS_LIST)
def test_finale_appears_whenever_there_is_room(eps: int):
    """クライマックスの**後ろに話があるなら**フィナーレを出す。

    **修正前の版は `room` が空だと `assert` に到達せず空振りしていた**
    （eps<20 で常有）。今回は「空振りしない」ことを明示的に保証する。
    """
    clim, fin = _windows(eps)
    assert clim, f"eps={eps}: クライマックス窓が見つからない"

    # ★ 修正前はここで `if room:` で分岐 entrainしていた
    room = [e for e in range(1, eps + 1) if e > max(clim)]
    if not room:
        # room が空 = クライマックスが最終話を含む。
        # それでもフィナーレが出るべきではない（意味的にTherefore正しい）。
        # **ただし「到達不能」を検出し Powder には test_finale_is_reachable_somewhere を使う**
        pytest.skip(
            f"eps={eps}: クライマックス({max(clim)}話)が最終話を含むため"
            "フィナーレを置く余地が無い（この場合が正しい）"
        )
    assert fin, (
        f"eps={eps}: クライマックス（{max(clim)}話）の後に {room} 話あるのに"
        "フィナーレ分岐が発火しない（到達不能）"
    )
    assert min(fin) > max(clim), f"eps={eps}: フィナーレ {fin} がクライマックス {clim} と重複/逆転"


def test_finale_is_reachable_at_every_length_ge_3():
    """**3話以上なら必ずどこかでフィナーレが出る**こと（S1-4 の直接の防止）。"""
    unreachable = []
    for eps in (3, 4, 5, 6, 8, 10, 12, 16, 20, 30, 40, 100, 300):
        _, fin = _windows(eps)
        if not fin:
            unreachable.append(eps)
    assert not unreachable, (
        f"フィナーレが到達不能な話数: {unreachable}。"
        "`_FINALE_START` が climax 区間に食われている可能性"
    )
```

2. `test_bounds_are_derived_from_story_spine_spans` を **Windows 表** の検証に書き換える:

```python
def test_pacing_windows_are_mutually_exclusive():
    """**区間表に重複が無いこと**（重複 있으면「後の区間が飲まれる」）。"""
    ws = PacingGraph.WINDOWS
    for i in range(len(ws) - 1):
        assert ws[i].hi <= ws[i + 1].lo, (
            f"{ws[i]} と {ws[i+1]} が重複している。"
            "重複があれば後続区間が到達不能になる（S1-4）"
        )


def test_finale_window_starts_after_climax_window():
    """**フィナーレの開始がクライマックスの終端以上**であること（S1-4 の核心）。"""
    ws = {w.key: w for w in PacingGraph.WINDOWS}
    assert ws["finale"].lo >= ws["climax"].hi, (
        f"フィナーレ {ws['finale']} がクライマックス {ws['climax']} に食われている"
    )


def test_hook_and_first_explosion_share_a_clean_boundary():
    """**導入窓と第1爆発窓の境界が重複しない**こと（旧 `_HOOK_END == _FIRST_EXPLOSION_START`）。"""
    ws = {w.key: w for w in PacingGraph.WINDOWS}
    assert ws["hook"].hi <= ws["first_explosion"].lo, (
        f"導入 {ws['hook']} と第1爆発 {ws['first_explosion']} の境界が重なっている"
    )
```

3. `_windows()` ヘルパ（`:910-913` 相当）に **フィナーレの判定が `"フィナーレ" in label` ではなく完全一致**であることを確認する。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_pacing_graph_relative.py -v
```

**完了判定**: 3 新規テスト緑。**`test_finale_is_reachable_at_every_length_ge_3` は修正前 13 件中 6 件赤**であることを記録（P4）。

---

### A13. 契約テスト `test_spine_prompt_injection.py:95` の空虚さの解消
- **対象ファイル**: `tests/contract/test_spine_prompt_injection.py`（`:90-96`）
- **依存**: A1
- **推定所持**: 30 分

**背景（レビュー時・証明済み）**

`:95`:
```python
assert str(spine.at(33).tension) in section or "テンション" in section
```

**第 2 項が常に成立する**。`build_spine_section(..., "hard")` の出力格式は:
```
【第33話】構造設計: クライマックス（climax） テンション 1.00 / 成果 scene : 伏線を全回収せよ。
```

「テンション」は**無条件ラベル**であり、**値の注入が完全に壊れても緑になる**。
（検証: `str(tension)` を含まない section を作っても `"テンション" in section` は True）

これは計画書が「空虚な閾値」として潰そうとした `assert r["alignment"] > 0.0` と同型の欠陥が、
**R8 の成果物に再発**したもの。

**回帰テスト（先に作る = 既存テストを書き換える）**

```python
def test_hard_includes_the_numeric_tension_value():
    """**テンションの「値」が入っている**こと。

    修正前: `assert str(tension) in section or "テンション" in section`
    → 第 2 項が format 文字列の無条件ラベルで常に True なので、
      値を注入し忘れても緑になっていた（**証明済み**）

    ここでは「ラベル」ではなく **「数値」** で検証する。
    """
    from config.story_spine import resolve_spine
    from src.services.llm.prompts import build_spine_section

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    section = build_spine_section(spine, "hard", ep_num=33)
    beat = spine.at(33)
    assert beat is not None

    # 値が 1.00 / 0.85 のような小数2桁形式で入っていること
    assert f"{beat.tension:.2f}" in section, (
        f"テンションの値 {beat.tension:.2f} が section に無い。\n"
        f"section = {section!r}\n"
        "ラベル「テンション」だけでは注入の証拠にならない（修正前の失敗）"
    )


def test_hard_label_alone_is_not_enough():
    """**「テンション」というラベルだけでは test が緑にならない**ことの固定。

    これが本ステップの目的を future に傳える。
    """
    from config.story_spine import resolve_spine
    from src.services.llm.prompts import build_spine_section

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    section = build_spine_section(spine, "hard", ep_num=33)
    stripped = section.replace("1.00", "").replace("0.85", "").replace("0.80", "").replace("0.90", "")
    assert "テンション" in stripped, "前提が成り立たない: ラベル自体が section に無い"
    # ラベルは残るが、値_assert は落ちる = 正しい設計
    assert f"{spine.at(33).tension:.2f}" not in stripped, (
        "値の除去方法に問題がある（テストの前提）"
    )
```

**作業内容**

1. 上記 2 テストを追加する。
2. `:90-96` の `test_hard_includes_tension_and_artifact` を**削除**（上位テストに置き換わる）。
3. `artifact` も同様に検証する:
   ```python
   def test_hard_includes_the_artifact_key():
       spine = resolve_spine("exile_rise", "web_volume", "web", 40)
       section = build_spine_section(spine, "hard", ep_num=33)
       assert spine.at(33).artifact in section, f"成果物 {spine.at(33).artifact!r} が section に無い: {section!r}"
   ```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_spine_prompt_injection.py -v
```

**完了判定**: 4 テスト緑。**旧テストは削除済み**。**「ラベルだけを検査する形が残っていない」こと**を diff で確認。

---

### A14. 章キー契約の統一（`ep_num` vs `chapter_number`）
- **対象ファイル**: `src/backend/routers/structure.py`（`:44`）、`src/services/structure_validator.py`（`:56-67`）
- **依存**: A1
- **推定所持**: 30 分

**背景（レビュー時）**

`structure.py:44`:
```python
plots = [{"ep_num": p.ep_num, "title": p.title, "tension": p.tension or 0} ...]
```
`structure_validator.assign_phases` (`:61`):
```python
max_num = max((c.get("chapter_number", 0) for c in chapters), default=0)
```

**キーが異なる**ため `max_num` は常に 0 → `max_num > n` は False → index ベースの分岐（`:67`）に落ちる。
「たまたま正しく動いている」状態で、`:61-64` の `chapter_number` 分岐はこの router からは**死んでいる**。

さらに `p.tension or 0` により、**tension が NULL の書籍は全部 0** になり、
`check_climax_placement` は `max(assigned, key=tension)` で**1 話目を選ぶ** → `phase = 0`
→ 常に「クライマックス相当の山場が前半に偏っています」と報告される（A19 で修正）。

**回帰テスト（先に作る）** — `tests/unit/story_spine/test_validator_chapter_keys.py`（新規）

```python
"""**章データのキー契約が一意であること**の回帰テスト。

レビュー実測: `structure.py:44` は `ep_num`、`assign_phases:61` は `chapter_number` を読む。
キーが違うため `max_num` が常に 0 → index 分岐に落ち、「たまたま正しく動いている」。
"""
from __future__ import annotations

import pytest

from src.services.structure_validator import assign_phases


def test_chapter_number_is_the_canonical_key():
    """**`chapter_number` が正規キー**であること。"""
    out = assign_phases([{"chapter_number": 1}, {"chapter_number": 5}, {"chapter_number": 9}])
    assert [c["_phase"] for c in out] == [0.0, 0.5, 1.0], f"phase が算出されていない: {out}"


def test_ep_num_alias_is_accepted_but_normalised():
    """**`ep_num` も受け付けるが、正規キーへ正規化する**こと（router との後方兼容）。"""
    out = assign_phases([{"ep_num": 1}, {"ep_num": 5}, {"ep_num": 9}])
    assert [c["_phase"] for c in out] == [0.0, 0.5, 1.0], f"ep_num が解釈されていない: {out}"
    assert all("chapter_number" in c for c in out), "正規化されていない"


def test_both_keys_present_agree_or_raise():
    """**両方与えられた場合に不整合を黙って通り抜けない**こと。"""
    with pytest.raises(ValueError, match="不整合"):
        assign_phases([{"chapter_number": 1, "ep_num": 7}, {"chapter_number": 2, "ep_num": 2}])
```

**修正内容**

`structure_validator.py:56-67`:
```python
_CHAPTER_KEY_ALIASES = ("chapter_number", "ep_num")


def _norm_chapter_number(ch: dict[str, Any]) -> int:
    values = {k: ch[k] for k in _CHAPTER_KEY_ALIASES if ch.get(k) is not None}
    if len(set(values.values())) > 1:
        raise ValueError(
            f"章番号が不整合です: {values}。"
            "`chapter_number` と `ep_num` は同値であるべきです"
        )
    return int(next(iter(values.values()), 0))


def assign_phases(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """各章を 0..1 のフェーズ（出現位置）に割り当てる。

    **キー契約**: `chapter_number` が正規。`ep_num` は後方互換の別名として受け付ける。
    両方が与えられた場合は同値であることを検証する。
    """
    if not chapters:
        return []
    normed = [{**ch, "chapter_number": _norm_chapter_number(ch)} for ch in chapters]
    n = len(normed)
    max_num = max(c["chapter_number"] for c in normed)
    if max_num > n:
        return [
            {**ch, "_phase": round((ch["chapter_number"] - 1) / max(max_num - 1, 1), 3)}
            for ch in normed
        ]
    return [{**ch, "_phase": round(i / max(n - 1, 1), 3)} for i, ch in enumerate(normed)]
```

`structure.py:44` も `chapter_number` を返すよう変更する（両方を入れて後方互換）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_validator_chapter_keys.py -v
C:\Python314\python.exe -m pytest tests\unit\test_structure_validator.py -v
```

**完了判定**: 3 テスト緑。**修正前に `test_ep_num_alias_is_accepted_but_normalised` が赤**を記録。

---

### A15. `check_required_beats` を話数非依存の判定へ
- **対象ファイル**: `src/services/structure_validator.py`（`:70-94`）、`tests/unit/story_spine/test_required_beats_scale_free.py`（新規）
- **依存**: A14
- **推定所持**: 45 分

**背景（レビュー時実測・S1-2）**

`check_required_beats:85`:
```python
present = any(abs(c["_phase"] - beat["phase"]) <= tol for c in assigned)
```

`tol = 0.10` だが、`_phase` の刻みは `1/(eps-1)` である。
- eps=20 → 刻み 0.053、窓 ±0.10 → **約 4 話**に必ず落入る → 検出できる
- eps=3 → 刻み 0.5、窓 ±0.10 → **どの phase も窓に入らない** → 全員「欠落」

実測（resolver の**自分自身の出力**に対して）:
```
small-eps false missing: 112/190 組
  academy_cinderella@3 → 必須ビート 11個中 7個を「欠落」と報告
```

R4 の回帰テスト `test_resolver_output_passes_its_own_validator` は eps=20/40/60 しか見ていないため、
**この領域は未テストのまま残った**。

**根本原因**: 「**各話の位置**」と「**各ビートの期待位置**」を同じ数量軸で比べるという設計自体が話数に依存する。

**修正方針**: 「 어느 NOUN が 生成されたか」を**区間Membership** で判定する。
`assigned` を `_phase` 昇順にソートし、`beat` の期待窓と**重なる区间**が存在するかを見る。
刻みが 0.5 でも、区間 `[0.42, 0.52]` は phase 0.5 と重なる → 検出できる。

**回帰テスト（先に作る）** — `tests/unit/story_spine/test_required_beats_scale_free.py`

```python
"""**beat の充足判定が話数に依存しない**ことの回帰テスト。

レビュー実測（修正前）:
  resolver の自分自身の出力に対し、eps 3..8 で
  必須ビート 11個中 7個を「欠落」と誤報告（112/190 組）

根本原因: `abs(phase - expected) <= tol` は phase 刻み 1/(eps-1) に依存する。
eps=3 の刻み 0.5 > 窓 0.20 のため、どの phase も窓に入らない。
"""
from __future__ import annotations

import pytest

from config.story_spine import PATTERNS, resolve_spine
from src.services.structure_validator import check_required_beats, load_pattern_beats


@pytest.mark.parametrize("eps", [3, 4, 5, 6, 8, 10])
@pytest.mark.parametrize("pk", ["exile_rise", "academy_cinderella", "alchemy_workshop", "army_rational"])
def test_beat_presence_is_detected_even_with_coarse_phase_grid(pk: str, eps: int):
    """**粗い phase 刻みでも、beat があれば検出できること**。"""
    spine = resolve_spine(pk, "short", "general", eps)
    assigned = [{"chapter_number": b.ep_start, "tension": int(b.tension * 100)} for b in spine.beats]
    assigned = [{**c, "_phase": i / max(len(assigned) - 1, 1)} for i, c in enumerate(assigned)]

    struct = load_pattern_beats(pk)
    results = {r["key"]: r["present"] for r in check_required_beats(assigned, struct)}

    for b in spine.beats:
        if b.key not in results:
            continue
        assert results[b.key], (
            f"{pk}@{eps}: beat {b.key!r} が生成されているのに「欠落」と判定された。"
            f"全結果 = {results}。phase 刻み 1/{len(assigned)-1} が beat_tol を上回った"
        )


@pytest.mark.parametrize("eps", [3, 5, 8, 20, 40])
def test_presence_decision_does_not_depend_on_eps_for_same_relative_layout():
    """**同じ相対レイアウトなら、話数が違っても判定が同じ**であること。"""
    # 単調増加の緊張这样：只有一个 peak の典型的なレイアウト
    for eps in (3, 5, 8, 20, 40):
        assigned = [
            {"chapter_number": i + 1, "tension": 5, "_phase": i / max(eps - 1, 1)}
            for i in range(eps)
        ]
        struct = load_pattern_beats("exile_rise")
        results = check_required_beats(assigned, struct)
        present_ratio = sum(r["present"] for r in results) / len(results)
        # 単調なレイアウトなら「すべての beat が充足される」とは限らないが、
        # **話数が違うだけで present 数 radically に変わる**のはバグ
        assert present_ratio > 0.4, f"eps={eps}: 充足率 {present_ratio:.0%} が異常に低い"


def test_legacy_structures_keep_eps_dependent_semantics():
    """**従来 3 構造は挙動を変えない**（後方互換）。"""
    from src.services.structure_validator import STRUCTURE_DEFINITIONS

    assigned = [{"_phase": 0.1, "tension": 5}, {"_phase": 0.5, "tension": 9}, {"_phase": 0.9, "tension": 3}]
    for name, struct in STRUCTURE_DEFINITIONS.items():
        out = check_required_beats(assigned, struct)
        assert out and all("present" in b for b in out), name
```

**修正内容**（`structure_validator.py:83-94`）

```python
    results = []
    phases = sorted(c["_phase"] for c in assigned)
    for beat in structure["required_beats"]:
        lo, hi = beat["phase"] - tol, beat["phase"] + tol
        # ★ phase 刻みに依存しない判定: 窓が [lo, hi] と重なる phase が 1 つでもあれば充足
        present = any(lo <= p <= hi for p in phases)
        results.append({...})
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_required_beats_scale_free.py -v
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_validator_span_source.py -v
```

**完了判定**: 新規 3 テスト緑。**修正前に `test_beat_presence_is_detected_even_with_coarse_phase_grid` が 112 件赤**を記録（P4）。

---

### A16. validator 短編域（eps=3..10）の自己充足テスト
- **対象ファイル**: `tests/unit/story_spine/test_validator_short_lengths.py`（新規）
- **依存**: A15
- **推定所持**: 30 分

**背景**

A15 の判定方式を変えると、**別の副作用**が-cartpossible:
「話数が少ないと必ず充足率が上がる」→ 判定が緩くなる → 偽陰性が増える。

よって「resolver の出力が自分の validator を通る」ことを **全 eps 域**で固定する必要がある。

**回帰テスト（先に作る）**

```python
"""**resolver の出力が、自前の validator で「充足」であること**（全話数域）。

R4 が書いたテストは eps=20/40/60 しか見ていなかった。
結果として eps 3..10 では「resolver 自身の出力が 112/190 組で欠落扱い」になり、
FE の「⚠️ 改善推奨」が短編で常に誤表示になっていた（S1-2）。
"""
from __future__ import annotations

import pytest

from config.story_spine import PATTERNS, resolve_spine
from src.services.structure_validator import validate

ALL_EPS = (1, 2, 3, 4, 5, 6, 8, 10, 12, 20, 40, 60, 100)


def _chapters(spine):
    return [
        {"chapter_number": i + 1, "tension": int(b.tension * 100)}
        for i, b in enumerate(spine.beats)
    ]


@pytest.mark.parametrize("eps", ALL_EPS)
@pytest.mark.parametrize("pk", sorted(PATTERNS))
def test_resolver_output_never_fails_its_own_validator(pk: str, eps: int):
    """**resolver 自身の出力が「欠落」判定されない**こと。"""
    spine = resolve_spine(pk, "short", "general", eps)
    r = validate(_chapters(spine), pattern_key=pk)
    assert r["missing_beats"] == [], (
        f"{pk}@{eps}: 必須ビートが {len(r['missing_beats'])} 個欠落と判定された "
        f"{[b['key'] for b in r['missing_beats'][:5]]}。"
        "生成器と検証器の基準が食い違っている"
    )
    assert r["alignment"] == 1.0, f"{pk}@{eps}: alignment={r['alignment']}"


@pytest.mark.parametrize("eps", ALL_EPS)
def test_flat_tension_is_not_reported_healthy(pk: str = "exile_rise", eps: int = 20):
    """**平坦な緊張でも「構造健全」にならない**こと（判定が緩くなりすぎないか）。"""
    chapters = [{"chapter_number": i + 1, "tension": 5} for i in range(eps)]
    r = validate(chapters, pattern_key=pk)
    assert not r["climax"]["ok"], (
        f"eps={eps}: 全 chapter が同一 tension なのにクライマックス位置を「健全」と判定した。"
        "判定が話数に対して緩%"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_validator_short_lengths.py -v
```

**完了判定**: 緑。**A15 前には `missing_beats` 系が大量赤**であることを記録（P4）。

---

### A17. `validate()` から `spine` を除去し `structure_key` を修正
- **対象ファイル**: `src/services/structure_validator.py`（`:251-278`）
- **依存**: A15 / A16
- **推定所持**: 30 分

**背景（レビュー時実測・S1-1）**

`:270-275`:
```python
result["spine"] = resolve_spine(
    resolved_pattern_key or "exile_rise",
    "single_volume",   # ★ ハードコード
    "general",         # ★ ハードコード
    len(chapters) or 1,
)
```

実測（40 話 Web 小説）:
```
jsonable_encoder OK, bytes: 3886
spine field: {"pattern": "exile_rise", "length": "single_volume", "market": "general", "total_eps": 40, ...}
```

**40 話 Web 小説なのに `length="single_volume"`（eps_range は [15,20]）と報告している。**
FE の `StructureValidationResult` は `spine` を宣言していないので **丸ごと 3.9KB が無駄**。

また `:253` の `"structure_key": structure_name` は、`pattern_key` が指定されても常に `"three_act"`（`structure.py:31` の既定値）。

**回帰テスト（先に作る）** — A18 のファイルに含めるが，这里で先に定義する:

```python
def test_response_does_not_embed_a_spine_with_hardcoded_length():
    """**応答に length/market を固定した spine を埋め込まない**こと（S1-1）。"""
    r = validate([{"chapter_number": i, "tension": 50} for i in range(1, 41)], pattern_key="exile_rise")
    assert "spine" not in r, (
        "応答に spine が含まれる。length/market が hardcode されるため"
        "実際の作品と食い違う内容を返す（S1-1）。BE が使うなら別キー名は禁止"
    )


def test_structure_key_reflects_the_evaluated_structure():
    """**structure_key が「実際に評価した構造」を示す**こと。"""
    r = validate([{"chapter_number": i, "tension": 50} for i in range(1, 41)], pattern_key="exile_rise")
    assert r["structure_key"] != "three_act", (
        "pattern_key 指定なのに structure_key が three_act のまま。"
        "実際の構造は three_act ではない（表示と実態の不一致）"
    )
    assert r["structure_key"] == r["resolved_pattern_key"], (
        f"structure_key={r['structure_key']} != resolved_pattern_key={r['resolved_pattern_key']}"
    )
```

**修正内容**（`:251-278`）

```python
    result = {
        "structure": structure["name"],
        # pattern_key 指定時は「実際に評価した構造」を入れる（three_act のままにしない）
        "structure_key": resolved_pattern_key or structure_name,
        "pattern_key": pattern_key,
        "total_chapters": len(chapters),
        "missing_beats": missing,
        "climax": climax,
        "pacing": pacing,
        "is_healthy": (not missing) and climax["ok"] and pacing["ok"],
    }
    if pattern_key:
        result["resolved_pattern_key"] = resolved_pattern_key
        result["required_beat_count"] = len(beats)
        result["alignment"] = (
            round((len(beats) - len(missing)) / len(beats), 3) if beats else 0.0
        )
        # ★ spine を埋め込まない。FE は使わないし、length/market を
        #   固定すると「実際の作品と違う構造」を返すことになる（S1-1）。
        #   構造を参照させたい場合は pattern_key と resolved_pattern_key を使うこと。
    return result
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine -q
C:\Python314\python.exe -m pytest tests\contract -q
```

**完了判定**: 新規 2 テスト緑。**修正前に両方赤**を記録。**FE が壊れないこと**は B3 で確認する（Gate HB1）。

---

### A18. `validate()` 応答の契約テスト（FE 壊れないことの保証）
- **対象ファイル**: `tests/unit/story_spine/test_validator_response_contract.py`（新規）、`tests/contract/test_structure_validate_endpoint.py`（新規）
- **依存**: A17
- **推定所持**: 35 分

**背景**

A17 で応答形を変えたので、**FE が型どおりに解釈できることを保証**する必要がある。
FE の型（`frontend/src/components/planning/BeatSheetViewer.tsx:10-20`）:
```typescript
export interface StructureValidationResult {
  pattern_key?: string;
  resolved_pattern_key?: string;
  structure_key?: string;
  is_healthy?: boolean;
  alignment?: number;
  missing_beats?: MissingBeat[];
  climax?: { ok: boolean; reason?: string; climax_phase?: number | null };
  pacing?: { ok: boolean; reason?: string; skew?: number };
  problems?: Array<string | { key: string; reason: string }>;
}
```

**回帰テスト（先に作る）** — `tests/contract/test_structure_validate_endpoint.py`

```python
"""`/api/structure/books/{id}/validate` の応答が **FE の型と一致**することの契約テスト。

FE は `frontend/src/components/planning/BeatSheetViewer.tsx:10-20` の型で解釈する。
Python 側が `missing_beats` を `list[dict]` に変えて `list[str]` のまま扱うと
「Objects are not valid as a React child」で落ちる（F3 で実際に起きた）。
"""
from __future__ import annotations

import pytest

from src.services.structure_validator import validate

REQUIRED_KEYS = {"structure", "structure_key", "pattern_key", "total_chapters",
                 "missing_beats", "climax", "pacing", "is_healthy"}


def _validate(**kw):
    return validate([{"chapter_number": i, "tension": 50} for i in range(1, 41)], **kw)


def test_top_level_keys_match_frontend_contract():
    r = _validate(pattern_key="exile_rise")
    assert REQUIRED_KEYS <= set(r), (
        f"FE が必須とするキーが無い: 不足 = {REQUIRED_KEYS - set(r)}"
    )
    assert "spine" not in r, "spine は FE の型に無い（S1-1）"


def test_missing_beats_are_dicts_not_strings():
    """**missing_beats は dict 配列**（FE は `beat.key` / `beat.label` / `beat.expected_phase` を読む）。"""
    r = _validate(pattern_key="exile_rise")
    for b in r["missing_beats"]:
        assert isinstance(b, dict), (
            f"missing_beats が文字列: {b!r}。"
            "FE は beat.key を参照するため必ず object である必要がある"
        )
        assert {"key", "label", "present", "expected_phase"} <= set(b), b


def test_climax_and_pacing_shapes_match_frontend_contract():
    """**climax / pacing の形**が FE の型と一致すること。"""
    r = _validate(pattern_key="exile_rise")
    assert {"ok", "reason", "climax_phase"} <= set(r["climax"]), r["climax"]
    assert {"ok", "reason", "skew"} <= set(r["pacing"]), r["pacing"]


def test_alignment_is_a_float_in_zero_one():
    """**alignment ∈ [0,1]**（FE は `(alignment*100).toFixed(1)%` で表示する）。"""
    r = _validate(pattern_key="exile_rise")
    assert isinstance(r["alignment"], float)
    assert 0.0 <= r["alignment"] <= 1.0, r["alignment"]


@pytest.mark.parametrize("pattern", [None, "exile_rise", "death_loop", "__unknown__"])
def test_every_entry_point_returns_a_serialisable_dict(pattern):
    """**全経路が `json.dumps` できる**こと（dataclass を混ぜない）。"""
    import json

    r = _validate(pattern_key=pattern)
    json.dumps(r, ensure_ascii=False)  # 例外が出れば失敗
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_structure_validate_endpoint.py -v
```

**完了判定**: 6 テスト緑。**修正前に `test_top_level_keys_match_frontend_contract` が `spine` で赤**を記録。

---

### A19. `check_climax_placement` の tension=None 防御
- **対象ファイル**: `src/services/structure_validator.py`（`:97-110`）
- **依存**: A14
- **推定所持**: 25 分

**背景（レビュー時）**

`structure.py:44` は `p.tension or 0` を渡す。**tension が NULL の書籍は全部 0**。
`check_climax_placement:104` は `max(assigned, key=lambda c: c.get("tension", 0) or 0)` で
**同値なら先頭（1 話目）を選び**、`phase = 0` → `ok = False`。

結果: **tension データが無い書籍は常に「クライマックス相当の山場が前半に偏っています」と報告される**。
「データが無い」と「構造が悪い」を区別していない。

**回帰テスト（先に作る）**

```python
"""**tension データが無い場合と、構造が悪い場合を区別する**ことの回帰テスト。

レビュー実測: `structure.py:44` の `p.tension or 0` により tension=NULL の書籍は全部 0。
`check_climax_placement` は同値なら 1 話目を選び phase=0 → 常に「前半に偏っています」と報告。
"""
from __future__ import annotations

from src.services.structure_validator import check_climax_placement


def test_all_none_tension_is_reported_as_unknown_not_as_failure():
    assigned = [{"chapter_number": i, "tension": None, "_phase": i / 9} for i in range(10)]
    r = check_climax_placement(assigned, {"climax_min_phase": 0.66})
    assert r["ok"] is None, (
        f"tension が全 None なのに判定結果が出た: {r}。"
        "「データが無い」を「構造が悪い」に変換してはいけない"
    )
    assert "tension" in r["reason"].lower() or "データ" in r["reason"], r["reason"]


def test_real_front_loaded_climax_is_still_detected():
    """**本当に前半偏向なら検出できる**こと（防御が機能しないになってはいけない）。"""
    assigned = [
        {"chapter_number": i, "tension": 9 if i < 3 else 1, "_phase": i / 9}
        for i in range(10)
    ]
    r = check_climax_placement(assigned, {"climax_min_phase": 0.66})
    assert r["ok"] is False, f"前半偏向が検出されていない: {r}"


def test_real_back_loaded_climax_is_ok():
    assigned = [
        {"chapter_number": i, "tension": 1 if i < 7 else 9, "_phase": i / 9}
        for i in range(10)
    ]
    r = check_climax_placement(assigned, {"climax_min_phase": 0.66})
    assert r["ok"] is True, f"正常な構成が誤って失敗している: {r}"
```

**修正内容**（`:97-110`）

```python
def check_climax_placement(
    assigned: list[dict[str, Any]], structure: dict[str, Any]
) -> dict[str, Any]:
    """後半1/3等にクライマックス相当の章（tension が最大の章）があるかを検証する。

    **tension データが 1 つも無い場合は「判定不能（ok=None）」を返す**。
    0 で埋められただけのデータで「構造が悪い」と報告してはならない。
    """
    min_phase = structure.get("climax_min_phase", 0.66)
    if not assigned:
        return {"ok": False, "reason": "章がありません", "climax_phase": None}

    tensions = [c.get("tension") for c in assigned]
    if not any(isinstance(t, (int, float)) and t > 0 for t in tensions):
        return {
            "ok": None,
            "reason": "tension データが未計測のためクライマックス位置を判定できません",
            "climax_phase": None,
        }

    best = max(assigned, key=lambda c: (c.get("tension") or 0))
    phase = best["_phase"]
    return {
        "ok": phase >= min_phase,
        "reason": "" if phase >= min_phase else "クライマックス相当の山場が前半に偏っています",
        "climax_phase": phase,
    }
```

**连带修正**: `validate:259` の `is_healthy` が `climax["ok"]` を直接使わないようにする。
`ok is None` の場合は `is_healthy = None`（判定不能）を返す:

```python
    if climax["ok"] is None:
        healthy = None
    else:
        healthy = (not missing) and climax["ok"] and pacing["ok"]
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine -q -k "climax or validator"
```

**完了判定**: 3 新規テスト緑。**修正前に `test_all_none_tension_is_reported_as_unknown_not_as_failure` が赤**を記録。

---

### A20. 逆プロットが length/market を無視する問題の修正
- **対象ファイル**: `src/backend/workflows/reverse_plot_workflow.py`（`:122-124`, `:166-213`）、`tests/unit/story_spine_wiring/test_reverse_plot_spine_wiring.py`（新規）
- **依存**: A2（`Spine.resolved_*` が必要です）
- **推定所持**: 40 分

**背景（レビュー時）**

`:122-124`:
```python
def _spine_for(self, target_episodes: int) -> "Spine":
    """逆プロット用の Spine を解決する（LLM を呼ばない）。"""
    return resolve_spine("exile_rise", "web_volume", "web", target_episodes)
```

**全てハードコード**。`:179` と `:241` の 2 箇所の呼び出しibaseline(metadata)。
ミステリーもホラーも `exile_rise` の web spine を使う。
**38 パターン層がこの経路では丸ごと迂回されている。**

`:133` も `get_length("web_volume")` 固定（実際の length を無視）。

**回帰テスト（先に作る）** — `tests/unit/story_spine_wiring/test_reverse_plot_spine_wiring.py`

```python
"""**逆プロットが実際の length/market/pattern を反映すること**の回帰テスト。

レビュー実測: `reverse_plot_workflow.py:122-124` の `_spine_for` が
`resolve_spine("exile_rise", "web_volume", "web", eps)` とハードコード。
ミステリーもホラーも exile_rise の web spine を使う。
"""
from __future__ import annotations

import pytest

from src.backend.workflows.reverse_plot_workflow import ReversePlotWorkflow


def _wf():
    return ReversePlotWorkflow.__new__(ReversePlotWorkflow)  # 初期化なしにヘルパだけ呼ぶ


@pytest.mark.parametrize(
    "length,market", [("web_volume", "web"), ("novella", "general"), ("single_volume", "light_novel")]
)
def test_spine_for_honours_length_and_market(length: str, market: str):
    """**渡された length/market が Spine に反映される**こと。"""
    wf = _wf()
    spine = wf._spine_for(12, length_key=length, market_key=market)
    assert spine.length == length, f"length={spine.length}（期待 {length}）"
    assert spine.market == market, f"market={spine.market}（期待 {market}）"


def test_spine_for_accepts_pattern():
    """**pattern が渡せる**こと（既定は exile_rise で良いが上書き可能であること）。"""
    wf = _wf()
    default = wf._spine_for(12, length_key="web_volume", market_key="web")
    other = wf._spine_for(12, length_key="web_volume", market_key="web", pattern_key="death_loop")
    assert [b.key for b in default.beats] != [b.key for b in other.beats], (
        "pattern を渡しても結果が変わらない。pattern が無視されている"
    )


def test_arc_range_comes_from_the_actual_length():
    """**arc 区間が実際の length プロファイルから来る**こと（`web_volume` 固定ではない）。"""
    from config.story_spine import get_length

    web_arcs = get_length("web_volume").get("arc_count")
    assert isinstance(web_arcs, list) and len(web_arcs) == 2, web_arcs


def test_workflow_run_uses_the_resolved_spine():
    """**`_design_episodes` が `_spine_for` の結果を素通しで使う**こと。"""
    wf = _wf()
    arcs = wf._design_arcs({"coreConflict": "ideal_vs_reality"}, 40)
    eps = wf._design_episodes(
        {"emotionalGoal": "triumph", "sacrifice": "peace", "openingHook": "isekai_awakening"},
        arcs, 40, genre="ミステリー",
    )
    assert len(eps) == 40
    assert all(e.one_line_summary for e in eps), "摘要が空の識別がある"
```

**修正内容**（`:122-124`）

```python
    def _spine_for(
        self,
        target_episodes: int,
        *,
        length_key: str | None = None,
        market_key: str | None = None,
        pattern_key: str | None = None,
    ) -> "Spine":
        """逆プロット用の Spine を解決する（LLM を呼ばない）。

        **length / market / pattern はすべて外部から受け取る**。
        ハードコードすると 38 パターン層がこの経路で迂回される。
        """
        from config.story_spine.beat import Spine  # 型注釈用にローカル import（F821 回避）

        return resolve_spine(
            pattern_key or "exile_rise",
            length_key or "web_volume",
            market_key or "web",
            target_episodes,
        )
```

`:179` / `:241` の呼び出しを `length_key` / `market_key` 付きに変更し、
`execute`（`:100-120`）まで length/market を引き回す。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring\test_reverse_plot_spine_wiring.py -v
C:\Python314\python.exe -m ruff check src\backend\workflows\reverse_plot_workflow.py --select F821
```

**完了判定**: 新規 4 テスト緑。**修正前に `test_spine_for_honours_length_and_market` が 6 件赤**を記録。
**`ruff --select F821` が 0**（`Spine` の未 import も解消）。

---

### A21. catharsis 判定の重複排除とハードコード除去
- **対象ファイル**: `src/backend/workflows/reverse_plot_workflow.py`（`:215-223`, `:225-251`, `:209`, `:254`, `:258`）
- **依存**: A20
- **推定所持**: 35 分

**背景（レビュー時）**

`:215-223` の `_is_catharsis_ep` と `:231-238` の `_design_catharsis` が
**explosion / wave / spike の判定を二重に実装**している。片方だけ変えて他方だけ壊れる。

`:209` `antagonist_status="強化" if ep < target_episodes * 0.7`、
`:254` `phase = "導入" if ep <= total * 0.25`、
`:258` `elif ep == total // 3` は
`:177` のコメント「**テンショと各話の役割は STORY_SPINE が単一のソースにする**」と矛盾するハードコード。

**回帰テスト（先に作る）** — 既存ファイルに追加

```python
@pytest.mark.parametrize("pattern", ["explosion", "wave", "spike", "__unknown__"])
@pytest.mark.parametrize("total", [6, 9, 12, 40, 41])
def test_catharsis_points_and_flags_agree(pattern: str, total: int):
    """**`_is_catharsis_ep` と `_design_catharsis` が同じリストを返す**こと（二重実装の排除）。"""
    from src.backend.workflows.reverse_plot_workflow import EMOTIONAL_GOAL_TO_CATHARSIS

    wf = _wf()
    catharsis = wf._design_catharsis({"emotionalGoal": "triumph"}, total)
    # CatharsisPattern.catharsis_points が「どの話で感情が解放されるか」
    flags = {ep for ep in range(1, total + 1) if wf._is_catharsis_ep(ep, total, pattern)}
    assert set(catharsis.catharsis_points) == flags, (
        f"pattern={pattern}@{total}: points={catharsis.catharsis_points} と "
        f"flags={sorted(flags)} が食い違う。二重実装が乖離している"
    )


@pytest.mark.parametrize("total", [6, 9, 12, 40, 41])
def test_arc_boundaries_never_exceed_target(total: int):
    """**arc の end_ep が target を超えない**こと（R6 の clamp が維持されている）。"""
    wf = _wf()
    arcs = wf._design_arcs({"coreConflict": "ideal_vs_reality"}, total)
    assert all(a.end_ep <= total for a in arcs), [a.end_ep for a in arcs]
    assert all(a.start_ep <= a.end_ep for a in arcs), [(a.start_ep, a.end_ep) for a in arcs]
    # 隙間・重複が無いこと
    eps_cover = [e for a in arcs for e in range(a.start_ep, a.end_ep + 1)]
    assert eps_cover == list(range(1, total + 1)), eps_cover
```

**修正内容**

1. 判定を 1 関数に集約する:
   ```python
   def _catharsis_episodes(self, total: int, pattern: str) -> list[int]:
       """** catharsis EMPLATEを 1 箇所に集約する**（二重実装の排除）。"""
       if pattern == "explosion":
           return [total]
       if pattern == "wave":
           return [total // 3, 2 * total // 3, total]
       if pattern == "spike":
           return [total // 2, total]
       return [total]

   def _is_catharsis_ep(self, ep: int, total: int, pattern: str) -> bool:
       return ep in self._catharsis_episodes(total, pattern)
   ```
   `_design_catharsis` も同じ関数を使う。

2. `:209` / `:254` / `:258` のハードコードを `SPINE_SPAN` 由来に置き換える
   （`config/story_spine/windows.py` の `exclusive_windows` を使う。**定数は beat span から導出**）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring -q
```

**完了判定**: 新規 2 テスト緑。**修正前に `test_catharsis_points_and_flags_agree` が赤**を記録。
**`test_arc_boundaries_never_exceed_target` が緑**（R6 の clamp を壊していない）。

---

### A22. `misc.py` の `card_id` 展開順序と `growth_curves` の truthiness
- **対象ファイル**: `src/backend/routers/misc.py`（`:105-111`, `:120`）
- **依存**: A1
- **推定所持**: 25 分

**背景（レビュー時）**

`:120`:
```python
"cards": [{"card_id": k, **v} for k, v in CARDS.items()],
```
**`card_id` を先に置いてから `**v` で上書きしている**。将来カード自身が `card_id` を持てば
**期待しないキーが勝つ**。現在 `cards.yaml` に `card_id` は 0 件なので潜在バグ。

`:105-111`:
```python
growth_curves = list(
    dict.fromkeys(
        v.get("growth_curve")
        for v in STORY_ARCHETYPES.values()
        if isinstance(v, dict) and "growth_curve" in v
    )
)
```
**`"growth_curve" in v` で truthiness を見ていない**。空文字や `None` が選択肢として出る。
現在 38 件すべて非空なので潜在。

**回帰テスト（先に作る）** — `tests/contract/test_planning_options_contract.py` に追加

```python
def test_card_id_cannot_be_overridden_by_the_card_body():
    """**カード自身の card_id が自動付与の card_id を上書きしない**こと。"""
    from src.backend.routers.misc import get_planning_options
    import asyncio

    payload = asyncio.run(get_planning_options())
    for card in payload["cards"]:
        assert "card_id" in card, f"card に card_id が無い: {card}"
        assert card["card_id"], f"card_id が空: {card}"


def test_growth_curves_are_non_empty_strings():
    """**growth_curves に空文字 / None が混ざらない**こと。"""
    import asyncio
    from src.backend.routers.misc import get_planning_options

    payload = asyncio.run(get_planning_options())
    curves = payload["growth_curves"]
    assert curves, "growth_curves が空"
    for c in curves:
        assert isinstance(c, str) and c.strip(), (
            f"growth_curves に空文字 / None が混ざっている: {c!r}"
        )
    assert len(curves) == len(set(curves)), f"重複がある: {curves}"


def test_card_ids_are_unique():
    """**card_id が一意**であること（React key として使うため）。"""
    import asyncio
    from src.backend.routers.misc import get_planning_options

    payload = asyncio.run(get_planning_options())
    ids = [c["card_id"] for c in payload["cards"]]
    assert len(ids) == len(set(ids)), f"card_id が重複: {len(ids) - len(set(ids))} 件"
```

**修正内容**

```python
    growth_curves = list(
        dict.fromkeys(
            gc
            for gc in (
                v.get("growth_curve")
                for v in STORY_ARCHETYPES.values()
                if isinstance(v, dict)
            )
            if isinstance(gc, str) and gc.strip()
        )
    )
    ...
        # **v を先に展開し、card_id で上書きする**（カード側の同名キーでは勝たせない）
        "cards": [{**v, "card_id": k} for k, v in CARDS.items()],
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_planning_options_contract.py -v
C:\Python314\python.exe scripts\export_planning_options.py --check
```

**完了判定**: 3 新規テスト緑。**`export_planning_options.py --check` が緑**（B12 で再実行する）。

---

### A23. `STORY_ARCHETYPES` の二重 SSOT の解消
- **対象ファイル**: `config/archetypes_new.py`、`config/data/archetypes.json`、`tests/unit/test_story_archetypes_ssot.py`（新規）
- **依存**: A22
- **推定所持**: 40 分

**背景（レビュー時）**

`STORY_ARCHETYPES` は **2 箇所に存在する**:
- `config/archetypes_new.py:49` — 38 エントリ（`growth_curve` を含む）
- `config/data/archetypes.json:282` — 38 エントリ

`src/backend/routers/misc.py:94` は `.py` 側を読む。
**同期を保つ仕組みもテストも無い** → 片方だけ編集すると静かに乖離する。

**回帰テスト（先に作る）** — `tests/unit/test_story_archetypes_ssot.py`

```python
"""**`STORY_ARCHETYPES` が二重定義されていない**ことの回帰テスト。

レビュー実測:
  - config/archetypes_new.py:49 に 38 エントリ
  - config/data/archetypes.json:282 にも 38 エントリ
  - `misc.py:94` は .py 側を読むだけ。同期を保つ仕組みが無い
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.archetypes_new import STORY_ARCHETYPES

JSON_PATH = Path("config/data/archetypes.json")


@pytest.mark.skipif(not JSON_PATH.exists(), reason="archetypes.json が無い")
def test_json_and_python_definitions_agree():
    """**JSON と Python の定義が完全に一致**すること（SSOT の二重定義を禁止）。"""
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    assert "STORY_ARCHETYPES" in data, "JSON 側に STORY_ARCHETYPES が無い"
    assert data["STORY_ARCHETYPES"] == STORY_ARCHETYPES, (
        "config/data/archetypes.json と config/archetypes_new.py が乖離している。"
        "片方だけ編集すると静かにずれる。片方に集約すること"
    )


def test_every_entry_has_a_non_empty_growth_curve():
    """**全エントリが非空の growth_curve を持つ**こと（選択肢に出るので）。"""
    for key, v in STORY_ARCHETYPES.items():
        assert isinstance(v, dict), f"{key}: dict ではない"
        assert v.get("growth_curve", "").strip(), f"{key}: growth_curve が空"


def test_growth_curve_count_is_stable():
    """**growth_curve の種類数が 4 以下**であること（＝選択肢が爆発しない）。"""
    curves = {v["growth_curve"] for v in STORY_ARCHETYPES.values() if v.get("growth_curve")}
    assert len(curves) <= 4, f"growth_curve が {len(curves)} 種類: {sorted(curves)}"
```

**修正内容**

**方針: JSON を正（SSOT）とし、`.py` は生成物にする。**
ただし今回は「生成スクリプトの追加」까지やるとCcordinatio irst なので、
**最低限として「CI で乖離を検出する」テストを入れる**（上の 1 本目）。

`sync_archetypes.py` を追加して `Makefile` にターゲットを足してもよいが、
**B10 が Makefile を持つ**ので **A23 はテストのみ**にし、
スクリプト追加は統合フェーズに送る（Conflict 回避）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\test_story_archetypes_ssot.py -v
```

**完了判定**: 3 テスト緑。**`test_json_and_python_definitions_agree` が現時点で緑ならその旨を記録**（既に一致しているならテストは価値がある）。

---

## 3. TRACK-B：FE + CI + ツール（13 ステップ）

### B1. Wizard が常に book 1 のデータを表示する問題の修正【S1-3・最優先】
- **対象ファイル**: `frontend/src/pages/WizardWorkflowPage.tsx`（`:264-267`）、`frontend/src/pages/WizardWorkflowPage.test.tsx`（新規）
- **依存**: A1
- **推定所持**: 40 分

**背景（レビュー時・S1-3）**

```tsx
{currentStep === 2 && (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
    <BeatSheetViewer
      bookId={bookId ?? 1}                     // ★ 常に 1
      patternKey={plotData?.patternKey || 'exile_rise'}
    />
```

`bookId` は `:103` の `handleStep2Confirm`（= ステップ2を**確認した後**）でしかセットされない。
**ステップ2表示時は必ず `null`** → `/api/structure/books/1/validate?pattern=exile_rise` を叩く。

**新規ユーザー全員に book #1 の構造充足度を見せる。**
F3 で「BeatSheetViewer を WizardWorkflowPage にマウント」した際に取り込まれた。

**回帰テスト（先に作る）** — `frontend/src/pages/WizardWorkflowPage.test.tsx`

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { WizardWorkflowPage } from './WizardWorkflowPage';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('WizardWorkflowPage BeatSheetViewer 配線', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ pattern_key: 'exile_rise', missing_beats: [], is_healthy: true, alignment: 1 }),
    });
  });

  it('**bookId が未確定の間は構造検証 API を叩かない**（book 1 を表示しない）', async () => {
    render(<WizardWorkflowPage onNavigate={() => {}} />);
    // step1 を進める
    const next = screen.getByRole('button', { name: /次へ|進む|下一步/ });
    // step2 に到達
    // @ts-expect-error テスト用にstep を進める
    await waitFor(() => expect(screen.queryByText(/物語構成充足度/)).toBeTruthy());

    const urls = mockFetch.mock.calls.map((c) => String(c[0]));
    const structureCalls = urls.filter((u) => u.includes('/api/structure/'));
    expect(structureCalls, `bookId 未確定で叩かれた URL: ${structureCalls}`).toHaveLength(0);
  });

  it('bookId が確定した後にのみ、その bookId で検証する', async () => {
    // saveWizardBook が book_id を返すシナリオ
    mockFetch.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/wizard')) {
        return { ok: true, json: async () => ({ book_id: 777 }) };
      }
      return { ok: true, json: async () => ({ missing_beats: [], is_healthy: true, alignment: 1 }) };
    });
    render(<WizardWorkflowPage onNavigate={() => {}} />);
    await waitFor(() => {
      const urls = mockFetch.mock.calls.map((c) => String(c[0]));
      const s = urls.filter((u) => u.includes('/api/structure/'));
      if (s.length) {
        expect(s.every((u) => u.includes('/777/'))).toBe(true);
      }
    });
  });
});
```

**修正内容**

```tsx
{currentStep === 2 && (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
    {/* ★ bookId が確定するまで構造検証は意味がない（未保存の書籍は DB に無い）。
        従来の `?? 1` は book #1 のデータを他人に見せるため削除する。 */}
    {bookId !== null && (
      <BeatSheetViewer
        bookId={bookId}
        patternKey={plotData?.patternKey ?? 'exile_rise'}
      />
    )}
    <Step2StructureReview ... />
  </div>
)}
```

**検証コマンド**
```powershell
cd frontend; npx vitest run src/pages/WizardWorkflowPage.test.tsx
npx tsc --noEmit
```

**完了判定**: 新規 2 テスト緑。**修正前に `bookId 未確定で叩かれた URL` が赤**を記録（P4）。かつ `tsc` 0 errors。

---

### B2. `patternKey` のフォールバック経路の是正
- **対象ファイル**: `frontend/src/pages/WizardWorkflowPage.tsx`（`:265`）、`frontend/src/components/wizard/Step1PlotInput.tsx`（`:148-161`）
- **依存**: B1
- **推定所持**: 25 分

**背景**

`patternKey={plotData?.patternKey || 'exile_rise'}` は **'exile_rise' を暗黙の既定**にしている。
`plotData.patternKey` は `Step1PlotInput` の `onNext({...patternKey})`（`:158`）経由で届くが、
カードを選ばなかった場合は `''`（`Step1PlotInput:82` `setPatternKey(card.pattern || '')`）になる。

つまり「**カードを選ばなかったユーザー**」も `exile_rise` として構造検証される。
**PatternA を明示していないのに「exile_rise の充足度 66%」と表示される**。

**回帰テスト（先に作る）** — `frontend/src/pages/WizardWorkflowPage.test.tsx` に追加

```tsx
it('**patternKey が未指定なら構造検証しない**（暗黙の exile_rise を表示しない）', async () => {
  render(<WizardWorkflowPage onNavigate={() => {}} />);
  await waitFor(() => expect(screen.queryByText(/物語構成充足度/)).toBeTruthy());
  const urls = mockFetch.mock.calls.map((c) => String(c[0]));
  const withPattern = urls.filter((u) => u.includes('/api/structure/') && u.includes('pattern='));
  expect(withPattern.every((u) => u.includes('exile_rise')), 
    `暗黙の exile_rise で検証している: ${withPattern}`).toBe(false);
});
```

**修正内容**

```tsx
{bookId !== null && plotData?.patternKey && (
  <BeatSheetViewer bookId={bookId} patternKey={plotData.patternKey} />
)}
```

`BeatSheetViewerProps.patternKey` の既定値（`:30` `'exile_rise'`）も `undefined` に変更し、
**「未指定」と「exile_rise を指定」を API 上で区別できる**ようにする。

**検証コマンド**
```powershell
cd frontend; npx vitest run src/pages/WizardWorkflowPage.test.tsx src/components/planning
```

**完了判定**: 新規 1 テスト緑。

---

### B3. `BeatSheetViewer` の型を API 実形状に追従させる
- **対象ファイル**: `frontend/src/components/planning/BeatSheetViewer.tsx`（`:10-20`, `:115`）
- **依存**: **A17 完了後**（Gate HB1）
- **推定所持**: 30 分

**背景**

A17 で Python 側が
- `spine` を応答から**除去**
- `structure_key` を `resolved_pattern_key` に**変更**

した。FE の型（`:10-20`）も追従が必要。

また F3 で `structure_key?: string` は型にあるが**どこにも表示していない**。
FE が `resolved_pattern_key || pattern_key`（`:115`、F3 で修正済み）を優先表示する点は正しい。

**回帰テスト（先に作る）** — `frontend/src/components/planning/BeatSheetViewer.test.tsx` に追加

```tsx
it('**Python 側の応答形（spine なし・structure_key=pattern）に耐える**', async () => {
  // A17 修正後の実形状
  mockFetch({
    pattern_key: 'exile_rise',
    resolved_pattern_key: 'exile_rise',
    structure_key: 'exile_rise',
    structure: '追放ざまぁ',
    is_healthy: true,
    alignment: 1,
    required_beat_count: 11,
    missing_beats: [],
    climax: { ok: true, reason: '', climax_phase: null },
    pacing: { ok: true, reason: '', skew: 0 },
    // spine は **無い**
  });
  expect(() => render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />)).not.toThrow();
  await waitFor(() => expect(screen.getByText(/すべての必須ビート/)).toBeTruthy());
});

it('climax_phase が null でもクラッシュしない', async () => {
  mockFetch({ ...REAL_API_RESPONSE, climax: { ok: null, reason: 'tension データが未計測', climax_phase: null } });
  expect(() => render(<BeatSheetViewer bookId={1} />)).not.toThrow();
  await waitFor(() => expect(screen.getByText(/tension データが未計測/)).toBeTruthy());
});
```

**修正内容**

```typescript
export interface StructureValidationResult {
  pattern_key?: string;
  resolved_pattern_key?: string;
  structure_key?: string;
  structure?: string;
  is_healthy?: boolean | null;          // ← A19 で None になり得る
  alignment?: number;
  required_beat_count?: number;
  missing_beats?: MissingBeat[];
  climax?: { ok: boolean | null; reason?: string; climax_phase?: number | null };
  pacing?: { ok: boolean; reason?: string; skew?: number };
  problems?: Array<string | { key: string; reason: string }>;
  // spine は **意図的に無い**（Python 側は埋め込まない。structure_validator の S1-1 修正）
}
```

`is_healthy === null` のとき「判定不能」の表示を追加する（A19 と対）。

**検証コマンド**
```powershell
cd frontend; npx vitest run src/components/planning; npx tsc --noEmit
```

**完了判定**: 新規 2 テスト緑、`tsc` 0 errors。

---

### B4. `style_key` の名前空間不一致の解消
- **対象ファイル**: `frontend/src/constants/genres.ts`（新規 export）、`frontend/src/constants/manuscript.fallback.test.ts`（新規）、`config/story_spine/cards.yaml`（読むだけ）
- **依存**: A1
- **推定所持**: 30 分

**背景（レビュー時実測・新規発見）**

2 つの**非互換な style 名前空間**が併存している:

```
STYLE_DEFINITIONS keys: ['style_web_standard', 'style_serious_fantasy',
                         'style_psychological_loop', 'style_chat_log', ...]
cards.yaml style_key  : ['comedy', 'cool_headed', 'dark', 'healing',
                         'hot_blooded', 'romantic']
```

**`cards.yaml` の `style_key` 値は 1 つも `STYLE_DEFINITIONS` に存在しない。**
`SimpleModePanel.tsx:92` の既定は `"style_web_standard"`（実在するキー）だが、
カードを選ぶと `setStyleKey(card.style_key)`（`:153`）で**無効な値**に変わる。

つまり B5 で配線しても**バックエンド側で解決できない値**を送ることになる。

**回帰テスト（先に作る）** — `frontend/src/constants/manuscript.fallback.test.ts`

```ts
import { describe, expect, it } from 'vitest';

/**
 * `cards.yaml` の `style_key` が **FE が送る style 名前空間**に存在することの検証。
 *
 * レビュー実測:
 *   STYLE_DEFINITIONS = ['style_web_standard', 'style_serious_fantasy', ...]
 *   cards.yaml style_key = ['comedy', 'cool_headed', 'dark', 'healing', 'hot_blooded', 'romantic']
 *   → **1 つも一致しない**。カードを選ぶと無効な style が送信される
 */
describe('style_key 名前空間の一致', () => {
  it('**全カードの style_key が style_definitions に実在する**', async () => {
    const res = await fetch('/api/config/planning_options');
    const data = await res.json();
    const validStyles = new Set(Object.keys(data.style_definitions));

    const invalid = data.cards
      .map((c: { card_id: string; style_key?: string }) => ({ id: c.card_id, style: c.style_key }))
      .filter((x: { style?: string }) => x.style && !validStyles.has(x.style));

    expect(
      invalid,
      `FE が解決できない style_key: ${JSON.stringify(invalid)}。` +
        `cards.yaml の値と STYLE_DEFINITIONS のキーが別名前空間になっている`
    ).toHaveLength(0);
  });
});
```

**修正内容（2 案・A と相談して決める）**

- **案1（推奨・サーバ側が正）**: `config/story_spine/cards.yaml` の `style_key` を
  `STYLE_DEFINITIONS` の実キー（`style_web_standard` 等）に**置き換える**。
  → 名前空間が 1 つになる。ただし `misc.py` は A の所有なので、
  **`config/story_spine/cards.yaml` だけが B の所有**（§0.2 に追記）。
- **案2**: `SimpleModePanel` の `styleKey` を `style_definitions` の**選択肢（select）**に変更し、
  カードの `style_key` は**プリセット選択のヒント**としてのみ使う。

**指示**: 案1 を採用し、`cards.yaml` を B の所有表に追加する。

**検証コマンド**
```powershell
cd frontend; npx vitest run src/constants
C:\Python314\python.exe -m pytest tests\contract\test_planning_options_contract.py -q
```

**完了判定**: 1 テスト緑。`invalid` が 0 件。

---

### B5. `styleKey` が死んだ制御である問題の解消
- **対象ファイル**: `frontend/src/components/generate/SimpleModePanel.tsx`（`:92`, `:153`, `:248-257`, `:354`, `:364`）、`frontend/src/hooks/useNovelGeneration.ts`
- **依存**: B4
- **推定所持**: 40 分

**背景（レビュー時実測）**

`SimpleModePanel.tsx:92`:
```typescript
const [styleKey, setStyleKey] = useState<string>("style_web_standard");
```

`:254` で入力 displayed されるが、
`:354` `onClick={() => props.startStreaming?.()}` と
`:364` `onClick={() => props.startGeneration?.()}` は
**どちらも引数を取らない**。

`useNovelGeneration.ts:37-44` の payload:
```typescript
const response = await generateContent({
   chapter_history: [currentChapterText],
   current_chapter: currentChapterText,
   character_params: character,
   content_length_limit: contentLengthLimit || 2000,
   target_episodes: targetEpisodes || 1,
   ...( (llmConfig && ...) ? { llm_config: llmConfig } : {} ),
 });
```
→ **`styleKey` はどこにも含まれない。**

F4 が追加したテスト（`SimpleModePanel.test.tsx` の「カード選択で style_key と chars_per_ep が反映される」）
は **`getByDisplayValue('hot_blooded')` が DOM に現れることだけ**を検証しており、
**バックエンドに届くことは検証していない**。→ 偽の安心感。

**回帰テスト（先に作る）** — `frontend/src/components/generate/SimpleModePanel.test.tsx` に追加

```tsx
it('**styleKey が生成リクエストに含まれる**（死んだ制御でないこと）', async () => {
  const startGeneration = vi.fn();
  setup({ ...REAL_API_CARDS, style_definitions: { hot_blooded: { name: 'TF', description: '' } } });
  render(<SimpleModePanel startGeneration={startGeneration} />);

  fireEvent.click((await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!);
  fireEvent.click(screen.getByRole('button', { name: /生成/ }));

  await waitFor(() => expect(startGeneration).toHaveBeenCalled());
  const arg = startGeneration.mock.calls[0][0];
  expect(arg, 'startGeneration に style が渡っていない').toBeDefined();
  expect(JSON.stringify(arg)).toContain('hot_blooded');
});
```

**修正内容（推奨案: `useNovelContext` 経由で渡す）**

1. `SimpleModePanel.tsx:92` のローカル state を**props 化**する:
   ```typescript
   styleKey?: string;
   setStyleKey?: React.Dispatch<React.SetState<string>>;
   ```
   既存の `targetEpisodes` と同じ「props 優先 / ローカルフォールバック」パターン（`:75-78`）に揃える。
2. `GeneratePanel.tsx:289-326` で `useNovelContext()` から `styleKey` / `setStyleKey` を取り出し渡す。
3. `useNovelGeneration.ts:41` の payload に追加:
   ```typescript
   style: styleKey,
   ```

> **注意**: `GeneratePanel` が既に `selectedStyleId` を `SimpleModePanel` に渡している（`:294`）。
> **`selectedStyleId` と `styleKey` が二重定義にならないか要先に確認すること**（B5 の前提）。

**検証コマンド**
```powershell
cd frontend; npx vitest run src/components/generate/SimpleModePanel.test.tsx; npx tsc --noEmit
```

**完了判定**: 新規 1 テスト緑。**修正前に `startGeneration に style が渡っていない` で赤**を記録。

---

### B6. `contentLengthLimit` の二重描画の解消
- **対象ファイル**: `frontend/src/components/generate/SimpleModePanel.tsx`（`:234-246`, `:317-328`）
- **依存**: A1
- **推定所持**: 25 分

**背景（レビュー時実測）**

**同じ状態変数 `contentLengthLimit` に束縛された入力欄が 2 箇所にある**:
- `:236-245` — 「1話あたりの目標文字数」（F4 が追加。`showCustomConfig` の外側）
- `:318-327` — 同名ラベル（`showCustomConfig` の内側、`:317` の `form-group` 内）

`:241` と `:323` は完全に同一の `onChange`。**片方だけ変更してもう片方に反映される**。
ユーザーは「2つの入力欄がある」ように見え、どちらが CustomConfig に対応するか分からない。

**回帰テスト（先に作る）**

```tsx
it('**1話あたりの目標文字数の入力欄が 1 つだけ**である（重複描画の防止）', async () => {
  setup();
  await screen.findByText('追放ざまぁ（Web連載・1巻40話）');
  fireEvent.click(screen.getByRole('button', { name: /カスタム設定|詳細| Moe/ }));
  const inputs = screen.getAllByLabelText(/1話あたりの目標文字数/);
  expect(inputs.length, `同一状態の入力欄が ${inputs.length} 個ある`).toBe(1);
});
```

**修正内容**

- `:234-246`（外側）を**削除**し、`:317-328`（CustomConfig 内側）だけを残す。
- 残す方に `htmlFor` / `id` を付ける（B8 と併せて）。
- CustomConfig が閉じている間は値が編集できないが、それは既存仕様に従う。

**検証コマンド**
```powershell
cd frontend; npx vitest run src/components/generate/SimpleModePanel.test.tsx
```

**完了判定**: 1 テスト緑。**修正前に `2 個ある` で赤**を記録。

---

### B7. `card_id` 欠落時の React key 破綻の修正
- **対象ファイル**: `frontend/src/components/generate/SimpleModePanel.tsx`（`:194-198`）、`frontend/src/components/wizard/Step1PlotInput.tsx`（`:79-81`, `:180-182`）
- **依存**: A22（`misc.py` が `card_id` を確実に付与することが前提）
- **推定所持**: 30 分

**背景（レビュー時）**

F4 で `const cid = card.card_id || card.id || card.label` を
`const cid = card.card_id;` に** 단순화**した（`:194`）。

**フォールバックが無くなったことで、payload に `card_id` が無い場合に:**
- `cid = undefined` が全カード → **React key が重複**（警告 + 差分更新バグ）
- `isSelected = (selectedCardId === undefined)` → `selectedCardId` は `null` なので **常に false**
- クリックしても `setSelectedCardId(card.card_id ?? null)` = `null` のまま → **ハイライトが一切付かない**

**F4 が直そうとした「カード選択ハイライトが無効になる」バグが、非適合 payload に対して再発する。**

**回帰テスト（先に作る）** — `SimpleModePanel.test.tsx` に追加

```tsx
it('**card_id が無い payload でも React key 重複が起きない**', async () => {
  const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
  setup({ cards: REAL_API_CARDS.cards.map(({ card_id, ...rest }) => rest) });  // card_id を剥がす
  await screen.findByText('追放ざまぁ（Web連載・1巻40話）');
  const keyWarnings = spy.mock.calls.filter((c) => String(c[0]).includes('key'));
  expect(keyWarnings, `React key 重複警告: ${keyWarnings}`).toHaveLength(0);
  spy.mockRestore();
});

it('**card_id が無い payload でもクリックで選択状態が変わる**', async () => {
  setup({ cards: REAL_API_CARDS.cards.map(({ card_id, ...rest }) => rest) });
  const tile = (await screen.findByText('密室殺人（短編）')).closest('div[style]')!;
  fireEvent.click(tile);
  await waitFor(() => expect(tile.getAttribute('style')).toContain('2px solid'));
});
```

**修正内容**

`SimpleModePanel.tsx:194` を**インデックス付きの決定論的 ID** に変更:

```typescript
const cid = card.card_id ?? `idx:${cards.indexOf(card)}`;
```

`Step1PlotInput.tsx:79-81` / `:180-182` の `card.card_id ?? card.id` も同じくする。

> **設計方針**: `card_id` が無いのは**異常**なので、ログで可視化しつつ
> 描画は壊さない。FE に警告を出す:
> `console.warn('[planning_options] card_id が無いカードがあります', card)`

**検証コマンド**
```powershell
cd frontend; npx vitest run src/components/generate/SimpleModePanel.test.tsx src/components/wizard
```

**完了判定**: 新規 2 テスト緑。**修正前に両方赤**を記録。

---

### B8. ラベルの `htmlFor` / `id` 付与（アクセシビリティ）
- **対象ファイル**: `frontend/src/components/generate/SimpleModePanel.tsx`（`:219-231`, `:234-246`, `:248-257`）
- **依存**: B6
- **推定所持**: 20 分

**背景**

F4 は「目標話数」だけに `htmlFor="target-episodes"` と `id` を付けた（`:219-225`）。
**同じコミットで追加した 2 つのラベルには付かなかった**:
- `:236` `<label className="label">1話あたりの目標文字数</label>`
- `:250` `<label className="label">文体スタイル</label>`

**スクリーンリーダー利用者が入力欄を特定できない**。
B6/B5 で残る 1 箇所に `htmlFor` / `id` を付ける。

**回帰テスト（先に作る）**

```tsx
it('**追加した入力欄が label で名前付けされている**', async () => {
  setup();
  await screen.findByText('追放ざまぁ（Web連載・1巻40話）');
  // getByLabelText は htmlFor/id による関連付けを要求する
  expect(() => screen.getByLabelText('1話あたりの目標文字数')).not.toThrow();
  expect(() => screen.getByLabelText('文体スタイル')).not.toThrow();
});
```

**修正内容**

```tsx
<label className="label" htmlFor="chars-per-ep">1話あたりの目標文字数</label>
<input id="chars-per-ep" type="number" ... />

<label className="label" htmlFor="style-key">文体スタイル</label>
<input id="style-key" type="text" ... />
```

**検証コマンド**
```powershell
cd frontend; npx vitest run src/components/generate/SimpleModePanel.test.tsx
```

**完了判定**: 1 テスト緑。**修正前に `Unable to find a label` で赤**を記録。

---

### B9. 警告判定の単一源化
- **対象ファイル**: `frontend/src/components/editor/ManuscriptTargetIndicator.tsx`（`:36-52`）
- **依存**: A1
- **推定所持**: 25 分

**背景（レビュー時）**

F2 で追加された `isWarningState`:
```typescript
const isWarningState = Boolean(
  targetState &&
    (targetState.isWarning ||
      (!targetState.isOver && !targetState.isMaxOver &&
        targetState.ratio >= activePreset.warningThreshold))
);
```

`targetState.isWarning` は `checkTarget` が**既に** `warningThreshold` で判定しているはず。
**同じ規則が 2 箇所に複製**されている。

どちらか一方が変わると、**プログレスバーの色とテキストが食い違う**可能性が生じる
（現状は両方 `isWarningState` を見ているので一致するが、規則の二重定義が危険）。

**回帰テスト（先に作る）** — `frontend/tests/unit/components/ManuscriptTargetIndicator.test.tsx` に追加

```tsx
it('**警告状態の判定が checkTarget と 1 箇所しか無い**（二重定義の防止）', async () => {
  // ratio が warningThreshold 未満なら「注意」であって「警告」ではない
  render(<ManuscriptTargetIndicator count={count} selectedPresetId="short" />);
  await waitFor(() => expect(screen.getByTestId('preset-select')).toBeTruthy());

  const bar = await screen.findByTestId('progress-bar');
  const yellow = bar.getAttribute('style')?.includes('#eab308');
  expect(yellow, 'warningThreshold 未満なのに警告色').toBe(false);
});

it('warningThreshold 到達で警告色になる（単一源で判定されている）', async () => {
  // targetChars の 90% 以上の count を与える
  const target = MANUSCRIPT_PRESETS.find((p) => p.id === 'short')!;
  render(<ManuscriptTargetIndicator count={Math.floor(target.targetChars * 0.92)} selectedPresetId="short" />);
  await waitFor(() => {
    expect(screen.getByText(/あと/)).toBeTruthy();
  });
});
```

**修正内容**

`checkTarget`（`src/utils/manuscriptCount.ts` 側）が `isWarning` を正しく判定しているなら、
`isWarningState` は `targetState.isWarning` に**委譲するだけに**する:

```typescript
// ★ 警告の判定は checkTarget に一本化する。
//   ここで ratio を再判定すると、プログレスバーの色とテキストが乖離する。
const isWarningState = Boolean(targetState?.isWarning);
```

`checkTarget` が `warningThreshold` を使っていない場合は、
**`checkTarget` 側を直す**（B は `src/utils/**` を持てるので §0.2 に追記）。

**検証コマンド**
```powershell
cd frontend; npx vitest run tests/unit/components/ManuscriptTargetIndicator.test.tsx
```

**完了判定**: 新規 2 テスト緑。

---

### B10. lint / format ゲートの実行可能性確保
- **対象ファイル**: `Makefile`（`:17-27`）、`.github/workflows/ci.yml` は B11
- **依存**: A1
- **推定所持**: 50 分

**背景（レビュー時実測）**

F2 の F5 で `Makefile` のスコープを `src tests` → `src tests config scripts` に**広げた**が、
**何も直していない**。結果として:

```
ruff check src tests config scripts          → 983 errors
  W293=150, F841=71, W292=41, F811=38, F821=36, E712=27, F541=26, E741=22, ...
ruff format --check src tests config scripts → 1641 files would be reformatted
```

**`make lint` も `make format-check` も通りらない。** つまり**どちらも「実行できないゲート」**。

特に **F821（未定義名）36 件は本物のバグ**:
- `config/streamlit_adapter.py:254` 他 13 箇所 — **module-level の関数内で `self` を使用**
  （到達すれば `NameError`）
- `scripts/detect_flaky.py:27` — `e` が未定義
- `src/backend/workflows/reverse_plot_workflow.py:122` — `Spine`（A20 で修正）

**F811（再定義）38 件**も `annotations.py` / `plots.py` で実際にモジュール上位の import を上書きしている。

**修正内容**

1. **`F821` / `F811` を 0 にする**（これらは本物）。`ruff check --fix` で安全に直せるものは自動修正、
   `config/streamlit_adapter.py` の `self` は手動。
2. **`W293` / `W292` / `W291`（CRLF/末尾空白 系）** を自動修正（`--fix` で 812 件 fixable）。
3. **`format` は「全部を 1 度に整形」しない**（1641 ファイルの変更はレビュー不能）。
   代わりに **`format-check` の対象を新規・変更ファイルに限定**する:
   ```makefile
   format-check:  ## ruff format チェック（変更ファイルのみ。既存 1641 件の滞留は別招生计划）
   	py -m ruff format --check $$(git diff --name-only origin/main...HEAD -- '*.py' | tr '\n' ' ')
   ```
4. `lint` に **`--select F821,F811` の hard gate** を追加:
   ```makefile
   lint-critical:  ## 未定義名・再定義のみ（これらは本物のバグなので hard gate）
   	py -m ruff check src tests config scripts --select F821,F811
   ```

**回帰テスト（先に作る）** — CI 側のゲートは B11。
ここでは `make lint-critical` が緑になることを完了条件にする。

**検証コマンド**
```powershell
make lint-critical
C:\Python314\python.exe -m ruff check src tests config scripts --select F821,F811
```

**完了判定**: **`ruff --select F821,F811` が 0 errors**（HG2）。`make lint-critical` が緑。

---

### B11. `.github/workflows/ci.yml` の静的解析 ratchet を実効化する
- **対象ファイル**: `.github/workflows/ci.yml`（`:14-43`）
- **依存**: B10
- **推定所持**: 35 分

**背景**

`:25-43` の `static-analysis` ジョブは `continue-on-error: true` で**記録のみ**。
コメント（`:17-24`）には「エラー数が 0 のルールセットが確定した時点で、そのルールだけを hard gate に格上げする」とある。

**B10 で F821/F811 を 0 にしたので、その 2 ルールを hard gate に格上げできる。**

また `:138` の
```yaml
python -m pip install -e .. || pip install -r ../requirements.txt || true
```
の末尾 `|| true` は **「両方失敗しても CI は緑」**を意味する。
続く `:153` の `python scripts/export_planning_options.py --check` が
Python 依存不足で失敗しても**気づけない**設計になっている（`:153` 自体は hard gate なので赤になるが、
原因が「依存不足」なのか「スナップショット不一致」なのか区別できない）。

**修正内容**

```yaml
  static-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
      - name: Install linters
        run: |
          python -m pip install --upgrade pip
          pip install "ruff==0.16.5" "mypy==2.3.1"

      # ★ B10 で 0 にしたルールセットを hard gate に格上げする
      - name: ruff critical (hard gate: F821 undefined-name / F811 redefinition)
        run: ruff check src tests config scripts --select F821,F811

      # 残りは記録のみ（ratchet）
      - name: ruff (record-only ratchet)
        run: ruff check src tests config scripts --statistics --output-format=concise || true
      - name: mypy (record-only ratchet)
        run: mypy src || true
```

`:138` の `|| true` を削除し、失敗時に**理由が分かるメッセージ**を出す:
```yaml
      - name: Install Python package for snapshot check
        run: |
          python -m pip install --upgrade pip
          pip install -e . -r requirements.txt
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m ruff check src tests config scripts --select F821,F811
# ci.yml の YAML 構文確認
C:\Python314\python.exe -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml',encoding='utf-8')); print('ci.yml OK')"
```

**完了判定**: `ci.yml` が YAML として妥当、`ruff --select F821,F811` が 0 errors。

---

### B12. `planning_options` スナップショットの射影化（113KB → 必要字段のみ）
- **対象ファイル**: `scripts/export_planning_options.py`、`frontend/tests/fixtures/planning_options.snapshot.json`、`tests/unit/scripts/test_planning_options_projection.py`（新規）
- **依存**: A22
- **推定所持**: 45 分

**背景（レビュー時実測）**

現状のスナップショットは **112,977 バイト（113KB）**。
`/api/config/planning_options` は `patterns`（`patterns.yaml` 全体）と `beat_vocabulary` を含むため。

**問題 3 つ:**
1. **FE 契約テストが `patterns.yaml` のバイト完全一致に結合している**
   → パターン 1 つにビートを 1 個足すだけで fixture 再生成が必須。
   FE の契約として必要なのは `cards` / `lengths` / `genres` / `growth_curves` だけ。
2. **同じ検査が 3 箇所で重複**:
   - `tests/unit/scripts/test_planning_options_snapshot.py:21` が subprocess で `--check`
   - `.github/workflows/ci.yml:151-153` が frontend ジョブで同じ `--check`
   - → 同じ検証が pytest 1 回 + CI 1 回 = **約 2 分の CI 時間**
3. **`export_planning_options.py` はアプリ全体を import する**
   （`from src.backend.routers.misc import get_planning_options`）ため subprocess 1 回に数十秒。

**回帰テスト（先に作る）** — `tests/unit/scripts/test_planning_options_projection.py`

```python
"""**スナップショットが FE が実際に消費するフィールドのみ**を含むことの検証。

レビュー実測: 現状 112,977 バイト。FE 契約として必要なのは
  cards / lengths / genres / growth_curves / style_definitions
のみ。`patterns` と `beat_vocabulary` の全体ダンプは FE 契約と無関係。
"""
from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT = Path("frontend/tests/fixtures/planning_options.snapshot.json")

# FE が実際に読むフィールド（Step1PlotInput / SimpleModePanel / Step2 から grep で確定）
FE_CONSUMED = {"cards", "lengths", "markets", "genres", "growth_curves", "style_definitions"}


def test_snapshot_exists_and_is_small_enough_to_review():
    assert SNAPSHOT.exists(), "スナップショットが無い"
    size = SNAPSHOT.stat().st_size
    assert size < 40_000, (
        f"スナップショットが {size:,} バイト。FE 契約と無関係な backend 設定が"
        "混ざっている可能性（113KB はレビュー不能）"
    )


def test_snapshot_only_contains_fe_consumed_fields():
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    extra = set(data) - FE_CONSUMED
    assert not extra, (
        f"FE が消費しないフィールドが含まれる: {sorted(extra)}。"
        "patterns / beat_vocabulary は FE 契約ではない"
    )


def test_projected_snapshot_still_covers_every_card():
    """**射影してもカードの網羅性が保たれる**こと（情報を削りすぎない）。"""
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    cards = data["cards"]
    assert len(cards) >= 100, f"カードが {len(cards)} 件しかない（全文flight なら 168 件）"
    for c in cards:
        assert {"card_id", "label", "pattern", "length", "market", "style_key"} <= set(c), c
```

**修正内容**

`scripts/export_planning_options.py` に射影を追加:
```python
#: FE が実際に消費するフィールドのみを残す（他の 113KB は FE 契約と無関係）
FE_FIELDS = ("cards", "lengths", "markets", "genres", "growth_curves", "style_definitions")


def project(payload: dict) -> dict:
    """FE 契約に必要なフィールドだけを切り出す。"""
    return {k: payload[k] for k in FE_FIELDS if k in payload}
```

`tests/unit/scripts/test_planning_options_snapshot.py:21-31` の subprocess 呼び出しを**削除**し、
`test_planning_options_projection.py` の静态チェックに置き換える
（CI の `ci.yml:151-153` が実際の鮮度確認を担当する。**pytest 側ではしない**）。

**検証コマンド**
```powershell
C:\Python314\python.exe scripts\export_planning_options.py
C:\Python314\python.exe scripts\export_planning_options.py --check
C:\Python314\python.exe -m pytest tests\unit\scripts -q
cd frontend; npx vitest run tests/unit/api/planningOptions.contract.test.ts src/components/wizard
```

**完了判定**: スナップショットが **40KB 未満**、`test_snapshot_only_contains_fe_consumed_fields` 緑、
**FE の既存テストが全て緑のまま**（`Step1PlotInput.test.tsx` が snapshot を読むため）。

---

### B13. `STATUS.md` ガードの 69 秒問題・skip 自己消滅・壊れた文言
- **対象ファイル**: `tests/regression/test_status_md_counts_match_reality.py`（`:27`, `:37`, `:59`）
- **依存**: A1
- **推定所持**: 40 分

**背景（レビュー時実測）**

`:41-50`:
```python
def test_status_md_test_counts_match_reality():
    for m in CLAIM_RE.finditer(text):
        path, claimed = m.group("path"), int(m.group("n"))
        actual = _collect(path)      # ★ subprocess pytest --collect-only
```

**実測: この 3 テストだけで 68.85 秒。**
CI は `pytest tests/regression/ -v --timeout=120`（`ci.yml:119`）、
回帰スイート全体は 1024 件 / 164 秒。
**1 つの文書メタデータテストが 1/3 の時間を消費**し、
ラrunner が数十 % 遅くなると **`--timeout=120` を超えて hard gate が赤くなる**。

**加えて 3 つの構造的欠陥:**

1. **`:27` の `pytest.skip` がループ内** → 参照パス 1 つが壊れると
   **ガード全体が失敗ではなくスキップされる**。
   「ガードが必要なときに消える」= 計画書が潰そうとした欠陥と同じ型。
2. **`:37` の assertion message が壊れている**:
   `"本テストが無意味になるoclude rior entiousな状態を検出する"`
   → 計画書の破損テキストがそのままソースにコミットされている。
3. **`:59` の `text.split("効果測定", 1)[-1]`** が
   **§5（`docs/STATUS.md:99` `## 5. v6 効果測定`）** を指している。
   R1 が対象にしたのは **§7（`:251` `## 7. STORY_SPINE 導入の効果測定`）**。
   つまり想定より遥かに広い範囲を検査しており、先頭に「効果測定」が書かれると範囲が動く。

**回帰テスト（先に作る）** — 本ファイル内に追加

```python
def test_measurement_section_selector_targets_section_7():
    """**「効果測定セクション」の切り出しが §7 を指す**こと。

    レビュー実測: `split("効果測定", 1)[-1]` の最初の出現は
    `docs/STATUS.md:99`（`## 5. v6 効果測定`）で、
    R1 が対象にしたのは `:251`（`## 7. STORY_SPINE 導入の効果測定`）。
    """
    text = STATUS.read_text(encoding="utf-8")
    section = _measurement_section(text)
    # §7 の見出しが含まれること
    assert "STORY_SPINE 導入の効果測定" in section, (
        "切り出したセクションが §7 を含まない。想定より狭い/広い"
    )
    # §5 の内容が混入していないこと
    assert "## 5. v6 効果測定" not in section, "§5 が混入している（起点が早すぎる）"


def test_guard_does_not_skip_when_a_claimed_path_is_broken(tmp_path, monkeypatch):
    """**参照パスが壊れたら skip ではなく fail する**ことの検証。

    レビュー実測: `_collect` の `pytest.skip` がループ内にあり、
    パス 1 つが壊れると**ガード全体がスキップされる**
    （= 必要なときに消える）。
    """
    import re as _re

    offenders = _verify_claims("tests/unit/does_not_exist.py (99件緑)".replace(" (99件緑)", ""))
    assert offenders, "壊れたパスが offenders に入っていない（skip している）"
```

**修正内容**

1. **`skip` → `fail` 化**（`:21-29`）:
```python
def _collect(path: str) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", path, "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        # ★ skip ではなく失敗にする。ガードが必要なときに消えてはならない。
        raise AssertionError(
            f"{path} を収集できない（collection error）。"
            f"STATUS.md の記載が古いか、テストが壊れている:\n{proc.stdout[-800:]}"
        )
    m = re.search(r"(\d+) tests? collected", proc.stdout)
    return int(m.group(1)) if m else len(re.findall(r"::", proc.stdout))
```

2. **subprocess を廃止して AST で数える**（**69 秒 → 0.1 秒**）:
```python
def _collect(path: str) -> int:
    """`pytest --collect-only` の代わりに **AST で test 関数を行数する**。

    レビュー実測: subprocess 版は 3 テストで 68.85 秒（CI の --timeout=120 に接近）。
    AST 版はファイルを読むだけなので 0.1 秒で終わる。
    正確な収集数が必要な場合は CI の `export_planning_options.py --check` 相当の
    「実測」と同じ原則 fulfち、**静的数で足りる**（本ガードの目的は陈腐化検出）。
    """
    import ast

    src = Path(path)
    if not src.exists():
        raise AssertionError(f"{path} が存在しない。STATUS.md の記載が古い")
    tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                n += _parametrized_count(node)
    return n
```
（`_parametrized_count` は `pytest.mark.parametrize` の積を数える簡易実装。
**完璧である必要はなく**、STATUS.md の数字を保守するインセンティブとして機能すればよい。
**ただし「完全一致でない」ことを docstring に明記すること**。）

3. **セクション切り出しを §7 固定に**（`:59`）:
```python
_MEASUREMENT_HEADING = "## 7. STORY_SPINE 導入の効果測定"


def _measurement_section(text: str) -> str:
    """効果測定セクション（§7）を厳密に切り出す。

    レビュー実測: `split("効果測定", 1)` は §5（STATUS.md:99）を指していた。
    見出し文字列で区切ることで、起点が前方に 늘어나ても影響を受けない。
    """
    idx = text.find(_MEASUREMENT_HEADING)
    if idx < 0:
        # 見出しが変わった場合も「効果測定」の最終出現でフォールバック
        idx = text.rfind("効果測定")
    assert idx >= 0, f"{_MEASUREMENT_HEADING} が見つからない（STATUS.md の構成が変わった）"
    return text[idx:]
```

4. **壊れた文言を修正**（`:36-37`）:
```python
    assert CLAIM_RE.findall(text), (
        "docs/STATUS.md に「（**N件**緑）」形式の自己申告が無い。"
        "本テストが無意味な状態 Detect であることを検出する"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_status_md_counts_match_reality.py -v --durations=5
```

**完了判定**: 5 テスト緑。**実行時間が 5 秒以内**（現状 68.85 秒 → HG3 達成 contribute）。
**`test_guard_does_not_skip_when_a_claimed_path_is_broken` が修正前に赤**（skip で消える）。

---

## 4. 統合フェーズ（I1）

### I1. 統合と「完成形」判定
- **担当**: 統合担当（**A/B どちらも触らない**）
- **依存**: **HA1 かつ HB1 かつ HG1-GH4 すべて充足**

**作業内容**

1. **ベースライン比較**（P: 未コミット変更があると全部が「回帰」になる）:
```powershell
git log --oneline origin/main..HEAD
# A/B の全ステップが 1 ステップ = 1 コミットになっているか確認
```

2. **FE テスト全緑**:
```powershell
cd frontend
npx tsc --noEmit                 # 0 errors
npm run lint                    # 0 errors
npm run test:ci                 # failed 0
cd ..
```

3. **Python テスト全緑**:
```powershell
C:\Python314\python.exe -m pytest tests\regression -q --timeout=300
C:\Python314\python.exe -m pytest tests\contract tests\unit -q --timeout=300
```

4. **`docs/STATUS.md` 差分反映**（統合담당のみ）:
   - 効果測定表の K1-K7 の件数表記を実測に更新する
   - **A23/B13 で「文書ガードが静的解析に変わった」ことを書く**
   - **`:190` 付近の未実装スタブの記述が現状と合っているか確認する**

5. **「完成形」判定**:

| 判定基準 | 確認方法 |
|:---|:---|
| S1-1 `validate()` が spine を埋め込まない | `A17` のテスト緑 |
| S1-2 短編で充足度が壊れない | `A15` / `A16` のテスト緑 |
| S1-3 Wizard が book 1 を表示しない | `B1` のテスト緑 |
| S1-4 フィナーレが全話数で到達可能 | `A12::test_finale_is_reachable_at_every_length_ge_3` 緑 |
| 空振りテスト 3 件が解消 | `A13` / `A12` / `B13` の各テスト緑 |
| lint の F821/F811 が 0 | `HG2` |
| 回帰スイートが 300 秒以内 | `HG3` |
| `make lint-critical` / `make format-check` が緑 | `HG4` |

6. **P4 の監査**: 全コミットメッセージに「修正前 N 件赤 → 修正後 0 件」が
   記録されているか確認する。**1 つも無いコミットがあれば、そのステップはやり直し**。

---

## 5. 完了判定サマリ

### 5.1 ゲート全充足 crossword

| ゲート | 条件 | 担当 |
|:---|:---|:---:|
| **HA0** | ブランチ作成済み・作業ツリークリーン | A1 |
| **HA1** | `pytest tests/unit/story_spine tests/unit/story_spine_wiring tests/contract tests/regression -q` 緑 | A23 |
| **HB1** | `tsc` 0 / `eslint` 0 / `vitest failed 0` | B13 |
| **HG1** | 全ステップで「修正前赤」を記録（P4） | I1 |
| **HG2** | `ruff --select F821,F811` が 0 errors | B10 |
| **HG3** | `pytest tests/regression` が 300 秒以内 | I1 |
| **HG4** | `make lint-critical` / `make format-check` 緑 | B10 |

### 5.2 S1 の消滅確認（レビュー Extr findings との対応）

| レビュー指摘 | 対応ステップ | 消滅の証拠 |
|:---|:---|:---|
| S1-1 `validate()` が book に無関係な spine を返す | **A17** | `test_response_does_not_embed_a_spine_with_hardcoded_length` |
| S1-2 短編で充足度が必ず壊れる | **A15 / A16** | `test_beat_presence_is_detected_even_with_coarse_phase_grid`（修正前 112 件赤） |
| S1-3 Wizard が常に book 1 を表示 | **B1** | `bookId 未確定で叩かれた URL` が空 |
| S1-4 フィナーレが到達不能 | **A10 / A11 / A12** | `test_finale_is_reachable_at_every_length_ge_3` |
| S2-5 `Spine` が実キーを報告しない | **A2 / A3** | `test_spine_reports_fallback_key_when_input_is_unknown` |
| S2-6 web+短編で close beat が消える | **A5 / A6** | `test_web_keeps_at_least_one_close_role_beat`（修正前 203 件赤） |
| S2-7 `_merge_duty` が情報損失 | **A7 / A8** | `test_merge_reports_which_beats_were_absorbed` |
| S2-8 逆プロットが genre を無視 | **A20** | `test_spine_for_honours_length_and_market`（修正前 6 件赤） |
| S2-9 契約テスト 95 行目が空虚 | **A13** | `test_hard_includes_the_numeric_tension_value` |
| S2-10 STATUS.md ガード 69 秒 + skip 自己消滅 | **B13** | `test_guard_does_not_skip_when_a_claimed_path_is_broken` |
| S2-11 効果測定セクションの起点ズレ | **B13** | `test_measurement_section_selector_targets_section_7` |
| S2-12 壊れたコメント文字列 | **B13** | コードレビュー |
| S2-13 `Spine` の未 import | **A20** | `ruff --select F821` が 0 |
| S3-14 `card_id` 展開順序 | **A22** | `test_card_id_cannot_be_overridden_by_the_card_body` |
| S3-15 `growth_curves` truthiness | **A22** | `test_growth_curves_are_non_empty_strings` |
| S3-16 113KB スナップショット | **B12** | `test_snapshot_only_contains_fe_consumed_fields` |
| S3-17 検査の 3 重複 | **B12 / B13** | pytest 側の subprocess 撤去 |
| S3-18 `styleKey` 死んだ制御 | **B5** | `styleKey が生成リクエストに含まれる` |
| S3-19 `contentLengthLimit` 二重描画 | **B6** | `入力欄が 1 つだけ` |
| S3-20 `card_id` 欠落時 key 破綻 | **B7** | `React key 重複警告` が 0 件 |
| S3-21 ラベル `htmlFor` 欠落 | **B8** | `getByLabelText` が例外を投げない |
| S3-22 警告判定の二重定義 | **B9** | `warningThreshold 未満なのに警告色` が false |
| S3-23 `test_random_chapters...` の余裕ゼロ | **A16** | 新しく margin を持った assertion に置換 |
| S3-24 lint / format ゲートが赤 | **B10 / B11** | HG2 / HG4 |
| S3-25 `STORY_ARCHETYPES` 二重 SSOT | **A23** | `test_json_and_python_definitions_agree` |

---

## 6. 失敗時の対処

### 6.1 1 ステップが赤で止まったら

```powershell
git reset --hard HEAD~1     # P6: 1 ステップ = 1 コミットなので巻き戻せる
# 次のステップに進む前に、なぜ赤なのかを notes/ に残す
```

### 6.2 A と B の間に競合が出たら

1. **どちらかを止める**（ファイル排他所有表 violated を確認）
2. §0.2 の表を**必ず更新**してから再開する
3. **統合担当のみ**が表を編集できる

### 6.3 「テストを弱めて緑にした」迹象を見つけたら

**そのステップは-rollback する。**
P4 の存在意義は「赤を確認できないテストを書かない」ことにある。
`assert healthy <= 3` → `assert healthy <= 10` のような変更は**工作量 against の完了宣言ではない**。

---

## 7. 付録：レビュー時点の全実測値

```
=== Python テスト ===
pytest tests/regression tests/contract tests/unit/story_spine tests/unit/story_spine_wiring
  → 1024 passed, 17 skipped (163.71s)
pytest tests/regression/test_status_md_counts_match_reality.py
  → 3 passed in 68.85s

=== フロントエンド ===
npx tsc --noEmit        → 0 errors
npm run lint             → 0 errors, 316 warnings
npm run test:ci          → 48 files / 238 tests passed (93.21s)

=== Lint ===
ruff check src tests config scripts      → 983 errors
  W293=150, F841=71, W292=41, F811=38, F821=36, E712=27, F541=26, E741=22, W291=15, ...
ruff format --check (同スコープ)          → 1641 files would be reformatted

=== spine_resolver 実測 ===
coverage violations (n > eps の重なり): 342 組  ※1話短編の仕様として意図的
duplicate keys:                           0 組
web ending_contract 違反:                 0 組
close-role 全滅 (web, eps 3..40):        203 組  ★S2-6

=== beat span 実測 ===
order violations (終端順序逆転):           7 組
overlapping spans:                        31/32 組
  climax(0.82,0.94) overlaps aftermath(0.88,0.94)   ★S1-4 の根因

=== PacingGraph 実測 ===
eps=3,5,8,10,12,16 → グランドフィナーレ None（到達不能）★S1-4

=== structure_validator 実測 ===
small-eps false missing (eps 3..8):       112/190 組  ★S1-2
alignment min/mean (eps 6..60):            0.889 / 0.998
random healthy (50 ケース):                 3/50   ← test の閾値と一致（余裕ゼロ）★S3-23
validate() 応答サイズ:                       3,886 bytes（うち spine が不要）★S1-1

=== misc.py 実測 ===
planning_options スナップショット:         112,977 bytes  ★S3-16
STYLE_DEFINITIONS:  style_web_standard, style_serious_fantasy, ...
cards.yaml style_key: comedy, cool_headed, dark, healing, hot_blooded, romantic
  → **1 つも一致しない** ★S3-18

=== Spine の追跡不能性 ===
resolve_spine("nope","bogus_len","bogus_market",5)
  Spine reported : nope bogus_len bogus_market
  Spine actual   : exile_rise novella general
  identical beats : True                    ★S2-5
```

---

## 8. 変更履歴

| 版 | 日付 | 内容 |
|:---|:---|:---|
| 1.0 | 2026-10-01 | 初版。36 ステップ（TRACK-A 23 / TRACK-B 13）作成 |


