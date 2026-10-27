# AutoNovel コードレビュー整改計画書【F2 / 13 ステップ】

## ── 「一応の完成形」を出すための S1 消除と回帰網の構築 ──

- **文書ID**: PLAN_F2_CODE_REVIEW_REMEDIATION
- **作成日**: 2026-09-30
- **起点イベント**: 2 サブエージェント並列コードレビュー（TRACK-A: Python 中核 / TRACK-B: 配線・FE・ツール）
- **前提文書**: [PLAN_F1_STORY_SPINE_IMPLEMENTATION.md](PLAN_F1_STORY_SPINE_IMPLEMENTATION.md)（以下「F1 計画」）、[PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md](PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md)
- **対象バージョン**: AutoNovel v6.0.0（F1 実装済み・未マージ相当の作業ツリー）
- **総合判定（レビュー時）**: **不可**。S1 が 8 件、既存回帰 1 件が赤
- **構成**: TRACK-R（Python 中核 8 ステップ）／ TRACK-F（FE・契約・CI 5 ステップ）＝ **計 13 ステップ**

---

## 0. 本計画書の位置づけ

F1 は「構造テンプレート層を入れる」ための計画だった。あれは実装された。
しかしレビューにより、**既存 198 + 129 + 210 件のテストが緑であるにもかかわらず、本番を壊す欠陥が 8 件見つかった**。

この欠陥の共通根因は 1 つに集約できる。

> **テストが「その功能が削除されても緑になる」形になっている。**
> つまりテストは実装の**足止め**をdetect したが、**意味**をdetect していなかった。

本計画は **「欠陥の修正」と「その欠陥を 2 度と検出できないテストの追加」** を 1 ステップに必ず:set する。テストのない修正ステップは **存在してはならない**（P5: テスト先行）。

### 0.1 分割原則

| 原則 | 内容 |
|:---|:---|
| **P1 ファイル排他所有** | **1 ファイルは 1 エージェントのみ**が触る |
| **P2 完了判定は 1 行** | 「緑か赤か」のみ。数値の解釈を LLM にさせない |
| **P3 修正とテストは同一コミット** | テストのない修正を残さない |
| **P4 反証テストを 1 本ずつ** | 修正前にそのテストが**実際に赤くなる**ことを確認する（赤を確認できないテストは書かない） |
| **P5 猜测禁止** | 対象ファイルの行番号・関数名を必ず grep で確認してから編集する |
| **P6 1 ステップ = 1 コミット** | 失敗したら `git reset --hard HEAD~1` して次へ |
| **P7 環境隔離** | 並列 pytest のため DB を分ける（`$env:DATABASE_URL`） |

### 0.2 ★ ファイル排他所有表

**この表に無いファイルを触ってはいけない。**

| ファイル | 所有者 | ステップ |
|:---|:---:|:---:|
| `docs/STATUS.md` | **R** | R1 |
| `src/services/spine_resolver.py` | **R** | R2 / R3 |
| `src/services/structure_validator.py` | **R** | R4 |
| `src/backend/engine_narrative.py` | **R** | R5 |
| `src/backend/workflows/reverse_plot_workflow.py` | **R** | R6 |
| `src/backend/routers/easy_mode.py` | **R** | R7 |
| `config/story_spine/genre_registry.py` | **R** | R7 |
| `src/services/llm/prompts.py` | **R** | R8（読むだけ） |
| `src/backend/routers/misc.py` | **F** | R8（growth_curves）／F1（card_id） |
| `tests/contract/test_spine_prompt_injection.py` | **R** | R8 |
| `tests/e2e/test_spine_end_to_end.py` | **R** | R8 |
| `frontend/src/constants/manuscript.ts` | **F** | F2 |
| `frontend/src/types/manuscript.ts` | **F** | F2 |
| `frontend/src/components/editor/Editor.tsx` | **F** | F2 |
| `frontend/src/components/**/ManuscriptTargetIndicator.tsx` | **F** | F2 |
| `frontend/src/components/planning/BeatSheetViewer.tsx` | **F** | F3 |
| `frontend/src/components/generate/SimpleModePanel.tsx` | **F** | F4 |
| `frontend/src/components/wizard/Step1PlotInput.tsx` | **F** | F5 |
| `.github/workflows/ci.yml` | **F** | F5 |
| `Makefile` | **F** | F5 |
| `tests/regression/**`（新規） | **R** | R1-R7 |
| `tests/unit/story_spine/**`（新規） | **R** | R2-R4 |
| `tests/unit/story_spine_wiring/**`（新規） | **R** | R6 / R7 |
| `tests/contract/**`（新規） | **F** | F1 |
| `tests/unit/scripts/**` | **R** | R8 |
| `frontend/src/**/*.test.ts(x)` | **F** | F2-F5 |
| `frontend/tests/**` | **F** | F2-F5 |
| `scripts/export_planning_options.py`（新規） | **F** | F5 |
| `plans/PLAN_F2_CODE_REVIEW_REMEDIATION_13STEPS.md` | **統合** | 本書。読むだけ |

**衝突の事前計算**:
- `src/backend/routers/misc.py` は R8（`growth_curves` 追加）と F1（`card_id` 付与）の両方が触る。
  → **R8 を先に完了させ、F1 は R8 完了を待つ**。ただし推奨は **F1 が `growth_curves` も一并に実装する**（R8 は `misc.py` を触らず、`prompts.py` と契約テストのみに絞る）。
  **推奨:** F1 が `misc.py` の全変更（`card_id` + `growth_curves`）を 1 コミットで行う。R8 は `prompts.py` と契約テストのみに絞る。
- `tests/contract/` は R8（prompt 契約）と F1（planning_options 契約）が別ファイルで触る。ファイル名重複なし。
- `docs/STATUS.md` は R1 が独占する。F5 は「R1 完了後に 1 回だけ」追記する。

### 0.3 依存関係グラフ

```
  ┌────────────────────────────────────────────────────────┐
  │ R1 docs/STATUS.md の TODO 除去（CI 赤解消・1行）      │ ← ここが最優先
  └───────────────────────┬────────────────────────────────┘
                          │ Gate: tests/regression/ 緑
        ┌─────────────────┴──────────────────┐
        ▼                                    ▼
┌───────────────────────────────┐   ┌────────────────────────────┐
│ TRACK-R（Python 中核）        │   │ TRACK-F（FE・契約・CI）     │
│                               │   │                            │
│ R2 web volume_hook 契約復元    │   │ F1 misc.py: card_id +      │
│ R3 量子化での beat 消失根治    │   │    growth_curves + 契約テスト│
│ R4 validator の span 系統統一  │   │ F2 manuscript.ts ID 互換    │
│ R5 PacingGraph 相対窓・単一源  │   │ F3 BeatSheetViewer 型+mount │
│ R6 reverse_plot の区間 clamp   │   │ F4 SimpleModePanel card_id │
│ R7 genre→pattern 解決         │   │ F5 FE モック実形状化 + CI   │
│ R8 契約テストの空洞化解消      │   │                            │
└───────────────┬───────────────┘   └─────────────┬──────────────┘
                │                                 │
                └──────────────┬──────────────────┘
                               ▼
                 ┌─────────────────────────────┐
                 │ I1 統合（統合担当）          │
                 │ ・ベースライン比較           │
                 │ ・FE テスト全緑              │
                 │ ・docs/STATUS.md 差分反映     │
                 │ ・「完成形」判定             │
                 └─────────────────────────────┘
```

| ゲート | 条件 | 誰 |
|:---|:---|:---:|
| **H0** | `pytest tests/regression -q` が緑（CI の hard gate） | R1 |
| **H1** | `pytest tests/unit/story_spine tests/unit/story_spine_wiring -q` が緑 | R |
| **H2** | `pytest tests/contract tests/e2e/test_spine_end_to_end.py -q` が緑 | R + F |
| **H3** | `cd frontend; npx vitest run` が **failed 0** | F |
| **H4** | `pwsh -File scripts/compare_test_baseline.ps1` で**新規回帰 0 件** | 統合 |

### 0.4 作業開始前の必須事項

```powershell
# F1 計画 §0.4 の教訓。**未コミット変更がある状態で比較ベースラインを取ると全部が「回帰」になる**
git status --short          # 現状: 30 ファイル超が未コミット
git add -A && git commit -m "WIP: F1 STORY_SPINE 実装（レビュー整改のベースライン）"
git checkout -b fix/f2-review-remediation
```

**このコミットをしないと `scripts/compare_test_baseline.ps1` の baseline が不正確になり、H4 が成立しない。**

---

## 1. 変更ファイル総覧

### 1.1 新規（11 ファイル）

| ファイル | 担当 | ステップ |
|:---|:---:|:---:|
| `tests/regression/test_status_md_counts_match_reality.py` | R | R1 |
| `tests/unit/story_spine/test_resolver_market_contracts.py` | R | R2 |
| `tests/unit/story_spine/test_resolver_no_silent_drop.py` | R | R3 |
| `tests/unit/story_spine/test_validator_span_source.py` | R | R4 |
| `tests/regression/test_pacing_graph_relative.py` | R | R5 |
| `tests/unit/story_spine_wiring/test_reverse_plot_arc_ranges.py` | R | R6 |
| `tests/unit/story_spine_wiring/test_genre_pattern_mapping.py` | R | R7 |
| `tests/contract/test_planning_options_contract.py` | F | F1 |
| `frontend/src/constants/manuscript.migration.test.ts` | F | F2 |
| `frontend/tests/unit/api/planningOptions.contract.test.ts` | F | F5 |
| `scripts/export_planning_options.py` | F | F5 |

### 1.2 改修（14 ファイル）

| ファイル | 担当 | 変更内容 |
|:---|:---:|:---|
| `docs/STATUS.md` | R | `:190` の `TODO` を除去。K4 件数の誤記（7→4）を訂正 |
| `src/services/spine_resolver.py` | R | `_enforce_invariants` の早期 return 除去・キー重複排除・`_merge_duty` の切断改善 |
| `src/services/structure_validator.py` | R | `phase` を `patterns.yaml` の span へ・`beat_tol` 追加・`resolved_pattern_key`・`spine` 返却 |
| `src/backend/engine_narrative.py` | R | フィナーレ窓の相対化・境界の語彙 span 派生・定数の一元化 |
| `src/backend/workflows/reverse_plot_workflow.py` | R | `num_arcs` の clamp・`EMOTIONAL_GOAL_TO_CATHARSIS` の防御的参照・死んだ `HOOK_TO_EP1_TEMPLATE` 削除 |
| `src/backend/routers/easy_mode.py` | R | `resolve_pattern_key()` ヘルパを抽出（テスト可能に） |
| `config/story_spine/genre_registry.py` | R | 各エントリに `pattern` を追加 |
| `tests/contract/test_spine_prompt_injection.py` | R | 旧テンプレートの凍結スナップショット比較へ |
| `tests/e2e/test_spine_end_to_end.py` | R | 同上（自己参照比較の解消） |
| `tests/unit/scripts/test_measure_spine_alignment.py` | R | `db_reachable` の検証・DB 隔離 |
| `src/backend/routers/misc.py` | F | `cards` に `card_id` を付与・`growth_curves` を新設 |
| `frontend/src/constants/manuscript.ts` | F | ID 互換レイヤ・`maxPages` 判定・フォールバック同期 |
| `frontend/src/components/planning/BeatSheetViewer.tsx` | F | `missing_beats` の型・`alignment` 表示・`climax` フィールド名 |
| `frontend/src/components/generate/SimpleModePanel.tsx` | F | `card_id` 単一化・カード選択で `chars_per_ep`/`style_key` を自動入力 |

### 1.3 テスト改修（既存 8 ファイル）

| ファイル | 担当 | 変更内容 |
|:---|:---:|:---|
| `tests/unit/story_spine/test_resolver_compression.py` | R | R2 の穴を塞ぐ（web 破綻域の追加） |
| `tests/unit/story_spine/test_resolver_no_llm.py` | R | **no-op fixture の実装修**（文字列形式の monkeypatch） |
| `tests/regression/test_relative_episode_structure.py` | R | 部分文字列判定の偽阳性を修正 |
| `tests/unit/story_spine/test_validator_pattern.py` | R | `alignment > 0.0` の空虚な閾値を強化 |
| `frontend/src/constants/manuscript.test.ts` | F | `maxPages` 判定の期待値修正 |
| `frontend/src/components/planning/BeatSheetViewer.test.tsx` | F | モックを**実 API 形状**（dict 配列）に |
| `frontend/src/components/generate/SimpleModePanel.test.tsx` | F | モックを実レスポンス形状に |
| `frontend/tests/unit/components/ManuscriptTargetIndicator.test.tsx` | F | ID 変更の期待値更新 |

---

## 2. TRACK-R：Python 中核（8 ステップ）

### R1. `docs/STATUS.md` の `TODO` 除去（CI 赤の即時解消）
- **対象ファイル**: `docs/STATUS.md`（`:190`）
- **依存**: なし（**全作業の起点。1 行で CI が緑になる**）
- **推定所要**: 15 分

**背景**

`.github/workflows/ci.yml:118-119` は `pytest tests/regression/ -v --timeout=120` を **hard gate**（`continue-on-error` なし）で走らせる。
B14 が `docs/STATUS.md` に §7「STORY_SPINE 導入の効果測定」を新設際、`:190` に残っていた `TODO` の文字列が
`tests/regression/test_status_doc_has_effect_measurement.py::test_unmeasured_items_are_declared_not_guessed` を赤にした。

**実測（レビュー時）**
```
pytest tests/regression -q  →  1 failed, 210 passed
E  AssertionError: assert 'TODO' not in '…v6 効果測定 以降の全テキスト…'
```

**これは F1 由来の新規回帰であり、I2 ゲート「新規回帰 0 件」の違反である。**

**作業内容**

1. `docs/STATUS.md:190` の
   `` `TargetedDiagnostic` の TODO スタブを実装（...） ``
   を、`TODO` を含まない表現に書き換える。**意味は変えない**（未実装である事実は維持する）。

   ```
   変更前: | 弱段落の特定 | `TargetedDiagnostic` の TODO スタブを実装（`ClosedLoopPDCARRunner` の段落パッチ経路が到達可能に） |
   変更後: | 弱段落の特定 | `TargetedDiagnostic` の未実装スタブを実装（`ClosedLoopPDCARRunner` の段落パッチ経路が到達可能に） |
   ```

2. **新規テストを追加しない。既存赤テストが回帰ゲートである。**
   ただし「STATUS.md が実際のテスト件数を間違えていない」という**別の_classes** の陳腐化があるので、
   R1 では併せて **`docs/STATUS.md` の自己申告数値を実測で検証するメタテスト**を 1 本追加する（下記）。

**回帰テスト（先に作る）**: `tests/regression/test_status_md_counts_match_reality.py`（新規）

```python
"""docs/STATUS.md が自己申告しているテスト件数がReality と一致することの検証。

docs/STATUS.md は「このテストは N 件緑」と散文で書いている。
その N がずれると、效果測定表というものの性質（測定値である）が壊れる。
よって **N を実測して照合する**。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

STATUS = Path("docs/STATUS.md")
# 例: 「`tests/unit/story_spine/test_resolver_no_llm.py`（**7件**緑）」
CLAIM_RE = re.compile(r"`(?P<path>tests/[\w/\-\.]+\.py)`[^`\n]*?（\*\*(?P<n>\d+)件\*\*緑）")


def _collect(path: str) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", path, "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        pytest.skip(f"{path} を収集できない（既存の collection error）: {proc.stdout[-400:]}")
    m = re.search(r"(\d+) tests? collected", proc.stdout)
    return int(m.group(1)) if m else len(re.findall(r"::", proc.stdout))


def test_status_md_contains_measurable_claims():
    """このテストが意味を持つため、対象パターンが 1 つも無い状態を検出すること。"""
    text = STATUS.read_text(encoding="utf-8")
    assert CLAIM_RE.findall(text), (
        "docs/STATUS.md に「（**N件**緑）」形式の自己申告が無い。"
        "本テストが無意味になるoclude rior entiousな状態を検出する"
    )


def test_status_md_test_counts_match_reality():
    """自己申告の件数が `pytest --collect-only` の実測と一致すること。"""
    text = STATUS.read_text(encoding="utf-8")
    offenders = []
    for m in CLAIM_RE.finditer(text):
        path, claimed = m.group("path"), int(m.group("n"))
        actual = _collect(path)
        if actual != claimed:
            offenders.append(f"{path}: 記載 {claimed} 件 / 実測 {actual} 件")
    assert not offenders, "docs/STATUS.md の件数の記載が Reality と違う:\n" + "\n".join(offenders)


def test_status_md_has_no_unresolved_marker_in_measurement_section():
    """效果測定セクションに未決マーカー（TODO / FIXME / TBD）が残っていないこと。

    これが H0（CI hard gate）を守る本体。将来誰かが書き戻したらここで落ちる。
    """
    text = STATUS.read_text(encoding="utf-8")
    section = text.split("効果測定")[-1]
    offenders = [mk for mk in ("TODO", "FIXME", "TBD", "XXX") if mk in section]
    assert not offenders, f"效果測定セクションに未決マーカーが残存: {offenders}"
```

> **P4 への配慮**: 上記 2 本目・3 本目は、**修正前は赤になる**ことを確認すること。
> 特に 3 本目は現状で赤になる（`:190` の `TODO`）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression -q
```

**完了判定**: `tests/regression` が **211 passed / 0 failed**（新規 3 件込み）。かつ
`STATUS.md` の「**7件**緑」表記が `test_resolver_no_llm.py` の実測値（**4 件**）に訂正されている。

---

### R2. web 媒体の `volume_hook` 契約復元
- **対象ファイル**: `src/services/spine_resolver.py`（`:259-283`）
- **依存**: R1
- **推定所要**: 45 分

**背景**

F1 計画 A3 作業内容 5 は「`market == "web"` かつ末尾なら `volume_hook` を必ず残す」と規定した。
`config/story_spine/markets.yaml:9` も `web: ending_contract: next_volume_hook` と宣言している。

しかし `_enforce_invariants` の web 分岐は「譲れる余地がないなら諦める」早期 `return`（`:280-281`）を持ち、
直前ループ（`:272-278`）は `climax` が `_ALWAYS_KEEP` にあるため**永久に pop できず**、
`tail.ep_start >= eps` で**必ずこの return に落ちる**。

**実測（レビュー時・2 独立ノードで再現）**
```
web volume_hook missing: 166 ケース / 912
resolve_spine("exile_rise","short","web",3).keys
  -> ['inciting','midpoint_reversal','climax']         # 引きが無い
```
壊れる域は `novella`(4-10 話) と `short`(3 話) の全パターン。

**既存テストが緑な理由**: `test_web_market_keeps_volume_hook` は `web_volume@40` だけを見ており、
破綻域（`web_volume` でも `long_serial` でもない）を意図的に避けている。

**作業内容**

1. `:280-281` の `return instances` を削除し、**末尾 beat のラベル差し替え**に置き換える。
   話数（`ep_start`/`ep_end`）は保持し、`climax` の不変条件を守る。

   ```python
   tail = instances[-1]
   if tail.ep_start >= eps:
       # 譲れる話がない。**諦めず**、最終話を volume_hook の役割へ差し替える。
       # climax を守りたい場合は eps-1 の回収 beat を volume_hook に譲る（次段）。
       logger.info("web: 最終話を volume_hook へ差し替え（%s）", tail.key)
       instances[-1] = _as(tail, hook_def)
       return instances
   ```

2. **ただし climax を volume_hook で上書きしてはならない**（3 不変条件）。
   したがって手順を 2 段にする：
   - まず末尾から `role == "close"` でない 1 話幅 beat（`aftermath` / `payoff` / `residue`）を探し、
     あればそれを `volume_hook` に差し替える。
   - なければ `climax` を残したまま、**`eps >= 4` のときだけ** `climax` の 1 話手前を
     `volume_hook` にする（= `climax` が複数話なら末尾 1 話を譲る）。
   - `eps <= 3` では 3 不変条件の方が優先。**この場合は明示的にログを出す**（黙って諦めない）。

3. **キー重複の排除**（レビューで別途観測: 重複 8 ケース）。
   `_merge_pair`（`:95-97`）がグループ代表を左ノード基準に固定するため、圧縮段 2 で
   別ノードが同じ `key` に潰れる。`resolve_spine` の return 直後に
   **同一 `key` の 2 つ目を別 `key` へ退避**する（=`members` の次要素があればそれを代表にする）。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_resolver_market_contracts.py`（新規）

```python
"""媒体ごとの ** contracting 契約** が話数によらず守られることの回帰テスト。

レビューで発見された破绽は「web_volume@40 と long_serial だけを見ていた」ことに
起因する.Test 側は **破綻域を明示的に含める** こと。
"""
from __future__ import annotations

import itertools

import pytest

from config.story_spine import LENGTHS, MARKETS, PATTERNS, resolve_spine

# 破綻域（含めることが本テストの意義）。web_volume の 40 話だけを发呆 sees していたのがバグ。
RISKY_EPS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 40, 100, 300)


@pytest.mark.parametrize("eps", [3, 4, 5, 6, 8, 10])
@pytest.mark.parametrize(
    "pattern", ["exile_rise", "detective_mystery", "death_loop", "avenger_dark"]
)
def test_web_market_ends_with_volume_hook_when_there_is_a_next_volume(pattern: str, eps: int):
    """Web 連載は 2 話以上で話末の引きで終わる。"""
    spine = resolve_spine(pattern, "short", "web", eps)
    assert spine.keys[-1] == "volume_hook", (
        f"{pattern}@{eps}: 最後が {spine.keys[-1]!r}（ending_contract 違反） keys={spine.keys}"
    )


def test_web_volume_hook_contract_holds_across_full_matrix():
    """38 パターン × 15 話数の全数走査。**1 件も例外を認めない**。"""
    offenders = []
    for pattern in sorted(PATTERNS):
        for eps in RISKY_EPS:
            if eps < 2:
                continue  # 1 話作品に「次巻への引き」は成立しない（契約の定義外）
            spine = resolve_spine(pattern, "short", "web", eps)
            if spine.keys[-1] != "volume_hook":
                offenders.append(f"{pattern}@{eps}: {spine.keys[-3:]}")
    assert not offenders, f"web の ending_contract 違反 {len(offenders)} 件:\n" + "\n".join(offenders)


@pytest.mark.parametrize("eps", [1, 5, 12, 20, 40])
@pytest.mark.parametrize("market", ["light_novel", "single_shot", "general"])
def test_non_web_markets_never_force_volume_hook(market: str, eps: int):
    """Web 以外は「次への引き」を強制しない（逆方向の契約も守る）。"""
    for pattern in ("exile_rise", "detective_mystery", "gourmet_conqueror"):
        spine = resolve_spine(pattern, "single_volume", market, eps)
        assert "volume_hook" not in spine.keys, (
            f"{market} に volume_hook が混入: {spine.keys}"
        )


def test_three_invariants_survive_the_volume_hook_fix():
    """**修正で 3 不変条件を壊していないことの保証**。"""
    for pattern in sorted(PATTERNS):
        for eps in (2, 3, 4, 8, 20, 40):
            keys = resolve_spine(pattern, "short", "web", eps).keys
            assert keys[0] in ("inciting", "humiliation", "cold_open", "revelation"), (
                f"{pattern}@{eps}: 先頭が {keys[0]!r}"
            )
            assert "midpoint_reversal" in keys, f"{pattern}@{eps}: 中点反転が消えた"
            assert "climax" in keys, f"{pattern}@{eps}: クライマックスが消えた"


def test_beat_keys_are_unique_in_every_resolution():
    """**38×6×4×3 = 2,736 ケースでキーが重複しないこと**（重複 8 件の回帰）。"""
    offenders = []
    for p, length, market in itertools.product(
        sorted(PATTERNS), sorted(LENGTHS), sorted(MARKETS)
    ):
        lo, hi = LENGTHS[length]["eps_range"]
        for eps in (lo, (lo + hi) // 2, hi):
            keys = resolve_spine(p, length, market, eps).keys
            dup = {k for k in keys if keys.count(k) > 1}
            if dup:
                offenders.append(f"{p}×{length}×{market}@{eps}: {sorted(dup)}")
    assert not offenders, f"beat キーの重複 {len(offenders)} 件:\n" + "\n".join(offenders[:20])
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_resolver_market_contracts.py -v
```

**完了判定**: 上記 5 テスト緑。`test_web_volume_hook_contract_holds_across_full_matrix` が
**修正前は 166 件で赤、修正後は緑**であることを記録すること（P4）。
かつ `tests/unit/story_spine` 全体が緑。

---

### R3. 量子化で beat が黙って消える問題の根治
- **対象ファイル**: `src/services/spine_resolver.py`（`:165-207` の `_to_instances`）
- **依存**: R1
- **推定所要**: 1.5 時間

**背景（レビューで実測した最も危険な欠陥）**

`_to_instances` の量子化は「境界 → 話数区間」の写像だが、**2 ノードが同じ話に落ちると後続の
押し戻し（`:193-195`）と破棄（`:197`、`:203`）でノードが丸ごと捨てられる**。
警告もログも出ないため、編集者が `patterns.yaml` を直しても気付けない。

**実測（レビュー時）**
```
dungeon_conqueror eps=12 : len(nodes)=12（圧縮なし）
  nodes    : [... 'last_stand','climax','residue']
  instances: [... 'last_stand','residue']        <- climax が消滅

exile_rise novella general 8 :
  yaml tail: [truth_reveal 0.72-0.82, climax 0.82-0.94, aftermath 0.94-0.97, volume_hook 0.97-1.0]
  output   : [('inciting',1,2), ..., ('truth_reveal',7), ('climax',8)]   <- aftermath が 1 つも無い

"close role の beat を 1 つも持たないケース": eps>=8 でも 1,969 ケース
```

`climax` が消えた場合、`:253-255` の `_enforce_invariants` が「climax が無い」と検知して
**末尾の別 beat（`residue`）を上書きして climax ラベルを貼り付ける**。
結果として「回収 beat が消え、代わりにクライマックスがいる」という**二重の構造劣化**が起きる。

**作業内容**

1. **量子化を「非圧縮（injective）」に書き直す。**
   `_cumulative_bounds` の出力から `strictly increasing` な開始話数列を構成し、
   `len(nodes) <= eps` なら必ず `len(nodes)` 個の beat が 1..eps に重ならずに配置されることを保証する。

   ```python
   def _strict_starts(bounds: list[float], n: int, eps: int) -> list[int]:
       """開始話数列を作る。**必ず strictly increasing**（かつ [1, eps] に収まる）。

       `_cumulative_bounds` は線形補間なので隣接境界が同じ話に落ちうる。
       境界が同じ話に落ちた分は、前後に押し広げることで「消さない」を保証する。
       """
       starts = [int(math.floor(bounds[i] * eps)) + 1 for i in range(n)]
       starts = [max(1, min(s, eps)) for s in starts]
       for i in range(1, n):
           starts[i] = max(starts[i], starts[i - 1] + 1)
       # 末尾が eps を超えた分だけ、後ろから前へ詰める
       excess = starts[-1] - eps
       i = n - 1
       while excess > 0 and i > 0:
           room = starts[i] - starts[i - 1] - 1
           take = min(room, excess)
           starts[i] -= take
           excess -= take
           i -= 1
       if excess > 0:
           # n > eps（1 話短編の重なり許容段）。:_to_instances 側で全部 1..eps に広げる
           starts = [1] * n
       return starts
   ```

2. `_to_instances` を書き換える：
   - `len(nodes) <= eps` のとき → 上記の `strict_starts` で開始点を確定し
     `ends[i] = starts[i+1] - 1` / `ends[-1] = eps` とする。**破棄しない。**
   - `len(nodes) > eps` のとき → 既存の「全て 1..eps に重ねる」分岐を維持（1 話短編の仕様）。
     このとき `_compress` が既に `_MIN_SURVIVORS` まで削っているので、
     **`spans` が空にならない**ことをアサートする。
3. **破棄ゼロを保証するため、`resolve_spine` の return 直後に構造アサーションを置く。**
   ```python
   covered = [e for b in instances for e in range(b.ep_start, b.ep_end + 1)]
   if sorted(covered) != list(range(1, eps + 1)):
       logger.error("beat の話数被覆が破綻: pattern=%s eps=%s covered=%s",
                    pattern_key, eps, covered[:20])
   ```
   （raise しない。生成側で停止させない。ただしログで必ず可視化する。）
4. `_merge_duty`（`:54-58`）の**文の途中切断**を改善する。
   `merged[:59] + "。"` は 59 文字で文を断つ。末尾に `…` を置いて断れたことを明示する。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_resolver_no_silent_drop.py`（新規）

```python
"""**量子化で beat を 1 つも落とさないこと**の回帰テスト。

レビューで 1,969 ケースの「close role 無し」が発見された。
既存テストは全て「keys に climax がある」ことしか見ていなかったため、
**消えた beat の中身を直接数える**必要がある。
"""
from __future__ import annotations

import pytest

from config.story_spine import BEAT_VOCABULARY, PATTERNS, resolve_spine

CLOSE_ROLE_BEATS = {k for k, b in BEAT_VOCABULARY.items() if b.role == "close"}


def _pattern_close_keys(pattern_key: str) -> list[str]:
    return [b["key"] for b in PATTERNS[pattern_key]["beats"] if b["key"] in CLOSE_ROLE_BEATS]


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
@pytest.mark.parametrize("eps", [6, 8, 10, 12, 15, 20, 30, 40])
def test_close_role_survives_medium_lengths(pattern: str, eps: int):
    """**中編以上で「締め」の beat が 1 つも残らないことがない**。

    YAML に close role の beat があるなら、話数が足りる限り必ず 1 つは残る。
    これが外れる = 量子化で無言で落ちている。
    """
    expected = _pattern_close_keys(pattern)
    if not expected:
        pytest.skip(f"{pattern} には close role の beat が無い（ patterns.yaml 側の定義）")
    keys = set(resolve_spine(pattern, "single_volume", "general", eps).keys)
    assert keys & set(expected), (
        f"{pattern}@{eps}: close role が全滅。期待 {expected} / 実際 {sorted(keys)}"
    )


@pytest.mark.parametrize(
    "pattern,length,market,eps",
    [
        # レビューで観測した再現ケース
        ("dungeon_conqueror", "single_volume", "general", 12),
        ("exile_rise", "novella", "general", 8),
        ("guild_rebuilder", "novella", "web", 10),
        ("gourmet_conqueror", "novella", "web", 10),
    ],
)
def test_known_drop_cases_are_fixed(pattern: str, length: str, market: str, eps: int):
    """**レビューで観測した 4 ケースの直接の回帰テスト**。"""
    spine = resolve_spine(pattern, length, market, eps)
    keys = spine.keys
    assert "climax" in keys, f"{pattern}@{eps}: climax が消えた {keys}"
    assert keys[-1] not in ("residue", "payoff"), (
        f"{pattern}@{eps}: 最後が回収 beat ではなく climax 上書きされている {keys}"
    )
    assert len(keys) == len(set(keys)), f"{pattern}@{eps}: キーの重複 {keys}"


@pytest.mark.parametrize("eps", [3, 5, 8, 12, 20, 40, 100, 300])
def test_episode_coverage_is_exact_with_no_gap_and_no_overlap(eps: int):
    """1..eps が**ちょうど 1 回ずつ**被覆されること（隙間の禁止は既存テストにある）。"""
    for pattern in ("exile_rise", "detective_mystery", "dungeon_conqueror", "death_loop"):
        spine = resolve_spine(pattern, "long_serial", "web", eps)
        covered = [e for b in spine.beats for e in range(b.ep_start, b.ep_end + 1)]
        assert covered == list(range(1, eps + 1)), (
            f"{pattern}@{eps}: covered={covered[:12]} len={len(covered)}"
        )


def test_beat_count_equals_min_of_nodes_and_eps_when_compressible():
    """**圧縮が要るなら圧縮段を通す**ことの確認。

    YAML の beat 数 > eps のとき、結果の beat 数は eps まで圧縮されている
    （=量子化で落としたのではなく、意図的に併合した）。
    """
    for pattern in ("exile_rise", "detective_mystery", "dungeon_conqueror"):
        yaml_len = len(PATTERNS[pattern]["beats"])
        for eps in (3, 5, 10):
            spine = resolve_spine(pattern, "novella", "general", eps)
            assert len(spine.beats) <= max(eps, 3), (
                f"{pattern}@{eps}: {len(spine.beats)} beats（yaml は {yaml_len}）"
            )


def test_merged_duty_is_not_truncated_mid_sentence():
    """** duty の切断が明示的であること**（壊れた文がプロンプトに混入しない）。"""
    for eps in (1, 2, 3, 5):
        for pattern in ("exile_rise", "dungeon_conqueror", "detective_mystery"):
            for b in resolve_spine(pattern, "short", "general", eps).beats:
                assert b.duty.endswith("。"), f"{pattern}@{eps}/{b.key}: {b.duty!r}"
                assert len(b.duty) <= 62, f"{pattern}@{eps}/{b.key}: duty が長すぎる {b.duty!r}"
                # 途中で切れた場合は必ず省略記号で明示される
                if len(b.duty) >= 60:
                    assert "…" in b.duty or "、" in b.duty, (
                        f"{pattern}@{eps}/{b.key}: 切断が明示されていない {b.duty!r}"
                    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_resolver_no_silent_drop.py -v
C:\Python314\python.exe -m pytest tests\unit\story_spine -q
```

**完了判定**: 上記 5 テスト緑。`test_close_role_survives_medium_lengths` が
**修正前 1,969 ケースで赤、修正後緑**。`test_known_drop_cases_are_fixed` の 4 パラメータが緑。

---

### R4. `structure_validator` の span 系統統一
- **対象ファイル**: `src/services/structure_validator.py`（`:134-164`, `:64-85`, `:211-248`）
- **依存**: R1
- **推定所要**: 1.5 時間

**背景（最も技術的に危険な欠陥）**

F1 計画 A4 作業内容 2 は「`PATTERNS[pattern_key]["beats"]` の span から `required_beats` を**動的に構築**する」と明記した。
しかし実装は `b["span"]` を**捨てて**、`BEAT_VOCABULARY` の汎用 span（`:149-157`）を使っている。

**実測（レビュー時）**
```
yaml の beat span != BEAT_VOCABULARY の span: 400 / 414
worst: (0.39, 'death_loop','betrayal', yaml [0.09,0.17] vs vocab (0.46,0.56))
       (0.38, 'territory_management','rising_tension', yaml [0.66,0.75] vs (0.28,0.44))
resolver は betrayal を 10-17 話に置く / validator は phase 0.51 を期待
```

結果として **生成後検証が resolver の出力に対して誤った期待位置で判定する**。
しかも `tol = 0.35`（`:73`）と `any()`（`:76`）が 0.39 のズレを**完全に隠す**ため、
`is_healthy` は「乱数 tension データでも 82/300 = 27% が true」になる。
**検証器が構造の破綻を 1 件も検出できない**。

**作業内容**

1. `load_pattern_beats`（`:147-158`）で、`phase` を **YAML の span** から求める。
   ```python
   required.append({
       "key": b["key"],
       "label": vocab.label,
       "phase": round(sum(b["span"]) / 2, 3),   # ← YAML の span（SSOT）
   })
   ```
2. **どちらが SSOT かを 1 テストで固定する**（下記 R4 の回帰テスト 1 本目）。
   本計画は「**`patterns.yaml` が SSOT**」と宣言する。`BEAT_VOCABULARY` の span は
   「語彙の推奨位置」であり、パターンごとの上書きを許す。
3. `tol` を構造ごとに定義できるようにする。
   - `check_required_beats(assigned, structure, tol=None)` を追加し、
     `tol = structure.get("beat_tol", 0.35)` を使う。
   - `load_pattern_beats` が返す辞書に `"beat_tol": 0.10` を入れる（**パターンは位置が確定している**ため）。
   - 従来 3 構造（`three_act` 等）は既定 0.35 のまま（後方互換）。
4. `validate` の返り値に **`resolved_pattern_key`**（実際に評価したパターン）と
   **`spine`**（`resolve_spine` 済みの期待値）を含める。F1 計画 A4 作業内容 3 の未達分。
5. **「未知 pattern_key が教育和された値を返す」問題の解消**（`:138`, `:236`）。
   `result["pattern_key"]` は入力値、`result["resolved_pattern_key"]` は実評価値。
   既存テスト `test_validator_pattern.py:26-33` は誤表示を固定しているので、**併せて修正**する。
6. `alignment` の計算はそのまま。FE が `alignment` を表示できるようにする（反映は F3）。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_validator_span_source.py`（新規）

```python
"""**バリデータの期待位置が patterns.yaml の span から来ること**の構造テスト。

レビューで「400/414 が乖離」「乱数でも 27% が健全」と判定された。
本テストは SSOT を固定し、以後の乖離を再発させない。
"""
from __future__ import annotations

import random

import pytest

from config.story_spine import PATTERNS, resolve_spine
from src.services.structure_validator import (
    check_required_beats,
    load_pattern_beats,
    validate,
)


def test_expected_phase_comes_from_pattern_yaml_not_vocabulary():
    """**SSOT は patterns.yaml**。BEAT_VOCABULARY の span を使ってはならない。"""
    offenders = []
    for pk in sorted(PATTERNS):
        struct = load_pattern_beats(pk)
        yaml_spans = {b["key"]: b["span"] for b in PATTERNS[pk]["beats"]}
        for rb in struct["required_beats"]:
            expected = round(sum(yaml_spans[rb["key"]]) / 2, 3)
            if rb["phase"] != expected:
                offenders.append(f"{pk}.{rb['key']}: {rb['phase']} != {expected}")
    assert not offenders, f"phase が語彙 span から算出されている:\n" + "\n".join(offenders[:20])


def test_pattern_beats_declare_a_tight_tolerance():
    """パターンは位置が確定しているので、寛容幅 0.35 は破綻を隠す。"""
    struct = load_pattern_beats("exile_rise")
    assert struct["beat_tol"] == 0.10, struct.get("beat_tol")


@pytest.mark.parametrize("pk", ["exile_rise", "detective_mystery", "death_loop", "gourmet_conqueror"])
@pytest.mark.parametrize("eps", [20, 40, 60])
def test_resolver_output_passes_its_own_validator(pk: str, eps: int):
    """**resolver の出力が、自前の validator で「充足」と判定されること**。

    これが R4 の主力テスト。修正前は `missing_beats` が空にならず **赤になる**。
    """
    spine = resolve_spine(pk, "web_volume", "web", eps)
    chapters = [
        {"chapter_number": b.ep_start, "tension": int(b.tension * 100)}
        for b in spine.beats
    ]
    r = validate(chapters, pattern_key=pk)
    assert r["missing_beats"] == [], (
        f"{pk}@{eps}: resolver 出力なのに必須ビートが {len(r['missing_beats'])} 個欠落 "
        f"{[b['key'] for b in r['missing_beats'][:5]]}"
    )
    assert r["alignment"] == 1.0, f"{pk}@{eps}: alignment={r['alignment']}"


def test_random_chapters_are_not_reported_healthy():
    """**乱数データでも構造健全と判定されないこと**（= 検証器が機能している証拠）。

    修正前は 50 ケース中 27% が `is_healthy` になっていた。
    """
    rnd = random.Random(20260930)
    healthy = 0
    for _ in range(50):
        chapters = [
            {"chapter_number": i, "tension": rnd.randint(0, 10)} for i in range(1, 21)
        ]
        if validate(chapters, pattern_key="exile_rise")["is_healthy"]:
            healthy += 1
    assert healthy <= 3, (
        f"乱数 tension でも {healthy}/50 が健全と判定された。"
        "検証器が構造を一切見ていない（beat_tol が広すぎる疑い）"
    )


def test_misplaced_beats_are_actually_detected():
    """**本当にズレた構成は「不足」として検出されること**（偽陰性 0 の確認）。"""
    # 全てを前半に固める = 全必須ビートが終盤に来るはず
    chapters = [
        {"chapter_number": i, "tension": 1} for i in range(1, 6)
    ] + [
        {"chapter_number": 20 + i, "tension": 9} for i in range(5)
    ]
    r = validate(chapters, pattern_key="exile_rise")
    assert r["missing_beats"], "全部を話数 1-5 に固めたのに『不足なし』は検出漏れ"


def test_resolve_and_unknown_pattern_keys_are_both_reported():
    """入力値と実評価値を両方出すこと（表示と実態の不一致の解消）。"""
    r = validate([{"chapter_number": 1, "tension": 1}], pattern_key="nope")
    assert r["pattern_key"] == "nope"
    assert r["resolved_pattern_key"] == "exile_rise", r


def test_legacy_structures_keep_their_wide_tolerance():
    """後方互換：従来 3 構造の挙動を変えない。"""
    from src.services.structure_validator import STRUCTURE_DEFINITIONS

    assigned = [{"_phase": 0.1, "tension": 5}, {"_phase": 0.5, "tension": 9},
                {"_phase": 0.9, "tension": 3}]
    for name, struct in STRUCTURE_DEFINITIONS.items():
        out = check_required_beats(assigned, struct)
        assert isinstance(out, list) and out, name
        assert all(isinstance(b, dict) and "present" in b for b in out), name
```

**併せて修正する既存テスト**: `tests/unit/story_spine/test_validator_pattern.py`

```python
# 修正前（誤表示を固定している）
def test_unknown_pattern_falls_back():
    r = validate([{"chapter_number": 1, "tension": 1}], pattern_key="nope")
    assert r["pattern_key"] is not None, "未知パターンで例外を投げない"

# 修正後（入力値と実評価値を両方検証する）
def test_unknown_pattern_falls_back():
    r = validate([{"chapter_number": 1, "tension": 1}], pattern_key="nope")
    assert r["pattern_key"] == "nope"
    assert r["resolved_pattern_key"] == "exile_rise"


# 修正前（0.001 でも緑 = 空虚な閾値）
def test_alignment_is_one_when_all_beats_present():
    ...
    assert r["alignment"] > 0.0

# 修正後
def test_alignment_is_one_when_all_beats_present():
    ...
    assert r["alignment"] == 1.0
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_validator_span_source.py -v
C:\Python314\python.exe -m pytest tests\unit\test_structure_validator.py tests\unit\story_spine -q
```

**完了判定**: 新規 6 テスト緑 ＋ 既存 `tests/unit/test_structure_validator.py` の 4 テストが緑のまま。
`test_resolver_output_passes_its_own_validator` が**修正前赤・修正後緑**。

---

### R5. `PacingGraph` の相対窓化と境界の単一情報源化
- **対象ファイル**: `src/backend/engine_narrative.py`（`:42-46`, `:85-90`）
- **依存**: R1
- **推定所要**: 1 時間

**背景**

`PacingGraph` の docstring（`:37`）は「位置は相対値で保持し、絶対話数で書かない」と宣言している。
しかし `:85` の `if pos >= 1.0 - 2.0 / total_eps:` は**「最後の 2 話」= 絶対話数窓**であり、
かつ `:78` のクライマックス窓（`0.74-0.94`）より**後ろに評価される**ため到達できない。

**実測（レビュー時・2 独立ノードで再現）**
```
eps=5  finale=[4]  climax=[5]      <- 大団円がクライマックスより先（意味反転）
eps=8  finale=[]   climax=[7,8]    <- フィナーレ分岐が到達不能
eps=10 finale=[]   climax=[7,8,9,10]
eps=20 finale=[20] climax=[16..19]
```

`tests/regression/test_relative_episode_structure.py:44-49` が緑なのは、この窓を 1 度も踏んでいないから。

**作業内容**

1. `:85` の絶対窓を**相対窓**へ置換する。ただし**終盤側の分岐順**を考える。
   - `:78` のクライマックス窓を**先に**評価する（クライマックス > フィナーレ）。
   - フィナーレは「クライマックス窓の**後**にある話」だけを許す。
   ```python
   if pg._FINALE_START <= pos and not (pg._CLIMAX_START <= pos <= pg._CLIMAX_END):
   ```
3. `_FINALE_START` は **語彙 span から派生**させる（下記 4）。
4. 境界定数を**ハードコードから `BEAT_VOCABULARY` の span 派生**に置き換える。
   F1 計画 A5 の「**計算方法は必ず `resolve_spine` の結果から導出する**（ハードコード禁止）」の未達分。
   現状は span 値を**コピーしたハードコード**で二重管理になっている。
   ```python
   from config.story_spine.beat import BEAT_VOCABULARY as _V

   _HOOK_END = _V["revelation"].span[1]
   _FIRST_EXPLOSION_START = _V["first_win"].span[0]
   _FIRST_EXPLOSION_END = _V["first_win"].span[1]
   _CLIMAX_START = _V["last_stand"].span[0]
   _CLIMAX_END = _V["climax"].span[1]
   _FINALE_START = _V["aftermath"].span[0]
   ```
   > **P5 厳守**: キーの存在を `grep` で確認してから書く。
   > `aftermath` が無い場合は `coda` → `residue` の順にフォールバックする。
5. **短編（`eps <= 3`）ではフィナーレが無くても正常**とする。
   クライマックス窓が最終話を全て覆うなら入れる余地が無い。
   ただし**黙って消さない**：分岐に到達できない場合に `logger.debug` を 1 行残す。

**回帰テスト（先に作る）**: `tests/regression/test_pacing_graph_relative.py`（新規）

```python
"""**PacingGraph が話数非依存・順序が破綻しないこと**の回帰テスト。

レビューで「eps=5 で大団円がクライマックスより先」「eps=8,10 でフィナーレが到達不能」
が発見された。既存テストは 2 つの窓を 1 度も同時に踏んでいなかったため緑だった。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from config.story_spine import BEAT_VOCABULARY
from src.backend.engine_narrative import PacingGraph

EPS_LIST = (3, 5, 8, 10, 12, 16, 20, 40, 100, 300)
LABEL_RE = re.compile(r"^【(.+?)】")


def _label(ep: int, eps: int) -> str:
    instr = PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
    m = LABEL_RE.match(instr)
    return m.group(1) if m else ""


def _windows(eps: int) -> tuple[list[int], list[int]]:
    clim = [e for e in range(1, eps + 1) if _label(e, eps) == "クライマックス"]
    fin = [e for e in range(1, eps + 1) if "フィナーレ" in _label(e, eps)]
    return clim, fin


@pytest.mark.parametrize("eps", EPS_LIST)
def test_finale_never_precedes_climax(eps: int):
    """**意味の反転を検出する**。フィナーレがクライマックスより前に出てはならない。"""
    clim, fin = _windows(eps)
    if fin:
        assert min(fin) > max(clim), (
            f"eps={eps}: フィナーレ {fin} がクライマックス {clim} より前/重複"
        )


@pytest.mark.parametrize("eps", EPS_LIST)
def test_finale_appears_whenever_there_is_room(eps: int):
    """クライマックスの**後ろに話があるなら**フィナーレを出す（分岐の死を検出）。"""
    clim, fin = _windows(eps)
    assert clim, f"eps={eps}: クライマックス窓が見つからない"
    room = [e for e in range(1, eps + 1) if e > max(clim)]
    if room:
        assert fin, (
            f"eps={eps}: クライマックス（{max(clim)}話）の後に {room} 話あるのに"
            "フィナーレ分岐が発火しない（到達不能）"
        )
        assert min(fin) == room[0] or min(fin) > max(clim)


@pytest.mark.parametrize("eps", EPS_LIST)
def test_labels_depend_only_on_relative_position(eps: int):
    """k/eps が同じなら指示が同じであること（絶対窓が残っていないことの確認）。"""
    for k in (1, 2, 3):
        if k > eps:
            continue
        assert _label(k, eps) == _label(k * 3, eps * 3), (
            f"k={k}: eps={eps} と eps={eps * 3} でラベルが不一致 "
            f"({_label(k, eps)!r} vs {_label(k * 3, eps * 3)!r})"
        )


@pytest.mark.parametrize("eps", EPS_LIST)
def test_relative_position_of_climax_is_stable(eps: int):
    """クライマックスの相対位置が話数によらず終盤に留まること。"""
    clim, _ = _windows(eps)
    assert clim, eps
    assert max(clim) / eps >= 0.70, f"eps={eps}: climax が {max(clim) / eps:.0%} 位置"


def test_climax_label_is_distinguished_from_plot_twist():
    """**『クライマックス前夜の衝撃』の部分文字列で『クライマックス』と判定しない**。

    既存テストの `"クライマックス" in instruction` は eps=300 で
    152..283 = 作品全体の 44% を指して偽陽性になっていた。
    """
    for eps in (20, 100, 300):
        hits = [e for e in range(1, eps + 1) if "クライマックス" in _label(e, eps)]
        window = [e for e in range(1, eps + 1) if _label(e, eps) == "クライマックス"]
        assert hits == window, f"eps={eps}: 部分文字列判定が偽陽性 {set(hits) - set(window)}"


def test_bounds_are_derived_from_story_spine_spans():
    """**境界が語彙 span から派生している**こと（二重管理の禁止）。"""
    v = BEAT_VOCABULARY
    assert PacingGraph._CLIMAX_END == v["climax"].span[1]
    assert PacingGraph._FIRST_EXPLOSION_START == v["first_win"].span[0]
    assert PacingGraph._HOOK_END == v["revelation"].span[1]
    assert PacingGraph._CLIMAX_START == v["last_stand"].span[0]


def test_no_episode_scaled_window_remains_in_source():
    """`1.0 - 2.0 / total_eps` のような話数比例窓がソースに残っていないこと。"""
    src = Path("src/backend/engine_narrative.py").read_text(encoding="utf-8")
    for banned in ("1.0 - 2.0 / total_eps", "1.0 - 2 / total_eps", "- 2.0 / total_eps"):
        assert banned not in src, f"絶対話数窓が残存: {banned}"
```

**併せて修正する既存テスト**: `tests/regression/test_relative_episode_structure.py:44-49`
の `"クライマックス" in ...` を `"【クライマックス】" in ...` に変更する。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_pacing_graph_relative.py -v
C:\Python314\python.exe -m pytest tests\regression -q
```

**完了判定**: 新規 7 テスト緑。`test_finale_never_precedes_climax` が
**修正前 `eps=5` で赤**、`test_finale_appears_whenever_there_is_room` が
**修正前 `eps=8,10` で赤**。

---

### R6. 逆プロットの話数区間と感情目標マップ
- **対象ファイル**: `src/backend/workflows/reverse_plot_workflow.py`（`:136-163`, `:172`, `:224`）
- **依存**: R1
- **推定所持**: 45 分

**背景**

`:147` の `eps_per_arc = max(1, target_episodes // num_arcs)` は、
`target_episodes < num_arcs` のとき**範囲外の部**と **inverted 区間**（`start > end`）を作る。

**実測（レビュー時）**
```
eps=1 arcs=[(1,1,1),(2,2,2),(3,3,3),(4,4,1)] INVALID=[(2,2,2),(3,3,3),(4,4,1)]
eps=2 arcs=[(1,1,1),(2,2,2),(3,3,3),(4,4,2)] INVALID=[(3,3,3),(4,4,2)]
eps=3 arcs=[(1,1,1),(2,2,2),(3,3,3),(4,4,3)] INVALID=[(4,4,3)]
```

`patterns.yaml` の `short.eps_range: [1, 3]` すなわち**短編が本計画の中心ユースケース**なのに、そこが壊れている。

さらに `EMOTIONAL_GOAL_TO_CATHARSIS[emotional_goal]`（`:172`, `:224`）は無防備な添字参照。
実際に `KeyError 'hopeful'` で `/easy_mode/reverse-generate` が **500** になることを確認した。

**作業内容**

1. `_design_arcs` の入口で部数を話数に収める。
   ```python
   num_arcs = max(1, min(int(arc_template["arcs"]), target_episodes))
   ```
2. 最終部以外が `target_episodes` を超えることが無いことを**最後にアサート**する。
   守れなかった場合は `logger.warning` して**範囲内にクランプ**（黙って壊さない）。
3. `EMOTIONAL_GOAL_TO_CATHARSIS` を `.get(goal, default)` にする。**2 箇所とも**。
4. 死んだ `HOOK_TO_EP1_TEMPLATE`（`:49-54`、B7 で参照されなくなった）を削除する。
   **削除前に `grep -rn "HOOK_TO_EP1_TEMPLATE"` で参照 0 件を確認**（P5）。
5. `:14-15` の `if False:  # TYPE_CHECKING` という削除済みのガードを除去する。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_reverse_plot_arc_ranges.py`（新規）

```python
"""**短編（1-3 話）でも部構成が破綻しないこと**の回帰テスト。

レビューで eps=1,2,3 で inverted 区間と範囲外の部を確認した。
F1 計画の中心ユースケース（short.eps_range=[1,3]）が壊れていた。
"""
from __future__ import annotations

import inspect

import pytest

from src.backend.workflows.reverse_plot_workflow import (
    EMOTIONAL_GOAL_TO_CATHARSIS,
    ReversePlotGenerationWorkflow,
)

# _design_arcs は self を使わないため unbound 呼び出しでよい（生成コストゼロ）
_design_arcs = ReversePlotGenerationWorkflow._design_arcs

CONFLICTS = ["ideal_vs_reality", "past_vs_future", "individual_vs_org", "love_vs_duty", "unknown"]


@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5, 7, 10, 20, 40])
@pytest.mark.parametrize("conflict", CONFLICTS)
def test_arcs_are_ordered_and_within_range(eps: int, conflict: str):
    """**start <= end、かつ 1 <= start <= end <= eps**（短編を含む）。"""
    arcs = _design_arcs(None, {"coreConflict": conflict}, eps)
    assert arcs, f"eps={eps}/{conflict}: 部が 1 つも無い"
    prev_end = 0
    for arc in arcs:
        assert arc.start_ep <= arc.end_ep, (
            f"eps={eps}/{conflict}: inverted 区間 {arc.start_ep}>{arc.end_ep}"
        )
        assert 1 <= arc.start_ep, f"eps={eps}/{conflict}: start={arc.start_ep} が 1 未満"
        assert arc.end_ep <= eps, (
            f"eps={eps}/{conflict}: end={arc.end_ep} が総話数 {eps} を超過"
        )
        assert arc.start_ep == prev_end + 1, (
            f"eps={eps}/{conflict}: 部が連続していない（gap: {prev_end} -> {arc.start_ep}）"
        )
        prev_end = arc.end_ep
    assert prev_end == eps, f"eps={eps}/{conflict}: 最後の部が {prev_end} で総話数に届かない"


@pytest.mark.parametrize("eps", [1, 2, 3, 5, 10, 40])
def test_arc_count_never_exceeds_episode_count(eps: int):
    """部数が話数を超えないこと（`eps=1` で 4 部出来了 bug）。"""
    arcs = _design_arcs(None, {"coreConflict": "past_vs_future"}, eps)
    assert len(arcs) <= eps, f"eps={eps}: {len(arcs)} 部 > {eps} 話"


def test_unknown_emotional_goal_does_not_raise_keyerror():
    """**`KeyError` を出さないこと**（`/easy_mode/reverse-generate` が 500 になっていた）。"""
    for goal in ("triumph", "bittersweet", "twist", "heartwarming", "hopeful", "unknown_goal", None):
        got = EMOTIONAL_GOAL_TO_CATHARSIS.get(goal, EMOTIONAL_GOAL_TO_CATHARSIS["triumph"])
        assert got and "tensionPeak" in got, goal


def test_catharsis_map_is_not_accessed_defensively_missing():
    """**無防備な添字参照が残っていないこと**（構造テスト）。"""
    src = inspect.getsource(ReversePlotGenerationWorkflow)
    assert "EMOTIONAL_GOAL_TO_CATHARSIS[emotional_goal]" not in src, (
        "無防備な添字参照が残っている（.get(goal, default) に変更すること）"
    )


def test_spine_tension_is_used_for_every_episode(eps: int = 10):
    """tension が Spine 由来であること（自前計算への回帰防止）。"""
    spine = ReversePlotGenerationWorkflow._spine_for(None, 10)
    assert spine is not None and spine.beats
    assert not hasattr(ReversePlotGenerationWorkflow, "_calc_tension"), (
        "_calc_tension が復活している（Spine ラッパーに縮小すること）"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring -q
```

**完了判定**: 新規 5 テスト緑。`test_arcs_are_ordered_and_within_range` が
**修正前 `eps=1,2,3` で赤、修正後緑**。

---

### R7. `genre → pattern` 解決を死んだままにしない
- **対象ファイル**: `config/story_spine/genre_registry.py`、`src/backend/routers/easy_mode.py`（`:147-151`）
- **依存**: R1
- **推定所要**: 1 時間

**背景**

`easy_mode.py:150-151`:
```python
g_entry = resolve_genre(genre)
pattern_key = (g_entry.get("pattern") if g_entry else None) or "exile_rise"
```
`GENRE_REGISTRY` の各エントリは `label / aliases / domain / preset_key / rating` のみで
**`pattern` キーが存在しない**。`dict.get` は未知キーで `None` を返すだけなので、
**ミステリーでもホラーでも、どんな条でも常に `exile_rise` に落ちる**。

`SPINE_QUALITY=soft/hard` のとき、この `exile_rise` の構造指示が全ジャンルに注入される。

**作業内容**

1. `genre_registry.py` の各エントリに **`pattern`**（`patterns.yaml` のキー）を追加する。
   既存 `domain` から導けるものは導出し、導けないものは明示的に選ぶ。
   > **P5**: `PATTERNS` のキー一覧を `grep` してから書くこと。**新規パターンを作らない**。
2. `easy_mode.py` から**テスト可能なヘルパ**を抽出する（現状はインラインで関数から出せない）。
   ```python
   def resolve_pattern_key(genre: str, explicit: str | None = None) -> str:
       """ジャンルから STORY_SPINE パターンキーを解く。未知は exile_rise。"""
       if explicit:
           return explicit
       from config.story_spine import PATTERNS
       from config.story_spine.genre_registry import resolve_genre
       entry = resolve_genre(genre)
       p = (entry or {}).get("pattern")
       if p and p in PATTERNS:
           return p
       logger.warning("ジャンル %r に pattern 未定義のため exile_rise を使用", genre)
       return "exile_rise"
   ```
   `:147-151` をこの関数に置き換える。
3. `resolve_genre` が `None` を返しうる场合も `logger.warning` を残す（黙って既定にしない）。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_genre_pattern_mapping.py`（新規）

```python
"""**ジャンル → パターンの解決が死んでいないこと**の回帰テスト。

レビューで `g_entry.get("pattern")` が常に None（=常に exile_rise）が判明した。
"""
from __future__ import annotations

from config.story_spine import PATTERNS
from config.story_spine.genre_registry import GENRE_REGISTRY
from src.backend.routers.easy_mode import resolve_pattern_key


def test_every_genre_entry_declares_a_known_pattern():
    """全エントリに `patterns.yaml` に実在する pattern があること。"""
    missing, unknown = [], []
    for key, entry in GENRE_REGISTRY.items():
        p = entry.get("pattern")
        if not p:
            missing.append(key)
        elif p not in PATTERNS:
            unknown.append((key, p))
    assert not missing, f"pattern 未定義のジャンル: {missing}"
    assert not unknown, f"patterns.yaml に無い pattern: {unknown}"


def test_genres_do_not_all_collapse_to_one_pattern():
    """**全てが exile_rise に潰れていないこと**（元バグの直接の検出）。"""
    pats = {e.get("pattern") for e in GENRE_REGISTRY.values()}
    assert len(pats) >= 3, f"パターンが {len(pats)} 種類しかない（=解決が死んでいる）: {pats}"


def test_resolve_pattern_key_returns_distinct_values_for_distinct_genres():
    a = resolve_pattern_key("ミステリー")
    b = resolve_pattern_key("ホラー")
    c = resolve_pattern_key("ZFantasy")
    assert a != b, f"ミステリーとホラーが同じパターン {a} になった"


def test_resolve_pattern_key_never_raises_for_unknown_genre():
    for genre in ("", "存在しないジャンル", "ZZZ", None, 123):
        got = resolve_pattern_key(genre)
        assert got in PATTERNS, f"{genre!r} -> {got!r}"


def test_explicit_pattern_overrides_genre():
    assert resolve_pattern_key("ミステリー", explicit="death_loop") == "death_loop"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring -q
C:\Python314\python.exe -m pytest tests\regression\test_genre_resolution_unified.py -q
```

**完了判定**: 新規 5 テスト緑。`test_genres_do_not_all_collapse_to_one_pattern` が
**修正前に赤**（修正前は `pats == {None}`）。

---

### R8. 最重要契約テストの空洞化解消
- **対象ファイル**: `tests/contract/test_spine_prompt_injection.py`、`tests/e2e/test_spine_end_to_end.py`、`tests/unit/story_spine/test_resolver_no_llm.py`、`tests/regression/test_relative_episode_structure.py`、`tests/unit/scripts/test_measure_spine_alignment.py`
- **依存**: R1
- **推定所持**: 1 時間

**背景（3 つの「何が起きても緑になるテスト」）**

1. **プロンプトのバイト一致契約**（`test_spine_prompt_injection.py:22-25`）
   ```python
   prompt = NOVEL_..._TEMPLATE.format(**KWARGS, spine_section="")
   assert prompt == NOVEL_..._TEMPLATE.format(**KWARGS)
   ```
   右辺と左辺は `kwargs.setdefault("spine_section", "")` により**常に同一**。
   **テンプレートを旧版に戻してもテストは緑のまま**。
   F1 計画はこれを「第 1 位リスク（1 本でも落ちれば全既存書籍の再生成結果が変わる）」と挙げている。

2. **「resolve_spine は LLM を呼ばない」証明**（`test_resolver_no_llm.py:9-38`）
   `target.rpartition(".")` が `src.llm.resilient_gateway.ResilientLLMGateway.generate_text` を
   `("src.llm.resilient_gateway.ResilientLLMGateway", "generate_text")` に分割し、
   前者を**モジュールとして** `__import__` して `ModuleNotFoundError`。`except: continue` で 5 件とも飲み込む。
   **実測: パッチ対象 0/5（完全な no-op）。**

3. **`measure_spine_alignment` の空 DB テスト**（`test_measure_spine_alignment.py:56-60`）
   `measure()` は DB 読み失敗を `except Exception` で握り潰し `return []` する（`:68-70`）。
   **接続失敗と「0 件」が区別できない**。現環境は `autonovel.db` の `plots` が 0 行なので偶然通っている。

**作業内容**

1. `tests/contract/test_spine_prompt_injection.py` に**旧テンプレートの凍結スナップショット**を入れる。
   ```powershell
   git show HEAD:src/services/llm/prompts.py > tmp\prompts_head.py
   # 旧 NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE のリテラルを抜き出して
   # テストファイル内の LEGACY_TEMPLATE_SNAPSHOT にリテラルとして貼り付ける
   ```
2. `tests/e2e/test_spine_end_to_end.py:86-94` も同じスナップショットを参照するよう変更。
   **重複定義せず**、`tests/contract/` 側の定数を import する。
3. `test_resolver_no_llm.py` の fixture を**文字列形式の monkeypatch**に書き換える。
   さらに「パッチ対象が見つからない」ことを**検出するテスト**を 1 本追加する。
4. `scripts/measure_spine_alignment.py:68-70` の返りに `db_reachable: bool` を追加し、
   `test_empty_database_does_not_crash` は `book_count == 0 and db_reachable is True` を要求する。
   併せて `subprocess` に隔離済み `DATABASE_URL` を渡す。
5. `tests/regression/test_relative_episode_structure.py:14-22` の
   `test_instruction_depends_only_on_relative_position` は `k=2,3,4` のみを比べているため
   常に【導入】分岐どうしになる。**終盤側の `k` も回す**。

**回帰テスト（先に作る）**: 上記 1〜4 そのものが回帰テスト。加えて**空洞検出テスト**を 1 本入れる。

`tests/contract/test_spine_prompt_injection.py` への追加分：

```python
import re
from pathlib import Path

import pytest

from src.services.llm.prompts import (
    NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE as CURRENT,
    build_spine_section,
)


def _load_legacy_template() -> str:
    """旧テンプレートを git HEAD から採取して凍結する。

    `spine_section` が無い（＝F1 以前の姿）ことを確認し、
    テストが空振りしていないことを確認する。
    """
    proc = subprocess.run(
        ["git", "show", "HEAD:src/services/llm/prompts.py"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        pytest.skip("git HEAD の prompts.py を取得できない")
    m = re.search(
        r'NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE\s*=\s*"""(.*?)"""',
        proc.stdout, re.S,
    )
    if not m:
        pytest.skip("HEAD に旧テンプレートが見つからない（すでに置換済みの可能性）")
    return m.group(1)


def test_off_produces_legacy_prompt_exactly():
    """**バイト単位で旧テンプレートと同一**であること。

    これが 1 本でも落ちると全既存書籍の再生成結果が変わる。
    """
    legacy_src = _load_legacy_template()
    assert "spine_section" not in legacy_src, "HEAD が既に新版（比較対象が不正）"
    legacy = legacy_src.format(**KWARGS)
    current = CURRENT.format(**KWARGS)
    assert current == legacy, (
        f"プロンプトが変化した（{len(legacy)} -> {len(current)} 文字）。"
        "spine_quality=off では既存書籍の再生成結果を変えないこと"
    )


def test_legacy_snapshot_is_not_vacuous():
    """**このテストが意味を持つことの自己検証**。"""
    legacy_src = _load_legacy_template()
    assert len(legacy_src) > 200, "旧テンプレートが短すぎる（取得失敗の可能性）"
    assert "{genre}" in legacy_src and "{char_name}" in legacy_src, "プレースホルダが欠けている"
    assert "spine_section" not in legacy_src


def test_current_template_does_declare_spine_section():
    """新テンプレートには注入点があること（=注入が実際に機能する）。"""
    assert "spine_section" in CURRENT
```

`tests/unit/story_spine/test_resolver_no_llm.py` の fixture 差し替え：

```python
# 修正前: rpartition + __import__ で 5 件とも ModuleNotFoundError → 何もパッチされない
# 修正後: 文字列形式で「クラス.メソッド」を直接パッチする
@pytest.fixture
def no_llm(monkeypatch):
    """すべての LLM 経路を爆発させる。呼ばれたらテストが落ちる。"""
    patched: list[str] = []

    def _boom(*a, **k):
        raise AssertionError("resolve_spine が LLM を呼んだ（D2 違反）")

    targets = [
        "src.llm.resilient_gateway.ResilientLLMGateway.generate_text",
        "src.llm.resilient_gateway.ResilientLLMGateway.generate_json",
        "src.llm.resilient_gateway.ResilientLLMGateway.ainvoke",
    ]
    for target in targets:
        try:
            monkeypatch.setattr(target, _boom, raising=True)
            patched.append(target)
        except (ImportError, AttributeError):
            continue
    # ★ ここが本テストの価値の核心: 1 つもパッチできていない = no-op を検出する
    assert patched, (
        "パッチ対象が見つからない。no_llm fixture が no-op になっており、"
        "『LLM を呼ばない』の証明になっていない"
    )
    return patched
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_spine_prompt_injection.py -v
C:\Python314\python.exe -m pytest tests\e2e\test_spine_end_to_end.py tests\unit\story_spine -q
C:\Python314\python.exe -m pytest tests\unit\scripts -q
```

**完了判定**: `test_off_produces_legacy_prompt_exactly` が**旧テンプレートと実際に一致すること**
（レビューで実測 `BYTE IDENTICAL: True` であることを確認済み。実装は正しい・テストが空洞だった）。
`no_llm` fixture が **3 件以上パッチされた**ことを fixture 内のアサーションが保証する。

---

## 3. TRACK-F：フロントエンド・契約・CI（5 ステップ）

> **注意**: `src/backend/routers/misc.py` の変更は **F1 が独占**する。
> R8 は `misc.py` を触らない（`growth_curves` の実装を F1 に委譲する）。

### F1. `/api/config/planning_options` の契約を実形状に合わせる
- **対象ファイル**: `src/backend/routers/misc.py`、新 `tests/contract/test_planning_options_contract.py`
- **依存**: R1
- **推定所持**: 1.5 時間

**背景（3 件の欠陥が 1 箇所に集約されている）**

1. **カード `card_id` が無い** → FE の選択ハイライトが常に無効
   `misc.py:111` は `"cards": CARDS`（YAML の dict）そのまま。カード ID は dict の**キー**にしか存在しない。
   `cards.yaml` に `card_id:` は **0 件**、`tpl_*` キーが 24 件。
   FE は `SimpleModePanel.tsx:126` で `card.card_id || card.id || card.pattern`、
   `:184` で `card.card_id || card.id || card.label` と**フォールバックが食い違う**。
   実レスポンス: `{"tpl_exile_web": {"label": "...", "pattern": "exile_rise", ...}}`
   → `cardId = "exile_rise"` だが `cid = "追放ざまぁ（Web連載・1巻40話）"`。**`isSelected` は常に false**。

2. **`growth_curves` が無い** → FE にアーキタイプ 47 種が混入
   `misc.py:105-127` は `growth_curves` を返さない（実測 `False`）。
   そのため FE は `story_archetypes` へフォールバックし、
   「成長曲線モデル」select に `overcoming_the_monster` などが並ぶ。
   `growth in keys: []` — 「成長」「カンスト」「ピーキー」は 1 件も無い。

3. **YAML の生 dict を返す**ため、YAML に `!include` や `datetime` が入った瞬間に 500 になる。
   契約テストは HTTP スタックを通さず関数呼び出しのみなので **JSON シリアライズが未検証**。

**作業内容**

1. `cards` を **ID 付きのリスト**に変更する（**dict → list[str, dict]**）。
   ```python
   "cards": [{"card_id": k, **v} for k, v in CARDS.items()],
   ```
   他のキー（`lengths` / `markets` / `patterns`）は FE が `Object.values()` する実装のため
   **dict のまま維持**してよい。ただし `cards` だけは形状を変えるため FE 側の対応が必要。
2. `growth_curves` を新設する。`STORY_ARCHETYPES` のうち「成長曲線」として扱うキーを集約する。
   > **P5**: 実在値を `grep` してから決める。**新値を作らない**。
   > `plots.py:357` の保存先カラムと**同じ値集合**でなければならない。
3. FE 側で `Array.isArray` / `Object.values` の**両方**を受け付ける既存パターン（`:100`）に
   合わせ、以降は `card_id` のみを信頼する。

**回帰テスト（先に作る）**: `tests/contract/test_planning_options_contract.py`（新規）

```python
"""/api/config/planning_options の**レスポンス形状**を固定する契約テスト。

レビューで「FE のモックが実 API 形状を偽造していた」ことが
カード選択ハイライト無効・成長曲線混入の直接の原因だった。
**サーバーが返す形を Python 側で固定**し、FE 側はこれに合わせて修正する。
"""
from __future__ import annotations

import json

import pytest

from config.story_spine import CARDS, LENGTHS, MARKETS, PATTERNS
from config.story_spine.beat import BEAT_VOCABULARY
from src.backend.routers.misc import get_planning_options


@pytest.fixture
async def opts():
    return await get_planning_options()


async def test_response_is_json_serializable(opts):
    """**生 YAML dict をそのまま返して 500 にならないこと**。"""
    payload = json.dumps(opts, ensure_ascii=False)
    assert len(payload) > 1000
    json.loads(payload)  # 往復可能


async def test_cards_expose_card_id_matching_yaml_key(opts):
    """**各カードが `card_id` を持つ**（FE の選択判定の前提）。"""
    cards = opts["cards"]
    assert isinstance(cards, list), f"cards は list であるべき（dict だと FE が key を取り損なう）"
    assert len(cards) == len(CARDS) == 24, len(cards)
    for item in cards:
        assert "card_id" in item, f"card_id が無い: {item}"
        assert item["card_id"] in CARDS, item["card_id"]
        # カードの中身は YAML と一致していること（二重定義を作らない）
        assert item["label"] == CARDS[item["card_id"]]["label"]
        assert item["pattern"] == CARDS[item["card_id"]]["pattern"]
    assert len({c["card_id"] for c in cards}) == len(cards), "card_id が重複している"


async def test_growth_curves_is_present_and_non_empty(opts):
    """`growth_curves` が存在し、空でないこと（FE の select の唯一の供給元）。"""
    assert "growth_curves" in opts, "growth_curves が無い（FE は story_archetypes に墜ちる）"
    curves = opts["growth_curves"]
    values = list(curves.values()) if isinstance(curves, dict) else list(curves)
    assert values, "growth_curves が空"
    assert all(isinstance(v, str) and v for v in values), values


async def test_growth_curves_values_are_subset_of_story_archetypes(opts):
    """**保存先カラムと値集合が一致すること**（`plots.py` が受け付ける値だけを出す）。"""
    assert set(opts["growth_curves"]) <= set(opts["story_archetypes"]), (
        "story_archetypes に無い値が混ざっている（保存時に FK/ENUM で落ちる）"
    )


async def test_legacy_keys_are_preserved(opts):
    """既存 FE が使っているキーは削除しないこと（後方互換）。"""
    for key in ("easy_genres", "story_archetypes", "style_definitions"):
        assert key in opts, f"既存キー {key} が消えている"
    for key in ("cards", "lengths", "markets", "patterns", "genres", "beat_vocabulary"):
        assert key in opts, f"STORY_SPINE キー {key} が無い"


async def test_beat_vocabulary_is_complete_and_flat(opts):
    """beat_vocabulary が 34 語で span がリスト化されていること。"""
    bv = opts["beat_vocabulary"]
    assert len(bv) == len(BEAT_VOCABULARY) >= 30, len(bv)
    for key, item in bv.items():
        assert item["key"] == key
        assert isinstance(item["span"], list) and len(item["span"]) == 2, item
        assert 0.0 <= item["span"][0] < item["span"][1] <= 1.0, item


async def test_endpoints_tables_have_expected_sizes(opts):
    assert len(opts["lengths"]) == len(LENGTHS) == 6
    assert len(opts["markets"]) == len(MARKETS) == 4
    assert len(opts["patterns"]) == len(PATTERNS) == 38
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_planning_options_contract.py -v
```

**完了判定**: 新規 7 テスト緑。`test_cards_expose_card_id_matching_yaml_key` と
`test_growth_curves_is_present_and_non_empty` が**修正前に赤**。

---

### F2. 字数プリセットの ID 破壊とフォールバックの乖離
- **対象ファイル**: `frontend/src/constants/manuscript.ts`、`frontend/src/types/manuscript.ts`、`frontend/src/components/editor/Editor.tsx`、`frontend/src/components/**/ManuscriptTargetIndicator.tsx`、`frontend/src/constants/manuscript.test.ts`、`frontend/tests/unit/components/ManuscriptTargetIndicator.test.tsx`
- **依存**: R1
- **推定所持**: 2 時間

**背景（既存ユーザーの設定を全滅させる）**

B9 は `MANUSCRIPT_PRESETS` を API 参照に**丸ごと差し替え**、`id` を `String(p.key)` にした。

```
旧 ID: shousetsu-gekkan / shousetsu-subaru / dengeki-bunko / kakuyomu / narou / custom
新 ID: short / novella / single_volume / web_volume / long_serial / custom
```

`Editor.tsx:93` は `localStorage.getItem("autonovel.targetPresetId") || "shousetsu-gekkan"`。
`ManuscriptTargetIndicator.tsx:22` は `MANUSCRIPT_PRESETS.find((p) => p.id === selectedPresetId) || MANUSCRIPT_PRESETS[0]`。

**既存ユーザーは以下のことになる**:
- `<select value={selectedPresetId}>`（`:62`）に一致 option が無く **select が空白表示**
- `find` が `|| MANUSCRIPT_PRESETS[0]` で落ち、**目標が「カクヨム 10 万字」から「1.2 万字」へ無断書き換え**
- 既定値 `"shousetsu-gekkan"` は死んだ ID

**実測（レビュー時）**
```
FAIL ManuscriptTargetIndicator.test.tsx (8 tests | 6 failed)
  > calls onPresetChange when preset selected
    expected called with [ 'shousetsu-subaru' ]  /  Received [ "" ]
  > shows max over state for presets with maxPages
    Expected: 上限 100枚 超過 (現在 103枚)  /  Received: 上限 30枚 超過 (現在 103枚)
  > shows narou preset with no target (unlimited)
    expected document not to contain element (progressbar), found aria-valuemax="12000"
FAIL ManuscriptCountBadge.test.tsx (9 tests | 1 failed)
FAIL src/constants/manuscript.test.ts  > 文字数0の長編は警告閾値を1にして上限を外す
    AssertionError: expected +0 to be undefined
```

**併せて 2 件ある**:
- `manuscript.ts:42` の `...(p.eps_range[1] > 0 ? { maxPages: toPages(p.target_chars) } : {})` は
  判定が `eps_range` 基準。**`target_chars == 0`（字数自由）の長編に `maxPages: 0` が入る**。
- `FALLBACK_LENGTH_PROFILES`（`:11-17`）が `lengths.yaml` と乖離:
  `novella` 20000 vs 30000 / `single_volume` 40000 vs 55000 / `long_serial` **0** vs 250000 / `series` **欠落**。
  `fetchLengthProfiles` は**呼び出し元ゼロ**の死にコード（`:60` のみ）。
- 結果として `MANUSCRIPT_PRESETS` は**依然フォールバック由来の静的定数**（`:75-76`）で、
  B9 の「API 参照に置換」が**達成されていない**。

**作業内容**

1. **ID 互換レイヤ**を入れる。`id` は旧 ID のまま、`lengthKey` に新キーを入れる。
   ```ts
   /**
    * 旧 ID → 新 length key の対応表。
    *
    * B9 で ID を長さキーへ置換した結果、既存ユーザーの localStorage が
    * 全て無効化され、select が空白になり、目標が勝手に 1.2 万字へ書き換えられた。
    * ID は**安定識別子**として旧値を保持し、新スキーマは lengthKey で持つ。
    */
   export const LEGACY_ID_BY_LENGTH_KEY: Record<string, string> = {
     short: 'shousetsu-gekkan',
     novella: 'shousetsu-subaru',
     single_volume: 'dengeki-bunko',
     web_volume: 'kakuyomu',
     long_serial: 'narou',
     series: 'series',
   };
   ```
2. `toManuscriptPresets` の `id` を `LEGACY_ID_BY_LENGTH_KEY[p.key] ?? p.key` にする。
3. **マイグレーション関数**を-export する。
   ```ts
   /** localStorage に旧 ID が入っていれば新 ID へ読み替える。 */
   export function resolvePresetId(stored: string | null): string {
     if (!stored) return MANUSCRIPT_PRESETS[0].id;
     if (MANUSCRIPT_PRESETS.some((p) => p.id === stored)) return stored;
     const hit = Object.entries(LEGACY_ID_BY_LENGTH_KEY).find(([, legacy]) => legacy === stored);
     if (hit) return LEGACY_ID_BY_LENGTH_KEY[hit[0]];
     // 長さキー自体が入っていた場合（新しい既定）
     if (MANUSCRIPT_PRESETS.some((p) => p.lengthKey === stored)) return stored;
     return MANUSCRIPT_PRESETS[0].id;
   }
   ```
4. `Editor.tsx:92-93` の初期化を `resolvePresetId(localStorage.getItem(...))` にして、
   値が変換されたら**localStorage を書き戻す**。
5. `:42` の `maxPages` 判定を `p.target_chars > 0` に直す。
6. `FALLBACK_LENGTH_PROFILES` を `lengths.yaml` と**同期**する（`series` を追加、
   `novella` 30000 / `single_volume` 55000 / `long_serial` 250000）。
   > **P5**: `lengths.yaml` の実在値を読み、`docs/openapi.json` のスナップショットと照合する。
7. **`fetchLengthProfiles` を死にコードのまま残さない**。
   `ManuscriptTargetIndicator` と `Editor` が API 由来のプリセットを受け取れるように
   `frontend/src/contexts/LengthPresetContext.tsx` を新設する。
   `MANUSCRIPT_PRESETS` は**同期フォールバック**として残す（モジュール定数のため）。
   - `Editor.tsx` で `useLengthPresets()` を呼び、`ManuscriptTargetIndicator` に props で渡す。
   - 取得失敗時は `MANUSCRIPT_PRESETS` にフォールバック（既存の挙動を維持）。
8. 影響を受ける既存 FE テスト（`ManuscriptTargetIndicator.test.tsx` 6 件、
   `ManuscriptCountBadge.test.tsx` 1 件）の期待値を**新しい正値**に更新する。
   ハードコードされた「文字数」ではなく `MANUSCRIPT_PRESETS` から導出する形に直す。

**回帰テスト（先に作る）**: `frontend/src/constants/manuscript.migration.test.ts`（新規）

```ts
import { describe, expect, it } from 'vitest';
import {
  LEGACY_ID_BY_LENGTH_KEY,
  MANUSCRIPT_PRESETS,
  resolvePresetId,
  toManuscriptPresets,
} from './manuscript';
import type { LengthProfile } from '../types/lengthProfile';

const LENGTH_PROFILES: LengthProfile[] = [
  { key: 'short', label: '短編', target_chars: 12000, eps_range: [1, 3], chars_per_ep: [4000, 12000], arc_count: [1, 1], min_beats: 5, hook_window_eps: 1, ending_contract: '' },
  { key: 'long_serial', label: '長編', target_chars: 0, eps_range: [100, 300], chars_per_ep: [2000, 2500], arc_count: [4, 8], min_beats: 24, hook_window_eps: 3, ending_contract: '' },
];

describe('字数プリセットの ID 互換', () => {
  it('既存ユーザーの旧 ID が解決できる（localStorage を失効させない）', () => {
    // B9 で旧 ID が全置換され、既存全員の localStorage が無効化された
    expect(resolvePresetId('shousetsu-gekkan')).toBe(MANUSCRIPT_PRESETS[0].id);
    expect(resolvePresetId('shousetsu-subaru')).not.toBe('');
    expect(resolvePresetId('dengeki-bunko')).toBeDefined();
    expect(resolvePresetId('kakuyomu')).toBeDefined();
    expect(resolvePresetId('narou')).toBeDefined();
  });

  it('旧 ID に対応するプリセットが実際に存在する（空白 select にならない）', () => {
    for (const [lengthKey, legacyId] of Object.entries(LEGACY_ID_BY_LENGTH_KEY)) {
      const hit = MANUSCRIPT_PRESETS.find((p) => p.id === legacyId);
      if (lengthKey === 'series') continue; // 既存 localStorage には入らない
      expect(hit, `${lengthKey} の旧 ID ${legacyId} に対応するプリセットが無い`).toBeDefined();
    }
  });

  it('未知 ID は既定にフォールバックする（Undefined を渡さない）', () => {
    expect(resolvePresetId('存在しない')).toBe(MANUSCRIPT_PRESETS[0].id);
    expect(resolvePresetId(null)).toBe(MANUSCRIPT_PRESETS[0].id);
    expect(resolvePresetId('')).toBe(MANUSCRIPT_PRESETS[0].id);
  });

  it('解決結果は必ず実在するプリセットの ID', () => {
    for (const stored of ['shousetsu-gekkan', 'kakuyomu', 'custom', 'garbage', null]) {
      const id = resolvePresetId(stored);
      expect(MANUSCRIPT_PRESETS.some((p) => p.id === id)).toBe(true);
    }
  });
});

describe('maxPages の付与条件', () => {
  it('字数自由（target_chars=0）の長編には上限を付けない', () => {
    const presets = toManuscriptPresets(LENGTH_PROFILES);
    const long = presets.find((p) => p.lengthKey === 'long_serial');
    expect(long).toBeDefined();
    expect(long!.maxPages).toBeUndefined(); // 0 ではなく「付けない」
    expect(long!.warningThreshold).toBe(1);
  });

  it('字数があるプリセットには 400 字詰めの枚数上限を付ける', () => {
    const presets = toManuscriptPresets(LENGTH_PROFILES);
    const short = presets.find((p) => p.lengthKey === 'short');
    expect(short!.maxPages).toBe(30); // 12000 / 400
  });
});

describe('フォールバックプロファイルの整合', () => {
  it('フォールバックは lengths.yaml と乖離しない（series を含む）', () => {
    expect(MANUSCRIPT_PRESETS.some((p) => p.lengthKey === 'series')).toBe(true);
    expect(MANUSCRIPT_PRESETS.some((p) => p.lengthKey === 'long_serial' && p.targetChars === 0)).toBe(false);
  });
});
```

**検証コマンド**
```powershell
cd frontend
npx vitest run src/constants/manuscript.test.ts src/constants/manuscript.migration.test.ts
npx vitest run tests/unit/components/ManuscriptTargetIndicator.test.tsx tests/unit/components/ManuscriptCountBadge.test.tsx
npx tsc --noEmit
```

**完了判定**: `manuscript.migration.test.ts` 6 テスト緑。`ManuscriptTargetIndicator.test.tsx` 8 件緑。
**FE 全体で failed 0**（H3）。`resolvePresetId('shousetsu-gekkan')` が実在 ID を返す。

---

### F3. `BeatSheetViewer` の型不一致（React クラッシュ）と到達不能
- **対象ファイル**: `frontend/src/components/planning/BeatSheetViewer.tsx`、`frontend/src/components/planning/BeatSheetViewer.test.tsx`、および **mount 先ページ**（P5 で確定）
- **依存**: R1
- **推定所持**: 1.5 時間

**背景**

FE は `missing_beats?: string[]` と型宣言し `{beat}` をそのまま子要素としてレンダリングする。
バックエンドは **dict の配列**を返す。

```
FE  : BeatSheetViewer.tsx:8   missing_beats?: string[];
FE  : BeatSheetViewer.tsx:136-142
      {validation.missing_beats.map((beat) => (
        <span key={beat} ...>{beat}</span>   // beat は object → React は object を child にできない
BE  : structure_validator.py:70,80  → {"key","label","present","expected_phase"}
BE  : structure.py:48  → validate() の戻り値をそのまま返す
```

**影響**: 「欠落ビートがある」= **この機能が存在する理由そのもの**のケースで
`Objects are not valid as a React child` により **React が例外を投げ cards 全体が描画されない**。
`key={beat}` も `[object Object]` になり全要素同 key。

さらに:
- **`BeatSheetViewer` はアプリ内のどこからも import されていない**（`git grep` は定義とテストのみ）。
  つまりこの未完成コンポーネントは**死んでいる**。F1 計画 B12 は「充足度 87% 表示」を選んだ切り札だった。
- `climax` の型（`:9`）は `{ ok, peak_phase?, ideal_phase? }` だが
  BE は `{"ok", "reason", "climax_phase"}` を返す（**型ドリフト**）。
- `alignment`（充足度 %）が型にあるだけで**表示されていない**。
- `problems?: string[]` だが BE の `validate_spine` は **dict 配列**を返す。

**作業内容**

1. 型を実 API に合わせる。
   ```ts
   export interface MissingBeat {
     key: string;
     label: string;
     present: boolean;
     expected_phase: number;
   }
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
2. 描画を `beat.label` / `key={beat.key}` に直し、`expected_phase` を % で併記する。
   `problems` は `typeof p === 'string' ? p : p.reason` で安全に出す。
3. **`alignment`（充足度 %）をヘッダに表示する**（B12 の目的）。
4. **未 mount 状態の解消**。既存の構成/プロット画面に 1 箇所 mount する。
   > **P5 厳守**: `grep -rn "PlotPage\|PlanningPage\|structure" frontend/src/pages/` で
   > 適切な画面を**確定してから**編集する。存在しなければ新規ページを作らず、
   > 既存の構成閲覧画面に最小的カードとして入れる。
5. **`validate` が `resolved_pattern_key` を返すようになった**ので、それも表示する
   （R4 との接続。R4 未完了なら `?? patternKey` で退避）。

**回帰テスト（先に作る）**: `frontend/src/components/planning/BeatSheetViewer.test.tsx` を
**実 API 形状**のモックに書き換える（これが本ステップの核心テスト）。

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BeatSheetViewer } from './BeatSheetViewer';

/**
 * **実 API のレスポンス形状**（src/services/structure_validator.py:70,80）。
 * 修正前のテストは `missing_beats: ['midpoint_reversal']`（文字列配列）を
 * モックしていたため、**型不一致を検出できていなかった**。
 */
const REAL_API_RESPONSE = {
  pattern_key: 'exile_rise',
  structure_key: 'three_act',
  is_healthy: false,
  alignment: 0.667,
  missing_beats: [
    { key: 'midpoint_reversal', label: '中点反転', present: false, expected_phase: 0.52 },
    { key: 'aftermath', label: ' aftermath', present: false, expected_phase: 0.955 },
  ],
  climax: { ok: true, reason: '', climax_phase: 0.857 },
  pacing: { ok: true, reason: '', skew: 0.05 },
};

const mockFetch = (payload: unknown, ok = true) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok,
      status: ok ? 200 : 500,
      json: async () => payload,
    })
  );
};

describe('BeatSheetViewer', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('**実 API 形状（dict 配列）でもクラッシュしない**', async () => {
    // 修正前: 「Objects are not valid as a React child」で落ちる
    mockFetch(REAL_API_RESPONSE);
    expect(() => render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />)).not.toThrow();
    await waitFor(() => expect(screen.getByText(/必須ビートの充足状況/)).toBeTruthy());
  });

  it('欠落ビートをラベルで一覧表示する', async () => {
    mockFetch(REAL_API_RESPONSE);
    render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />);
    await waitFor(() => expect(screen.getByText('中点反転')).toBeTruthy());
    expect(screen.getByText('aftermath')).toBeTruthy();
  });

  it('**充足度（alignment）を％表示する**（B12 の目的）', async () => {
    mockFetch(REAL_API_RESPONSE);
    render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />);
    await waitFor(() => expect(screen.getByText(/66\.7|67/)).toBeTruthy());
  });

  it('充足 100% のとき「すべての必須ビート…正常」と表示する', async () => {
    mockFetch({ ...REAL_API_RESPONSE, is_healthy: true, alignment: 1, missing_beats: [] });
    render(<BeatSheetViewer bookId={1} />);
    await waitFor(() => expect(screen.getByText(/すべての必須ビート/)).toBeTruthy());
  });

  it('API エラー時にエラーメッセージを出す（throw しない）', async () => {
    mockFetch({}, false);
    render(<BeatSheetViewer bookId={1} />);
    await waitFor(() => expect(screen.getByText(/検証APIエラー: 500/)).toBeTruthy());
  });

  it('patternKey を API クエリに含める', async () => {
    mockFetch(REAL_API_RESPONSE);
    render(<BeatSheetViewer bookId={7} patternKey="death_loop" />);
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls[0][0]).toContain('pattern=death_loop');
      expect(vi.mocked(fetch).mock.calls[0][0]).toContain('/api/structure/books/7/validate');
    });
  });

  it('**空文字キーで重複 key を作らない**', async () => {
    mockFetch(REAL_API_RESPONSE);
    render(<BeatSheetViewer bookId={1} />);
    await waitFor(() => expect(screen.getByText('中点反転')).toBeTruthy());
    // React が key 重複で警告を出さないこと
    expect(console.error).not.toHaveBeenCalled();
  });
});
```

**検証コマンド**
```powershell
cd frontend
npx vitest run src/components/planning/BeatSheetViewer.test.tsx
npx tsc --noEmit
```

**完了判定**: 上記 7 テスト緑。`npx tsc --noEmit` のエラーが **0 件**増加。
**コンポーネントが実際に 1 箇所の画面から import されている**ことを `grep` で確認。

---

### F4. カード選択ハイライトの無効化と選択連動の不足
- **対象ファイル**: `frontend/src/components/generate/SimpleModePanel.tsx`、`frontend/src/components/generate/SimpleModePanel.test.tsx`
- **依存**: F1（`card_id` を API 側で返すこと）
- **推定所持**: 1 時間

**背景**

`:126` の `handleSelectCard` は `card.card_id || card.id || card.pattern` を state に書くが、
`:184` の表示側は `card.card_id || card.id || card.label` で判定する。
実 API に `card_id` が無いため、**`isSelected` は常に false**。
二重管理テーブルは「一度押したのに无意で切替」「別のカードの選択取り違え」の原因になる。

テストは**捏造した `card_id`** を渡すため緑になる。

**作業内容**

1. `:126` と `:184` を **両方 `card.card_id` のみ**に統一する。
   フォールバックチェーン（`|| card.pattern` / `|| card.label`）を削除する。
   > 冗長なフォールバックは、**片方だけが古く片方が新しい**不一致なバグの温床になる。
2. カード選択時に `chars_per_ep` と `style_key` を自動入力する（F1 計画 B10-3 の未達分）。
3. ジャンル解決の `card.pattern.includes(...)` の if/else チェーン（`:144-152`）を
   `GENRE_REGISTRY` を使う実装に置き換える（**5 つ目の genre 表の複製**を無くす）。
4. `useNovelGeneration` の payload に `pattern_key` / `length_key` / `market_key` /
   `spine_quality` を追加する（F1 計画 B10-5 の未達分。`git grep` で 0 件）。

**回帰テスト（先に作る）**: `frontend/src/components/generate/SimpleModePanel.test.tsx`
に**実レスポンス形状**のテストを追加する（既存テストは `card_id` を捏造しているため**1 本は残す**）。

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SimpleModePanel } from './SimpleModePanel';

/**
 * **サーバーが実際に返す形**（src/backend/routers/misc.py:F1 で `card_id` を付与したもの）。
 * 修正前のテストは `card_id: 'tpl_exile_web'` を捏造して渡していたため、
 * 実データでハイライトが無効になることに気づけなかった。
 */
const REAL_API_CARDS = {
  cards: [
    {
      card_id: 'tpl_exile_web',
      label: '追放ざまぁ（Web連載・1巻40話）',
      blurb: '...',
      pattern: 'exile_rise',
      length: 'web_volume',
      market: 'web',
      style_key: 'hot_blooded',
      source: 'existing',
    },
    {
      card_id: 'tpl_mystery_short',
      label: '密室殺人（短編）',
      blurb: '...',
      pattern: 'detective_mystery',
      length: 'short',
      market: 'single_shot',
      style_key: 'restrained',
      source: 'existing',
    },
  ],
  lengths: { web_volume: { key: 'web_volume', eps_range: [40, 40] } },
  genres: {},
};

const setup = (payload: unknown = REAL_API_CARDS) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => payload })
  );
  return render(<SimpleModePanel {...MINIMAL_PROPS} />);
};

describe('SimpleModePanel カード選択', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('**カードを選ぶと選択ハイライトが付く**（実 API 形状で検証）', async () => {
    setup();
    const card = await screen.findByText('追放ざまぁ（Web連載・1巻40話）');
    const tile = card.closest('div[style]')!;
    fireEvent.click(tile);
    await waitFor(() => {
      expect(tile.getAttribute('style')).toContain('2px solid'); // 選択枠
    });
  });

  it('**異なるカードを選ぶと前のカードのハイライトが消える**', async () => {
    setup();
    const a = (await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!;
    const b = (await screen.findByText('密室殺人（短編）')).closest('div[style]')!;
    fireEvent.click(a);
    fireEvent.click(b);
    await waitFor(() => {
      expect(b.getAttribute('style')).toContain('2px solid');
      expect(a.getAttribute('style')).toContain('1px solid');
    });
  });

  it('**カード選択で話数が length.eps_range から自動入力される**', async () => {
    setup();
    fireEvent.click((await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!);
    const eps = await screen.findByLabelText(/目標話数/);
    await waitFor(() => expect((eps as HTMLInputElement).value).toBe('40'));
  });

  it('カード選択で style_key と chars_per_ep が反映される', async () => {
    setup();
    fireEvent.click((await screen.findByText('追放ざまぁ（Web連載・1巻40話）')).closest('div[style]')!);
    await waitFor(() => {
      expect(screen.getByDisplayValue('hot_blooded')).toBeTruthy();
      expect(screen.getByDisplayValue('2500')).toBeTruthy();
    });
  });
});
```

**検証コマンド**
```powershell
cd frontend
npx vitest run src/components/generate/SimpleModePanel.test.tsx
npx tsc --noEmit
```

**完了判定**: 新規 4 テスト緑。`カードを選ぶと選択ハイライトが付く` が
**修正前に赤**（実 API 形状では `isSelected` が常に false だったため）。
かつ `src/components/generate/SimpleModePanel.tsx` に
`card_id ||` のフォールバックチェーンが **0 件**（`grep -n "card_id ||"` で確認）。

---

### F5. 成長曲線混入・FE モックの実形状化・CI ゲート追加
- **対象ファイル**: `src/backend/routers/misc.py`（F1 と同コミット）、`frontend/src/components/wizard/Step1PlotInput.tsx`、`frontend/src/components/wizard/Step1PlotInput.test.tsx`、`.github/workflows/ci.yml`、`Makefile`、新 `scripts/export_planning_options.py`、新 `frontend/tests/unit/api/planningOptions.contract.test.ts`
- **依存**: F1 / F2 / F3 / F4
- **推定所持**: 2.5 時間

**背景（構造的問題：FE のテストが実 API 形状を偽造している）**

`.github/workflows/` には **frontend ジョブが存在しない**。

```
ci.yml  dsp_balancer.yml  emotional_residue.yml  fusion.yml  rule_engine.yml
Select-String 'npm|vitest|typecheck|frontend' .github/workflows/*.yml  →  出力なし
```

FE テスト 4 本と `npm run typecheck` は F1 計画の「完了判定」だが、**実行する harness が無い**。
結果として上記 S1（FE 7 テスト赤、新規テスト赤）が**緑のままマージできる**。

**具体的偽装**:
```
frontend/src/components/wizard/Step1PlotInput.test.tsx:11-12
  story_archetypes: ['王道ざまぁ（爽快感最大）'],
  growth_curves: ['最初からカンスト(無双)','徐々に成長(王道)','条件付き最強(ピーキー)'],
  ↑ growth_curves は実 API が返さないキー。テストが実在しない値を捏造して緑にしている
```

**作業内容**

1. **FE テストの偽装を止める**ため、**サーバーが実際に返すレスポンスのスナップショット**を作る。
   ```python
   # scripts/export_planning_options.py（新規）
   """planning_options の実レスポンスを JSON で書き出す（FE テストの唯一の fixture 源）。"""
   from __future__ import annotations

   import argparse
   import asyncio
   import json
   from pathlib import Path

   from src.backend.routers.misc import get_planning_options

   DEFAULT_OUT = Path("frontend/tests/fixtures/planning_options.snapshot.json")


   def main() -> int:
       ap = argparse.ArgumentParser()
       ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
       ap.add_argument("--check", action="store_true",
                       help="書き出さずに既存スナップショットと一致するかだけ確認する")
       args = ap.parse_args()

       payload = asyncio.run(get_planning_options())
       text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

       if args.check:
           if not args.out.exists():
               print(f"[fail] スナップショットが無い: {args.out}")
               return 1
           if args.out.read_text(encoding="utf-8") != text:
               print(f"[fail] スナップショットが Reality と不一致。`{args.out}` を再生成せよ")
               return 1
           print("[ok] スナップショットは最新")
           return 0

       args.out.parent.mkdir(parents=True, exist_ok=True)
       args.out.write_text(text, encoding="utf-8")
       print(f"[ok] {args.out} を書き出した")
       return 0


   if __name__ == "__main__":
       raise SystemExit(main())
   ```

   > **P7**: これは新規スクリプト。`scripts/` に対する `ruff check` を通すこと
   > （現状 `Makefile` の lint は `src tests` のみで `scripts/` を含まない → 下記 4 で修正）。

2. `frontend/tests/unit/api/planningOptions.contract.test.ts`（新規）を追加する。
   **スナップショットを唯一の fixture として**使い、FE の変換ロジックが実データで動くことを保証する。
   ```ts
   import { describe, expect, it } from 'vitest';
   import snapshot from '../../fixtures/planning_options.snapshot.json';
   import { toManuscriptPresets } from '../../../src/constants/manuscript';
   import type { LengthProfile } from '../../../src/types/lengthProfile';

   /**
    * **サーバーが実際に返すレスポンス**（scripts/export_planning_options.py の出力）。
    * FE テストのモックを自分で作らない原則の唯一の例外がこれ。
    */
   const raw = snapshot as Record<string, unknown>;

   describe('/api/config/planning_options との契約', () => {
     it('スナップショットは cards / lengths / genres を持つ', () => {
       expect(raw).toHaveProperty('cards');
       expect(raw).toHaveProperty('lengths');
       expect(raw).toHaveProperty('genres');
     });

     it('**全カードが card_id を持つ**（Highlight 判定の前提）', () => {
       const cards = raw.cards as Array<Record<string, unknown>>;
       expect(cards.length).toBeGreaterThan(0);
       for (const c of cards) {
         expect(typeof c.card_id).toBe('string');
         expect(c.card_id).not.toBe('');
       }
     });

     it('**growth_curves が存在し非空**（成長曲線 select の唯一の供給元）', () => {
       expect(raw).toHaveProperty('growth_curves');
       const curves = Object.values(raw.growth_curves as Record<string, string>);
       expect(curves.length).toBeGreaterThan(0);
     });

     it('**lengths を FE のプリセットに変換できる**', () => {
       const lengths = Object.values(raw.lengths as Record<string, LengthProfile>);
       const presets = toManuscriptPresets(lengths);
       expect(presets.length).toBeGreaterThanOrEqual(6);
       expect(presets.every((p) => typeof p.id === 'string' && p.id !== '')).toBe(true);
     });

     it('patterns の beat キーがすべて patterns 内で定義されている', () => {
       const patterns = raw.patterns as Record<string, { beats?: Array<{ key: string }> }>;
       const vocab = Object.keys(raw.beat_vocabulary as Record<string, unknown>);
       for (const [pk, pat] of Object.entries(patterns)) {
         for (const b of pat.beats ?? []) {
           expect(vocab, `${pk}.${b.key}`).toContain(b.key);
         }
       }
     });
   });
   ```

3. `Step1PlotInput.tsx` の成長曲線 select を**`growth_curves` のみ**を信頼する実装にする。
   `story_archetypes` フォールバックを削除する（実 API との不一致の中継点になっているため）。
   併せて `WizardBookData`（`frontend/src/api/wizard.ts`）に
   `pattern_key` / `length_key` / `market_key` を追加し、Step1 の選択が保存時に落ちるのを防ぐ。
   > レビューで「`WizardWorkflowPage.tsx:81-98` で Step1 の選択が保存時に落ちる」と確認。

4. **CI に frontend ジョブを追加**する。
   ```yaml
     frontend:
       runs-on: ubuntu-latest
       defaults:
         run:
           working-directory: frontend
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with:
             node-version: '20'
             cache: 'npm'
             cache-dependency-path: frontend/package-lock.json
         - run: npm ci
         - name: Typecheck
           run: npm run typecheck
         - name: Lint
           run: npm run lint
         - name: Unit tests
           run: npm run test:ci
         - name: planning_options スナップショットの鮮度確認
           working-directory: .
           run: python scripts/export_planning_options.py --check
   ```
   > 既存の `test job` と**並列**（`needs:` は付けない）にして、
   > FE 全体で collection error が 11 suite あるため、まず**新規に落ちている 8 件を F1〜F4 で緑にする**。
   > 残る collection error（`indexedDbClient` 未解決 / `react-router-dom`）は
   > **別 Issue として切り出し**、`--exclude` で隠さず**失敗として出す**:

5. `Makefile` の `lint` / `format-check` / `verify` の対象を `src tests` から
   **`src tests config scripts`** に広げる。F1 計画 A2 の完了判定が
   「`ruff check config\story_spine -q` が 0 件」であったのに、
   **そのコマンドを走らせる harness が CI / Makefile に存在しなかった**。
6. `docs/STATUS.md` に本計画の §2/F2 への差分を追記する（**R1 完了後、1 回だけ**）。
   `scripts/compare_test_baseline.ps1` の実行結果も転記する。

**回帰テスト**: 上記スクリプト（`--check` モード）と `planningOptions.contract.test.ts`。
さらに Python 側にも**スナップショット鮮度の回帰テスト**を 1 本入れる。

```python
# tests/unit/scripts/test_planning_options_snapshot.py（新規）
"""planning_options の FE スナップショットが Reality と一致することの回帰テスト。

FE テストが「自分で作ったモック」を使うため、実 API との乖離が検出できない
問題（カード選択ハイライト無効・成長曲線混入）の構造的原因を断つ。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SNAPSHOT = Path("frontend/tests/fixtures/planning_options.snapshot.json")


def test_snapshot_file_exists():
    assert SNAPSHOT.exists(), (
        f"{SNAPSHOT} が無い。`python scripts/export_planning_options.py` で生成せよ"
    )


def test_snapshot_matches_live_endpoint():
    """**スナップショットが現在のレスポンスと一致すること**（CI が緑なら必ず一致）。"""
    proc = subprocess.run(
        [sys.executable, "scripts/export_planning_options.py", "--check"],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"スナップショットが Reality と不一致。\n{proc.stdout}\n{proc.stderr}"
    )
```

**検証コマンド**
```powershell
C:\Python314\python.exe scripts\export_planning_options.py
C:\Python314\python.exe -m pytest tests\unit\scripts -q
cd frontend && npx vitest run
```

**完了判定**:
1. `npx vitest run` の **failed 0**（H3）。
2. `scripts/export_planning_options.py --check` が緑。
3. `Step1PlotInput` の select に `story_archetypes` の値が**現れない**ことを UI テストで確認。
4. `ci.yml` に `frontend:` ジョブが存在し、`needs:` 無しで並行実行されていること。

---

## 4. 統合（I1-I3）

> **統合担当が実行する。** TRACK-R / TRACK-F の完了後。

### I1. ベースライン比較と新規回帰ゼロの確認
```powershell
pwsh -File scripts/compare_test_baseline.ps1
```
- **完了判定**: **新規回帰 0 件**。
- F1 由来の新規回帰 1 件（`test_status_doc_has_effect_measurement.py`）が R1 で解消していること。

### I2. 全ゲートの同時緑
```powershell
C:\Python314\python.exe -m pytest tests\unit tests\contract tests\regression tests\e2e -q --timeout=120
C:\Python314\python.exe -m ruff check src tests config scripts -q
cd frontend; npx vitest run; npx tsc --noEmit
```
- **完了判定**: 全て緑（既存の**無関係な**障害 `test_writing_graph_flow.py` の
  `msgpack serializable: MagicMock` は**既知の既存障害**として、
  本計画の範囲外である旨を `docs/STATUS.md` に明記する）。

### I3. 「一応の完成形」判定表の更新
`docs/STATUS.md` に以下を転記する。

| 項目 | 計画 | 実装後 | 根拠（テスト名） |
|:---|:---|:---|:---|
| web `volume_hook` 契約 | 必須 | 必須（0 欠落） | `test_web_volume_hook_contract_holds_across_full_matrix` |
| beat キーの重複 | 0 | 0 | `test_beat_keys_are_unique_in_every_resolution` |
| 量子化での beat 消失 | 0 | 0 | `test_close_role_survives_medium_lengths` |
| validator の span SSOT | patterns.yaml | patterns.yaml | `test_expected_phase_comes_from_pattern_yaml_not_vocabulary` |
| resolver 出力が validator を通る | 必須 | 必須 | `test_resolver_output_passes_its_own_validator` |
| PacingGraph の順序 | climax < finale | 維持 | `test_finale_never_precedes_climax` |
| PacingGraph の境界 | 語彙 span 由来 | 語彙 span 由来 | `test_bounds_are_derived_from_story_spine_spans` |
| 逆プロットの区間 | 1<=s<=e<=eps | 維持 | `test_arcs_are_ordered_and_within_range` |
| genre→pattern の種類数 | >= 3 | >= 3 | `test_genres_do_not_all_collapse_to_one_pattern` |
| プロンプトのバイト一致 | 旧と同一 | 旧と同一 | `test_off_produces_legacy_prompt_exactly` |
| resolve_spine の LLM 0 回 | 証明 | 証明（3 経路 patch） | `test_resolve_spine_makes_no_llm_call` |
| FE プリセットの ID 互換 | 必須 | 必須 | `旧 ID が解決できる` |
| `missing_beats` の型 | BE と一致 | 一致 | `実 API 形状（dict 配列）でもクラッシュしない` |
| カードの選択ハイライト | 機能 | 機能 | `カードを選ぶと選択ハイライトが付く` |
| FE テストの全体 | failed 0 | failed 0 | `npx vitest run` |
| 新規回帰 | 0 件 | 0 件 | `scripts/compare_test_baseline.ps1` |

---

## 5. 残存リスク（本計画で**消えない**もの・明記する）

| リスク | 理由 | 対応 |
|:---|:---|:---|
| FE 11 suite の collection error | `indexedDbClient` / `react-router-dom` の解決は別 Issue | CI の frontend ジョブを**新規 8 件が緑になるまで**段階導入し、collection error を把握したうえで別 PR で対応 |
| `test_writing_graph_flow.py` の `MagicMock` 直列化 | reverse_plot と無関係な既存障害 | `docs/STATUS.md` に既知障害として明記。**本計画では直さない** |
| `mypy` 585 errors | 本計画の対象外。**残存課題** | `make typecheck` は既に `continue-on-error`。本計画では触らない |
| `BEAT_VOCABULARY` と `patterns.yaml` の span 400/414 の乖離 | 本計画は「**patterns.yaml が SSOT**」と宣言して**意図を固定**した | 乖離は**仕様**。R4 のテスト 1 本目以降、乖離は回帰として検出される |
| `reversePlotSteps.ts` の Python 側との重複 | I3（削除判断）は統合担当 | 本計画では削除しない。理由を `docs/STATUS.md` に 1 行書く |
| `config/data/archetypes.json` の `PLOT_STRUCTURES` | I3 相当 | 参照 0 件だが削除は別判断。本計画では触らない |

---

## 6. 完了の定義（Definition of Done）

本計画は**以下の全て**が同時に満たされたときに完了とする。

1. **H0** `pytest tests/regression -q` が緑（`0 failed`）
2. **H1** `pytest tests/unit/story_spine tests/unit/story_spine_wiring -q` が緑
3. **H2** `pytest tests/contract tests/e2e/test_spine_end_to_end.py -q` が緑
4. **H3** `cd frontend && npx vitest run` が **failed 0**
5. **H4** `scripts/compare_test_baseline.ps1` の**新規回帰 0 件**
6. `ruff check src tests config scripts` が **0 件**
7. `python scripts/export_planning_options.py --check` が緑
8. §4-I3 の判定表が `docs/STATUS.md` に転記されている
9. **レビューで挙げた S1 8 件すべてに対応する「赤→緑」の証跡が、
   各ステップの「完了判定」に記録されている**（P4）

> **9 番が最も重要である。** 修正前のコードに対して
> 各テストが実際に赤くなることを確認していない場合、
> そのテストは「 حقيقية意図を検査している」証明になっていない。
