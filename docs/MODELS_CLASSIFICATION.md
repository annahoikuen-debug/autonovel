# モデル分類 (MODELS_CLASSIFICATION.md)

> **目的**: `src/models/` の48ファイルを「DBモデル」と「APIスキーマ」に分類し、
> 今後の移動・統合計画の基礎とする。

---

## 分類結果

### DBモデル (5ファイル) - SQLAlchemy やリポジトリ層と密接に関連

| ファイル | 内容（推定） |
|----------|-------------|
| `src/models/character.py` | キャラクターDBモデル |
| `src/models/editor.py` | エディタ関連DBモデル |
| `src/models/graph_schemas.py` | グラフDBスキーマ |
| `src/models/narrative_metrics_db.py` | ナラティブメトリクスDBモデル |

### APIスキーマ (30ファイル) - Pydantic BaseModel

| ファイル | 内容（推定） |
|----------|-------------|
| `src/models/api_schemas.py` | API共通スキーマ |
| `src/models/audit.py` | 監査スキーマ |
| `src/models/base.py` | ベースモデル |
| `src/models/beat_sheet.py` | ビートシートスキーマ |
| `src/models/bible.py` | 聖書（設定集）スキーマ |
| `src/models/billing.py` | 課金スキーマ |
| `src/models/character_flaw.py` | キャラクター欠陥スキーマ |
| `src/models/character_voice_profile.py` | キャラクターボイススキーマ |
| `src/models/context.py` | コンテキストスキーマ |
| `src/models/db.py` | DBモデル共通スキーマ |
| `src/models/emotional_hook.py` | 感情フックスキーマ |
| `src/models/ensemble_foreshadowing.py` | アンサンブル伏線スキーマ |
| `src/models/entertainment_check.py` | エンタメチェックスキーマ |
| `src/models/generation_progress.py` | 生成進捗スキーマ |
| `src/models/marketing.py` | マーケティングスキーマ |
| `src/models/marketing_ctr.py` | マーケティングCTRスキーマ |
| `src/models/narrative_metrics.py` | ナラティブメトリクススキーマ |
| `src/models/opening_booster.py` | オープニングブースタースキーマ |
| `src/models/patch_pdca.py` | パッチPDCAスキーマ |
| `src/models/planning_config.py` | 企画設定スキーマ |
| `src/models/predicate_match.py` | 述語マッチングスキーマ |
| `src/models/prompt_version.py` | プロンプトバージョンスキーマ |
| `src/models/prose_refinement.py` | プロセス洗練スキーマ |
| `src/models/publishing_assistant.py` | 出版アシスタントスキーマ |
| `src/models/report.py` | レポートスキーマ |
| `src/models/sharp_edge.py` | シャープエッジスキーマ |
| `src/models/social_reaction.py` | ソーシャル反応スキーマ |
| `src/models/style_profile.py` | スタイルプロファイルスキーマ |
| `src/models/subversion.py` | サブバージョンスキーマ |
| `src/models/unified_audit.py` | 統合監査スキーマ |
| `src/models/user.py` | ユーザースキーマ |
| `src/models/visual_key_scene.py` | 視覚キースシーンスキーマ |
| `src/models/world.py` | ワールドスキーマ |
| `src/models/writing.py` | ライティングスキーマ |
| `src/models/writing_metadata.py` | ライティングメタデータスキーマ |

### 不明 (9ファイル) - 個別確認が必要

| ファイル | 判定が必要な理由 |
|----------|----------------|
| `src/models/__init__.py` | パッケージ初期化 |
| `src/models/foreshadowing.py` | 伏線モデル/スキーマのどちらか |
| `src/models/foreshadowing_status.py` | スキーマかDBモデルか |
| `src/models/hook.py` | フックモデル/スキーマのどちらか |
| `src/models/illustration.py` | イラストモデル/スキーマのどちらか |
| `src/models/illustration_point.py` | イラストポイントモデル/スキーマのどちらか |
| `src/models/plot.py` | プロットモデル/スキーマのどちらか |
| `src/models/production_config.py` | プロダクション設定 |
| `src/models/task.py` | タスクモデル/スキーマのどちらか |

---

## 移動方針（Step 31-32 で詳細設計）

- DBモデル（5ファイル）→ `src/domain/models/` または `src/infrastructure/database/models/` に移動候補
- APIスキーマ（30ファイル）→ `src/domain/schemas/` または `src/application/dtos/` に移動候補
- 不明ファイル→ 個別確認後に判断

### src/backend/schemas/ の棚卸し結果

| ファイル | サイズ | src/models/ との重複 | 判断 |
|----------|--------|---------------------|------|
| `branch.py` | 2,656 bytes | `src/domain/models/branch.py` | 重複あり - 統合検討 |
| `branch_play.py` | 2,044 bytes | なし | 独立スキーマ |
| `illustrations.py` | 2,008 bytes | `src/models/illustration.py` | 重複あり - 統合検討 |
| `multimedia.py` | 3,781 bytes | なし | 独立スキーマ |
| `pipeline_events.py` | 396 bytes | なし | 独立スキーマ |
| `problem_details.py` | 1,079 bytes | なし | 独立スキーマ |

重複ファイル（branch.py, illustrations.py）は、Step 32 以降で `src/domain/schemas/` または `src/domain/models/` と統合するか、片方を shim にして整理する。
