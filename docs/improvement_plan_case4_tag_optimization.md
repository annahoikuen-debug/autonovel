# AutoNovel 改善案4：タグ最適化＋トレンド構文タイトル推薦（実装計画書）

## 1. 概要

- **目的**: 初心者が「どのタグを付ければカクヨムの検索にヒットするか」を迷わず選べるようにする。タグは検索・ランキング流入の決定要因。
- **既存資産**: 案8で実装済みの `KAKUYOMU_RANKING_PRESETS`（ジャンル別 `recommended_tags` 含む）を**そのまま再利用**する。案2で配線済みの `trend_syntax_extractor` と組み合わせる。
- **スコープ**: 生成ジャンルからプリセット推奨タグ＋トレンド構文に基づくタグ候補を提案し、`GenerationResponse.tag_suggestions` として返す。フロントエンドは SimpleModePanel にタグ提案パネルを追加（ワンクリックでジャンル選択に反映）。
- **実装方針**: 案1・2と同一パターン。フラグ `ENABLE_TAG_WIRING`（既定 OFF）、OFF時バイト同一契約、テスト充実。

## 2. 対象ファイル一覧

| # | ファイルパス | 役割 | 変更種別 |
|:---|:---|:---|:---|
| 1 | `src/infrastructure/config/settings.py` | 環境変数 `ENABLE_TAG_WIRING` 追加 | 設定 |
| 2 | `src/easy_mode/hooks.py` | `generate_tag_suggestions` / `suggest_syntax_labels` 関数追加 | 変更 |
| 3 | `src/easy_mode/pipeline.py` | タグ提案配線追加 | 変更 |
| 4 | `src/domain/entities/easy_mode.py` | `GenerationResponse.tag_suggestions` 追加 | 変更 |
| 5 | `frontend/src/components/generate/SimpleModePanel.tsx` | タグ提案パネル追加 | UI |
| 6 | `frontend/src/components/GeneratePanel.tsx` | プロパティ渡し | UI |
| 7 | `tests/unit/easy_mode/test_tag_wiring.py` | ユニットテスト | 新規 |
| 8 | `tests/contract/test_tag_contract.py` | 契約テスト | 新規 |

## 3. 設計

### 3.1 設定

```python
ENABLE_TAG_WIRING: bool = False  # 既定OFF。ONでタグ最適化を配線
```

### 3.2 タグ提案ロジック（`hooks.py`）

- `resolve_preset_key(genre)` で UI ジャンル → プリセットキー解決（既存 `genre_registry` 再利用）
- `KAKUYOMU_RANKING_PRESETS[preset_key].recommended_tags` を第1候補にする
- キーワード（`keywords`）があれば追加候補に統合（重複除去、最大10件）
- ジャンルがプリセット未解決の場合は空リスト

### 3.3 API

`GenerationResponse` に `tag_suggestions: list[str] = Field(default_factory=list)` を追加（Optional だが既定空リストで契約維持）。

## 4. テスト計画

| テスト | 条件 | 期待結果 |
|:---|:---|:---|
| `test_flag_off_empty` | フラグOFF | 空リスト |
| `test_cheat_tensei_tags` | cheat_tensei プリセット解決 | 「異世界転生」「チート」等を含む |
| `test_unknown_genre_empty` | 未解決ジャンル | 空リスト |
| `test_keywords_merged_dedup` | キーワード統合 | 重複なし・10件以下 |
| `test_contract_optional_field` | 未指定 | 既定空リストでバイト同一 |

## 5. 完了定義

- ruff / format / mypy / レイヤー境界が緑
- 新規テスト全緑、easy_mode 既存テスト（265件）リグレッションなし
- フロント typecheck / lint 0 エラー
