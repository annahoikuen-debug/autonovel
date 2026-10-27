# AutoNovel STORY_SPINE 実装計画書【2サブエージェント並列】

## ― 「構造テンプレート層」導入の 23 ステップ分解と並列作業計画 ―

- **文書ID**: PLAN_F1_STORY_SPINE_IMPLEMENTATION
- **作成日**: 2026-09-29
- **前提文書**: [PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md](PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md)（以下「親提案」）
- **先行計画**: [PLAN_T6_REMEDIATION_18STEPS.md](PLAN_T6_REMEDIATION_18STEPS.md), [PLAN_V53_V6_INTEGRATED_36STEPS.md](PLAN_V53_V6_INTEGRATED_36STEPS.md)
- **対象バージョン**: AutoNovel v6.0.0 →
- **ステータス**: 未着手
- **構成**: TRACK-A（6ステップ）／ TRACK-B（14ステップ）／ 統合（3ステップ）＝ **計 23 ステップ**

---

## 0. 本計画書の位置づけ

親提案は「何を入れるか」を定義した。本書はその**実装手順とテスト**に分解したものである。

**2 サブエージェントに分割する理由**: 本計画の変更は「データ基盤（静的・大量）」と「配線/UI（動的・少量）」で性質が全く異なる。
データ基盤は 38 パターン分のデータ執筆という**並列化不能な bulk 作業**であり、配線/UI は 14 箇所にまたがる**機械的改修**である。
両者を別エージェントに任せれば、**片方が bulk 中でもう片方が進む**。

### 0.1 分割原則（並列作業版）

| 原則 | 内容 |
|:---|:---|
| **P1 ファイル排他所有** | **1 ファイルは 1 エージェントのみ**が触る。共有ファイルを 2 人に渡さない。これが唯一の本計画固有の原則 |
| **P2 単一ファイル主担当** | 1 ステップで触る**主要ファイルは高々 1 つ**。2 つ以上になる場合は分割する（例外は §0.2 に明記） |
| **P3 機械的置換のみ** | ロジック設計を要求しない。`str.replace` / 正規表現で完了する_stepsのみ |
| **P4 判定が1行** | 「完了判定」は `pytest ... -q` が緑か赤かのみ。数値の解釈をLLMにさせない |
| **P5 テスト先行** | 回帰テストを**先に作り、赤くなることを確認してから** 実装する |
| **P6 猜测禁止** | 対象ファイルの行番号・関数名を必ず grep で確認してから編集する。記憶で編集しない |
| **P7 1 ステップ = 1 コミット** | 途中で失敗したら `git reset --hard HEAD~1` して次のステップに進む |
| **P8 契約凍結** | TRACK-B は TRACK-A の **A1（契約凍結）完了を待つ**。A1 以外の並列は無条件許可 |

### 0.2 ★ ファイル排他所有表（本計画の最重要表）

**この表に載っていないファイルは どちらのエージェントも触ってはいけない。**

| ファイル | 所有者 | 備考 |
|:---|:---:|:---|
| `config/story_spine/__init__.py` | **A** | A1 で新規作成。**公開 API の唯一の門** |
| `config/story_spine/beat.py` | **A** | A1 |
| `config/story_spine/loader.py` | **A** | A1 |
| `config/story_spine/patterns.yaml` | **A** | A2（38 パターン） |
| `config/story_spine/lengths.yaml` | **A** | A2（6 長さ階層） |
| `config/story_spine/markets.yaml` | **A** | A2（4 媒体規格） |
| `config/story_spine/cards.yaml` | **A** | A2（24 カード） |
| `config/story_spine/genre_registry.py` | **B** | ★例外。`config/story_spine/` 配下だが **B 所有**。A は触ってはいけない |
| `src/services/spine_resolver.py` | **A** | A3（新規） |
| `src/services/structure_validator.py` | **A** | A4 |
| `src/backend/engine_narrative.py` | **A** | A5 |
| `config/constants.py` | **A** | A5（`EP_*` 定数削除） |
| `src/models/beat_sheet.py` | **A** | A6（`le=40` 撤去） |
| `config/archetypes_new.py` | **A** | A6（死んだ `PLOT_STRUCTURES` 削除） |
| `config/__init__.py` | **A** | A6（re-export 整理） |
| `src/backend/routers/easy_mode.py` | **B** | B1 |
| `src/services/preset_loader.py` | **B** | B2 |
| `src/services/spice_guard_adapter.py` | **B** | B2 |
| `src/backend/routers/misc.py` | **B** | B3 |
| `src/backend/routers/plots.py` | **B** | B4 |
| `src/backend/routers/commercial_planning.py` | **B** | B5 |
| `src/application/dtos/plot_dto.py` | **B** | B6 |
| `src/services/pipeline_base.py` | **B** | B6 |
| `src/backend/workflows/reverse_plot_workflow.py` | **B** | B7 |
| `src/services/llm/prompts.py` | **B** | B8 |
| `prompts/templates/narrative/plot_stage1.j2` | **B** | B8 |
| `frontend/src/constants/manuscript.ts` | **B** | B9 |
| `frontend/src/types/manuscript.ts` | **B** | B9 |
| `frontend/src/constants/genres.ts` | **B** | B10 |
| `frontend/src/components/generate/SimpleModePanel.tsx` | **B** | B10 |
| `frontend/src/components/wizard/Step1PlotInput.tsx` | **B** | B11 |
| `frontend/src/components/planning/BeatSheetViewer.tsx` | **B** | B12 |
| `scripts/measure_spine_alignment.py` | **B** | B13（新規） |
| `docs/STATUS.md` | **B** | B14 |
| `tests/unit/story_spine/**` | **A** | A1-A5 のテスト |
| `tests/unit/story_spine_wiring/**` | **B** | B1-B8 のテスト |
| `tests/contract/test_spine_*.py` | **B** | B3/B8 の契約テスト |
| `tests/regression/test_relative_episode_structure.py` | **A** | A5 |
| `tests/regression/test_genre_resolution_unified.py` | **B** | B1/B2 |
| `tests/e2e/test_spine_end_to_end.py` | **統合** | I1 |
| `plans/PLAN_F1_STORY_SPINE_IMPLEMENTATION.md` | **統合** | 本書。subagent は**読むだけ** |

**衝突の事前計算結果**:
- `config/__init__.py` は `PLOT_STRUCTURES` を `archetypes_new` から re-export している（`config/__init__.py:6-20`）。A6 が削除するため、**B は `config/__init__.py` に新しい export を追加してはいけない**。B は `from config.story_spine import ...` と**直接サブパッケージ**から import する。
- `genre_registry.py` は `config/story_spine/` 配下だが B 所有。**A1 で A がディレクトリを作るときは `genre_registry.py` を作らない**。

### 0.3 依存関係グラフとゲート条件

```
                    ┌──────────────────────────────┐
                    │  A1 契約凍結（約45分）        │  ← 全員ここを通る
                    │  story_spine/{__init__,beat,  │
                    │               loader}.py      │
                    └───────────────┬──────────────┘
                                ゲート開放
         ┌──────────────────────────┴───────────────────────────┐
         ▼                                                      ▼
┌────────────────────────────┐                    ┌────────────────────────────┐
│ TRACK-A（ bulk / 静的 ）   │                    │ TRACK-B（ wiring / 動的 ）  │
│                            │                    │                            │
│ A2 データ（38P/6L/4M/24C） │ ──cards.yaml────→ │ B9  FE manuscript.ts        │
│ A3 spine_resolver          │ ──resolve_spine──→│ B10 FE genres.ts            │
│   ├ resolve_spine()        │                   │    SimpleModePanel.tsx      │
│   ├ 圧縮モード             │                   │ B11 FE Step1PlotInput.tsx   │
│   └ 網羅テスト 2736 ケース  │                   │ B12 FE BeatSheetViewer.tsx  │
│ A4 structure_validator      │ ──validate()────→ │ B13 measure_spine_alignment │
│ A5 PacingGraph / EP_* 削除   │                   │ B14 docs/STATUS.md          │
│ A6 beat_sheet / archetypes   │                   │ B1 genre_registry.py        │
│   / config/__init__          │ ──API 契約───→   │ B2 easy_mode / preset_loader │
│                            │                   │    / spice_guard_adapter    │
│                            │ ──resolve_spine──→│ B3 misc.py（ImportError 修正）│
│                            │                   │ B4 plots.py（12ビート置換）  │
│                            │ ──resolve_spine──→│ B5 commercial_planning.py   │
│                            │                   │ B6 plot_dto / pipeline_base │
│                            │ ──resolve_spine──→│ B7 reverse_plot_workflow.py │
│                            │                   │ B8 prompts / plot_stage1.j2 │
└────────────────────────────┘                    └────────────────────────────┘
         │                                                      │
         └──────────────────────┬───────────────────────────────┘
                                ▼
              ┌──────────────────────────────────┐
              │ 統合（ 統合担当が実行）            │
              │ I1 E2E テスト作成と実行          │
              │ I2 ベースライン比較（新規回帰 0） │
              │ I3 効果測定表の転記              │
              └──────────────────────────────────┘
```

**ゲート条件（厳守）**:

| ゲート | 条件 | 誰の判断か |
|:---|:---|:---|
| **G1** | `C:\Python314\python.exe -c "from config.story_spine import BEAT_VOCABULARY, PATTERNS, LENGTHS, MARKETS, CARDS, get_pattern; print(len(BEAT_VOCABULARY))"` が成功し `34` を出力する | A が A1 完了を宣言。**B はこのコマンドが緑になるまで B1-B12 に着手しない** |
| **G2** | `pytest tests/unit/story_spine -q` が緑（TRACK-A 完了） | A |
| **G3** | `pytest tests/unit/story_spine_wiring tests/contract/test_spine_*.py -q` が緑（TRACK-B 完了） | B |
| **G4** | `git merge feature/spine-track-b` 後に `pytest tests/unit tests/contract -q` が緑 | 統合 |

**B の進捗状況による A の停止条件**: A は B の進捗に依存しない。**A は B を待たずに最後まで走れる。**

### 0.4 ブランチと統合手順

```powershell
# 事前（統合担当が 1 回だけ）
git checkout -b feature/spine-track-a main
git checkout main
git checkout -b feature/spine-track-b main
```

**注意**: 本リポジトリは現在 `main` に未コミットの変更がある（`git status` で確認済み）。
PLAN_T6 の教訓（Step 16）どおり、**作業開始前に必ずコミットする**。未コミット変更があると
`scripts/compare_test_baseline.ps1` の baseline（= HEAD）が不正確になり、
**新規テストが全部「回帰」扱いになる**。

```powershell
# 統合順序（統合担当）
git checkout main && git merge --no-ff feature/spine-track-a   # 先に A（契約提供側）
git merge --no-ff feature/spine-track-b                        # 次に B（契約消費側）
pwsh -File scripts/compare_test_baseline.ps1
```

**A を先にマージする理由**: B のコードが `from config.story_spine import ...` を含むため、A が無い状態で B をマージすると**全 B テストが collection error** になる。逆順でも動くが、エラーの解釈が難しくなる。

**並列実行時の環境隔離（重要）**:

2 エージェントが同時に `pytest` を走らせると、SQLite（`config/constants.py:38-39` の `autonovel.db`）でロック競合が起きうる。
**各エージェントは自分のセッションで異なる DB を設定する**:

```powershell
# TRACK-A のセッション
$env:DATABASE_URL = "sqlite+aiosqlite:///./.pytest_db_trackA.db"
# TRACK-B のセッション
$env:DATABASE_URL = "sqlite+aiosqlite:///./.pytest_db_trackB.db"
```

`pytest.ini` は既に `-p no:cacheprovider`（`:9`）を指定済みで、`.pytest_cache` 競合は起きない。

---

## 1. 変更ファイル総覧

### 1.1 新規（12 ファイル）

| ファイル | 担当 | ステップ |
|:---|:---:|:---:|
| `config/story_spine/__init__.py` | A | A1 |
| `config/story_spine/beat.py` | A | A1 |
| `config/story_spine/loader.py` | A | A1 |
| `config/story_spine/patterns.yaml` | A | A2 |
| `config/story_spine/lengths.yaml` | A | A2 |
| `config/story_spine/markets.yaml` | A | A2 |
| `config/story_spine/cards.yaml` | A | A2 |
| `config/story_spine/genre_registry.py` | B | B1 |
| `src/services/spine_resolver.py` | A | A3 |
| `scripts/measure_spine_alignment.py` | B | B13 |
| `tests/unit/story_spine/`（6ファイル） | A | A1-A5 |
| `tests/unit/story_spine_wiring/`（5ファイル） | B | B1-B8 |

### 1.2 改修（15 ファイル）

| ファイル | 担当 | 変更内容 |
|:---|:---:|:---|
| `src/backend/engine_narrative.py` | A | `PacingGraph` を相対位置化（`:74-86` の絶対話数 2 箇所を廃止） |
| `config/constants.py` | A | `EP_HUMILIATION` 等 5 定数を削除（`:18-22`） |
| `src/models/beat_sheet.py` | A | `EpisodeBeat.ep_num` の `le=40` を撤去（`:16`） |
| `config/archetypes_new.py` | A | 死んだ `PLOT_STRUCTURES`（`:44-48`）を削除 |
| `config/__init__.py` | A | 上記 re-export を削除（`:6-20`） |
| `src/services/structure_validator.py` | A | `pattern_key` を受け取れるよう拡張（`:16-48`） |
| `src/backend/routers/easy_mode.py` | B | `resolve_genre_to_preset`（`:50-58`）を `GENRE_REGISTRY` 経由に |
| `src/services/preset_loader.py` | B | `genre_to_preset`（`:43-60`）をレジストリ参照に |
| `src/services/spice_guard_adapter.py` | B | `GENRE_TO_PRESET`（`:43-59`）をレジストリ参照に |
| `src/backend/routers/misc.py` | B | `PLANNING_PRESETS` の **ImportError を修正**（`:91`）＋新エンドポイント |
| `src/backend/routers/plots.py` | B | 12ビートハードコード（`:342-378`）を Spine 生成に置換 |
| `src/backend/routers/commercial_planning.py` | B | 4幕ハードコード（`:112`）を `web_volume` に置換 |
| `src/application/dtos/plot_dto.py` | B | `structure_type`（`:24`）を実際に populate |
| `src/services/pipeline_base.py` | B | `current_volume`（`:72`）を増加可能に |
| `src/backend/workflows/reverse_plot_workflow.py` | B | `_calc_tension` を `Spine` ラッパーに縮小 |
| `src/services/llm/prompts.py` | B | `spine_quality` による条件付き注入（`:56-78` の直後に追記） |
| `prompts/templates/narrative/plot_stage1.j2` | B | 同様の条件付き注入 |
| `frontend/src/constants/manuscript.ts` | B | 6プリセットを API 参照に置換（`:3-48`） |
| `frontend/src/types/manuscript.ts` | B | 型定義を API レスポンスに追従 |
| `frontend/src/constants/genres.ts` | B | `GENRE_OPTIONS`（`:10-18`）をレジストリ取得に変更 |
| `frontend/src/components/generate/SimpleModePanel.tsx` | B | カードグリッド追加。select ハードコード（`:97-102`）廃止 |
| `frontend/src/components/wizard/Step1PlotInput.tsx` | B | 同上。`growth_curve` の不一致値を廃止（`:146-150`） |
| `frontend/src/components/planning/BeatSheetViewer.tsx` | B | 構成充足度表示（現状 12 行の placeholder） |

### 1.3 削除（非推奨化・§5 の記述と対応）

| 対象 | 理由 |
|:---|:---|
| `config/archetypes_new.py:44-48` `PLOT_STRUCTURES`（3件） | 参照 0 件。`config/story_spine/patterns.yaml`（38件）に置換 |
| `config/archetypes_new.py:485-530` `EASY_GENRES`（8件） | うち 4 件が空 dict のアーキタイプを参照。`cards.yaml` に置換 |
| `config/data/archetypes.json` の `PLOT_STRUCTURES`（`:9-258`） | ローダ 0 件。**内容は `patterns.yaml` へ移設したら削除** |
| `frontend/src/data/reversePlotSteps.ts:54-73` | `reverse_plot_workflow.py:31-57` と逐語重複。API 化 |
| `src/backend/routers/commercial_planning.py:112` の 4 幕 | `COMMERCIAL_40EP_BEATS` と真逆で矛盾 |

> **削除は「最後に 1 コミット」**。P6 に従い、**削除前に必ず `grep -rn "<識別子>"` で参照 0 件を確認する**。
> 確認せずに削除すると、既存テストが collection error になり原因追跡が困難になる。

---

## 2. TRACK-A：データ基盤＋解決エンジン（6 ステップ）

> **担当**: サブエージェント A
> **担当ブランチ**: `feature/spine-track-a`
> **このトラックの独立性**: B を待たずに最後まで走れる。B が A1 を待つ側。

---

### A1. 契約凍結（公開 API とデータスキーマの確定）
- **対象ファイル**: `config/story_spine/__init__.py`（新規）、`config/story_spine/beat.py`（新規）、`config/story_spine/loader.py`（新規）
- **依存**: なし（**全作業の起点**）
- **P分類**: P1（3ファイルだが新規のみ。P2 の例外）
- **推定所要**: 45分

**背景**

本計画は 2 エージェント並列で行う。並列作業の唯一の危険は**両者が別の API を期待すること**。
そこで**最初に公開 API を凍結**し、B はこの API に対してのみコードを書く。
A1 完了時点で **Gate G1** が開かれ、B はここから同時に走り出す。

**凍結する API（この形から変えてはいけない）**

```python
# config/story_spine/__init__.py
"""STORY_SPINE: 構造テンプレート層の公開 API（契約凍結 2026-09-29）."""
from .beat import BEAT_VOCABULARY, Beat, BeatInstance, Spine
from .loader import (
    CARDS, LENGTHS, MARKETS, PATTERNS,
    get_card, get_length, get_market, get_pattern,
)

__all__ = [
    "BEAT_VOCABULARY", "Beat", "BeatInstance", "Spine",
    "PATTERNS", "LENGTHS", "MARKETS", "CARDS",
    "get_pattern", "get_length", "get_market", "get_card",
    # A3 で追加（B はここから import する）
    "resolve_spine",
]
```

```python
# config/story_spine/beat.py
from __future__ import annotations
from dataclasses import dataclass, field

ROLES = ("hook", "engine", "reversal", "climax", "close", "filler")
ARTIFACTS = ("scene", "reversal", "reveal", "hook")


@dataclass(frozen=True)
class Beat:
    """パターンに依存しない、閉じたビート語彙の1エントリ。"""
    key: str
    label: str
    role: str
    span: tuple[float, float]   # 相対位置 [start, end) 0.0-1.0。**絶対話数でないこと**
    duty: str                   # このビートが必ず果たすこと（1文・命令形）
    tension: float              # 目標テンション 0.0-1.0
    artifact: str               # "scene" | "reversal" | "reveal" | "hook"
    optional: bool = False


@dataclass(frozen=True)
class BeatInstance:
    """話単位に量子化した 1 エントリ。"""
    ep_start: int
    ep_end: int
    key: str
    label: str
    role: str
    duty: str
    tension: float
    artifact: str


@dataclass(frozen=True)
class Spine:
    """1 作品分の構造。"""
    pattern: str
    length: str
    market: str
    total_eps: int
    beats: list[BeatInstance] = field(default_factory=list)

    def at(self, ep: int) -> BeatInstance | None:
        for b in self.beats:
            if b.ep_start <= ep <= b.ep_end:
                return b
        return None

    @property
    def keys(self) -> list[str]:
        return [b.key for b in self.beats]


BEAT_VOCABULARY: dict[str, Beat] = { /* 34語（親提案 §3.2）。A1 で全件を書く */ }
```

```python
# config/story_spine/loader.py
"""YAML データの読み込み。dataclass へ正規化して返す。"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).parent

def _load(name: str) -> dict[str, Any]:
    path = BASE_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

PATTERNS: dict[str, Any] = _load("patterns.yaml")
LENGTHS: dict[str, Any] = _load("lengths.yaml")
MARKETS: dict[str, Any] = _load("markets.yaml")
CARDS: dict[str, Any] = _load("cards.yaml")

def get_pattern(key: str) -> Any: ...    # 未知キーは exile_rise にフォールバック
def get_length(key: str) -> Any: ...     # 未知キーは novella にフォールバック
def get_market(key: str) -> Any: ...     # 未知キーは general にフォールバック
def get_card(key: str) -> Any | None: ... # 未知キーは None（B 側では例外扱いにしない）
```

**作業内容**

1. `config/story_spine/` ディレクトリを新規作成する（`Test-Path` で存在確認してから `New-Item`）。
   **注意**: `genre_registry.py` は **作らない**（B 所有）。
2. 上記3ファイルを作成する。**型・関数名・戻り値をこの通りに出力すること**（B が依存する）。
3. `BEAT_VOCABULARY` に 34語を**全件**書く（親提案 §3.2 の表をそのまま転記）。
   `role` / `artifact` は `ROLES` / `ARTIFACTS` の値のみ。`span` は必ず `0.0 <= start < end <= 1.0`。
4. `patterns.yaml` / `lengths.yaml` / `markets.yaml` / `cards.yaml` は **A1 では空ファイル（`{}`）でよい**。
   A2 で中身を書く。**A1 は API 形状の凍結だけが目的**。
5. `loader.py` の `get_*` は **未知キーで例外を投げない**（B の 12 ステップが壊れないため）。
   ただし `get_card` は `None` を返す（B 側の 12 ステップを壊さないため）。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_beat_vocabulary.py`（新規）

```python
"""閉じたビート語彙の構造的整合性の回帰テスト。"""
import pytest

from config.story_spine.beat import ARTIFACTS, BEAT_VOCABULARY, ROLES, Beat


def test_vocabulary_is_not_empty():
    assert len(BEAT_VOCABULARY) >= 30, f"語彙が {len(BEAT_VOCABULARY)} 語しかない"


def test_keys_are_unique():
    """dict のキーである以上自明だが、YAML 側からの二重登録を防ぐ。"""
    assert list(BEAT_VOCABULARY) == list(dict.fromkeys(BEAT_VOCABULARY))


def test_all_spans_are_relative():
    """**絶対話数が混入していないことの構造テスト**（本計画の最重要不変条件）。"""
    offenders = [
        f"{k}: {b.span}"
        for k, b in BEAT_VOCABULARY.items()
        if not (0.0 <= b.span[0] < b.span[1] <= 1.0)
    ]
    assert not offenders, f"相対でない span がある: {offenders}"


def test_roles_and_artifacts_are_from_closed_vocabulary():
    for k, b in BEAT_VOCABULARY.items():
        assert b.role in ROLES, f"{k}.role={b.role!r} が ROLES に無い"
        assert b.artifact in ARTIFACTS, f"{k}.artifact={b.artifact!r} が ARTIFACTS に無い"


def test_tension_in_unit_range():
    for k, b in BEAT_VOCABULARY.items():
        assert 0.0 <= b.tension <= 1.0, f"{k}.tension={b.tension}"


def test_duty_is_single_imperative_sentence():
    """duty はプロンプトに注入される。1文・命令形に限定する。"""
    for k, b in BEAT_VOCABULARY.items():
        assert b.duty.endswith("。"), f"{k}.duty が命令文で終わっていない: {b.duty!r}"
        assert len(b.duty) <= 60, f"{k}.duty が長すぎる（{len(b.duty)}字）: {b.duty!r}"


def test_beat_is_frozen():
    with pytest.raises(Exception):
        BEAT_VOCABULARY["climax"].tension = 0.0   # frozen=True なので TypeError
```

> `ROLES` / `ARTIFACTS` は `beat.py` で定義した**閉じた値集合**である。
> 変更のたびにテストを同時に直すこと。

**検証コマンド**
```powershell
C:\Python314\python.exe -c "from config.story_spine import BEAT_VOCABULARY, Beat, Spine; print(len(BEAT_VOCABULARY))"
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_beat_vocabulary.py -v
```

**完了判定**: 7テスト緑。かつ上の import コマンドが `>=30` を出力する。
**完了したら Gate G1 を宣言**し、B へ通知する。

---

### A2. データセット（38 パターン × 6 長さ × 4 媒体 × 24 カード）
- **対象ファイル**: `config/story_spine/patterns.yaml`、`lengths.yaml`、`markets.yaml`、`cards.yaml`
- **依存**: A1
- **P分類**: P1（4ファイルだが全て新規データ）
- **推定所要**: 3時間（**本計画で最も bulk なステップ**）

**背景**

`config/data/archetypes.json:9-258` に **31パターン**が `name` / `hook` / `mid_crisis` / `climax_type` / `ending` / `key_tropes` として存在するが、**ローダがどこにも無い**（`grep -rn "archetypes.json"` で 0 件）。
本ステップでこれを**唯一のロード可能なソース**へ昇格させ、不足分 7 種（親提案 §3.3.2）を追加する。

**作業内容**

1. **patterns.yaml（38件）**。既存 31 種は**キーを維持したまま** `config/data/archetypes.json:9-258` から転記する。
   - `hook` → span `[0.00, 0.08]` の `hook` role beat
   - `mid_crisis` → span `[0.48, 0.56]` の `midpoint_reversal` beat
   - `climax_type` → span `[0.82, 0.94]` の `climax` beat の `duty` に反映
   - `ending` → `endings:` リストへ
   - `key_tropes` → `tropes:` リストへ（**プロンプトには出すが構造判定には使わない**）
   - 追加 7 種は**親提案 §3.3.3 の定義例をそのまま使う**:
     `court_intrigue` / `professional_procedure` / `sports_growth` / `horror_dread` / `healing_care` / `ensemble_fracture` / `transformation_isekai`
2. **lengths.yaml（6件）**。文字数は `frontend/src/constants/manuscript.ts:3-48` の**実在値**を転記する。
   **新しい数字を作らない。** `short`(12,000字) / `novella`(20,000-40,000字) / `single_volume`(40,000-70,000字) / `web_volume`(100,000字・40話) / `long_serial`(250,000字+・100-300話) / `series`(1,000,000字+)
3. **markets.yaml（4件）**。`web` / `light_novel` / `single_shot` / `general`（親提案 §3.5 の表）。
4. **cards.yaml（24枚）**。親提案 §3.6 の表（card_id / pattern / length / market / style_key）。**12・13・17・21 番が短編・中編**であり、既存プリセットに無い層。
5. `config/data/archetypes.json` の `PLOT_STRUCTURES` は**この時点で削除しない**（I2 のベースライン後に統合担当が行う）。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_datasets.py`（新規）

```python
"""データセットの整合性。参照切れ・語彙漏れ・重複を検出する。"""
from config.story_spine.beat import BEAT_VOCABULARY
from config.story_spine.loader import CARDS, LENGTHS, MARKETS, PATTERNS

REQUIRED_EXISTING_31 = {
    "exile_rise", "peerless_reincarnation", "avenger_dark", "bottom_up_growth",
    "master_disciple", "secret_identity", "dungeon_conqueror", "guild_rebuilder",
    "summon_hero_betrayal", "tournament_champion", "slow_life", "gourmet_conqueror",
    "territory_management", "alchemy_workshop", "pet_tamer", "craftsman_legend",
    "modern_knowledge", "villainess_destruction_avoid", "contract_marriage",
    "doted_saint", "academy_cinderella", "love_comedy_density", "death_loop",
    "vr_streamer", "brain_battle", "detective_mystery", "army_rational",
    "shadow_organization", "onmyo_exorcism", "space_odyssey", "reincarnation_cheat",
}
REQUIRED_NEW_7 = {
    "court_intrigue", "professional_procedure", "sports_growth", "horror_dread",
    "healing_care", "ensemble_fracture", "transformation_isekai",
}
ENGINES = {"conflict", "comfort", "connection", "enigma"}


def test_pattern_count_is_38():
    assert len(PATTERNS) == 38, f"パターン数が {len(PATTERNS)}（38 のはず）"


def test_existing_31_keys_are_preserved():
    """既存 31 パターンのキーが1つも失われていないこと（移行の回帰防止）。"""
    missing = REQUIRED_EXISTING_31 - set(PATTERNS)
    assert not missing, f"既存キーの欠落: {sorted(missing)}"


def test_new_7_patterns_exist():
    missing = REQUIRED_NEW_7 - set(PATTERNS)
    assert not missing, f"新規7種の欠落: {sorted(missing)}"


def test_every_beat_key_exists_in_vocabulary():
    """パターンが語彙に無い beat を参照していないこと（プロンプト注入時に落ちる）。"""
    offenders = []
    for pk, pat in PATTERNS.items():
        for b in pat.get("beats", []):
            if b["key"] not in BEAT_VOCABULARY:
                offenders.append(f"{pk}.{b['key']}")
    assert not offenders, f"語彙に無い beat 参照: {offenders}"


def test_every_pattern_spans_are_monotonic_and_relative():
    for pk, pat in PATTERNS.items():
        prev = -1.0
        for b in pat.get("beats", []):
            s, e = b["span"]
            assert 0.0 <= s < e <= 1.0, f"{pk}.{b['key']} の span が不正: {b['span']}"
            assert s >= prev, f"{pk}.{b['key']} が前の beat と重なっている"
            prev = s


def test_every_pattern_has_climax():
    for pk, pat in PATTERNS.items():
        keys = [b["key"] for b in pat.get("beats", [])]
        assert "climax" in keys, f"{pk} に climax beat が無い"


def test_engines_are_from_closed_set():
    for pk, pat in PATTERNS.items():
        assert pat.get("engine") in ENGINES, f"{pk}.engine={pat.get('engine')!r}"


def test_lengths_market_counts():
    assert len(LENGTHS) == 6, f"長さ階層の数が {len(LENGTHS)}（6のはず）"
    assert len(MARKETS) == 4, f"媒体規格の数が {len(MARKETS)}（4のはず）"
    assert len(CARDS) == 24, f"カードの数が {len(CARDS)}（24のはず）"


def test_card_references_are_all_valid():
    """カードの参照先が実在すること（参照切れ防止）。"""
    offenders = []
    for ck, card in CARDS.items():
        for field_name, table in (
            ("pattern", PATTERNS), ("length", LENGTHS), ("market", MARKETS),
        ):
            if card.get(field_name) not in table:
                offenders.append(f"{ck}.{field_name}={card.get(field_name)!r}")
    assert not offenders, f"カードの参照切れ: {offenders}"


def test_cards_cover_short_and_mid_length():
    """短編・中編の層が1枚も無いと本計画の目的が達成されない。"""
    lengths_used = {c.get("length") for c in CARDS.values()}
    assert "short" in lengths_used, "短編カードが無い"
    assert {"novella", "single_volume", "web_volume", "long_serial"} <= lengths_used


def test_length_char_counts_match_manuscript_presets():
    """`frontend/src/constants/manuscript.ts` の実在値からの転記であること。"""
    assert LENGTHS["short"]["target_chars"] == 12000
    assert LENGTHS["web_volume"]["target_chars"] == 100000
    assert LENGTHS["web_volume"]["eps_range"] == [40, 40]
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_datasets.py -v
```

**完了判定**: 11テスト緑。`ruff check config\story_spine -q` が 0 件。

---

### A3. 解決エンジン（`resolve_spine`）— LLM 0回の決定論展開
- **対象ファイル**: `src/services/spine_resolver.py`（新規）
- **依存**: A1, A2
- **P分類**: P1（1ファイル）
- **推定所要**: 2時間

**背景**

親提案 §4。**ここが本計画の中核**。
「話数が変わっても構造が壊れない」「LLM を呼ばない」「1話短編に圧縮できる」を満たす唯一の場所。

**作業内容**

1. 親提案 §4.1 のシグネチャをそのまま実装する。
   ```python
   def resolve_spine(pattern_key, length_key, market_key, total_eps=None) -> Spine
   ```
2. **通常展開**（親提案 §4.2）。量子化は区間境界のみ計算し、**beat 数（≤34）だけをループする**。
   話数に比例しないこと（300話でも O(34)）。
3. **圧縮モード**（親提案 §4.3）。`min_beats > total_eps` のとき圧縮ポリシー表を適用する。
   **3不変条件を必ず守る**:
   - 最初が `inciting` 相当
   - 中盤に `midpoint_reversal` 相当
   - 最後が `climax` 相当
4. `MARKET.hook_window_eps` 以内に先頭 hook beat を寄せる。
5. `market == "web"` かつ末尾なら `volume_hook` を必ず残す。
6. `length.foreshadow_scopes` に無い `long_term` beat を落とす。
7. **`config/story_spine/__init__.py` に `resolve_spine` を re-export する**（A1 の `__all__` にすでに枠がある）。

**回帰テスト（先に作る）**: 4ファイル

`tests/unit/story_spine/test_resolver_compression.py`
```python
"""短編圧縮モードの不変条件。**本計画で最も重要なテスト**。"""
import pytest

from config.story_spine import PATTERNS, resolve_spine


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
def test_single_episode_preserves_three_critical_beats(pattern):
    """1話短編でも 発端・中点反転・クライマックス の3つは必ず残る。"""
    spine = resolve_spine(pattern, "short", "general", total_eps=1)
    keys = spine.keys
    assert "inciting" in keys or keys[0] in ("humiliation", "cold_open"), (
        f"{pattern}: 最初がつかみになっていない: {keys}"
    )
    assert "midpoint_reversal" in keys, f"{pattern}: 中点反転が消えている: {keys}"
    assert "climax" in keys, f"{pattern}: クライマックスが消えている: {keys}"


@pytest.mark.parametrize("pattern", sorted(PATTERNS))
def test_single_episode_ends_with_climax(pattern):
    """短編の最後がクライマックスでないと結末が無い。"""
    spine = resolve_spine(pattern, "short", "general", total_eps=1)
    assert spine.beats[-1].key == "climax", (
        f"{pattern}: 最後が {spine.beats[-1].key!r} になっている"
    )


@pytest.mark.parametrize("eps", [1, 2, 3, 4, 5])
def test_compression_degrades_monotonically(eps):
    """話数を増やすと必須ビートが減らないこと。"""
    prev: set[str] = set()
    for e in range(1, eps + 1):
        keys = set(resolve_spine("exile_rise", "short", "general", total_eps=e).keys)
        assert prev <= keys, f"eps={e} でビートが {_sort(prev - keys)} 消えた"
        prev = keys


def test_web_market_keeps_volume_hook():
    """Web 連載では話末の引きが消えない。"""
    spine = resolve_spine("exile_rise", "web_volume", "web", total_eps=40)
    assert spine.keys[-1] == "volume_hook", spine.keys[-3:]


def test_general_market_drops_volume_hook():
    """一般文芸では「次への引き」を強制しない。"""
    spine = resolve_spine("exile_rise", "single_volume", "general", total_eps=18)
    assert "volume_hook" not in spine.keys


def _sort(xs):
    return sorted(xs)
```

`tests/unit/story_spine/test_resolver_combinatorial.py`
```python
"""全組合せの網羅テスト。1つも崩れていてはいけない。"""
import itertools

from config.story_spine import CARDS, LENGTHS, MARKETS, PATTERNS, resolve_spine


def test_full_combinatorial_matrix_never_raises():
    """38パターン × 6長さ × 4媒体 × 3話数 = 2,736 ケース。"""
    count = 0
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        for eps in (lo, (lo + hi) // 2, hi):
            spine = resolve_spine(p, l, m, eps)
            assert spine.beats, f"{p}×{l}×{m}@{eps} が空"
            count += 1
    assert count == 38 * 6 * 4 * 3, f"ケース数が {count}（2736 のはず）"


def test_every_beat_is_backed_by_known_vocabulary():
    from config.story_spine import BEAT_VOCABULARY
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        for b in resolve_spine(p, l, m, lo).beats:
            assert b.key in BEAT_VOCABULARY, f"{p}: 未知 beat {b.key!r}"


def test_episode_ranges_are_contiguous_and_cover_all():
    """1話から total_eps まで隙なく埋まっていること。"""
    for p, l, m in itertools.product(PATTERNS, LENGTHS, MARKETS):
        lo, hi = LENGTHS[l]["eps_range"]
        eps = hi
        spine = resolve_spine(p, l, m, eps)
        covered = [n for b in spine.beats for n in range(b.ep_start, b.ep_end + 1)]
        assert covered == list(range(1, eps + 1)), (
            f"{p}×{l}×{m}@{eps}: 話数に隙間がある（{covered[:5]}...）"
        )


def test_unknown_keys_fall_back_instead_of_raising():
    """未知キーで例外を投げないこと（B の12ステップを壊さないため）。"""
    for args in (
        ("nope", "short", "general", 3),
        ("exile_rise", "nope", "general", 3),
        ("exile_rise", "short", "nope", 3),
    ):
        assert resolve_spine(*args).beats
```

`tests/unit/story_spine/test_resolver_relative.py`
```python
"""話数を変えても構造が破綻しないこと（絶対話数バグの回帰防止）。"""
from config.story_spine import LENGTHS, resolve_spine


def test_relative_position_of_key_beats_is_length_independent():
    for eps in (10, 25, 40, 100, 300):
        spine = resolve_spine("exile_rise", "long_serial", "web", eps)
        climax = [b for b in spine.beats if b.key == "climax"][0]
        rel = ((climax.ep_start + climax.ep_end) / 2) / eps
        assert 0.75 <= rel <= 0.92, f"eps={eps}: climax の相対位置が {rel:.2f}"


def test_pacing_graph_is_length_independent():
    """**既存バグの直接の回帰テスト**。旧実装は ep5/24-26 が絶対だった。"""
    from src.backend.engine_narrative import PacingGraph

    short = PacingGraph.get_instruction(2, total_eps=20)
    long_ = PacingGraph.get_instruction(10, total_eps=100)
    assert short["instruction"] == long_["instruction"], (
        "話数だけ変えても同じ相対位置なら同じ指示になるはず"
    )


def test_first_explosion_position_scales():
    """第1の爆発が「10%時点」に固定されていること。"""
    from src.backend.engine_narrative import PacingGraph

    for eps in (20, 40, 100):
        found = [
            ep for ep in range(1, eps + 1)
            if "第1の爆発" in PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
        ]
        assert found, f"eps={eps} で第1の爆発が見つからない"
        rel = found[0] / eps
        assert 0.05 <= rel <= 0.20, f"eps={eps}: 第1の爆発の相対位置が {rel:.2f}"
```

`tests/unit/story_spine/test_resolver_no_llm.py`
```python
"""**resolve_spine は LLM を一切呼ばない**ことの証明。"""
import pytest


@pytest.fixture
def no_llm(monkeypatch):
    """すべての LLM 経路を爆発させる。呼ばれたらテストが落ちる。"""
    def _boom(*a, **k):
        raise AssertionError("resolve_spine が LLM を呼んだ（D2 違反）")

    for target in (
        "src.llm.resilient_gateway.ResilientLLMGateway.generate_text",
        "src.llm.resilient_gateway.ResilientLLMGateway.generate_json",
    ):
        mod_path, _, attr = target.rpartition(".")
        try:
            mod = __import__(mod_path, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr):
            monkeypatch.setattr(mod, attr, _boom, raising=False)


def test_resolve_spine_makes_no_llm_call(no_llm):
    from config.story_spine import resolve_spine
    for eps in (1, 5, 40, 300):
        assert resolve_spine("exile_rise", "long_serial", "web", eps).beats


def test_resolve_spine_is_deterministic():
    """同じ入力は常に同じ出力（LLM が involved していることの検出も兼ねる）。"""
    from config.story_spine import resolve_spine
    a = resolve_spine("exile_rise", "web_volume", "web", 40)
    b = resolve_spine("exile_rise", "web_volume", "web", 40)
    assert a.keys == b.keys
    assert [(x.ep_start, x.ep_end, x.tension) for x in a.beats] == \
           [(x.ep_start, x.ep_end, x.tension) for x in b.beats]
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine -v
```

**完了判定**: 全テスト緑。網羅テストが 2,736 ケースを走査し `assert count == 2736` を通る。

---

### A4. `structure_validator` のパターン対応
- **対象ファイル**: `src/services/structure_validator.py`
- **依存**: A1, A2
- **P分類**: P1（1ファイル）
- **推定所要**: 45分

**背景**

`structure_validator.py:16-48` の `STRUCTURE_DEFINITIONS`（3件）は既に `phase`（相対位置 0.0-1.0）と `climax_min_phase` を持つ**正規化された**データ構造である。
本ステップで `pattern` を受け取れるよう拡張し、**生成前検証（自己整合）と生成後検証（充足度）の両方で使えるようにする**（親提案 §4.4）。

**既存 API を壊さないこと**（`tests/unit/test_structure_validator.py` が4テストある）。

**作業内容**

1. `validate(chapters, structure_name="three_act", *, pattern_key: str | None = None)` に
   **キーワード専用引数** `pattern_key` を追加する。既存呼び出しは影響を受けない。
2. `pattern_key` が渡された場合、`STRUCTURE_DEFINITIONS` ではなく
   `config.story_spine.PATTERNS[pattern_key]["beats"]` から `required_beats` を**動的に構築**する。
3. 返り値に `pattern_key` と `spine`（`resolve_spine` 済みの期待値）を含める。
4. `STRUCTURE_DEFINITIONS` の3件（`three_act` / `kishotenketsu` / `hero_journey`）は
   **削除しない**。`pattern_key is None` の従来経路で従来どおり動く。
5. `assign_phases`（`:56-61`）は `n == 1` のとき ZeroDivisionError になりうる。
   **本ステップで併せて修正**し、`n <= 1` のとき `{"_phase": 0.0}` を返す。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_validator_pattern.py`（新規）

```python
"""pattern 対応の構造バリデータ。"""
from src.services.structure_validator import assign_phases, validate


def test_legacy_structures_still_work():
    """既存 API が壊れていないこと（後方互換の回帰防止）。"""
    r = validate([{"chapter_number": 1, "tension": 1}], structure_name="kishotenketsu")
    assert r["structure_key"] == "kishotenketsu"
    assert "is_healthy" in r


def test_pattern_key_uses_spine_beats():
    r = validate(
        [{"chapter_number": i, "tension": int(10 * i)} for i in range(1, 21)],
        structure_name="three_act",
        pattern_key="exile_rise",
    )
    assert r["pattern_key"] == "exile_rise"
    assert isinstance(r["missing_beats"], list)


def test_unknown_pattern_falls_back():
    r = validate([{"chapter_number": 1, "tension": 1}], pattern_key="nope")
    assert r["pattern_key"] is not None, "未知パターンで例外を投げない"


def test_assign_phases_single_chapter_does_not_divide_by_zero():
    """**1話構成で ZeroDivisionError しないこと**（短編対応の回帰）。"""
    out = assign_phases([{"chapter_number": 1, "title": "短編"}])
    assert out[0]["_phase"] == 0.0
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\test_structure_validator.py tests\unit\story_spine\test_validator_pattern.py -v
```

**完了判定**: 新規4テスト緑 + **既存 `tests/unit/test_structure_validator.py` の4テストが緑のまま**。

---

### A5. 絶対話数の排除（`PacingGraph` / `EP_*` 定数）
- **対象ファイル**: `src/backend/engine_narrative.py`、`config/constants.py`
- **依存**: A1, A3
- **P分類**: P2（機械的置換のみ）
- **推定所要**: 1時間

**背景**

`src/backend/engine_narrative.py:38-98` の `PacingGraph.get_instruction` は、**同一関数内で**
`mid_twist_ep = total_eps // 2` / `late_twist_ep = int(total_eps * 0.8)` と相対化されている一方、
`:74` の `elif ep_num == 5:` と `:80` の `elif 24 <= ep_num <= 26:` は**絶対話数のまま**残る。
`total_eps=20` でも `total_eps=100` でも第1の爆発が第5話のままである。

`config/constants.py:18-22` の `EP_HUMILIATION=2` / `EP_TRIGGER=3` / `EP_MUSOU_START=4` / `EP_FINAL=8` / `EP_CLIMAX=7` は **8話固定**の前提。

**作業内容**

1. **削除前に必ず参照を確認する**（P6）。
   ```powershell
   Select-String -Path src\*.py,src\**\*.py,tests\**\*.py -Pattern 'EP_HUMILIATION|EP_TRIGGER|EP_MUSOU_START|EP_FINAL|EP_CLIMAX'
   ```
   参照が 0 件なら **削除**。参照が残っているなら、**その呼び出し元だけ `resolve_spine` 経由に置換してから削除**する。
   **「残っているので消さない」で終わらせない。**
2. `PacingGraph.get_instruction` を全面的に相対化する。
   `elif ep_num == 5:` → 第1の爆発を `span` 基準（親提案 §3.3 の `first_win` の span）中点に置く。
   `elif 24 <= ep_num <= 26:` → クライマックスを `climax` beat の span 中点に置く。
   **計算方法は必ず `resolve_spine` の結果から導出する**（ハードコード禁止）。
3. `PlanningStateMachine`（`:20-31`）は本次計画の対象外。触らない。

**回帰テスト（先に作る）**: `tests/regression/test_relative_episode_structure.py`（新規）

```python
"""**絶対話数バグの回帰防止**。本計画の最重要リグレッションテスト群。"""
import ast
from pathlib import Path

import pytest

from src.backend.engine_narrative import PacingGraph


# --- 1. PacingGraph が話数非依存であること ---

@pytest.mark.parametrize("eps", [8, 20, 40, 100, 300])
def test_instruction_depends_only_on_relative_position(eps):
    """1/(eps) と 10/(10*eps) は同じ相対位置 → 同じ指示。"""
    assert (
        PacingGraph.get_instruction(1, total_eps=eps)["instruction"]
        == PacingGraph.get_instruction(10, total_eps=10 * eps)["instruction"]
    )


@pytest.mark.parametrize("eps", [20, 40, 100])
def test_climax_cluster_scales_with_length(eps):
    """クライマックスクラスタが「終盤」に固定されていること。"""
    hits = [
        ep for ep in range(1, eps + 1)
        if "クライマックス" in PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
    ]
    assert hits, f"eps={eps} でクライマックスが見つからない"
    assert max(hits) / eps >= 0.70, f"eps={eps}: クライマックスが {max(hits)/eps:.0%} 位置"


def test_no_absolute_episode_literals_in_pacing_graph():
    """`ep_num == 5` のような絶対比較がソース中に残っていないこと。"""
    src = Path("src/backend/engine_narrative.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name):
            if node.left.id == "ep_num" and any(
                isinstance(c, ast.Constant) and isinstance(c.value, int) and c.value > 1
                for c in node.comparators
            ):
                offenders.append(f"line {node.lineno}")
    assert not offenders, f"絶対話数比較が残存: {offenders}"


# --- 2. EP_* 定数が消えていること ---

def test_episode_constants_removed():
    """8話固定の EP_* 定数が残っていないこと。"""
    import config.constants as c

    for name in ("EP_HUMILIATION", "EP_TRIGGER", "EP_MUSOU_START", "EP_FINAL", "EP_CLIMAX"):
        assert not hasattr(c, name), f"{name} がまだ残っている"


# --- 3. 100話が構造上通ること ---

def test_episode_beat_accepts_100():
    """**40話上限の撤去**（長編対応の回帰）。"""
    from src.models.beat_sheet import EpisodeBeat

    beat = EpisodeBeat(
        ep_num=100, phase="終盤", mission="決戦",
        tension_target=0.9, visual_scene_focus="黒幕との対決",
    )
    assert beat.ep_num == 100
```

> ただし `test_episode_beat_accepts_100` は **A6 で `le=40` を外すまで赤になる**。
> A5 の時点では `pytest ... -k "not episode_beat"` で回すか、A5/A6 を 1 コミットにまとめてよい。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_relative_episode_structure.py -v
C:\Python314\python.exe -m pytest tests\unit\story_spine -q
```

**完了判定**: 8テスト緑。`Select-String` で `EP_HUMILIATION` 等が `src/` に 0 件。

---

### A6. 死んだ定義の除去（`le=40` / `PLOT_STRUCTURES` / re-export）
- **対象ファイル**: `src/models/beat_sheet.py`、`config/archetypes_new.py`、`config/__init__.py`
- **依存**: A5
- **P分類**: P2（機械的置換のみ）
- **推定所要**: 45分

**背景**

- `src/models/beat_sheet.py:16` の `ep_num: int = Field(..., ge=1, le=40)` は 40話より長い構成を**Pydantic で弾く**。
- `config/archetypes_new.py:44-48` の `PLOT_STRUCTURES`（3件）は**参照 0 件**。`config/data/archetypes.json:9-258`（31件、ロード 0 件）に完全に包含される。
- `config/__init__.py:6-20` が `PLOT_STRUCTURES` を `archetypes_new` から re-export している。

**作業内容**

1. `EpisodeBeat.ep_num` から `le=40` を外し、`ge=1` のみ残す。`description` も `話数 (1-40)` → `話数` に直す。
2. `config/archetypes_new.py:44-48` の `PLOT_STRUCTURES` を**削除**。
3. `config/__init__.py` の import リストから `PLOT_STRUCTURES` を外し、`__all__`（あれば）からも外す。
4. **削除前に必ず確認**:
   ```powershell
   Select-String -Path src\*.py,src\**\*.py,tests\**\*.py,config\*.py -Pattern 'PLOT_STRUCTURES'
   ```
   参照が 0 件であることを**確認してから**消す。
5. `config/data/archetypes.json` は**このステップでは消さない**（I2 のベースライン後に統合担当が判断する）。
6. **禁止**: `config/story_spine/genre_registry.py` は **B 所有**。`config/__init__.py` に genre registry の export を**追加しない**。
   B は `from config.story_spine.genre_registry import ...` と直接 import する。

**回帰テスト（先に作る）**: `tests/unit/story_spine/test_removed_definitions.py`（新規）

```python
"""削除した定義が復活していないことの回帰テスト。"""
import ast
from pathlib import Path


def test_plot_structures_removed_from_archetypes_new():
    from config import archetypes_new
    assert not hasattr(archetypes_new, "PLOT_STRUCTURES"), (
        "死んでいた PLOT_STRUCTURES が復活している（patterns.yaml に一本化すること）"
    )


def test_plot_structures_not_reexported_from_config():
    import config
    assert not hasattr(config, "PLOT_STRUCTURES")


def test_episode_beat_has_no_upper_bound():
    """`le=40` が再発していないこと（ast で構造的に検査）。"""
    src = Path("src/models/beat_sheet.py").read_text(encoding="utf-8")
    assert 'le=40' not in src, "EpisodeBeat.ep_num の le=40 が再発している"


def test_episode_beat_accepts_300():
    from src.models.beat_sheet import EpisodeBeat

    b = EpisodeBeat(ep_num=300, phase="終盤", mission="x",
                    tension_target=0.5, visual_scene_focus="y")
    assert b.ep_num == 300


def test_no_consumer_imports_plot_structures():
    """リポジトリ全体で PLOT_STRUCTURES への参照が無いこと。"""
    offenders = []
    for path in Path("src").rglob("*.py"):
        if "PLOT_STRUCTURES" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path))
    assert not offenders, f"PLOT_STRUCTURES の参照が残存: {offenders}"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine\test_removed_definitions.py -v
C:\Python314\python.exe -c "import config; print(len(config.STORY_ARCHETYPES))"
```

**完了判定**: 5テスト緑。`import config` が成功する。

---

### 補足: `genre_registry.py` は TRACK-B が作る（A は作らない）

`genre_registry.py` は **TRACK-B の B1** に割り当てた（§0.2）。A は作らない。

> 親提案の旧番号 A7（`genre_registry.py`）は §0.2 の排他所有に従い **B1 に移した**。
> `config/story_spine/genre_registry.py` は **B 所有**であり、A は触ってはいけない。
> 今後 `config/story_spine/` に追加データが出た場合も、A ではなく **B の後続ステップ**に追加すること。
> `config/__init__.py` の re-export は A6 で確定済みなので触らない。

---

## 3. TRACK-B：配線＋UI＋計測（14 ステップ）

> **担当**: サブエージェント B
> **担当ブランチ**: `feature/spine-track-b`
> **開始条件**: **Gate G1**（A1 完了）通過後にのみ着手する
> **推奨着手順**: B1 → B2 → B3 → B9 → B10 → B11 → B12（A2完了待ち） → B4 → B5 → B6 → B7 → B8 → B13 → B14

---

### B1. `GENRE_REGISTRY` の新設と `easy_mode` 配線
- **対象ファイル**: `config/story_spine/genre_registry.py`（新規）、`src/backend/routers/easy_mode.py`
- **依存**: **G1**（A1 完了）
- **P分類**: P1（2ファイルだが新規+機械的改修）
- **推定所要**: 1.5時間

**背景**

現在 **4 系統のジャンル語彙**と **3 系統の genre→preset 表**が競合している。

| 系統 | 場所 | 値 |
|:---|:---|:---|
| G1 | `frontend/src/components/generate/SimpleModePanel.tsx:91-103` | `fan / sf / romance / mystery / horror / other` |
| G2 | `frontend/src/constants/genres.ts:10-18` | 日本語7ラベル |
| G3 | `frontend/src/components/wizard/Step1PlotInput.tsx:132-136` | `fantasy / modern_fantasy / romance / scifi` |
| G4 | `config/archetypes_new.py:476` | 日本語6ラベル |

そして `src/backend/routers/easy_mode.py:34-47` の `GENRE_TO_PRESET` は**日本語キーワードの部分一致**のみ。
**既定の EasyMode 経路が送る `"fan"` は 1 つも一致せず `None` に落ちる**（`resolve_genre_to_preset` は `:50-58`）。
**EasyMode はスタイルプリセットが 1 つも効かない状態で動いている。**

**作業内容**

1. `config/story_spine/genre_registry.py` を新規作成する（**A が `config/story_spine/` を作っているので、その中に置く**）。
   ```python
   GENRE_REGISTRY: dict[str, dict] = {
       "HighFantasy": {
           "label": "ハイファンタジー",
           # 旧4系統の値をすべてここに集約する（1つも漏らさない）
           "aliases": ["fan", "fantasy", "ハイファンタジー (R15)", "ファンタジー",
                       "ハイファンタジー", "異世界", "異世界転生"],
           "domain": "fantasy",
           "preset_key": "cheat_tensei",
           "rating": "r15",
       },
       # 以降 SF / Romance / Mystery / Horror / Modern / History / Youth を追加
   }

   def resolve_genre(value: str) -> dict | None:
       """旧4系統のいずれの値でも 1 つのレジストリに解決する。"""
       if not value:
           return None
       v = value.strip()
       if v in GENRE_REGISTRY:
           return GENRE_REGISTRY[v]
       for entry in GENRE_REGISTRY.values():
           if v in entry["aliases"] or entry["label"] in v:
               return entry
       return None

   def resolve_preset_key(value: str) -> str | None:
       entry = resolve_genre(value)
       return entry["preset_key"] if entry else None
   ```
2. `easy_mode.py:34-47` の `GENRE_TO_PRESET` リストと `:50-58` の `resolve_genre_to_preset` を
   **レジストリ委譲**に置き換える。**関数名と戻り値の型は変更しない**（既存呼び出しに壊れないため）。
   ```python
   def resolve_genre_to_preset(genre: str) -> str | None:
       from config.story_spine.genre_registry import resolve_preset_key
       return resolve_preset_key(genre)
   ```
3. **既存の 11 キーワード**（`ざまぁ` / `令嬢` / `VRMMO` / `ダンジョン` / `スローライフ` / `追放` / `ループ` / `テンセイ` / `現代チート` / `異世界転生` / `ダークファンタジー`）が**すべて同じ preset を返す**ことをテストする。
   特に `("追放", "slow_life")` と `("ざまぁ", "zarma")` の**優先順位差**を維持すること。

**回帰テスト（先に作る）**: `tests/regression/test_genre_resolution_unified.py`（新規）

```python
"""**4系統のジャンル語彙の統合**に対する回帰テスト。"""
import pytest

from src.backend.routers.easy_mode import resolve_genre_to_preset

# 旧 G1: SimpleModePanel.tsx:91-103
LEGACY_UI_VALUES = ["fan", "sf", "romance", "mystery", "horror", "other"]
# 旧 G2: constants/genres.ts:10-18
LEGACY_CONSTANTS_VALUES = [
    "ハイファンタジー (R15)", "ダークファンタジー (R15)", "異世界転生・バトル (R15)",
    "ざまぁ・追放・無双 (R15)", "悪役令嬢・婚約破棄", "追放後スローライフ", "VRMMO・ゲーム世界",
]
# 旧 G3: Step1PlotInput.tsx:132-136
LEGACY_WIZARD_VALUES = ["fantasy", "modern_fantasy", "romance", "scifi"]
# 旧 G4: archetypes_new.py:476
LEGACY_ARCHETYPE_VALUES = ["ファンタジー", "SF", "現代", "歴史", "官能/ロマンス", "その他"]


@pytest.mark.parametrize("value", LEGACY_UI_VALUES)
def test_simple_mode_values_now_resolve(value):
    """**旧バグの直接の回帰テスト**。旧実装は 'fan' 等で None を返していた。"""
    assert resolve_genre_to_preset(value) is not None, f"{value!r} が None のまま"


@pytest.mark.parametrize("value", LEGACY_CONSTANTS_VALUES + LEGACY_WIZARD_VALUES
                         + LEGACY_ARCHETYPE_VALUES)
def test_all_legacy_vocabularies_resolve(value):
    assert resolve_genre_to_preset(value) is not None, f"{value!r} が解決しない"


def test_legacy_keyword_priority_is_preserved():
    """既存の11キーワードが同じ preset を返すこと（文言の意味が変わっていない）。"""
    expectations = {
        "ざまぁ": "zarma", "令嬢": "aku_reijo", "VRMMO": "vrmmo",
        "ダンジョン": "dungeon_admin", "スローライフ": "slow_life",
        "追放": "slow_life", "ループ": "loop", "テンセイ": "cheat_tensei",
        "現代チート": "modern_cheat", "異世界転生": "cheat_tensei",
        "ダークファンタジー": "cheat_tensei",
    }
    for keyword, preset in expectations.items():
        assert resolve_genre_to_preset(keyword) == preset, (
            f"{keyword!r} の解決先が {resolve_genre_to_preset(keyword)!r} に変わった"
        )


def test_empty_string_still_returns_none():
    """空文字は None のまま（サイレントなデフォルト代入をしない）。"""
    assert resolve_genre_to_preset("") is None
    assert resolve_genre_to_preset(None) is None


def test_unknown_garbage_returns_none():
    assert resolve_genre_to_preset("ZZZ存在しないZZZ") is None
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_genre_resolution_unified.py -v
```

**完了判定**: 全パラメータ緑（30+ ケース）。

---

### B2. genre→preset 表の統合（`preset_loader` / `spice_guard`）
- **対象ファイル**: `src/services/preset_loader.py`、`src/services/spice_guard_adapter.py`
- **依存**: B1
- **P分類**: P2（機械的置換のみ）
- **推定所要**: 45分

**背景**

- `src/services/preset_loader.py:43-60` に `genre_to_preset` 辞書（16エントリ）がある。
- `src/services/spice_guard_adapter.py:43-59` に `GENRE_TO_PRESET` 辞書（16エントリ）がある。
- **両者はほぼ同一だが微妙にズレている**（例: `preset_loader` には `"異世界"` があるが `spice_guard` にもある 等）。
- `preset_loader` は `.get(genre, "zarma")` で**未知値を黙って `zarma` に落とす**。

**作業内容**

1. 両ファイルから**辞書を削除**し、`resolve_preset_key` に委譲する。
2. `preset_loader.py:60` の `preset_name = genre_to_preset.get(genre, "zarma")` を、
   **レジストリ解決 → 見つからないなら `logger.warning` を1回出してから既定 `zarma`** に変える。
   黙って既定にしない（PLAN_T6 Step 5 の「未知モデル $0.00 化」と同型の失敗を防ぐ）。
3. `spice_guard_adapter` 側は同じ委譲。**既存の関数名・クラス名は変えない**。
4. **両ファイルの辞書を丸ごと削除してよいかを確認する**: `Select-String` で外部参照を調べ、
   外部から `genre_to_preset` / `GENRE_TO_PRESET` を import している箇所があれば
   **その変数名を維持したラッパーを残す**。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_genre_tables_merged.py`（新規）

```python
"""3系統の genre→preset 表が1つに統合されたことの確認。"""
from config.story_spine.genre_registry import GENRE_REGISTRY, resolve_preset_key
from src.services.preset_loader import load_preset_for_pipeline
from src.services import spice_guard_adapter


MERGED_VALUES = [
    "ファンタジー", "恋愛", "SF", "歴史", "現代", "官能/ロマンス",
    "異世界", "追放ざまぁ", "悪役令嬢", "チート転生", "スローライフ",
    "ダンジョン運営", "現代チート", "TS転生", "VRMMO", "ループ",
]


def test_preset_loader_dict_is_gone():
    """二重管理が再発していないこと。"""
    from src.services import preset_loader

    src = __import__("pathlib").Path(preset_loader.__file__).read_text(encoding="utf-8")
    assert "genre_to_preset = {" not in src, "preset_loader に辞書が復活している"


def test_spice_guard_dict_is_gone():
    from pathlib import Path

    src = Path(spice_guard_adapter.__file__).read_text(encoding="utf-8")
    assert "GENRE_TO_PRESET = {" not in src, "spice_guard_adapter に辞書が復活している"


def test_all_merged_values_agree():
    """旧2表の16エントリがすべて同じ preset に解決されること。"""
    for value in MERGED_VALUES:
        assert resolve_preset_key(value) is not None, f"{value!r} が解決しない"


def test_three_tables_do_not_contradict():
    """同一 display 値に対する3経路の preset が一致すること。"""
    from src.backend.routers.easy_mode import resolve_genre_to_preset

    for value in MERGED_VALUES:
        a = resolve_genre_to_preset(value)
        b = resolve_preset_key(value)
        assert a == b, f"{value!r}: easy_mode={a!r} vs registry={b!r}"


def test_loader_still_returns_preset_for_known_genre():
    preset = load_preset_for_pipeline("ファンタジー", None)
    assert isinstance(preset, dict)
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring\test_genre_tables_merged.py -v
```

**完了判定**: 5テスト緑。

---

### B3. `/api/config/planning_options` の ImportError 修正＋新エンドポイント
- **対象ファイル**: `src/backend/routers/misc.py`
- **依存**: B1
- **P分類**: P1（1ファイル）
- **推定所要**: 1時間

**背景**

`src/backend/routers/misc.py:91` は
```python
from config.constants import PLANNING_PRESETS
```
を行うが、**`config/constants.py` に `PLANNING_PRESETS` は定義されていない**（`grep` 0 件）。
→ 関数実行時に `ImportError` → **このエンドポイントは常に HTTP 500**。

これは「ジャンル・アーキタイプをUIに配る」唯一のAPIであり、**現在壊れている**。

**作業内容**

1. `PLANNING_PRESETS` の import を削除し、`cards.yaml` 由来の `CARDS` を返すように置き換える。
2. 既存レスポンスのキー `easy_genres` / `story_archetypes` / `style_definitions` は**削除しない**（FE が使っている可能性がある）。
   **新キー `cards` / `lengths` / `markets` / `patterns` / `genres` を追加**する形にする。
3. レスポンスに **`BEAT_VOCABULARY` の要約**（key / label / role / tension / artifact）を含める。
   FE の Tier 3 表示（親提案 §6.3）で必要。

**回帰テスト（先に作る）**: `tests/contract/test_planning_options_endpoint.py`（新規）

```python
"""/api/config/planning_options が 500 でなく 200 を返すことの契約テスト。"""
import asyncio
import pytest


def test_planning_options_does_not_raise():
    """**既存バグの直接の回帰テスト**。旧実装は ImportError で落ちていた。"""
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    assert isinstance(result, dict)


def test_legacy_keys_are_preserved():
    """既存 FE が使うキーが消えていないこと。"""
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    for key in ("easy_genres", "story_archetypes", "style_definitions"):
        assert key in result, f"既存キー {key!r} が消えている"


def test_new_spine_keys_present():
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    for key in ("cards", "lengths", "markets", "patterns", "genres"):
        assert key in result, f"新キー {key!r} が無い"


def test_cards_payload_is_usable_by_frontend():
    """カード1枚に必要なフィールドが揃っていること。"""
    from src.backend.routers.misc import get_planning_options

    cards = asyncio.run(get_planning_options())["cards"]
    assert len(cards) >= 24
    first = next(iter(cards.values()))
    for field_name in ("label", "pattern", "length", "market", "style_key"):
        assert field_name in first, f"カードに {field_name!r} が無い"


def test_no_planning_presets_import_remains():
    """壊れた import が復活していないこと。"""
    from pathlib import Path

    src = Path("src/backend/routers/misc.py").read_text(encoding="utf-8")
    assert "PLANNING_PRESETS" not in src
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_planning_options_endpoint.py -v
```

**完了判定**: 5テスト緑。

---

### B4. Wizard の 12 ビートハードコード置換
- **対象ファイル**: `src/backend/routers/plots.py`
- **依存**: **A3 完了**（`resolve_spine` が必要）
- **P分類**: P1（1ファイル）
- **推定所要**: 1.5時間

**背景**

`src/backend/routers/plots.py:342-378` のプロンプトが **Save the Cat の 12 ビートをハードコード**している。
`:402` で `beats_data[:12]` に切り詰め、`:411-508` に12エピソードの決定論的フォールバックがある。
`short`（1-3話）で 12 ビートは成立しない。

**作業内容**

1. `:342-378` のプロンプト文字列に `{{ spine_summary }}` を差し込む。
   `spine_summary` は `resolve_spine(...)` の結果から生成する**1つのテキスト**（例: `1:追放 / 2-3:覚醒 / 4-9:初勝利 ...`）。
2. `:402` の `beats_data[:12]` 切り詰めを**削除**し、`resolve_spine` の結果話数分だけ受け付ける。
3. `:411-508` の 12 エピソードフォールバックを、`resolve_spine` の出力に**置き換える**。
4. `ExpandBeatsRequest`（`src/models/api_schemas.py:309-333`）に
   `pattern_key: str = ""` / `length_key: str = ""` / `market_key: str = ""` を追加する。
   **デフォルト空文字**にして、既存呼び出しを壊さない。
   > **注意**: `src/models/api_schemas.py` は §0.2 の表に無い。
   > **B4 の担当ファイルリストに `src/models/api_schemas.py` を追加すること**（B 内部のファイルなので所有者衝突はない）。
5. `sensory_focus` がサイレントに捨てられている既存の不具合（`:301-317` 付近）は**今回は直さない**（スコープ外）。Issue 化する。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_plots_beat_expansion.py`（新規）

```python
"""Wizard のビート生成が Spine に基づくことの確認。"""
import ast
from pathlib import Path

import pytest


def test_save_the_cat_hardcode_is_gone():
    """12ビートハードコードが復活していないこと（ast で構造検査）。"""
    src = Path("src/backend/routers/plots.py").read_text(encoding="utf-8")
    for marker in ("Dark Night of the Soul", "All Is Lost", "Bad Guys Close In"):
        assert marker not in src, f"{marker!r} のハードコードが復活している"


def test_no_beat_truncation_to_12():
    """`beats_data[:12]` による切り詰めが復活していないこと。"""
    src = Path("src/backend/routers/plots.py").read_text(encoding="utf-8")
    assert "[:12]" not in src, "12件への切り詰めが復活している"


def test_expand_beats_request_has_optional_spine_fields():
    from src.models.api_schemas import ExpandBeatsRequest

    req = ExpandBeatsRequest(title="t", genre="g", target_chapters=3)
    assert req.pattern_key == "" and req.length_key == "" and req.market_key == ""


def test_expand_beats_request_legacy_construction_still_works():
    """既存呼び出し（キーなし）が壊れていないこと。"""
    from src.models.api_schemas import ExpandBeatsRequest

    req = ExpandBeatsRequest(title="t", genre="g", target_chapters=20,
                             cheat_scale=4, growth_curve="最初からカンスト(無双)",
                             system_assist=70, cost_severity=2)
    assert req.target_chapters == 20
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring\test_plots_beat_expansion.py -v
```

**完了判定**: 4テスト緑。

---

### B5. `commercial_planning` の 4 幕矛盾を解消
- **対象ファイル**: `src/backend/routers/commercial_planning.py`
- **依存**: A3
- **P分類**: P1（1ファイル）
- **推定所要**: 1時間

**背景**

`src/backend/routers/commercial_planning.py:112` は
```python
phases = ["起 (Setup)", "承 (Confrontation)", "転 (Climax)", "結 (Resolution)"]
phase_idx = min(3, (ep - 1) * 4 // request.target_episodes)
```
という**4 幕をハードコード**している。
一方 `src/config/commercial_beat_sheet.py:5-59` の `COMMERCIAL_40EP_BEATS` は**7 phase**。
**同じ「商業構成」に 2 つの答えが存在する**という矛盾。

**作業内容**

1. `resolve_spine(<pattern>, "web_volume", "web", target_episodes)` を呼ぶ。
   `<pattern>` は `BeatSheetGenerateRequest`（`:37-42`）に `pattern_key: str = "exile_rise"` として追加（既定あり）。
2. `phase` を `spine.at(ep).label` から取る。4 幕配列を**削除**。
3. `tension_target` を `spine.at(ep).tension` から取る。`COMMERCIAL_40EP_BEATS` を**参考値**として
   `spine_quality="off"` のときだけ使うフォールバックに残す。
4. **`COMMERCIAL_40EP_BEATS` の削除はしない**（`src/agents/planning.py:267` と
   `prompts/templates/narrative/beat_sheet_generation.j2` が使っている）。
   **消すと既存経路が壊れる。** 段階的に縮めるなら別ステップ。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_commercial_planning_spine.py`（新規）

```python
"""商業構成が Spine 単一ソースに統一されたことの確認。"""
from pathlib import Path

import pytest


def test_four_act_hardcode_removed():
    """4幕ハードコードが復活していないこと。"""
    src = Path("src/backend/routers/commercial_planning.py").read_text(encoding="utf-8")
    assert '["起 (Setup)"' not in src, "4幕のハードコードが復活している"
    assert "min(3, (ep - 1) * 4" not in src, "4幕のインデックス計算が復活している"


def test_commercial_beat_sheet_still_present():
    """**既存利用者を壊していないことの確認**。消してはいけない。"""
    from src.config.commercial_beat_sheet import COMMERCIAL_40EP_BEATS

    assert len(COMMERCIAL_40EP_BEATS) == 7


def test_agent_planning_still_imports():
    """`src/agents/planning.py:267` の参照が生きていること。"""
    import src.agents.planning as planning

    assert hasattr(planning, "generate_commercial_beat_sheet")


def test_beat_sheet_request_has_pattern_key():
    from src.backend.routers.commercial_planning import BeatSheetGenerateRequest

    req = BeatSheetGenerateRequest(title="t")
    assert req.pattern_key == "exile_rise", "既定パターンが無いと既存呼び出しが壊れる"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring\test_commercial_planning_spine.py -v
C:\Python314\python.exe -m pytest tests\unit -k "commercial" -q
```

**完了判定**: 4テスト緑 + 既存 commercial テストに回帰なし。

---

### B6. `structure_type` の結線と `current_volume` の増加
- **対象ファイル**: `src/application/dtos/plot_dto.py`、`src/services/pipeline_base.py`
- **依存**: A3
- **P分類**: P1（2ファイル、どちらも小改修）
- **推定所要**: 1時間

**背景**

- `src/application/dtos/plot_dto.py:24` の `structure_type: str = Field(default="three_act")` は
  **どこからも populate されない死んだフィールド**。
- `src/services/pipeline_base.py:72` の `current_volume: int = 1` は**増加箇所が無い**。
  「1巻」を扱う系譜が存在しない。

**作業内容**

1. `GeneratePlotDTO` に `pattern_key: str = ""` / `length_key: str = ""` / `market_key: str = ""` を追加。
   `structure_type` は**削除しない**（`GeneratePlotDTO.structure_type` のコメントにある4値は `structure_validator` が使う）。
2. `WorkflowContext` に `volume_index: int = 1` を**追加**し、`current_volume` は**残す**（後方互換）。
   1 巻完走時に `volume_index += 1` する箇所を、`src/services/auto_workflow_pipeline.py` に 1 つだけ入れる。
   > **注意**: `src/services/auto_workflow_pipeline.py` は §0.2 の表に無い。
   > **B6 の担当に `src/services/auto_workflow_pipeline.py` を追加すること**（B 内部のファイル、B のみ所有）。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_dto_and_volume.py`（新規）

```python
"""DTO の結線と volume カウンタの確認。"""
import pytest


def test_generate_plot_dto_accepts_spine_keys():
    from src.application.dtos.plot_dto import GeneratePlotDTO

    dto = GeneratePlotDTO(
        novel_id="n", branch_id="b",
        pattern_key="exile_rise", length_key="web_volume", market_key="web",
    )
    assert dto.pattern_key == "exile_rise"


def test_generate_plot_dto_legacy_construction():
    """既存呼び出し（キーなし）が壊れていないこと。"""
    from src.application.dtos.plot_dto import GeneratePlotDTO

    dto = GeneratePlotDTO(novel_id="n", branch_id="b")
    assert dto.structure_type == "three_act"
    assert dto.pattern_key == ""


def test_workflow_context_has_volume_index():
    from src.services.pipeline_base import WorkflowContext

    ctx = WorkflowContext(genre="g")
    assert ctx.volume_index == 1
    assert ctx.current_volume == 1, "既存フィールドは後方互換のため残す"


def test_volume_index_increments():
    from src.services.pipeline_base import WorkflowContext

    ctx = WorkflowContext(genre="g")
    ctx.volume_index += 1
    assert ctx.volume_index == 2
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring\test_dto_and_volume.py -v
```

**完了判定**: 4テスト緑。

---

### B7. `reverse_plot_workflow` を Spine ラッパーに縮小
- **対象ファイル**: `src/backend/workflows/reverse_plot_workflow.py`
- **依存**: A3
- **P分類**: P1（1ファイル）
- **推定所要**: 1.5時間

**背景**

`reverse_plot_workflow.py:97-223` は **LLM を一切呼ばない決定論的**に arc と tension を組み立てる。
`:182-190` の `_calc_tension` は純算術であり、**`Spine` にそのまま移せる**。
また `:225-228` の `_ep_summary` は `sacrifice` と `openingHook` を無視し、
全エピソードに同じ文言（`f"[{phase}] {conflict}の局面で、主人公が選択を迫られる"`）を出力する。

**作業内容**

1. `_calc_tension`（`:182-190`）を**削除**し、`spine.at(ep).tension` を使う。
2. `_design_arcs`（`:128-149`）の `eps_per_arc = target // num_arcs` を、
   `LENGTH_PROFILES[length].arc_count` に基づく区割りに置き換える。
3. `_ep_summary`（`:225-228`）で **`sacrifice` と `openingHook` を実際に使う**。
   - `openingHook` → 第1話の `BeatInstance.duty` に反映
   - `sacrifice` → 最終話の `burned_cost_or_loot` に反映（現状は `:175` のみ）
4. `CONFLICT_TO_ARC_TEMPLATE`（`:31-40`）は**残す**（逆プロット質問は本計画の対象外）。
5. `frontend/src/data/reversePlotSteps.ts:54-73` との**逐語重複は本ステップでは消さない**（FE 側 B12 で対応）。

**回帰テスト（先に作る）**: `tests/unit/story_spine_wiring/test_reverse_plot_uses_spine.py`（新規）

```python
"""逆プロット系が Spine を土台にしていることの確認。"""
import pytest


@pytest.mark.asyncio
async def test_reverse_plot_uses_spine_tension():
    """テンション値が `Spine` の値と一致すること（`Spine` による tension 計算の二重実装の排除）。"""
    from config.story_spine import resolve_spine
    from src.backend.workflows.reverse_plot_workflow import (
        ReversePlotGenerationWorkflow,
    )

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    assert len(spine.beats) > 0


def test_calc_tension_removed():
    """`Spine` と二重実装された tension 計算が消えていること。"""
    from pathlib import Path

    src = Path("src/backend/workflows/reverse_plot_workflow.py").read_text(encoding="utf-8")
    assert "def _calc_tension" not in src, "_calc_tension が復活している"


def test_sacrifice_answer_is_used():
    """`sacrifice` 回答が最終話に反映されていること（旧実装は無視していた）。"""
    from pathlib import Path

    src = Path("src/backend/workflows/reverse_plot_workflow.py").read_text(encoding="utf-8")
    assert src.count("sacrifice") >= 2, "sacrifice が1箇所しか参照されていない（無視されている疑い）"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\story_spine_wiring\test_reverse_plot_uses_spine.py -v
C:\Python314\python.exe -m pytest tests\unit\workflows -q
```

**完了判定**: 3テスト緑 + 既存 workflow テストに回帰なし。

---

### B8. プロンプト注入（`spine_quality` による段階適用）
- **対象ファイル**: `src/services/llm/prompts.py`、`prompts/templates/narrative/plot_stage1.j2`
- **依存**: A3
- **P分類**: P1（2ファイル）
- **推定所要**: 1.5時間

**背景**

`src/services/llm/prompts.py:56-78` の `NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE` は
`{genre}` `{char_name}` `{char_personality}` `{char_ability}` `{style_bias_section}` `{graph_context}` `{vector_context}` `{history_context}` `{current_chapter}` の **9 変数**。
**構造・パターン・アーキタイプ は一切含まれない。**

**既存生成結果を壊してはならない**ため、`spine_quality` の既定は **`off`**。

**作業内容**

1. `NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE` は**変更しない**。
   代わりに、既存文字列の**直後に** `{spine_section}` を1行追加する（空文字なら出力が完全一致する）。
2. 新規関数 `build_spine_section(spine, quality, ep_num) -> str` を追加する。
   - `off` → `""`
   - `soft` → `"【構造の参考】" + duty 1行`
   - `hard` → `"【この話で必ず果たすこと】" + duty + tension目標 + artifact`
3. `easy_mode.py:156-157` で `target_eps` は `_` に捨てられている。`spine_quality` とともに
   **`target_episodes` も実際にプロンプトへ渡す**ようにする。
   > `src/backend/routers/easy_mode.py` は **B1 所有**。B1 完了後に B8 で**同じ所有者のもとで**編集してよい。
4. `plot_stage1.j2` にも同じ `{spine_section}` 差し込みを行う（Jinja の `{% if %}` で空文字を弾く）。
5. **Must**: `spine_quality` は `os.getenv("SPINE_QUALITY", "off")` で読む（PLAN_T6 原則 P5）。

**回帰テスト（先にやる）**: `tests/contract/test_spine_prompt_injection.py`（新規）

```python
"""**`spine_quality=off` で既存プロンプトが完全に不変**であること（最重要契約）。"""
import pytest

from src.services.llm.prompts import (
    NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE,
    build_spine_section,
)

KWARGS = dict(
    genre="ハイファンタジー (R15)",
    char_name="山田太郎",
    char_personality="冷静",
    char_ability="万能鑑定",
    style_bias_section="【作家性DNA】短文主体",
    graph_context="(なし)",
    vector_context="(なし)",
    history_context="(なし)",
    current_chapter="第1話の本文",
)


def test_off_produces_legacy_prompt_exactly():
    """**バイト単位で同一**であること。これが変わると全書籍の再生成結果が変わる。"""
    prompt = NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(**KWARGS, spine_section="")
    assert prompt == NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE.format(**KWARGS)


def test_build_spine_section_off_returns_empty():
    assert build_spine_section(None, "off", 1) == ""


def test_soft_includes_duty():
    from config.story_spine import resolve_spine

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    section = build_spine_section(spine, "soft", ep_num=1)
    assert section, "soft で duty が入っていない"
    assert spine.at(1).duty[:8] in section


def test_hard_includes_tension_and_artifact():
    from config.story_spine import resolve_spine

    spine = resolve_spine("exile_rise", "web_volume", "web", 40)
    section = build_spine_section(spine, "hard", ep_num=33)
    assert str(spine.at(33).tension) in section or "テンション" in section


def test_unknown_quality_falls_back_to_off():
    """未知の値が `hard` になってしまわないこと（安全側）。"""
    assert build_spine_section(None, "bogus", 1) == ""


def test_default_env_is_off(monkeypatch):
    monkeypatch.delenv("SPINE_QUALITY", raising=False)
    from src.config import quality_flags  # 存在しなければこのテストは削除

    assert quality_flags.spine_quality() == "off"
```

> 最後のテストは `quality_flags` が存在しない場合に落ちる。
> **B8 で `spine_quality` をどこかに定義する.tasks場合のみ残す**。
> 定義しない場合は**この1本だけ削除**する（フォームだけ通すテストを作らない）。

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\contract\test_spine_prompt_injection.py -v
C:\Python314\python.exe -m pytest tests\contract -q
```

**完了判定**: 6テスト緑（`quality_flags` 未定義なら 5テスト緑）。

---

### B9. FE: 文字数プリセットを API 参照に置換
- **対象ファイル**: `frontend/src/constants/manuscript.ts`、`frontend/src/types/manuscript.ts`
- **依存**: B3
- **P分類**: P2（機械的置換のみ）
- **推定所要**: 1時間
- **並列可能**: A2 の完了を待つ必要なし（`LENGTHS` を使うが、A1 で loader が用意されていれば足りる）

**背景**

`frontend/src/constants/manuscript.ts:3-48` の 6 プリセット（1.2万/2万/4万/10万字）は
**エディタ内字数カウンタ専用**で、backend に一切送られない。
A2 が同じ値を `config/story_spine/lengths.yaml` に移したため、**二重管理になっている**。

**作業内容**

1. `MANUSCRIPT_PRESETS` を**ハードコード配列から API 取得**に変更する。
   - `custom`（カスタム設定…）だけは**ローカルに保持**（サーバー設定ではないため）。
2. `useLengthProfiles()` フックを新規作成し、`GET /api/config/planning_options` の `lengths` を取得する。
   **取得失敗時は既存のローカルフォールバックを使う**（API 未起動でもエディタが壊れないこと）。
3. `ManuscriptTargetPreset` 型に `key: string`（`short` / `novella` / …）を追加する。
4. `frontend/src/types/manuscript.ts` の型定義を API レスポンスに追従させる。

**回帰テスト（先に作る）**: `frontend/src/constants/manuscript.test.ts`（新規）

```ts
import { describe, expect, it } from 'vitest';
import { toManuscriptPresets } from './manuscript';

describe('length profile → manuscript preset', () => {
  it('数値を落とさない（既存 6プリセットと同値）', () => {
    const presets = toManuscriptPresets([
      { key: 'short', label: '小説現代・新人賞', target_chars: 12000, target_pages: 30 },
      { key: 'web_volume', label: 'カクヨム・コンテスト', target_chars: 100000, target_pages: 250 },
    ]);
    expect(presets[0]?.targetChars).toBe(12000);
    expect(presets[1]?.targetChars).toBe(100000);
  });

  it('custom は常に先頭ではなく末尾に1枚だけ入る', () => {
    const presets = toManuscriptPresets([{ key: 'short', target_chars: 12000, target_pages: 30 }]);
    expect(presets.filter((p) => p.id === 'custom')).toHaveLength(1);
  });

  it('length key が保持される（template 選択に渡すため）', () => {
    const presets = toManuscriptPresets([{ key: 'web_volume', target_chars: 100000, target_pages: 250 }]);
    expect(presets[0]?.lengthKey).toBe('web_volume');
  });
});
```

**検証コマンド**
```powershell
cd frontend
npm run typecheck
npx vitest run src/constants/manuscript.test.ts
```

**完了判定**: typecheck が 0 エラー。vitest 3テスト緑。

---

### B10. FE: ジャンル語彙の統合とカードグリッド
- **対象ファイル**: `frontend/src/constants/genres.ts`、`frontend/src/components/generate/SimpleModePanel.tsx`
- **依存**: B3, **A2**（cards.yaml の中身の読取）
- **P分類**: P1（2ファイル）
- **推定所要**: 2.5時間

**背景**

`SimpleModePanel.tsx:91-103` の select は `fan` / `sf` / `romance` / `mystery` / `horror` / `other` を
**ハードコード**しており、backend の `resolve_genre_to_preset` は日本語部分一致なので**必ず `None` に落ちる**。
`constants/genres.ts:10-18` の `GENRE_OPTIONS` は import されているが**使われていない**。

**作業内容**

1. `genres.ts` の `GENRE_OPTIONS` を API 取得に変更する（`/api/config/planning_options` の `genres`）。
   `GENRE_BADGE_CONFIG` は**残す**（既存の表示用）。
2. `SimpleModePanel.tsx` の select を API 取得値に変更し、**`value` をレジストリのキー**（`HighFantasy` 等）に変える。
3. **カードグリッド（Tier 1）**をフォームの先頭に追加する。
   24 枚をグリッド表示し、選択すると以下を自動入力する:
   - ジャンル（`pattern` → `genre_coord` → `GENRE_REGISTRY`）
   - 話数（`length.eps_range` の中央）
   - 1 話字数（`length.chars_per_ep` の中央）
   - `style_key`（カードの値）
4. 「→ カスタムで組み立てる」で Tier 2（微調整）へ降りる。
5. `useNovelGeneration.startGeneration()`（`frontend/src/hooks/useNovelGeneration.ts:37-44`）の
   payload に `pattern_key` / `length_key` / `market_key` / `spine_quality` を追加する。
   > `frontend/src/hooks/useNovelGeneration.ts` は §0.2 に無い。**B10 の担当に追加すること**（B のみ所有）。

**回帰テスト（先に作る）**: `frontend/src/components/generate/SimpleModePanel.test.tsx`（新規）

```tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SimpleModePanel } from './SimpleModePanel';

const mockCards = [
  { card_id: 'tpl_exile_web', label: '⚔️ 追放ざまぁ', pattern: 'exile_rise',
    length: 'web_volume', market: 'web', style_key: 'style_web_standard' },
  { card_id: 'tpl_mystery_short', label: '🔍 事件の謎', pattern: 'detective_mystery',
    length: 'short', market: 'general', style_key: 'style_serious_fantasy' },
];

describe('SimpleModePanel テンプレートカード', () => {
  it('カードが選択式として表示される', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({ cards: mockCards, genres: [], lengths: [], markets: [] }),
    }));
    render(<SimpleModePanel />);
    await waitFor(() => expect(screen.getByText('⚔️ 追放ざまぁ')).toBeTruthy());
  });

  it('カードを選ぶと話数が自動入力される', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({ cards: mockCards, genres: [], lengths: [{ key: 'web_volume', eps_range: [40, 40] }], markets: [] }),
    }));
    render(<SimpleModePanel />);
    await waitFor(() => screen.getByText('⚔️ 追放ざまぁ').click());
    await waitFor(() => expect(screen.getByDisplayValue('40')).toBeTruthy());
  });

  it('カードのハードコード select（fan/sf/...）が消えている', () => {
    const src = require('fs').readFileSync(__filename, 'utf-8');
    expect(src).not.toContain('value="fan"');
  });
});
```

> 3本目は **FE コンポーネントに select が残っていないことの構造テスト**。
> FE の DOM テストが不安定な場合、この1本だけでも残す（意味がある）。

**検証コマンド**
```powershell
cd frontend
npm run typecheck
npx vitest run src/components/generate/SimpleModePanel.test.tsx
```

**完了判定**: typecheck 0 エラー。vitest 緑。

---

### B11. FE: Wizard Step1 の一致
- **対象ファイル**: `frontend/src/components/wizard/Step1PlotInput.tsx`
- **依存**: B10
- **P分類**: P1（1ファイル）
- **推定所要**: 1.5時間

**背景**

`Step1PlotInput.tsx:146-150` の `growth_curve` select の4値
（`最初からカンスト(無双)` / `段階的覚醒` / `どん底下克上` / `頭脳戦特化`）は
**`STORY_ARCHETYPES` の値と一致しない**
（実値は `最初からカンスト(無双)` / `徐々に成長(王道)` / `条件付き最強(ピーキー)`）。

`src/models/api_schemas.py:317` の `growth_curve` は自由文字列なので**サーバ側で弾けない**が、
**プリセットの選択が効かない**（該当なし → 既定値に落ちる）。

**作業内容**

1. `growth_curve` の選択肢を `GET /api/config/planning_options` の `story_archetypes` から
   **実際に存在する値だけ**を列挙するようにする。
2. `genre` の select（`:132-136` の `fantasy` / `modern_fantasy` / `romance` / `scifi`）を
   B10 と同じレジストリ取得に変更する。
3. カード選択 UI（B10 と共通コンポーネント化してよい）を配置する。
4. `title` / `synopsis` の自由入力は**残す**（テンプレは初期値であり、上書きを尊重する）。

**回帰テスト（先に作る）**: `frontend/src/components/wizard/Step1PlotInput.test.tsx`（新規）

```tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Step1PlotInput } from './Step1PlotInput';

describe('Step1PlotInput GenreRegistry 統合', () => {
  it('growth_curve の選択肢が実在の値だけになる', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({
        story_archetypes: ['王道ざまぁ（爽快感最大）'],
        growth_curves: ['最初からカンスト(無双)', '徐々に成長(王道)', '条件付き最強(ピーキー)'],
        cards: [], genres: [], lengths: [], markets: [],
      }),
    }));
    render(<Step1PlotInput onNext={() => {}} />);
    await waitFor(() => expect(screen.getByText(/徐々に成長\(王道\)/)).toBeTruthy());
    expect(screen.queryByText('段階的覚醒')).toBeNull();
  });
});
```

**検証コマンド**
```powershell
cd frontend
npm run typecheck
npx vitest run src/components/wizard/Step1PlotInput.test.tsx
```

**完了判定**: typecheck 0 エラー。vitest 緑。

---

### B12. FE: 構成充足度の表示
- **対象ファイル**: `frontend/src/components/planning/BeatSheetViewer.tsx`
- **依存**: A4, B3
- **P分類**: P1（1ファイル）
- **推定所要**: 1.5時間

**背景**

`frontend/src/components/planning/BeatSheetViewer.tsx` は**12 行の placeholder**で、タイトルだけ描画する。
本計画の中核的なユーザー価値（**「この作品は『追放ざまぁ Web1巻』テンプレの充足度 87%」**）の受け皿。

**作業内容**

1. `GET /api/structure/books/{book_id}/validate?pattern=...` を呼ぶ表示を実装する。
   A4 で `pattern_key` を受け取れるようにした `validate` の結果を使う。
2. `missing_beats` / `climax` / `pacing` / `is_healthy` を表示する。
3. `ForeshadowingScopeBadge.tsx` が同じディレクトリにある。**壊さない**（触らない）。

**回帰テスト（先に作る）**: `frontend/src/components/planning/BeatSheetViewer.test.tsx`（新規）

```tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BeatSheetViewer } from './BeatSheetViewer';

describe('BeatSheetViewer 構成充足度', () => {
  it('充足度と欠落ビートが提示される', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({
        pattern_key: 'exile_rise',
        missing_beats: ['midpoint_reversal'],
        climax: { ok: true },
        pacing: { skew: 0.1, ok: true },
        is_healthy: false,
      }),
    }));
    render(<BeatSheetViewer bookId={1} patternKey="exile_rise" />);
    await waitFor(() => expect(screen.getByText(/midpoint_reversal/)).toBeTruthy());
  });
});
```

**検証コマンド**
```powershell
cd frontend
npm run typecheck
npx vitest run src/components/planning/BeatSheetViewer.test.tsx
```

**完了判定**: typecheck 0 エラー。vitest 緑。

---

### B13. 効果計測スクリプト
- **対象ファイル**: `scripts/measure_spine_alignment.py`（新規）
- **依存**: A4
- **P分類**: P1（1ファイル）
- **推定所要**: 1.5時間

**背景**

親提案 §8 の K1-K3 を**実測**するためのスクリプト。
**ベースラインが無ければ効果は証明できない**（PLAN_T6 の教訓「数値を推測で埋めない」）。

**作業内容**

1. 既存書籍（`Book` × `Plot`）を読み、`structure_validator.validate` を **pattern 付きで**実行する。
2. K1（構成充足度）・K2（中点反転の相対位置の散らばり）・K3（Climax 位置の散ららり）を算出する。
3. `--json` フラグで機械可読出力（I3 の転記用）。

**回帰テスト（先に作る）**: `tests/unit/scripts/test_measure_spine_alignment.py`（新規）

```python
"""計測スクリプトが機械可読な JSON を返すことの確認。"""
import json
import subprocess
import sys
from pathlib import Path


def test_cli_emits_valid_json():
    result = subprocess.run(
        [sys.executable, "scripts/measure_spine_alignment.py", "--json"],
        capture_output=True, text=True, cwd=Path.cwd(),
    )
    assert result.returncode == 0, f"スクリプトが失敗: {result.stderr}"
    payload = json.loads(result.stdout)
    for key in ("k1_alignment", "k2_midpoint", "k3_climax", "books"):
        assert key in payload, f"キー {key!r} が無い"


def test_no_hardcoded_numbers():
    """**推測値をハードコードしていないこと**（PLAN_T6 教訓）。"""
    src = Path("scripts/measure_spine_alignment.py").read_text(encoding="utf-8")
    assert "0.87" not in src, "充足度 0.87 のような具体値が埋め込まれている"
    assert "0.92" not in src


def test_output_is_reproducible():
    """2 回走らせて出力が一致すること（実測であることの間接証明）。"""
    outs = [
        subprocess.run(
            [sys.executable, "scripts/measure_spine_alignment.py", "--json"],
            capture_output=True, text=True, cwd=Path.cwd(),
        ).stdout
        for _ in range(2)
    ]
    assert outs[0] == outs[1], "2回の出力が違う（実測値が安定していない）"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\unit\scripts\test_measure_spine_alignment.py -v
C:\Python314\python.exe scripts\measure_spine_alignment.py --json
```

**完了判定**: 3テスト緑。CLI が JSON を出力する。

---

### B14. 効果測定表の転記
- **対象ファイル**: `docs/STATUS.md`
- **依存**: B13
- **P分類**: P1（転記作業のみ）
- **推定所要**: 30分

**作業内容**

1. `docs/STATUS.md` に「STORY_SPINE 導入の効果測定」節を新設する（現状は 5 節構成なので 6 節目）。
2. 親提案 §8 の K1-K8 の表を**そのまま転記**し、実測欄は B13 の出力値を入れる。
3. **推測値を書いてはならない**。不明なセルは `未計測` と**正直に書く**。
4. 出典（どのスクリプト/テストの出力か）を**各行に明記**する。

**回帰テスト（先に作る）**: `tests/regression/test_status_spine_measurement.py`（新規）

```python
"""docs/STATUS.md の効果測定が推測値を含まないことの回帰テスト。"""
import re
from pathlib import Path


def test_status_has_spine_measurement_section():
    text = Path("docs/STATUS.md").read_text(encoding="utf-8")
    assert "STORY_SPINE" in text
    for metric in ("K1", "K2", "K3", "K4"):
        assert metric in text, f"{metric} の行が無い"


def test_no_placeholder_remains():
    """`(B13)` のような未転記プレースホルダが残っていないこと。"""
    text = Path("docs/STATUS.md").read_text(encoding="utf-8")
    section = text.split("STORY_SPINE")[-1]
    assert not re.search(r"\(B1\d\)", section), "未転記のプレースホルダが残っている"


def test_unmeasured_cells_are_honest():
    """未計測セルは `未計測` と書いてあること（空欄や '-' を残さない）。"""
    text = Path("docs/STATUS.md").read_text(encoding="utf-8")
    section = text.split("STORY_SPINE")[-1]
    for line in section.splitlines():
        if line.startswith("|") and "未計測" not in line and "K" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            assert all(c for c in cells), f"空欄セルがある: {line}"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\regression\test_status_spine_measurement.py -v
```

**完了判定**: 3テスト緑。

---

## 4. 統合（3 ステップ）

> **実行者**: 統合担当（main）。サブエージェント A・B は実行しない。

---

### I1. E2E テストの作成
- **対象ファイル**: `tests/e2e/test_spine_end_to_end.py`（新規）
- **依存**: G2（TRACK-A 完了）かつ G3（TRACK-B 完了）
- **推定所要**: 1.5時間

**背景**

A と B の**それぞれの単体テストは緑でも、接続点で壊れている**可能性がある
（親提案 §4.4 の「生成後検証」が未証明）。

**作業内容**

```python
"""**カード1枚 → Spine → プロンプト注入**の通し確認。"""
import pytest


def test_card_to_spine_to_prompt():
    """1枚のカードから最終プロンプトまでが繋がること。"""
    from config.story_spine import CARDS, resolve_spine
    from src.services.llm.prompts import NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE, build_spine_section

    card = CARDS["tpl_exile_web"]
    spine = resolve_spine(card["pattern"], card["length"], card["market"], 40)

    assert len(spine.beats) >= 18, "Web1巻は最低18ビートのはず"
    assert spine.at(1) is not None
    assert spine.at(40) is not None

    section = build_spine_section(spine, "hard", ep_num=1)
    assert section


def test_every_card_resolves():
    """24枚すべてが解決できること。"""
    from config.story_spine import CARDS, resolve_spine

    for ck, card in CARDS.items():
        spine = resolve_spine(card["pattern"], card["length"], card["market"])
        assert spine.beats, f"{ck} が解決しない"


def test_long_serial_100ep_passes_validation():
    """**100話構成が検証器を通ること**（40話上限撤去の実証）。"""
    from config.story_spine import resolve_spine
    from src.services.structure_validator import validate

    spine = resolve_spine("exile_rise", "long_serial", "web", 100)
    chapters = [{"chapter_number": b.ep_start, "tension": int(b.tension * 10)} for b in spine.beats]
    result = validate(chapters, pattern_key="exile_rise")
    assert result["pattern_key"] == "exile_rise"


def test_short_form_e2e():
    """1話短編の通し確認。"""
    from config.story_spine import resolve_spine

    spine = resolve_spine("exile_rise", "short", "general", 1)
    assert spine.keys == ["inciting", "midpoint_reversal", "climax"] or \
           {"inciting", "midpoint_reversal", "climax"} <= set(spine.keys)
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests\e2e\test_spine_end_to_end.py -v -s
```

**完了判定**: 4テスト緑。

---

### I2. ベースライン比較（新規回帰 0 件）
- **対象ファイル**: なし（実行のみ）
- **依存**: I1
- **推定所要**: 30分

**作業内容**

1. **作業開始前に、全変更をコミットする**（PLAN_T6 Step 16 と同じ教訓）。
   未コミットだと baseline = HEAD に変更が含まれず、**新規テストが全部「回帰」扱いになる**。
2. ```powershell
   pwsh -File scripts\compare_test_baseline.ps1
   ```
3. `新規回帰: 0 件` を確認し、`exit 0` で終了すること。
4. 1件でも出たら、**握り潰さない**。原因を特定して A または B に戻す。

**完了判定**: スクリプトが `新規回帰: 0 件` を出力し、`exit 0`。

---

### I3. 非推奨コードの最終削除判断
- **対象ファイル**: `config/data/archetypes.json`（或其它）
- **依存**: I2
- **推定所要**: 45分

**作業内容**

1. `config/data/archetypes.json` の `PLOT_STRUCTURES` が `patterns.yaml` へ完全転記されていることを確認する
   （**キー数・duty 数の一致**を見る）。
2. 転記が完了していれば、`PLOT_STRUCTURES` ブロックのみ**削除**する。
   ファイル内の `ARCHETYPE_ENGINES` 等は**残る**（別計画の対象）。
3. 削除後 `pytest tests/unit tests/regression -q` が緑であることを確認する。
4. 削除しない判断をした場合は、その理由を `docs/STATUS.md` に**1行で**書く。

**完了判定**: 削除テストが緑、または「不削除」の理由が `docs/STATUS.md` にある。

---

## 5. リグレッション防止テスト一覧

### 5.1 新規テストのマトリクス（計 12 ファイル / 約 70 ケース）

| # | ファイル | 層 | 防止する回帰 | 担当 |
|:---|:---|:---:|:---|:---:|
| T1 | `tests/unit/story_spine/test_beat_vocabulary.py` | 契約 | span が絶対値になる／duty が長文になる | A1 |
| T2 | `tests/unit/story_spine/test_datasets.py` | 契約 | 既存31キーの欠落／beat 語彙漏れ／カード参照切れ | A2 |
| T3 | `tests/unit/story_spine/test_resolver_compression.py` | 不変条件 | **1話短編で中点反転・クライマックスが消える** | A3 |
| T4 | `tests/unit/story_spine/test_resolver_combinatorial.py` | 網羅 | 特定の組合せで `resolve_spine` が例外を投げる | A3 |
| T5 | `tests/unit/story_spine/test_resolver_relative.py` | **既存バグ** | **PacingGraph が話数に依存する** | A3 |
| T6 | `tests/unit/story_spine/test_resolver_no_llm.py` | 制約 | テンプレート展開が LLM 課金になる | A3 |
| T7 | `tests/unit/story_spine/test_validator_pattern.py` | 後方互換 | 既存 3 構造が壊れる／1話で ZeroDivisionError | A4 |
| T8 | `tests/unit/story_spine/test_removed_definitions.py` | 陳腐化 | 削除した `PLOT_STRUCTURES` / `le=40` の復活 | A6 |
| T9 | `tests/regression/test_relative_episode_structure.py` | **既存バグ** | **絶対話数の回帰** | A5 |
| T10 | `tests/regression/test_genre_resolution_unified.py` | **既存バグ** | **`"fan"` が `None` を返す** | B1 |
| T11 | `tests/unit/story_spine_wiring/test_genre_tables_merged.py` | 二重管理 | 3表の二重定義の復活 | B2 |
| T12 | `tests/contract/test_planning_options_endpoint.py` | **既存バグ** | **`/api/config/planning_options` が 500** | B3 |
| T13 | `tests/unit/story_spine_wiring/test_plots_beat_expansion.py` | 陳腐化 | Save the Cat 12ビートの復活 | B4 |
| T14 | `tests/unit/story_spine_wiring/test_commercial_planning_spine.py` | 矛盾 | 4幕ハードコードの復活 | B5 |
| T15 | `tests/unit/story_spine_wiring/test_dto_and_volume.py` | 結線 | `structure_type` が再び未設定 | B6 |
| T16 | `tests/unit/story_spine_wiring/test_reverse_plot_uses_spine.py` | 二重実装 | `_calc_tension` の二重実装 | B7 |
| T17 | `tests/contract/test_spine_prompt_injection.py` | **最重要契約** | **`spine_quality=off` で既存プロンプトが変わる** | B8 |
| T18 | `frontend/src/constants/manuscript.test.ts` | FE | 文字数の二重管理 | B9 |
| T19 | `frontend/src/components/generate/SimpleModePanel.test.tsx` | FE | カード UI と select ハードコード | B10 |
| T20 | `frontend/src/components/wizard/Step1PlotInput.test.tsx` | FE | growth_curve の不一致 | B11 |
| T21 | `frontend/src/components/planning/BeatSheetViewer.test.tsx` | FE | 充足度表示の消失 | B12 |
| T22 | `tests/unit/scripts/test_measure_spine_alignment.py` | 計測 | 計測値に推測が混ざる | B13 |
| T23 | `tests/regression/test_status_spine_measurement.py` | docs | 効果測定表に未転記が残る | B14 |
| T24 | `tests/e2e/test_spine_end_to_end.py` | 統合 | A と B の接続点の破綻 | I1 |

### 5.2 特に重要な回帰 5 本

| 順位 | テスト | 理由 |
|:---:|:---|:---|
| 1 | **T17** `test_off_produces_legacy_prompt_exactly` | 1本でも落ちれば**全既存書籍の再生成結果が変わる**。本計画最大のリスク |
| 2 | **T3** 短編 3不変条件 | 元提案で**最も大きかった穴**（1話で構造が消える）の防止 |
| 3 | **T10** `"fan"` 解決 | 実害が既に発生しているバグ。放置すると「EasyMode が壊れている」状態が固定される |
| 4 | **T12** `planning_options` 200 | 常に 500。UI へのテンプレート配布の唯一の道が塞がれている |
| 5 | **T9** 絶対話数 | 話数を変えると構造が壊れる。**本計画の目的そのものがこれ** |

### 5.3 既存テストへの影響（破壊しないことの確認）

| 既存スイート | 影響 | 確認方法 |
|:---|:---|:---|
| `tests/unit/test_structure_validator.py`（4テスト） | A4 で**壊してはいけない** | A4 完了判定に含める |
| `tests/unit/agents/` / `tests/unit/workflows/` | B7 で `reverse_plot_workflow` を変更する | B7 で `tests/unit/workflows -q` を回す |
| `tests/e2e/test_v53_long_form_wiring_e2e.py` | A5/A6 で `engine_narrative` を触る | I2 のベースライン比較で検出 |
| `tests/contract/` 一式 | B3/B8 でルータと prompt を触る | B8 で `tests/contract -q` を回す |
| FE 全体 | B9-B12 | `cd frontend && npm run typecheck && npx vitest run` |

> **本リポジトリは HEAD 時点で既に約 130 件の失敗/エラーが既存する**
> （`scripts/compare_test_baseline.ps1` の冒頭コメント記載）。
> したがって**「失敗件数そのもの」ではなく「新規回帰か否か」だけ**を見る。
> **既存テストを削除して通そうとしてはいけない**（PLAN_T6 教訓）。

---

## 6. フェーズ別完了条件

| フェーズ | ステップ | 完了条件 | 並列 |
|:---|:---|:---|:---:|
| **P0: 契約凍結** | A1 | Gate G1（`import config.story_spine` 成功） | 単独 |
| **P1: データ** | A2 | `test_datasets.py` 11テスト緑。38P/6L/4M/24C | A と B 並行 |
| **P2: エンジン** | A3 | 網羅 2,736 ケース + 短編不変条件のテストが緑 | A と B 並行 |
| **P3: 検証器** | A4 | 新規4 + 既存4 緑 | A と B 並行 |
| **P4: 既存バグ** | A5, A6 / B1, B2, B3 | T9/T8/T10/T11/T12 緑 | A と B 並行 |
| **P5: 配線** | B4-B8 | T13-T17 緑。**T17 が緑であること** | B のみ |
| **P6: UI** | B9-B12 | FE typecheck 0 エラー。T18-T21 緑 | B のみ（並列可） |
| **P7: 計測** | B13, B14 | T22, T23 緑。STATUS.md に実測値 | B のみ |
| **P8: 統合** | I1, I2, I3 | T24 緑。**新規回帰 0 件** | 統合担当 |

---

## 7. 完了の定義（Definition of Done）

0. `Gate G1`（`from config.story_spine import BEAT_VOCABULARY, PATTERNS, ...`）が成功し、`len(BEAT_VOCABULARY) == 34`。さらに `from services.spine_resolver import resolve_spine` が成功する（A3 完了時点）。
1. `config/story_spine/` に **38 パターン / 6 長さ / 4 媒体 / 24 カード / 34 ビート**が存在し、参照切れ 0 件。
2. `resolve_spine` が **全 2,736 組合せ**で例外を投げない。
3. **1話短編でも「発端・中点反転・クライマックス」が必ず残る**ことがテストで証明される。
4. `resolve_spine` が **LLM を 1 回も呼ばない**ことがテストで証明される。
5. **`spine_quality=off` で生成プロンプトがバイト単位で不変**であることが証明される（最重要）。
6. `resolve_genre_to_preset("fan")` が `None` ではなく preset を返す。
7. `GET /api/config/planning_options` が **HTTP 200** を返す。
8. `PacingGraph` が**話数に依存しない**ことが証明される。`EP_*` 定数が 0 件。
9. `EpisodeBeat` が **300 話まで**受け付ける。
10. `structure_validator` の既存 3 構造が**壊れていない**。
11. 効果測定表に**実測値**が数値として入り、未達項目には原因ステップが書いてある。
12. `scripts/compare_test_baseline.ps1` が**新規回帰 0 件**で `exit 0`。

---

## 8. リスクと対策

| リスク | 影響 | 対策 |
|:---|:---|:---|
| **A と B が同じファイルを編集する** | **Critical** | §0.2 の排他所有表を**各エージェントの起動プロンプトに埋め込む**。衝突したら **小さい側を `git checkout -- <file>` で戻す**（手でマージしない） |
| **`spine_quality=off` で既存プロンプトが変わる**（T17 が落ちる） | **Critical** | B8 の `test_off_produces_legacy_prompt_exactly` を**先に**走红なければ実装に入らない。既存テンプレート文字列を**1文字も変えない** |
| **2 エージェントが同時に pytest を実行し SQLite がロック** | High | §0.4 の環境隔離。**各セッションで `DATABASE_URL` を分ける** |
| **`config/__init__.py` を A と B の両方が触る** | High | A6 で A 所有に固定。B は `from config.story_spine import ...` と**直接サブパッケージ**から import する |
| **38パターンの `duty` が不揃いになる** | High | T1 の `test_duty_is_single_imperative_sentence`（60字以内・命令形）を機械的に強制。**LLM に自動生成させない**（PLAN_T6 原則 P6） |
| **A2 が 3 時間かかる間に B が手が止まる** | Medium | B の **B1, B2, B3, B9** は `patterns.yaml` の**中身**を必要としない。 Gate G1 通過直後に着手できる |
| **A6 で `PLOT_STRUCTURES` を削除したら既存テストが落ちる** | Medium | 削除前に `Select-String` で参照 0 件を確認（P6）。参照があれば**ラッパーを残す** |
| **`PacingGraph` を変えると既存プロンプトが変わる** | Medium | A5 は**相対値↔絶対値**の対応を保つこと。T5 の「同じ相対位置 → 同じ指示」で検証する |
| **FE を触ると型エラーが大量に出る** | Medium | 各 FE ステップの完了判定に `npm run typecheck` を含める |
| **作業開始前にコミットしていない** | Medium | §0.4 の冒頭。**PLAN_T6 Step 16 と同じ失敗を繰り返さない** |
| **効果測定に推測値が混入する** | Medium | T22 の `test_no_hardcoded_numbers` が 0.87 / 0.92 のような具体値を禁止する |

---

## 9. サブエージェント起動プロンプト

### 9.1 サブエージェント A 向け

```
あなたは AutoNovel リポジトリ（E:\ssssad\autonovel）で TRACK-A を実装する。

必読:
  plans/PLAN_F1_STORY_SPINE_IMPLEMENTATION.md の §0（分割原則・排他所有表・依存グラフ）と §2（TRACK-A 全7ステップ）
  plans/PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md（親提案。データ設計の根拠）

担当ブランチ: feature/spine-track-a
作業順序: A1 → A2 → A3 → A4 → A5 → A6

絶対守るルール:
1. 触ってよいのは §0.2 の表で「A」と書かれたファイルだけ。 genre_registry.py は B 所有。
2. 1 ステップ = 1 コミット。失敗したら git reset --hard HEAD~1。
3. 各ステップの「回帰テスト」を先に書いて赤くなることを確認し、その後に実装する。
4. 行番号・関数名は必ず grep で確認してから使う（記憶で編集しない）。
5. 完了判定は検証コマンドが緑か赤かだけで決める。数値を解釈しない。
6. テストを弱めない。既存テストを削除して通さない。

最初の45分: A1 のみに集中する。完了したら「Gate G1 開通」と報告して止まれ。
（B エージェントが Gate G1 を待つ。）
```

### 9.2 サブエージェント B 向け

```
あなたは AutoNovel リポジトリ（E:\ssssad\autonovel）で TRACK-B を実装する。

必読:
  plans/PLAN_F1_STORY_SPINE_IMPLEMENTATION.md の §0（分割原則・排他所有表・依存グラフ）と §3（TRACK-B 全14ステップ）
  plans/PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md（親提案）

担当ブランチ: feature/spine-track-b
作業順序: B1 → B2 → B3 → B9 → B10 → B11 → B12 → B4 → B5 → B6 → B7 → B8 → B13 → B14

絶対守るルール:
1. 触ってよいのは §0.2 の表で「B」と書かれたファイルだけ。config/__init__.py は A 所有（触らない）。
2. 最初のコマンドで Gate G1 を確認する:
   C:\Python314\python.exe -c "from config.story_spine import BEAT_VOCABULARY; print(len(BEAT_VOCABULARY))"
   これが `34` が出ない間は B1-B12 に着手しないこと。
3. 1 ステップ = 1 コミット。失敗したら git reset --hard HEAD~1。
4. B8（プロンプト注入）は既存テンプレート文字列を1文字も変えない。
   test_off_produces_legacy_prompt_exactly が緑にならなければ実装に入らない。
5. 行番号・関数名は必ず grep で確認してから使う。
6. テストを弱めない。既存テストを削除して通さない。

注意:
- B4/B6 で src/models/api_schemas.py と src/services/auto_workflow_pipeline.py を
  触る必要がある。どちらも §0.2 の表に無いので、触る前に自分の担当に追加すること。
  （A は触らない。）
- B8 で easy_mode.py を触る必要があるが、これは B1 所有。同一所有者なので問題ない。
```

---

## 10. 低性能LLM実装者向けの最終注意事項

1. **行番号は記憶で書かない**。必ず `Select-String` / `grep` で**その場で確認**する。
2. **§0.2 の排他所有表を最初に 1 遍だけ全文読む**。ここを飛ばすと 2 人で同じファイルを壊す。
3. **1 ステップ = 1 コミット**。途中で失敗したら `git reset --hard HEAD~1` して次へ。
4. **「完了判定」= 検証コマンドが緑**。それ以外は判断しない。
5. **テストを弱めない**。アサーション数が減っていないか自查する。
6. **推測の数値を書かない**。不明なものは `未計測` と書く。
7. **既存テストを削除して通さない**。壊れた既存テストは**実装を直す**のが正解。
8. **T17（`spine_quality=off` のバイト一致）が本計画最大のリスク**。これが落ちたら全実装を捨ててよい。
9. 迷ったら**元の提案書（PROPOSAL_F1）を読み直す**。本計画は差分であり、全部ではない。
