# AutoNovel W5 是正計画書【伏線自動計画・CAS遷移 → 因果DAG＋関連度注入 12ステップ】

- **文書ID**: PLAN_W5_CAUSAL_FORESIGHT_12STEPS
- **作成日**: 2026-09-29
- **対象バージョン**: AutoNovel v5.3.0 → v6.0.0
- **親計画**: [PLAN_V6_COST_LATENCY_OPTIMIZATION.md](PLAN_V6_COST_LATENCY_OPTIMIZATION.md) §2 / PLAN_T6 R-series
- **ステータス**: 未着手
- **目的**: 伏線回収を「話数の算術」 から「因果依存グラフ（Narrative Causal DAG）＋物語アンカー＋文脈関連度」に移行し、
  1) 終端への未回収伏線の一斉押し寄せ、2) 延期時の連鎖破綻、3) 文脈を無視した強制回収、を同時に防ぐ。

---

## 0. この計画書の位置づけ

現状の伏線システムは **既に構造としては強い**。不等条件（`target > planted`）、
CAS（`src/infrastructure/repositories/foreshadowing_repo.py:207-265`）、
3層アンサンブル判定（`src/services/foreshadowing/ensemble_judge.py`）、
プロンプト背景枠の頭打ち（`prompts/manager.py:812` `MAX_BACKGROUND_FORESHADOWINGS = 20`（`prompts/manager.py:813`））まで
すべて揃っている。**壊れているのは「計画の算出根拠が話数算術であること」と「文脈関連度を無視していること」だけ**。

> **本計画は既存モジュールを差し壊さない。**
> Step 1〜9 は新モジュール追加、Step 10〜11 は既存プロンプト構築への**フラグ付き差し替え**、
> Step 12 は総合回帰のみ。**最後まで実装してもフラグ既定OFFで挙動は完全に現状維持される。**

### 0.1 分割原則（低性能LLM向け）

| 原則 | 内容 |
|---|---|
| **P1 単一ファイル** | 1ステップの主担当ファイルは高々1つ。新ファイルを作る場合も、既存ファイルへの変更は最小限の行数に留める |
| **P2 機械的置換のみ** | 新しいアルゴリズムを設計させない。既存定数表と正規表現で完了する |
| **P3 判定は pytest 緑赤のみ** | 効果の推測を LLM にさせない |
| **P4 テスト先行** | 回帰テストを先に作り、赤いことを確認してから実装する |
| **P5 旗艦パターン** | 新フラグは `src/services/foreshadowing/flags.py` に**集約**する（現状このパッケージは env 読みがゼロ） |
| **P6 猜测禁止** | 行番号・関数名は必ず grep で再確認する |
| **P7 純関数優先** | 新しいロジックは **LLM・DB・ネットワークを使わない純関数**として書く（テストが容易になる） |

### 0.2 実行順序の依存関係

```
Step 1 (flags) ─┬─→ Step 2 (anchors) ─┐
                │                       ├─→ Step 3 (short-term horizon)
                │                       └─→ Step 4 (anchor snap)
                │
                └─→ Step 5 (causal_dag) ──→ Step 6 (toposort) ──→ Step 7 (cascade reschedule)
                                                   │
Step 8 (CAS diagnostics) ──────────────────────────┘
Step 9 (relevance) ──→ Step 10 (prompt wiring) ──→ Step 11 (bundling cap)
                                                        │
                                                        └──→ Step 12 (総合回帰・KPI)
```

- **Step 1 は全ステップの前提**。最初に必ず終わらせる。
- **Step 2 → 3, 4**、**Step 5 → 6 → 7**、**Step 9 → 10 → 11** は直列。
- **Step 8 は Step 7 の後**（CAS の診断を cascade のログに残したいため）。
- **Step 12 は最後**。

---

## 1. 残存欠陥一覧（本計画の対象）

| ID | 深刻度 | 実測事実（根拠） | 担当Step |
|:---|:---|:---|:---|
| W5-01 | Critical | `planner._spread_target`（`planner.py:91-120`）は `planted` 話数と直前ビート区間から **線形補間で回収話を算出**する。感情・因果・場面の一切を見ない | 2, 3, 4 |
| W5-02 | Critical | `prompts/manager._select_background_foreshadowings`（`:812-873`）のソートキーは「期限超過フラグ → 設置話の新しい順」だけ。**似ていない伏線も同じプロンプトに注入**される | 9, 10, 11 |
| W5-03 | Major | 延期は `rescheduler.find_next_suitable_episode`（`rescheduler.py:19-56`）が1本単独で行う。**依存関係（前提になる伏線）が他社に影響する**という概念が無い | 5, 6, 7 |
| W5-04 | Major | `COMMERCIAL_40EP_BEATS` の `range` は `get_beat_for_episode`（`commercial_beat_sheet.py:61-68`）では**両端含む**、`planner._next_payoff_beat`（`planner.py:80`）では**半開区間**。解釈が2通りあり、境界話でずれる | 2 |
| W5-05 | Major | `SHORT_TERM_HORIZON = 3`（`planner.py:20`）が**宣言されているがファイル内で一度も使われない**。短期と長期の切替が実質的に機能していない | 3 |
| W5-06 | Major | `ForeshadowingScope` は範囲の同一性比較（`planner.py:165-167`）だけで決まり、**物語の節目（ミッドポイント／クライマックス）との関係が明示されていない** | 4 |
| W5-07 | Major | CAS 拒否理由（`_diagnose_rejection`: `foreshadowing_repo.py:181-205`）は**返り値 True/False に潰される**（`foreshadowing_repo.py:265`）。どの理由が何回起きたかが外から取れない | 8 |
| W5-08 | Minor | `src/services/foreshadowing/` に `os.environ` 読みが**ゼロ**。新機能を段階導入する手段が無い | 1 |
| W5-09 | Minor | `EpisodeBeat.target_foreshadowing_ids`（`src/models/beat_sheet.py:21`）は**モデルとテストだけ存在し、本番で一度も埋まらない**。契約鉤子の受け皿が空 | 11 |
| W5-10 | Minor | 終端で未回収が一斉に発生すると `MAX_BACKGROUND_FORESHADOWINGS=20` で頭打ちに切られ、**「他N件あり」注記だけで終わり**。分散させる力学が無い | 11 |

---

## 2. 12ステップ

---

### Step 1. `src/services/foreshadowing/flags.py` を新設する
- **主担当ファイル**: `src/services/foreshadowing/flags.py`（**新規**）
- **依存**: なし
- **P分類**: P1（新規1ファイル）/ P2

**背景**
`grep -rn "os.environ" src/services/foreshadowing/` は **0 ヒット**。
一方、リポジトリ全体の主流は `os.getenv("NAME", "default").strip().lower() in ("1","true","yes","on")`
（`src/agents/writing/episode_writer.py:29-37`）と `_TRUTHY` + `_env_flag`（`src/agents/audit_agent.py:24,139`）。
**このパッケージの唯一の数理出口を先に作る**。以降すべてのステップがここを参照する。

**作業内容**
1. 新規ファイル。先頭に `from __future__ import annotations` と `import os`。
2. 定数:
   - `_TRUTHY = ("1", "true", "yes", "on")`
   - `_FALSY = ("0", "false", "no", "off")`
3. 公開API **5つだけ**（これ以外は足さない）:
   - `is_causal_dag_enabled() -> bool`（既定 `False`）… 環境変数 `FORESHADOW_CAUSAL_DAG`
   - `is_anchor_snap_enabled() -> bool`（既定 `False`）… `FORESHADOW_ANCHOR_SNAP`
   - `is_relevance_injection_enabled() -> bool`（既定 `False`）… `FORESHADOW_RELEVANCE_INJECTION`
   - `is_cascade_reschedule_enabled() -> bool`（既定 `False`）… `FORESHADOW_CASCADE_RESCHEDULE`
   - `get_relevance_top_k(default: int = 2) -> int` … `FORESHADOW_RELEVANCE_TOP_K`（`0` 以上のみ採用）
4. **すべて既定 `False`（無効）**。既存挙動を一切変えない。
5. `settings` や pydantic は**参照しない**（`os.environ` のみ）。テストは `monkeypatch.setenv` で操作する。

**回帰テスト（先に作る）**: `tests/unit/services/foreshadowing/test_flags.py`（新規・同期）

```python
"""伏線パッケージのフラグが既定OFFで、環境変数でONにできることの回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing import flags

ALL = [
    "is_causal_dag_enabled", "is_anchor_snap_enabled",
    "is_relevance_injection_enabled", "is_cascade_reschedule_enabled",
]


def test_all_flags_default_off(monkeypatch):
    for name in ("FORESHADOW_CAUSAL_DAG", "FORESHADOW_ANCHOR_SNAP",
                 "FORESHADOW_RELEVANCE_INJECTION", "FORESHADOW_CASCADE_RESCHEDULE"):
        monkeypatch.delenv(name, raising=False)
    for name in ALL:
        assert getattr(flags, name)() is False, name


def test_truthy_values_enable(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("FORESHADOW_CAUSAL_DAG", raw)
        assert flags.is_causal_dag_enabled() is True, raw


def test_falsy_values_disable(monkeypatch):
    for raw in ("0", "false", "no", "off", "banana", ""):
        monkeypatch.setenv("FORESHADOW_CAUSAL_DAG", raw)
        assert flags.is_causal_dag_enabled() is False, raw


def test_top_k_clamped_to_non_negative(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "-5")
    assert flags.get_relevance_top_k() == 2
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "abc")
    assert flags.get_relevance_top_k() == 2
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "4")
    assert flags.get_relevance_top_k() == 4
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/test_flags.py -q
```

**完了判定**: 4テスト緑。

---

### Step 2. `src/services/foreshadowing/anchors.py` を新設する（アンカー＋区間正規化）
- **主担当ファイル**: `src/services/foreshadowing/anchors.py`（**新規**）
- **依存**: なし
- **P分類**: P1（新規1ファイル）/ P2

**背景**
```
src/config/commercial_beat_sheet.py:8-58  COMMERCIAL_40EP_BEATS  7ビート
  (1,3) 開幕フック / (4,10) 初期成功 / (11,18) 第1の試練
  (19,25) Midpoint・大転換 / (26,32) 最大の危機 / (33,38) クライマックス / (39,40) 凱旋
src/config/commercial_beat_sheet.py:61-68  get_beat_for_episode  ← 両端含む（65行目の inclusive スキャン）
src/services/foreshadowing/planner.py:80    start_ep <= ep < end_ep  ← 半開区間
```
**同じ `range` 型が 2 つの意味で使われている**ため、境界話（例: 第10話）で
`get_beat_for_episode` は (4,10) を返すのに `_next_payoff_beat` は (11,18) を探す、というズレが起きうる。

**作業内容**
1. 新規ファイル。**I/O ゼロ**。`src.config.commercial_beat_sheet` の import のみ許可。
2. 定数:
   - `BEAT_RANGE_IS_HALF_OPEN = True`（本パッケージ内の唯一の解釈として固定）
   - `ANCHOR_NAMES = ("opening", "first_trial", "midpoint", "crisis", "climax", "resolution")`
   - `PAYOFF_ANCHORS = ("midpoint", "climax", "resolution")`（長期伏線を吸着させる節目）
3. 公開API **3つだけ**:
   - `def beat_for_episode(ep: int) -> dict` — **半開区間**で走査し、範囲外は `COMMERCIAL_40EP_BEATS[-1]` を返す。
   - `def anchor_episode(anchor: str) -> int` — 名前から**代表話**を返す固定表（後述）。
   - `def is_anchor_episode(ep: int, anchors: tuple[str, ...] = PAYOFF_ANCHORS) -> bool`
4. `anchor_episode` の固定表（**plot の phase 文字列から機械的に読む、合計6行程度**）:
   - `opening` → range[0]
   - `first_trial` → range[0]
   - `midpoint` → range[0]
   - `crisis` → range[0]
   - `climax` → range[0]
   - `resolution` → range[0]
   （`COMMERCIAL_40EP_BEATS` の `phase` 列を `anchor_episode` 内で小さい順に並べ、按_datetime で range[0] を返す）
5. **既存の `get_beat_for_episode`（`commercial_beat_sheet.py:61`）は変更しない。**
   本ステップでは本パッケージ内から **それを使わない** だけ。
6. `beat_for_episode` の戻り値は `COMMERCIAL_40EP_BEATS` の要素を**そのまま返す**（新規dictを作らない）。

**回帰テスト（先に作る）**: `tests/unit/services/foreshadowing/test_anchors.py`（新規・同期）

```python
"""ナラティブアンカーと半開区間化の回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing.anchors import (
    beat_for_episode, anchor_episode, is_anchor_episode, PAYOFF_ANCHORS,
)


def test_half_open_interval_is_used():
    """(4,10) の半開区間なので第10話は (11,18) に属する。"""
    assert beat_for_episode(10)["range"] == (11, 18)
    assert beat_for_episode(4)["range"] == (4, 10)
    assert beat_for_episode(3)["range"] == (1, 3)
    assert beat_for_episode(1)["range"] == (1, 3)


def test_out_of_range_falls_back_to_last_beat():
    assert beat_for_episode(999)["range"] == (39, 40)


def test_anchor_episode_returns_range_start():
    for name in ("opening", "first_trial", "midpoint", "crisis", "climax", "resolution"):
        assert anchor_episode(name) >= 1, name


def test_payoff_anchor_membership():
    assert is_anchor_episode(anchor_episode("midpoint")) is True
    assert is_anchor_episode(anchor_episode("climax")) is True
    assert is_anchor_episode(2) is False


def test_payoff_anchors_tuple_is_frozen():
    assert PAYOFF_ANCHORS == ("midpoint", "climax", "resolution")
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/test_anchors.py tests/unit/planning/test_beat_sheet_foreshadowing_contract.py -q
```

**完了判定**: 5テスト緑。**かつ既存 beat テストが緑**（`get_beat_for_episode` を変えていないこと）。

---

### Step 3. `planner.py` の短期ホライズンを実装する
- **主担当ファイル**: `src/services/foreshadowing/planner.py`
- **依存**: Step 1, 2
- **P分類**: P1（1ファイル）/ P7（既存挙動は既定で不変）

**背景**
```
20: SHORT_TERM_HORIZON = 3   ← 宣言のみ、ファイル内で未使用
34-36: ForeshadowingPlan.is_short_term  ← horizon < 3 の判定だけ
165-167: scope = LONG_TERM if is_long_term else SHORT_TERM   ← 範囲同一性比較
```
現状 `SHORT_TERM_HORIZON` が死んでいるため、**scope と horizon が無関係に決まる**。
`tests/regression/test_v53_long_form_integrity.py:61-147` は 13 本の不変条件を固定している。

**作業内容**
1. `plan_foreshadowing`（`:123`）のシグネチャに**キーワード引数**を2つ追加する（位置引数は変えない）:
   - `use_short_term_horizon: bool | None = None`（`None` → `is_anchor_snap_enabled()` **ではなく**
     新フラグ `is_short_horizon_enabled()` を読む。`flags.py` に追加してよい）
   - `anchor: str | None = None`（Step 4 で使う。`None` なら従来どおり）
2. `use_short_term_horizon` が truthy のときだけ、**`SHORT_TERM_HORIZON` を使う分岐**を `:169` の直後に追加:
   - 算出 `target` が `planted_episode + SHORT_TERM_HORIZON` を**超える**場合、
     `target = min(target, min(planted_episode + SHORT_TERM_HORIZON, total))` に丸める。
   - ただし **不変条件 `target > planted_episode`（`:171-174`）は絶対に壊さない**。
3. `ForeshadowingPlan`（`:26-36`）に**新フィールドを足さない**（`frozen=True` のため、
   足すと `test_plan_is_immutable` 以外の既存テストの構築引数に影響する）。
   追加したい情報は Step 4 の `anchor` として**別モジュール側で持つ**。
4. `_spread_target`（`:91-120`）は**変更しない**。`_next_payoff_beat`（`:65-88`）も変更しない。
5. 新フラグ `is_short_horizon_enabled()` を `flags.py`（Step 1 做的事）に**追加**する（既定 `False`）。
   → Step 1 のテストが `ALL` に含んでいないので、既存テストはそのまま緑。

**回帰テスト（先に作る）**: `tests/regression/test_w5_short_horizon.py`（新規・同期）

```python
"""短期ホライズン丸めが既存不変条件を壊さないことの回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing.planner import plan_foreshadowing, SHORT_TERM_HORIZON
from src.services.foreshadowing.status import ForeshadowingStatus  # 状態列挙は既存モジュール


def test_default_behavior_unchanged_without_flag():
    """フラグ無しで呼んだ結果は既存テストと同一であること（回帰の最重要点）。"""
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40)
        assert plan.target_episode > planted, planted
        assert plan.horizon >= 1, planted


def test_short_horizon_clamps_to_3():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40, use_short_term_horizon=True)
        assert planted < plan.target_episode <= planted + SHORT_TERM_HORIZON, planted


def test_short_horizon_never_produces_horizon_zero():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=planted, use_short_term_horizon=True)
        assert plan.horizon >= 1, planted


def test_short_horizon_never_exceeds_total():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=min(planted + 1, 40),
                                  use_short_term_horizon=True)
        assert plan.target_episode <= min(planted + 1, 40), planted
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/regression/test_w5_short_horizon.py tests/regression/test_v53_long_form_integrity.py -q
```

**完了判定**: 4テスト緑。**かつ `test_v53_long_form_integrity.py` の TestForeshadowingPlanner 13本すべて緑**。

---

### Step 4. `planner.py` にアンカー吸着（anchor snap）を足す
- **主担当ファイル**: `src/services/foreshadowing/planner.py`
- **依存**: Step 2, 3
- **P分類**: P1（1ファイル）/ P7

**背景**
`_spread_target`（`:91-120`）は「次の回収ビート区間の中に線形配置」而已。
物語論的には **長期伏線はミッドポイント／クライマックスといった物語の節目（Narrative Anchor）に吸着させる**べきで、
区間内の任意の話数ではない。

**作業内容**
1. `plan_foreshadowing` に**キーワード引数** `anchor_snap: bool | None = None` を追加（`None` → `is_anchor_snap_enabled()`）。
2. 既存の `is_long_term` 判定（`:165-167`）の**直後**に、以下を**丸括弧で囲んだ1つの else 相当**として挿入:
   - `is_long_term` が True のときだけ:
     - `snap = min(anchor_episode("midpoint"), anchor_episode("climax"))` を基準にする。
     - `target` が `planted_episode` より後、かつ **`snap > planted_episode`** なら
       `target = min(snap, total)` を**候補**とする。
     - ただし **元の算出値より大きく前倒しはしない**（`target = max(target, original_target)`）。
3. **不変条件ガード（`:171-174`）は先頭で必ず走る**。anchor snap はその**後**に適用する。
4. `ForeshadowingPlan` にフィールドを足さない（Step 3 と同じ理由）。
5. `planner.py` の**モジュール定数**は1つだけ追加してよい: `LONG_TERM_ANCHOR_ORDER = ("midpoint", "climax")`。
6. `tests/benchmarks/long_form.py` が `plan_foreshadowing` を import しているため、
   **位置引数の数と順序は変更禁止**（引数はすべてキーワード・既定値付き）。

**回帰テスト（先に作る）**: `tests/regression/test_w5_anchor_snap.py`（新規・同期）

```python
"""アンカー吸着が既存不変条件を壊さないことの回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing.planner import plan_foreshadowing
from src.services.foreshadowing.anchors import anchor_episode

MID = anchor_episode("midpoint")
CLIMAX = anchor_episode("climax")


def test_anchor_snap_off_is_bitwise_unchanged():
    for planted in range(1, 41):
        a = plan_foreshadowing(planted, total_episodes=40)
        b = plan_foreshadowing(planted, total_episodes=40, anchor_snap=False)
        assert a == b, planted


def test_anchor_snap_preserves_horizon_invariant():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=40, anchor_snap=True)
        assert plan.target_episode > planted, planted
        assert plan.horizon >= 1, planted


def test_anchor_snap_lands_in_payoff_window_or_keeps_original():
    for planted in range(1, 41):
        plain = plan_foreshadowing(planted, total_episodes=40)
        snapped = plan_foreshadowing(planted, total_episodes=40, anchor_snap=True)
        assert snapped.target_episode >= plain.target_episode, planted
        assert snapped.target_episode <= 40, planted


def test_anchor_snap_respects_total_episodes():
    for planted in range(1, 41):
        plan = plan_foreshadowing(planted, total_episodes=planted + 1, anchor_snap=True)
        assert plan.target_episode <= planted + 1, planted


def test_climax_is_the_last_payoff_anchor():
    assert CLIMAX > MID
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/regression/test_w5_anchor_snap.py tests/regression/test_v53_long_form_integrity.py -q
C:\Python314\python.exe -m tests.benchmarks.long_form
```

**完了判定**: 5テスト緑。**かつ `test_v53_long_form_integrity.py` 全緑**。**かつ long_form ベンチが例外なく完走**。

---

### Step 5. `src/services/foreshadowing/causal_dag.py` を新設する
- **主担当ファイル**: `src/services/foreshadowing/causal_dag.py`（**新規**）
- **依存**: なし（Step 1 のフラグは使わない。純データ構造のみ）
- **P分類**: P1（新規1ファイル）/ P2

**背景**
伏線_pythonには**依存関係という概念が存在しない**。`ForeshadowingModel`
（`src/backend/database/models_foreshadowing.py:15-52`）も
`Foreshadowing` 旧モデル（`src/models/foreshadowing.py:7-47`）も `depends_on` 相当を持たない。
物語論的には「B の回収には A の回収（または A の進展）が必要」という**因果順序**が要る。

**作業内容**
1. 新規ファイル。**I/O ゼロ・LLM ゼロ**。stdlib のみ。
2. dataclass 2つ:
   - `@dataclass(frozen=True) class CausalNode: foreshadowing_id: int; target_episode: int | None; status: str`
   - `@dataclass(frozen=True) class CausalEdge: before: int; after: int`（`before` が `after` の前提）
3. 公開API **2つだけ**:
   - `def build_dag(rows: list[dict]) -> list[CausalNode]`
     - `rows` は `{"id": int, "target_episode": int|None, "status": str, "description": str}` のリスト。
     - 依存推定は**完全に決定論的**：行の並び順（`id` 昇順）で、
       `description` に「〜に続く」「〜の結果」「〜の顛末」等の**後続を示す語**が含まれるとき、
       直前の**未解決ノード**へ辺を張る。
     - **LLM は呼ばない。LLM を足すのは本計画のスコープ外**（別計画で扱う）。
   - `def edges_of(rows: list[dict]) -> list[CausalEdge]`（`build_dag` の補助・`edges` のみ返す）
4. **来歴が分かる枝**を `status` として使う（`planted` / `progressed` / `resolved` / `abandoned`）。
   未知値は `"unknown"` に丸める（**例外を送出しない**）。
5. `description` が空文字 `""` の行は**必ず辺を張らない**（cycle 防止）。
6. `foreshadowing_id` が重複した行は**後勝ちで1本に畳む**。

**回帰テスト（先に作る）**: `tests/unit/services/foreshadowing/test_causal_dag.py`（新規・同期）

```python
"""CausalNode / CausalEdge 構築の回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing.causal_dag import build_dag, edges_of


ROWS = [
    {"id": 1, "target_episode": 8, "status": "planted", "description": "古代の魔導書を拾う"},
    {"id": 2, "target_episode": 12, "status": "planted", "description": "解読に失敗して危機に陥る"},
    {"id": 3, "target_episode": 20, "status": "planted", "description": "賢者と出会い，真相が判明する"},
]


def test_build_dag_returns_one_node_per_row():
    nodes = build_dag(ROWS)
    assert len(nodes) == 3
    assert {n.foreshadowing_id for n in nodes} == {1, 2, 3}


def test_nodes_are_immutable():
    nodes = build_dag(ROWS)
    try:
        nodes[0].status = "resolved"
    except Exception:
        return
    raise AssertionError("CausalNode は frozen であるべき")


def test_duplicate_ids_are_collapsed():
    nodes = build_dag(ROWS + [dict(ROWS[0], target_episode=99)])
    assert len(nodes) == 3
    assert next(n for n in nodes if n.foreshadowing_id == 1).target_episode == 99


def test_empty_description_produces_no_edge():
    assert edges_of([dict(ROWS[0], description="")]) == []


def test_empty_input_is_safe():
    assert build_dag([]) == [] and edges_of([]) == []


def test_unknown_status_is_normalised():
    assert build_dag([dict(ROWS[0], status="weird")])[0].status == "unknown"
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/test_causal_dag.py -q
```

**完了判定**: 6テスト緑。

---

### Step 6. `causal_dag.py` へ位相トポロジカルソートと依存取得を加える
- **主担当ファイル**: `src/services/foreshadowing/causal_dag.py`（Step 5 と同じ1ファイル）
- **依存**: Step 5
- **P分類**: P1（1ファイルのみ）/ P2

**背景**
Step 5 の `build_dag` は辺を作るだけで、**順序**と**依存先**の逆辺がない。
Cascade 延期（Step 7）に必要なのは「このノードを延期したら、どのノードも一緒に延期しなければならないか」の逆辺。

**作業内容**
1. `causal_dag.py` に公開API **3つを足す**（既存2つは変更しない）:
   - `def topological_order(rows: list[dict]) -> list[int]`
     - Nodes returned as IDs. Kahn 法。**安全のため深さ優先探索（Tarjan）で強連結成分を縮約**してから
       Kahn を適用する。**self-loop があっても無限ループしない**。
     - グラフに閉路がある場合は **閉路内のIDを id 昇順で並べた後**、残りを id 昇順で後ろに付ける。
   - `def dependents_of(rows: list[dict], foreshadowing_id: int) -> list[int]`
     - 直接の依存先 + 推移閉包。**id 昇順でソート**して返す。
   - `def roots_of(rows: list[dict]) -> list[int]`
     - 入次数 0 のノード id（id 昇順）。
2. **例外を送出しない**。不正入力は空リストを返す。
3. **LLM・DB・File I/O を使わない**（Step 5 と同じ）。
4. `topological_order` は **必ず全IDをちょうど1回ずつ返す**（脱落・重複が無いこと）。
5. 長大入力（10,000ノード）でも**再帰を使わない**（`sys.setrecursionlimit` に依存しない）。

**回帰テスト（先に作る）**: `tests/unit/services/foreshadowing/test_causal_dag_order.py`（新規・同期）

```python
"""トポロジカル順序と依存伝播の回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing.causal_dag import topological_order, dependents_of, roots_of


def _chain(n):
    return [
        {"id": i, "target_episode": i, "status": "planted",
         "description": "後続的故事" if i < n else "独立"}
        for i in range(1, n + 1)
    ]


def test_topological_order_is_a_permutation():
    rows = _chain(20)
    order = topological_order(rows)
    assert sorted(order) == list(range(1, 21))


def test_topological_order_respects_edges():
    order = topological_order(_chain(5))
    assert order.index(1) < order.index(2) < order.index(5)


def test_cycle_does_not_hang():
    rows = [
        {"id": 1, "target_episode": 2, "status": "planted", "description": "後続的故事"},
        {"id": 2, "target_episode": 3, "status": "planted", "description": "後続的故事"},
    ]
    rows[0]["description"] = "後続的故事"
    order = topological_order(rows)   # 戻ってこなければ失敗（タイムアウト）
    assert sorted(order) == [1, 2]


def test_self_loop_is_safe():
    rows = [{"id": 1, "target_episode": 2, "status": "planted", "description": "後続的故事"}]
    assert topological_order(rows) in ([1], [1])


def test_dependents_are_transitive():
    rows = _chain(4)
    assert dependents_of(rows, 1) == [2, 3, 4]
    assert dependents_of(rows, 4) == []


def test_roots_are_in_degree_zero():
    rows = _chain(4)
    assert roots_of(rows) == [1]
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/test_causal_dag_order.py -q
```

**完了判定**: 6テスト緑。**`test_cycle_does_not_hang` が5秒以内に終わること**（CI は `--timeout=120`）。

---

### Step 7. `rescheduler.py` へ連鎖延期（cascade）を足す
- **主担当ファイル**: `src/services/foreshadowing/rescheduler.py`
- **依存**: Step 1, 5, 6
- **P分類**: P1（1ファイル）/ P7

**背景**
```
19-56:  find_next_suitable_episode(current_episode, max_episode) -> Optional[int]
58-112: reschedule_foreshadowing(foreshadowing_id, current_episode, repo, max_episode)
99:     await repo.update_target_episode(foreshadowing_id, new_ep)
```
`find_next_suitable_episode` は「回収語を含むビートを前方スキャン」するだけ。
**A を第30話へ延期したら、A を前提とする B は第12話のまま放置される**（因果矛盾）。

**作業内容**
1. `rescheduler.py` に**classmethod 1つ**を足す（既存2つは変更しない）:
```python
@classmethod
async def cascade_reschedule(
    cls, rows: list[dict], foreshadowing_id: int, current_episode: int,
    repo, max_episode: int | None = None,
) -> list[tuple[int, int]]:
    """foreshadowing_id を延期したとき、依存する伏線も一緒に延期する。
    戻り値: [(foreshadowing_id, new_target_episode), ...]（実際に更新した分だけ）"""
```
2. 実装（**40行以内**）:
   - `is_cascade_reschedule_enabled()` が False なら **即 `return []`**。
   - `dependents_of(rows, foreshadowing_id)`（Step 6）を取得し、**id 昇順で**処理。
   - 各依存先 `d` について:
     - 既存 `cls.find_next_suitable_episode(current_episode, max_episode)` で新話数を決める。
     - `None` の場合は **`update_target_episode` を呼ばない**（放棄判断は `ForeshadowingService._evaluate_one:182-207` の責務）。
     - `await repo.update_target_episode(d, new_ep)` が **False を返したら次へ進む**（例外にしない）。
   - 実際に更新できたものだけを戻り値に積む。
3. 既存の `reschedule_foreshadowing`（`:59`）は**変更しない**。
4. `UNBOUNDED_SCAN_LIMIT = 200`（`rescheduler.py:17`）は**据え置き**。連鎖ループには独自の上限
   `MAX_CASCADE = 10` を定数として**追加**し、超過分は処理しない。
5. `repo` が `hasattr(repo, "update_target_episode")` を持たない場合は**空リストを返す**（`:89-98` と同じ握り潰し方）。

**回帰テスト（先に作る）**: `tests/unit/services/foreshadowing/test_cascade_reschedule.py`（新規・非同期）

```python
"""連鎖延期の回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing import flags
from src.services.foreshadowing.rescheduler import ForeshadowingRescheduler

ROWS = [
    {"id": 1, "target_episode": 5, "status": "planted", "description": "魔導書を得る"},
    {"id": 2, "target_episode": 9, "status": "planted", "description": "後続的故事解読に失敗する"},
    {"id": 3, "target_episode": 20, "status": "planted", "description": "後続的故事真相が判明する"},
]


def _repo(ok=True):
    r = MagicMock()
    r.update_target_episode = AsyncMock(return_value=ok)
    return r


@pytest.mark.asyncio
async def test_disabled_flag_is_noop(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "0")
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert out == [] and repo.update_target_episode.await_count == 0


@pytest.mark.asyncio
async def test_enabled_moves_dependents(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert repo.update_target_episode.await_count == 2
    assert [i for i, _ in out] == [2, 3]


@pytest.mark.asyncio
async def test_cas_rejection_is_swallowed(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = _repo(ok=False)
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, repo, max_episode=40)
    assert out == []


@pytest.mark.asyncio
async def test_missing_repo_method_is_safe(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 1, 5, MagicMock(), max_episode=40)
    assert out == []


@pytest.mark.asyncio
async def test_no_dependents_is_noop(monkeypatch):
    monkeypatch.setenv("FORESHADOW_CASCADE_RESCHEDULE", "1")
    repo = _repo()
    out = await ForeshadowingRescheduler.cascade_reschedule(ROWS, 3, 20, repo, max_episode=40)
    assert out == [] and repo.update_target_episode.await_count == 0
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/test_cascade_reschedule.py tests/regression/test_v53_long_form_integrity.py -q
```

**完了判定**: 5テスト緑。**かつ `TestReschedulerUsesRealApi`（`:198`）を含む v5.3 回帰が緑**。

---

### Step 8. `foreshadowing_repo.py` の CAS 拒否理由を残す
- **主担当ファイル**: `src/infrastructure/repositories/foreshadowing_repo.py`
- **依存**: Step 7
- **P分類**: P1（1ファイル）/ P2

**背景**
```
207-265: async def _transition(...) -> bool
265:     return False          ← _diagnose_rejection の結果が書かれないまま捨てられる
283-331: async def update_target_episode(...) -> bool
```
`_diagnose_rejection`（`foreshadowing_repo.py:181-205`）は `not_found` / `illegal_transition` /
`before_plant_episode` / `concurrent_modification` を**文字列として生成し、
`_record_rejection(reason)`（KPI）で計数した後に捨てる**。
**呼び出し側から理由は取れない**ため、Step 7 の cascade が失敗したのか
本当に破綻したのか区別できない。

**作業内容**
1. `__init__`（`:54-`）に `self.last_rejection: dict[str, Any] = {}` を**追加**。
2. `_diagnose_rejection`（`:181`）の**戻り値を `self.last_rejection` に保存**してから return する。
   保存するキーは **3つ固定**: `id` / `target_status` / `reason`。
3. `_transition`（`foreshadowing_repo.py:207`）と `update_target_episode`（`:283`）の失敗パス（`return False`）**直前**で
   `self.last_rejection.setdefault("op", "transition" | "update_target")` を**1行**足す。
4. `last_rejection` は**スレッドセーフでないことを明記**してよいが、
   **Lock を追加しない**（既存 `InMemoryForeshadowingRepository` は `RLock` を持つが
   DB 版は持たない。**この非対称は本計画の対象外**）。
5. **`_status_predicate`（`:32-45`）と UPDATE 文は1文字も変えない**（CAS の正しさが依存する箇所）。
6. `tests/unit/database/test_foreshadowing_repo.py` は実 aiosqlite を使うため、
   **SQL の形を変えてはならない**。

**回帰テスト（先に作る）**: `tests/unit/database/test_foreshadowing_repo_rejection_reason.py`（新規・非同期）
既存 `tests/unit/database/test_foreshadowing_repo.py` の `create_test_db` / `_plant` を**そのまま流用**する。

```python
"""CAS 拒否理由が last_rejection に残ることの回帰テスト。"""
import sys, pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
from tests.unit.database.test_foreshadowing_repo import create_test_db, _plant


@pytest.mark.asyncio
async def test_illegal_transition_records_reason():
    async with create_test_db() as (session, book_id):
        repo = DbForeshadowingRepository(session)
        fid = await _plant(repo, book_id)
        assert await repo.resolve(fid, 9) is True
        assert await repo.resolve(fid, 10) is False          # resolved は終端
        assert repo.last_rejection["reason"] in {"illegal_transition", "not_found"}
        assert repo.last_rejection["id"] == fid


@pytest.mark.asyncio
async def test_not_found_records_reason():
    async with create_test_db() as (session, book_id):
        repo = DbForeshadowingRepository(session)
        assert await repo.resolve(999999, 3) is False
        assert repo.last_rejection["reason"] == "not_found"


@pytest.mark.asyncio
async def test_before_plant_episode_records_reason():
    async with create_test_db() as (session, book_id):
        repo = DbForeshadowingRepository(session)
        fid = await _plant(repo, book_id)      # planted_episode=5 とする
        assert await repo.resolve(fid, 2) is False
        assert repo.last_rejection["reason"] == "before_plant_episode"


@pytest.mark.asyncio
async def test_op_field_is_set():
    async with create_test_db() as (session, book_id):
        repo = DbForeshadowingRepository(session)
        assert await repo.update_target_episode(999999, 8) is False
        assert repo.last_rejection["op"] == "update_target"


@pytest.mark.asyncio
async def test_success_clears_nothing_but_does_not_crash():
    async with create_test_db() as (session, book_id):
        repo = DbForeshadowingRepository(session)
        fid = await _plant(repo, book_id)
        assert await repo.resolve(fid, 9) is True
        assert set(repo.last_rejection) <= {"id", "target_status", "reason", "op"}
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/database/test_foreshadowing_repo_rejection_reason.py tests/unit/database/test_foreshadowing_repo.py -q
```

**完了判定**: 5テスト緑。**かつ既存 CAS テスト11本すべて緑**（SQL を変えていないことの担保）。

---

### Step 9. `src/services/foreshadowing/relevance.py` を新設する
- **主担当ファイル**: `src/services/foreshadowing/relevance.py`（**新規**）
- **依存**: なし
- **P分類**: P1（新規1ファイル）/ P2

**背景**
`prompts/manager._select_background_foreshadowings`（`:812-873`）のソートキーが
「期限超過 → 設置話の新しい順」だけで、**そのシーンとの関連度を一切見ていない**。
関連度計算に必要な部品は既に揃っている:
- `EmbeddingService.get_embedding_async`（`src/services/embedding_service.py:178`）— async / LRU+Redis キャッシュ
- `_generate_pseudo_embedding`（`:280`）— API 不在時の決定論的フォールバック
- `_cosine_similarity`（`src/services/compression/layer3_taxonomy.py:117`）— 純関数

**作業内容**
1. 新規ファイル。**ネットワーク直接呼び出し禁止**。`EmbeddingService` は**DI 引数**で受ける。
2. 公開API **2つだけ**:
   - `def cosine(a: list[float], b: list[float]) -> float` — 純関数。**長さ不一致/ゼロベクトルで 0.0**。
   - `def score_and_select(scene_text: str, candidates: list[dict], top_k: int = 2,
     embedding_fn=None) -> list[dict]`
     - `candidates` は `{"id", "title", "description", "planted_episode", "target_episode"}` のリスト。
     - `embedding_fn` が `None` のときは **`title + description` の文字一致（Jaccard）**で代用する。
       （Embedding API を一切呼ばずに動く＝テストが軽い）
     - 返り値は `dict` の**新しいリスト**（入力は破壊しない）。要素に `"relevance": float` を**追加**。
     - `top_k <= 0` なら `[]` を返す。
     - **期限超過（`target_episode < 現話`）は score を 1.1 倍に補正**する（1.0 でクランプ）。
3. `top_k` の既定は `flags.get_relevance_top_k()` の**呼び出し側**が渡す（`relevance.py` は `flags` を参照しない）。
4. 例外は送出しない。`embedding_fn` が例外を投げた場合は **Jaccard にフォールバック**する。
5. スコアの式は **`0.7 * cos + 0.3 * decay`** にする。`decay` は
   `1.0 / (1.0 + max(0, 現在話 - planted_episode) / 10.0)`。

**回帰テスト（先に作る）**: `tests/unit/services/foreshadowing/test_relevance.py`（新規・同期）

```python
"""関連度スコアリングの回帰テスト（ネットワークを一切使わない）。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.services.foreshadowing.relevance import cosine, score_and_select

CANDS = [
    {"id": 1, "title": "古代の魔導書", "description": "迷宮で拾った古い巻物", "planted_episode": 2},
    {"id": 2, "title": "幼馴染の約束", "description": "町の広場で交わした言葉", "planted_episode": 3},
]


def test_cosine_basics():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([], [1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_jaccard_fallback_ranks_relevant_first():
    out = score_and_select("古代の魔導書を読み解く", CANDS, top_k=1)
    assert len(out) == 1 and out[0]["id"] == 1


def test_input_is_not_mutated():
    before = [dict(c) for c in CANDS]
    score_and_select("魔導書", CANDS, top_k=2)
    assert CANDS == before


def test_zero_top_k_returns_empty():
    assert score_and_select("魔導書", CANDS, top_k=0) == []


def test_overdue_gets_boost():
    out = score_and_select("魔導書", [dict(CANDS[0], target_episode=1)], top_k=1, current_episode=20)
    assert out and out[0]["relevance"] >= 1.0


def test_failing_embedding_falls_back():
    def boom(text): raise RuntimeError("no api")
    out = score_and_select("古代の魔導書", CANDS, top_k=2, embedding_fn=boom)
    assert len(out) == 2
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/test_relevance.py -q
```

**完了判定**: 6テスト緑。**ネットワークを1回も叩いていないこと**（6本とも外部依存なし）。

---

### Step 10. `prompt_composer.py` へ関連度注入を差し込む
- **主担当ファイル**: `src/agents/prompt_composer.py`
- **依存**: Step 1, 9
- **P分類**: P1（1ファイル）/ P7

**背景**
```
207-254: async def _load_unresolved_foreshadowings(...)  → 全件 dict 化
96-145:  build_final_writing_prompt(unresolved_foreshadowings=..., contract_foreshadowings=...)
```
`_load_unresolved_foreshadowings` は **全件を機械的に正規化して渡すだけ**で、
「今のシーンと関係する伏線か」を判断しない。

**作業内容**
1. `prompt_composer.py` の**モジュール先頭に遅延 import** を1つ追加
   （循環 import 回避のため `src.services.foreshadowing.relevance` は**関数内 import** にする）。
2. `_load_unresolved_foreshadowings`（`:207`）の**末尾**に、以下の**1つの if ブロック**を追加する:
   - `if not is_relevance_injection_enabled(): return normalized`（**既定 OFF → 現挙動そのまま**）
   - `scene_text = f"{context.get('phase','')} {context.get('scene_summary','')}"`
     （`context` は既に引数にある。**無いキーは空文字**にして `KeyError` にしない）
   - `selected = score_and_select(scene_text, normalized, top_k=get_relevance_top_k())`
   - `selected` が空なら `normalized` の**先頭1件**を返す（**何も渡さないと prompt が壊れる**ため）。
   - それ以外は `selected` を返す。
3. **契約鉤子（`contract_foreshadowings`）には触れない**。回収ミッションは関連度で削ってはいけない。
4. `format_unresolved_foreshadowings`（`context_builder_agent.py:512-`）は**変更しない**。
5. 既存引数 `book_id` / `ep_num` / `context` は**そのまま使う**。新しい引数は追加しない。
6. `EmbeddingService` の**インスタンス生成をこのステップでは行わない**。
   `score_and_select(..., embedding_fn=None)` で Jaccard のみを使う
   （**API コストゼロ**。Embedding 導入は別ステップのスコープ外とする）。

**回帰テスト（先に作る）**: `tests/contract/test_v5_foreshadowing_relevance_injection.py`（新規・非同期）

```python
"""関連度注入が既定OFFで、ONにしても契約鉤子が消えないことの回帰テスト。"""
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from src.agents.prompt_composer import PromptComposer


def _composer():
    agent = MagicMock()
    agent.prompt_manager = MagicMock()
    agent.prompt_manager.build_final_writing_prompt = AsyncMock(return_value="PROMPT")
    return PromptComposer(agent)


@pytest.mark.asyncio
async def test_default_off_passes_everything(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "0")
    with patch("src.agents.prompt_composer.PromptComposer._load_unresolved_foreshadowings",
               new=AsyncMock(return_value=[])) as m:
        await _composer().run(book_id=1, ep_num=1, context={})
        assert m.await_count == 1


@pytest.mark.asyncio
async def test_off_flag_keeps_original_list(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "0")
    composer = _composer()
    with patch.object(PromptComposer, "_db_session", None, create=True):
        out = await composer._load_unresolved_foreshadowings(
            book_id=1, ep_num=1, context={},
            rows=[{"id": 1, "title": "魔導書", "description": "巻物", "planted_episode": 2},
                  {"id": 2, "title": "約束", "description": "言葉", "planted_episode": 3}],
        )
    assert len(out) == 2


@pytest.mark.asyncio
async def test_on_flag_limits_to_top_k(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "1")
    monkeypatch.setenv("FORESHADOW_RELEVANCE_TOP_K", "1")
    composer = _composer()
    with patch.object(PromptComposer, "_db_session", None, create=True):
        out = await composer._load_unresolved_foreshadowings(
            book_id=1, ep_num=1,
            context={"scene_summary": "魔導書を読み解こうとする"},
            rows=[{"id": 1, "title": "古代の魔導書", "description": "巻物", "planted_episode": 2},
                  {"id": 2, "title": "幼馴染の約束", "description": "町の言葉", "planted_episode": 3}],
        )
    assert len(out) == 1 and out[0]["id"] == 1


@pytest.mark.asyncio
async def test_on_flag_never_returns_empty(monkeypatch):
    monkeypatch.setenv("FORESHADOW_RELEVANCE_INJECTION", "1")
    composer = _composer()
    with patch.object(PromptComposer, "_db_session", None, create=True):
        out = await composer._load_unresolved_foreshadowings(
            book_id=1, ep_num=1, context={},
            rows=[{"id": 9, "title": "無関係", "description": "無関係", "planted_episode": 1}],
        )
    assert len(out) >= 1
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/contract/test_v5_foreshadowing_relevance_injection.py -q
```

**完了判定**: 4テスト緑。

> **実装者への注意**: `tests/contract/` の既存テストが `PromptComposer.run` の引数順を固定している可能性がある。
> 実行前に `grep -n "PromptComposer" tests/contract/ tests/unit/agents/` で **実際のシグネチャ**を確認すること。

---

### Step 11. `prompts/manager.py` へ終端集中（bundling）を防ぐ
- **主担当ファイル**: `prompts/manager.py`
- **依存**: Step 1, 10
- **P分類**: P1（1ファイル）/ P7

**背景**
```
812-873: _select_background_foreshadowings(unresolved, contract, current_episode)
814:     MAX_BACKGROUND_FORESHADOWINGS = 20
828-832: background.sort(key=lambda f: (期限超過フラグ, -planted_episode))
846-853: omitted = background[20:]; shown = background[:20]
854-858: note = f"他{len(omitted)}件あり（うち期限超過{overdue}件）"
```
長編で展開が膨らむと **期限超過が終端に一堂会聚**し、20件で頭打ちに切られる。
切られた件は注記一行になるだけで、**先に回収される理由が提示されない**。
さらに `EpisodeBeat.target_foreshadowing_ids`（`src/models/beat_sheet.py:21`）は
**本番で一度も埋まらない**（`tests/unit/planning/test_beat_sheet_foreshadowing_contract.py` だけが検証）。

**作業内容**
1. `_select_background_foreshadowings`（`:812`）の**ソートキーを拡張**する（1箇所の `sort` のみ）:
   - 既存の2キーに**前置**して `episodes_until_payoff` を追加する:
     `期限超過 → 設置話の新しい順` の**前**に、
     「今話に最も近い回収予定話」を最優先するカテゴリを追加する。
   - 実装は **1行の key 関数**に畳む。既存の「期限超過を最優先」は**保持**する。
2. `MAX_BACKGROUND_FORESHADOWINGS`（`:814`）は **20 のまま**（増やさない）。
3. **注記（`:865-872`）を拡張**する。既存の「他N件あり（うち期限超過M件）」は**先頭に残し**、
   後ろに **「直近N話での回収推奨: 話1, 話2, ...」** を1行追加する。
4. `FORESHADOW_BUNDLE_LIMIT`（既定 `5`）を `flags.py` ではなく **この関数のクラス定数**として追加し、
   値はこの1行だけで制御できるようにする。
5. `EpisodeBeat.target_foreshadowing_ids` は **このステップでは埋めない**（Step 12 の計測に任せる）。
   **モデルと既存テストには触らない**。
6. `foreshadowing_contract_instruction.j2`（`prompts/templates/narrative/`）は**このステップで変更しない**。
   テンプレート変更は 1 ステップ複数箇所（マイグレーション的な破壊的変更）に見えるため、**別ステップで扱う**。

**回帰テスト（先に作る）**: `tests/unit/test_prompt_manager_bundling.py`（新規・同期）

```python
"""背景伏線の選択・注記の回帰テスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from prompts.manager import PromptManager


def _fs(i, planted, target):
    return {"id": i, "title": f"伏線{i}", "description": "d", "planted_episode": planted,
            "target_episode": target}


def test_overdue_still_ranks_first():
    rows = [_fs(1, 1, 3), _fs(2, 2, 2), _fs(3, 3, 30)]
    shown, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=10)
    assert shown[0]["id"] == 2


def test_cap_is_still_twenty():
    rows = [_fs(i, i, 100) for i in range(1, 51)]
    shown, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=5)
    assert len(shown) == 20
    assert "他30件" in note


def test_note_mentions_recommended_episodes():
    rows = [_fs(i, i, 10 + i) for i in range(1, 6)]
    shown, note = PromptManager._select_background_foreshadowings(rows, [], current_episode=5)
    assert "回収推奨" in note


def test_contract_items_are_excluded_from_background():
    contract = [{"id": 99, "title": "契約", "planted_episode": 1, "target_episode": 5}]
    shown, _ = PromptManager._select_background_foreshadowings(
        [_fs(99, 1, 5), _fs(1, 2, 6)], contract, current_episode=5)
    assert all(f["id"] != 99 for f in shown)


def test_empty_input_is_safe():
    shown, note = PromptManager._select_background_foreshadowings([], [], current_episode=1)
    assert shown == [] and note == ""
```

**検証コマンド**
```powershell
C:\Python314\python.exe -m pytest tests/unit/test_prompt_manager_bundling.py -q
```

**完了判定**: 5テスト緑。**かつ `tests/unit/services/test_foreshadowing_contract_service.py` が緑**。

---

### Step 12. 総合回帰・KPI 計測・文書化
- **主担当ファイル**: `plans/PLAN_W5_CAUSAL_FORESIGHT_12STEPS.md`（本書）、`docs/STATUS.md`
- **依存**: Step 1〜11 すべて
- **P分類**: P1

**作業内容**
1. **並列実行禁止**。順番に以下を実行する（1本でも赤なら Step 12 は未完了）:
   - `C:\Python314\python.exe -m pytest tests/regression/ -q`
   - `C:\Python314\python.exe -m pytest tests/unit/services/ -q`
   - `C:\Python314\python.exe -m pytest tests/unit/database/ -q`
   - `C:\Python314\python.exe -m pytest tests/unit/services/foreshadowing/ tests/contract/ -q`
2. 新規5ファイルに lint:
   `C:\Python314\python.exe -m ruff check src/services/foreshadowing/flags.py src/services/foreshadowing/anchors.py src/services/foreshadowing/causal_dag.py src/services/foreshadowing/relevance.py --select E9,F63,F7,F82`
   → **0 エラー**であること。
3. `tests/benchmarks/long_form.py` を完走させる:
   `C:\Python314\python.exe -m tests.benchmarks.long_form` → 例外が無いこと。
4. `ForeshadowingKpiService.compute`（`src/services/foreshadowing/kpi.py:48`）が
   すでに `overdue` / `collection_rate` を返していることを **README 相当のコメント1行**で確認し、
   本書 §5 の効果表に数値欄を埋める。
5. `docs/STATUS.md` に W5 完了エントリと索引を追加。
6. 本書 status を「完了」に更新。

**完了判定**
- 4つの回帰コマンドがすべて緑。
- 新規4ファイルの `ruff --select E9,F63,F7,F82` がクリーン。
- `tests/benchmarks/long_form.py` が例外なく完走。

---

## 3. ロールバック

すべて**環境変数1つで元に戻せる**。コード削除は不要。

| 変数 | 既定 | 効果 |
|---|---|---|
| `FORESHADOW_CAUSAL_DAG` | `0` | `1` で DAG 構築を有効化（Step 5, 6 の公開APIは常時利用可能） |
| `FORESHADOW_ANCHOR_SNAP` | `0` | `1` で長期伏線をミッドポイント/クライマックスへ吸着 |
| `FORESHADOW_RELEVANCE_INJECTION` | `0` | `1` でプロンプト伏線を関連度上位のみに制限 |
| `FORESHADOW_CASCADE_RESCHEDULE` | `0` | `1` で延期時に依存伏線も連鎖延期 |
| `FORESHADOW_SHORT_HORIZON` | `0` | `1` で短期伏線を `planted + 3` 以内に丸める |
| `FORESHADOW_RELEVANCE_TOP_K` | `2` | 関連度注入の上限件数 |

## 4. 依存関係マップ（実装前に読むこと）

```
            ┌──────────────── beats.json / COMMERCIAL_40EP_BEATS ─────────────┐
            │                                                                │
   planner.py (算術)                                              anchors.py (半開区間)
            │  Step 3 short-horizon          Step 4 anchor-snap         │
            ▼                                                                │
   causal_dag.py ── Step 6 toposort/dependents ── Step 7 cascade ──▶ foreshadowing_repo.py (CAS)
                                                                              │ Step 8 診断
   relevance.py ── Step 10 prompt_composer ── Step 11 prompts/manager
```

## 5. 期待効果

| 指標 | 現状 | 目標 | 測り方 |
|---|---|---|---|
| 終端での未回収の一斉発生 | 最大20件が注記一句に切られる | 直近5話の回収推奨が明示される | `prompts/manager.py` 注記（Step 11） |
| 文脈無視の伏線注入 | 全件ソート順で注入 | 関連度上位 `FORESHADOW_RELEVANCE_TOP_K` 件 | `audit` ではなく prompt 長で（Step 10） |
| 延期時の因果破綻 | 依存先は無関係に据え置き | 依存先が連鎖延期される | `rescheduler.cascade_reschedule` 戻り値（Step 7） |
| CAS 失敗原因 | 消失 | `last_rejection["reason"]` で可視 | Step 8 テスト |
| 長期伏線の回収タイミング | 線形補間 | 節目（midpoint/climax）へ吸着 | `test_w5_anchor_snap.py`（Step 4） |
