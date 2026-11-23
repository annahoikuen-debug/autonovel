# AutoNovel 改善案1：序盤フックエンジンの「かんたん執筆」完全配線（実装計画書）

## 1. 概要

- **目的**: 初心者が「1話目で読者を繋ぎ止め、章末で次話を読ませる」構造を何も意識せずに獲得できるようにする。
- **既存資産**: `OpeningBoosterAgent`、`OpeningBoosterService`、`score_cliffhanger`、`enforce_cliffhanger`（`src/backend/sanitizer.py`）が実装済み。問題は「かんたん執筆（EasyModePipeline）経路で確実に呼び出されていない」こと。
- **スコープ**: EasyModePipeline生成フローへの1-3話フックエンジン配線＋章末引き自動リライト＋UI可視化。フラグOFFで現行挙動とバイト同一を保つ（契約テスト対象）。
- **実装方針**: フラグ `ENABLE_SEQ_HOOK_WIRING`（既定 OFF）で制御。ON時のみ配線を有効化。CIパリティとリグレッションテストを必須化。

## 2. 実装対象ファイル一覧

| # | ファイルパス | 役割 | 変更種別 |
|:---|:---|:---|:---|
| 1 | `src/infrastructure/config/settings.py` | 環境変数 `ENABLE_SEQ_HOOK_WIRING` 追加 | 設定 |
| 2 | `src/easy_mode/pipeline.py` | EasyModePipelineへのフック配線ポイント追加 | 配線 |
| 3 | `src/easy_mode/hooks.py` | 新規。フック制御・採点・リライトオーケストレーション | 新規 |
| 4 | `src/backend/routers/easy_mode.py` | 応答モデルに `hook_metrics` 追加、レスポンス変更 | API |
| 5 | `src/models/seq_hook.py` | 新規。フック採点結果モデル | モデル |
| 6 | `frontend/src/pages/EasyModePage.tsx` | フックメトリクス表示セクション追加 | UI |
| 7 | `tests/unit/easy_mode/test_seq_hook_wiring.py` | 新規。配線ユニットテスト | テスト |
| 8 | `tests/contract/test_seq_hook_contract.py` | 新規。フラグOFF時バイト同一契約テスト | テスト |

## 3. 環境変数（settings.py）

```python
# src/infrastructure/config/settings.py の末尾付近に追加
ENABLE_SEQ_HOOK_WIRING: bool = False  # 既定OFF。ONで1-3話フックエンジンを配線
```

## 4. 実装ステップ（パート1：バックエンド配線）

### ステップ1-1: 設定値追加（`src/infrastructure/config/settings.py`）

`ENABLE_SEQ_HOOK_WIRING` 環境変数を既定 `False` で追加。

### ステップ1-2: モデル追加（新規 `src/models/seq_hook.py`）

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class HookMetrics(BaseModel):
    ep_num: int = Field(..., ge=1, le=3)
    hook_type: str  # crisis / shocking_truth / triumph_trigger / peaceful
    score: float = Field(..., ge=0.0, le=100.0)
    requires_rewrite: bool
    reason: str
    tail_sentence: str
```

### ステップ1-3: フック制御モジュール新規（`src/easy_mode/hooks.py`）

`src/easy_mode/hooks.py` を新規作成。以下の関数を提供：

- `should_apply_hook(ep_num: int, settings) -> bool`: エピソード番号とフラグを判定
- `evaluate_and_maybe_rewrite(text: str, ep_num: int) -> tuple[str, HookMetrics | None]`: 採点→平穏ならリライト指令付与→結果返却
- `build_hook_directive(metrics: HookMetrics) -> str`: リライト指令文字列生成

### ステップ1-4: EasyModePipelineへ配線（`src/easy_mode/pipeline.py`）

生成完了後のテキストに対し、`evaluate_and_maybe_rewrite` を呼び出し、結果をパラメータに添付。

### ステップ1-5: API応答モデル拡張（`src/backend/routers/easy_mode.py`）

`GenerationResponse` に `hook_metrics: HookMetrics | None = None` を追加し、Pipeline結果を返す。

## 5. テスト計画（パート1）

### 5.1 ユニットテスト（新規 `tests/unit/easy_mode/test_seq_hook_wiring.py`）

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `test_should_apply_hook_ep1_flag_on` | `ep_num=1`、`ENABLE_SEQ_HOOK_WIRING=True` | `True` |
| `test_should_apply_hook_ep4_flag_on` | `ep_num=4`、`ENABLE_SEQ_HOOK_WIRING=True` | `False`（1-3話のみ対象） |
| `test_should_apply_hook_flag_off` | `ep_num=1`、`ENABLE_SEQ_HOOK_WIRING=False` | `False` |
| `test_evaluate_peaceful_rewrite` | 平穏結末テキスト | `requires_rewrite=True`、指令文字列が含まれる |
| `test_evaluate_crisis_no_rewrite` | 危機結末テキスト | `requires_rewrite=False` |

### 5.2 契約テスト（新規 `tests/contract/test_seq_hook_contract.py`）

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `test_flag_off_byte_identical_prompt` | フラグOFF時 | 生成プロンプトが現行とバイト単位同一 |
| `test_hook_metrics_none_when_flag_off` | フラグOFF時 | `hook_metrics=None` |

### 5.3 リグレッション対策

- `make test-unit` で `tests/unit/easy_mode/` 全体が緑であることを確認
- `make test-contract` で `tests/contract/test_seq_hook_contract.py` が緑であることを確認
- フラグOFFでは既存の `tests/e2e/test_spine_end_to_end.py` 等に影響しないことを確認

## 6. 完了定義（パート1）

- `ENABLE_SEQ_HOOK_WIRING` が既定OFFで設定追加済み
- `src/easy_mode/hooks.py` に `should_apply_hook` / `evaluate_and_maybe_rewrite` / `build_hook_directive` が実装済み
- EasyModePipelineに配線済み
- `GenerationResponse` に `hook_metrics` 追加済み
- ユニットテスト・契約テストが緑
- `make verify` が通過（CIパリティ維持）

---

続きは「案1 パート2（フロントエンドUI）」を作成します。準備でき次第お知らせください。