# AutoNovel 改善案2：タイトル・キャッチコピーCTR最適化の「かんたん執筆」配線（パート1：バックエンド）

## 1. 概要

- **目的**: 初心者が「クリックされやすいタイトル・あらすじ・キャッチコピー」を何も意識せずに獲得できるようにする。カクヨムでは新着・ランキング一覧でのクリック率がPVの源泉。
- **既存資産**: `score_title_ctr`（`src/integrations/marketing/ctr_scorer.py`）、`score_catchphrase_ctr`（`src/integrations/marketing/catchphrase_scorer.py`）、`trend_syntax_extractor`（`src/integrations/marketing/trend_syntax_extractor.py`）、`ViralTitleGenerator.tsx` が実装済み。問題は「かんたん執筆フローに組み込まれていない」こと。
- **スコープ**: 生成確定時にタイトル・あらすじ・キャッチコピーを自動採点、60点未満ならトレンド構文ベースの改善案3案を提案。フラグ `ENABLE_CTR_WIRING`（既定 OFF）で制御。
- **実装方針**: フラグOFFで現行挙動とバイト同一を保つ。契約テスト対象。

## 2. 実装対象ファイル一覧

| # | ファイルパス | 役割 | 変更種別 |
|:---|:---|:---|:---|
| 1 | `src/infrastructure/config/settings.py` | 環境変数 `ENABLE_CTR_WIRING` 追加 | 設定 |
| 2 | `src/easy_mode/hooks.py` | CTR採点・改善案生成関数追加 | 変更（案1と同じファイル） |
| 3 | `src/models/seq_hook.py` | `CTRMetrics` モデル追加 | モデル |
| 4 | `src/backend/routers/easy_mode.py` | `GenerationResponse` に `ctr_metrics` / `ctr_suggestions` 追加 | API |
| 5 | `frontend/src/pages/EasyModePage.tsx` | CTRスコア表示・改善案選択UI追加 | UI（パート2） |
| 6 | `tests/unit/easy_mode/test_ctr_wiring.py` | 新規。CTR配線ユニットテスト | テスト |
| 7 | `tests/contract/test_ctr_contract.py` | 新規。フラグOFF時バイト同一契約テスト | テスト |

## 3. 環境変数（settings.py）

```python
# src/infrastructure/config/settings.py の末尾付近に追加
ENABLE_CTR_WIRING: bool = False  # 既定OFF。ONでCTR最適化を配線
```

## 4. モデル追加（`src/models/seq_hook.py`）

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class CTRMetrics(BaseModel):
    title_score: float = Field(..., ge=0.0, le=100.0)
    catchphrase_score: float = Field(..., ge=0.0, le=100.0)
    title_needs_improvement: bool
    catchphrase_needs_improvement: bool
    syntax_type: str  # 追放ざまぁ / 勘違い無双 / 無自覚無双 / 一般
```

## 5. 実装ステップ（パート1：バックエンド）

### ステップ2-1: 設定値追加（`src/infrastructure/config/settings.py`）

`ENABLE_CTR_WIRING` 環境変数を既定 `False` で追加。

### ステップ2-2: CTR採点・改善案生成モジュール（`src/easy_mode/hooks.py` 追加）

`src/easy_mode/hooks.py` に以下を追加：

- `evaluate_ctr(title: str, catchphrase: str | None) -> CTRMetrics`: `score_title_ctr` / `score_catchphrase_ctr` / `extract_syntax_features` を呼び出し
- `generate_ctr_suggestions(title: str, genre: str, syntax_type: str) -> list[str]`: トレンド構文ベースのタイトル改善案3案生成

### ステップ2-3: EasyModePipelineへ配線（`src/easy_mode/pipeline.py`）

生成確定時にタイトル・キャッチコピーを抽出し、`evaluate_ctr` を呼び出し。結果をパラメータに添付。

### ステップ2-4: API応答モデル拡張（`src/backend/routers/easy_mode.py`）

`GenerationResponse` に以下を追加：

- `ctr_metrics: CTRMetrics | None = None`
- `ctr_suggestions: list[str] = []`

## 6. テスト計画（パート1）

### 6.1 ユニットテスト（新規 `tests/unit/easy_mode/test_ctr_wiring.py`）

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `test_evaluate_ctr_optimal_title` | 35-55字＋パワーワード | `title_score` 高、改善不要 |
| `test_evaluate_ctr_short_title` | 15字未満 | `title_score` 低、改善必要 |
| `test_generate_ctr_suggestions_exile` | 構文=追放ざまぁ | 改善案に「追放」関連キーワード含む |
| `test_flag_off_no_ctr` | `ENABLE_CTR_WIRING=False` | `ctr_metrics=None`、`ctr_suggestions=[]` |

### 6.2 契約テスト（新規 `tests/contract/test_ctr_contract.py`）

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `test_flag_off_byte_identical_prompt` | フラグOFF時 | 生成プロンプトが現行とバイト単位同一 |
| `test_ctr_fields_none_when_flag_off` | フラグOFF時 | `ctr_metrics=None`、`ctr_suggestions=[]` |

### 6.3 リグレッション対策

- `make test-unit` で `tests/unit/easy_mode/` 全体が緑
- `make test-contract` で `tests/contract/test_ctr_contract.py` が緑
- フラグOFFでは `tests/e2e/test_spine_end_to_end.py` に影響しないことを確認

## 7. 完了定義（パート1）

- `ENABLE_CTR_WIRING` が既定OFFで設定追加済み
- `src/easy_mode/hooks.py` に `evaluate_ctr` / `generate_ctr_suggestions` 実装済み
- `CTRMetrics` モデル実装済み
- `GenerationResponse` に `ctr_metrics` / `ctr_suggestions` 追加済み
- ユニットテスト・契約テストが緑
- `make verify` が通過

---

案2 パート2（フロントエンドUI）へ進みます。準備でき次第お知らせください。