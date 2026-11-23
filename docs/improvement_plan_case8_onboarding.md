# AutoNovel 改善案8：「カクヨムランキング上位を狙う」初心者オンボーディング（パート1：バックエンド導線）

## 1. 概要

- **目的**: 初回アクセス時に「カクヨムでランキング上位を狙う」モードを選択し、ジャンル・タグ・タイトル・更新スケジュール・投稿チェックをガイド付きウィザードで設定。ツール導入からカクヨム投稿までの「最初の一歩」を迷わせない。
- **既存資産**: `/welcome`（入口選択）、`/app/easy`（2手順）、`SubmissionChecklist.tsx`（投稿前セーフティチェック）、`PublishAssistantModal.tsx`（整形＋コピー）、`kakuyomu.py`（カクヨム形式整形・投稿画面URL返却）
- **スコープ**: 初回オンボーディングフローの新設（「カクヨム上位狙い」モード）、ジャンル・タグ推奨セットのデータ化、投稿チェックリストの執筆画面常時表示、整形→投稿画面URLワンクリック誘導。フラグ `ENABLE_ONBOARDING_KAKUYOMU_MODE`（既定 OFF）で制御。
- **実装方針**: フラグOFFで現行挙動とバイト同一。契約テスト対象。

## 2. 実装対象ファイル一覧

| # | ファイルパス | 役割 | 変更種別 |
|:---|:---|:---|:---|
| 1 | `src/infrastructure/config/settings.py` | 環境変数 `ENABLE_ONBOARDING_KAKUYOMU_MODE` 追加 | 設定 |
| 2 | `src/config/kakuyomu_ranking_presets.py` | 新規。カクヨム上位向けジャンル・タグ・タイトル構文・あらすじテンプレート | 新規（設定データ） |
| 3 | `src/backend/routers/easy_mode.py` | オンボーディングモード応答エンドポイント追加 | API |
| 4 | `src/backend/routers/platform_export.py` | カクヨム整形パッケージエクスポートエンドポイント追加 | API |
| 5 | `frontend/src/pages/WelcomePage.tsx` | 「カクヨムランキング上位を狙う」モード選択追加 | UI |
| 6 | `frontend/src/pages/EasyModePage.tsx` | 投稿チェックリスト常時表示、整形→投稿URL誘導追加 | UI |
| 7 | `tests/unit/test_kakuyomu_ranking_presets.py` | 新規。プリセットデータの妥当性テスト | テスト |
| 8 | `tests/contract/test_onboarding_contract.py` | 新規。フラグOFF時バイト同一契約テスト | テスト |

## 3. 環境変数（settings.py）

```python
# src/infrastructure/config/settings.py の末尾付近に追加
ENABLE_ONBOARDING_KAKUYOMU_MODE: bool = False  # 既定OFF。ONでカクヨム上位狙いオンボーディングを有効化
```

## 4. 設定データ新規（`src/config/kakuyomu_ranking_presets.py`）

カクヨム上位作品に共通するジャンル・タグ・タイトル構文・あらすじテンプレートをデータ化。

```python
from __future__ import annotations

from typing import Any


class KakuyomuRankingPreset(BaseModel):
    genre: str
    recommended_tags: list[str]
    title_patterns: list[str]  # タイトル構文テンプレート
    synopsis_template: str  # あらすじテンプレート
    target_word_count_per_ep: int  # 1話あたり目標文字数
    update_frequency_recommendation: str  # 更新頻度推奨


KAKUYOMU_RANKING_PRESETS: dict[str, KakuyomuRankingPreset] = {
    "cheat_tensei": KakuyomuRankingPreset(
        genre="異世界転生",
        recommended_tags=["異世界転生", "チート", "成り上がり", "ざまぁ"],
        title_patterns=[
            "【追放】〜されたので、〜",
            "実は世界最強の〜、勘違いされて無双",
            "転生したら最強チート持ちでした",
        ],
        synopsis_template=(
            "理不尽な追放にあった主人公が、隠されたチート能力を覚醒。\n"
            "元の仲間をざまぁしながら、新天地で無双する成り上がり物語。"
        ),
        target_word_count_per_ep=3000,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
    "villainess": KakuyomuRankingPreset(
        genre="悪役令嬢",
        recommended_tags=["悪役令嬢", "婚約破棄", "溺愛", "ざまぁ"],
        title_patterns=[
            "婚約破棄された悪役令嬢は、〜で逆転する",
            "破滅フラグを回避して、隣国王子に溺愛される",
        ],
        synopsis_template=(
            "乙女ゲームの悪役令嬢に転生した主人公が、\n"
            "破滅フラグを回避し、周囲の溺愛を勝ち取る物語。"
        ),
        target_word_count_per_ep=2500,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
    "dungeon_stream": KakuyomuRankingPreset(
        genre="ダンジョン配信",
        recommended_tags=["ダンジョン", "配信", "現代ダンジョン", "無自覚無双"],
        title_patterns=[
            "底辺配信者が隠し部屋で最強スキル覚醒",
            "同接1人から始めるダンジョン配信、気づけばトレンド1位",
        ],
        synopsis_template=(
            "ダンジョン配信で同接1人の絶望的な配信者が、\n"
            "隠し部屋でユニークスキルを覚醒。配信切り忘れでバズり、無双する。"
        ),
        target_word_count_per_ep=2800,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
}
```

## 5. 実装ステップ（パート1：バックエンド）

### ステップ8-1: 設定値追加（`src/infrastructure/config/settings.py`）

`ENABLE_ONBOARDING_KAKUYOMU_MODE` 環境変数を既定 `False` で追加。

### ステップ8-2: プリセットデータ新規（`src/config/kakuyomu_ranking_presets.py`）

上記 `KAKUYOMU_RANKING_PRESETS` を実装。

### ステップ8-3: オンボーディングエンドポイント（`src/backend/routers/easy_mode.py`）

`GET /easy_mode/onboarding-presets` 追加。フラグON時のみプリセット一覧を返す。OFF時は空リスト。

### ステップ8-4: カクヨム整形エクスポートエンドポイント（`src/backend/routers/platform_export.py` または既存）

`POST /easy_mode/export-kakuyomu-package/{book_id}` 追加。本文・タイトル・あらすじ・タグ・表紙を整形したZIPを返す。投稿画面URLも併記。

## 6. テスト計画（パート1）

### 6.1 ユニットテスト（新規 `tests/unit/test_kakuyomu_ranking_presets.py`）

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `test_preset_has_required_fields` | 各プリセット | 必須フィールド（genre, recommended_tags, title_patterns等）が全て存在 |
| `test_cheat_tensei_tags_include_exile` | cheat_tenseiプリセット | `recommended_tags` に「追放」または「ざまぁ」含む |
| `test_target_word_count_positive` | 各プリセット | `target_word_count_per_ep` が正の整数 |

### 6.2 契約テスト（新規 `tests/contract/test_onboarding_contract.py`）

| テスト名 | 条件 | 期待結果 |
|:---|:---|:---|
| `test_flag_off_presets_empty` | `ENABLE_ONBOARDING_KAKUYOMU_MODE=False` | プリセット一覧が空リスト |
| `test_flag_on_presets_non_empty` | `ENABLE_ONBOARDING_KAKUYOMU_MODE=True` | プリセット一覧が1件以上 |

### 6.3 リグレッション対策

- `make test-unit` で `tests/unit/` 全体が緑
- `make test-contract` で `tests/contract/` 全体が緑
- フラグOFFでは既存の `/easy_mode/generate` 等に影響しないことを確認

## 7. 完了定義（パート1）

- `ENABLE_ONBOARDING_KAKUYOMU_MODE` が既定OFFで設定追加済み
- `src/config/kakuyomu_ranking_presets.py` に 3ジャンル以上のプリセット実装済み
- オンボーディングエンドポイント実装済み
- ユニットテスト・契約テストが緑
- `make verify` が通過

---

案8 パート2（フロントエンドUI）へ進みます。準備でき次第お知らせください。