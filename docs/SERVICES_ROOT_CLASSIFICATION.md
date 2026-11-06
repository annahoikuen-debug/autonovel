# src/services/ ルートファイル分類表 (SERVICES_ROOT_CLASSIFICATION.md)

> **目的**: `src/services/` 直下に残存する 88 個の .py ファイルを、「移設する / ルートに残す」に分類し、Phase B の移動計画を確定する。
>
> **作成**: Phase B Step B1
> **分類基準**: src/ と tests/ 内での参照数（`services.<モジュール名>` の文字列出現数）を基に、単一レイヤーに属するものは対応先パッケージへ移設し、横断ユーティリティや参照数が少ないものはルートに残置する。

---

## 分類方針

| 参照数 | 判断 | 根拠 |
|--------|------|------|
| ≥ 10 | **移設対象** | 複数ファイルから参照されており、単一レイヤーに属する可能性が高い |
| 3-9 | **個別判断** | 横断ユーティリティならルート残置、単一レイヤーなら移設 |
| 0-2 | **ルート残置** | 参照が少ないため、移設コストよりルート残置の方が適切 |

---

## 移設対象 (参照数 ≥ 10) — Phase B Step B2-B3 で移動

| # | ファイル | 参照数 | 推奨移動先 | 根拠 |
|---|---------|--------|-----------|------|
| 1 | `rag_service.py` | 26 | `src/integrations/rag/rag_service.py` | RAG は外部連携 → integrations |
| 2 | `audit_aggregator.py` | 22 | `src/engine/audit/aggregator.py` | 監査は生成系 → engine |
| 3 | `book_score_service.py` | 21 | `src/engine/book_score/service.py` | スコア算出は生成系 → engine |
| 4 | `pipeline_base.py` | 18 | `src/engine/pipeline_base.py` | パイプライン基盤は生成系 → engine |
| 5 | `llm_service.py` | 17 | `src/llm/service.py` | LLM 統合の最終ピース → llm |
| 6 | `image_service.py` | 15 | `src/publishing/illustration/image_service.py` | 画像生成は出版系 → publishing |
| 7 | `pipeline_steps.py` | 15 | `src/engine/pipeline_steps.py` | パイプラインステップは生成系 → engine |
| 8 | `reflective_rag.py` | 13 | `src/integrations/rag/reflective_rag.py` | RAG は外部連携 → integrations |
| 9 | `auto_workflow_pipeline.py` | 12 | `src/engine/auto_workflow_pipeline.py` | ワークフローは生成系 → engine |
| 10 | `foreshadowing_service.py` | 12 | `src/engine/foreshadowing/service.py` | 伏線は生成系 → engine |
| 11 | `blind_review.py` | 11 | `src/engine/blind_review.py` | ブラインドレビューは生成系 → engine |
| 12 | `embedding_service.py` | 11 | `src/integrations/rag/embedding_service.py` | 埋め込みは RAG 系 → integrations |
| 13 | `semantic_cache.py` | 11 | `src/integrations/semantic_cache.py` | キャッシュは外部連携 → integrations |
| 14 | `age_client.py` | 10 | `src/integrations/age_client.py` | 外部 API クライアント → integrations |
| 15 | `spine_resolver.py` | 10 | `src/engine/spine_resolver.py` | 構造解決は生成系 → engine |

---

## 個別判断 (参照数 3-9)

| # | ファイル | 参照数 | 判断 | 移動先/残置 | 根拠 |
|---|---------|--------|------|-----------|------|
| 16 | `book_score_mapping.py` | 8 | 移設 | `src/engine/book_score/mapping.py` | book_score_service と同グループ |
| 17 | `graph_pipeline.py` | 8 | 移設 | `src/engine/graph_pipeline.py` | パイプラインは engine |
| 18 | `bible_service.py` | 7 | 移設 | `src/engine/bible_service.py` | 聖書サービスは生成系 → engine |
| 19 | `cost_analytics.py` | 7 | 移設 | `src/integrations/cost_guard/analytics.py` | コスト分析は外部連携 → integrations |
| 20 | `pdca_cycle.py` | 7 | 移設 | `src/engine/pdca_cycle.py` | PDCA は生成系 → engine |
| 21 | `token_tracker.py` | 7 | ルート残置 | `src/services/token_tracker.py` | 複数レイヤーから使用される横断ユーティリティ |
| 22 | `episode_context.py` | 6 | 移設 | `src/engine/episode_context.py` | エピソード文脈は生成系 → engine |
| 23 | `rag_prefetch_service.py` | 6 | 移設 | `src/integrations/rag/prefetch_service.py` | RAG 関連 → integrations |
| 24 | `redis_cache.py` | 6 | ルート残置 | `src/services/redis_cache.py` | 複数レイヤーから使用されるキャッシュ基盤 |
| 25 | `digest_service.py` | 5 | 移設 | `src/engine/digest_service.py` | ダイジェストは生成系 → engine |
| 26 | `marketing.py` | 5 | 移設 | `src/integrations/marketing/marketing.py` | マーケティングは integrations（パッケージ存在） |
| 27 | `pdca_directive.py` | 5 | 移設 | `src/engine/pdca_directive.py` | PDCA は生成系 → engine |
| 28 | `progress_reporter.py` | 5 | ルート残置 | `src/services/progress_reporter.py` | 複数レイヤーから使用される進捗レポーター |
| 29 | `structure_validator.py` | 5 | ルート残置 | `src/services/structure_validator.py` | バリデーション基盤は横断 |
| 30 | `commercial_benchmarks.py` | 4 | ルート残置 | `src/services/commercial_benchmarks.py` | 参照数少、ベンチマーク用 |
| 31 | `conflict_report_service.py` | 4 | 移設 | `src/engine/conflict_report_service.py` | 競合レポートは生成系 → engine |
| 32 | `cost_budget_guard.py` | 4 | 移設 | `src/integrations/cost_guard/budget_guard.py` | コストガードは integrations |
| 33 | `extraction_service.py` | 4 | 移設 | `src/engine/extraction_service.py` | 抽出は生成系 → engine |
| 34 | `gacha_service.py` | 4 | ルート残置 | `src/services/gacha_service.py` | 参照数少、ガチャ機能 |
| 35 | `learning_data_service.py` | 4 | 移設 | `src/integrations/learning_data_service.py` | 学習データは外部連携 → integrations |
| 36 | `next_beats_service.py` | 4 | 移設 | `src/engine/next_beats_service.py` | 次ビートは生成系 → engine |
| 37 | `promotion_service.py` | 4 | ルート残置 | `src/services/promotion_service.py` | 参照数少、プロモーション機能 |
| 38 | `proposal_isolation.py` | 4 | ルート残置 | `src/services/proposal_isolation.py` | 参照数少、隔離ロジック |
| 39 | `quality_scorer.py` | 4 | 移設 | `src/engine/quality_scorer.py` | 品質スコアは生成系 → engine |
| 40 | `resilience.py` | 4 | ルート残置 | `src/services/resilience.py` | 耐性基盤は横断ユーティリティ |
| 41 | `score_calibrator.py` | 4 | ルート残置 | `src/services/score_calibrator.py` | スコア較正は横断 |
| 42 | `audit_service.py` | 3 | 移設 | `src/engine/audit/service.py` | 監査サービスは engine |
| 43 | `book_score_models.py` | 3 | 移設 | `src/engine/book_score/models.py` | book_score と同グループ |
| 44 | `chunk_ingestion.py` | 3 | 移設 | `src/engine/chunk_ingestion.py` | チャンク取り込みは生成系 → engine |
| 45 | `default_plot_expander.py` | 3 | 移設 | `src/engine/default_plot_expander.py` | プロット展開は生成系 → engine |
| 46 | `editor_assist_service.py` | 3 | ルート残置 | `src/services/editor_assist_service.py` | 参照数少、エディタ支援 |
| 47 | `editorial_assistant_service.py` | 3 | ルート残置 | `src/services/editorial_assistant_service.py` | 参照数少 |
| 48 | `episode_writer.py` | 3 | 移設 | `src/engine/episode_writer.py` | エピソード執筆は生成系 → engine |
| 49 | `erotic_afterglow_evaluator.py` | 3 | ルート残置 | `src/services/erotic_afterglow_evaluator.py` | NSFW 関連は config/erotic_* に近い扱い |
| 50 | `erotic_density_controller.py` | 3 | ルート残置 | `src/services/erotic_density_controller.py` | NSFW 関連 |
| 51 | `erotic_diversity_score.py` | 3 | ルート残置 | `src/services/erotic_diversity_score.py` | NSFW 関連 |
| 52 | `experiment_allocator.py` | 3 | ルート残置 | `src/services/experiment_allocator.py` | 実験割り当ては横断 |
| 53 | `hook_diagnoser.py` | 3 | 移設 | `src/engine/hook_diagnoser.py` | フック診断は生成系 → engine |
| 54 | `prompt_version_service.py` | 3 | ルート残置 | `src/services/prompt_version_service.py` | 参照数少 |
| 55 | `query_reformulator.py` | 3 | 移設 | `src/integrations/rag/query_reformulator.py` | クエリ再構築は RAG 系 → integrations |
| 56 | `reranker.py` | 3 | 移設 | `src/integrations/rag/reranker.py` | リランカーは RAG 系 → integrations |
| 57 | `retry_decorator.py` | 3 | ルート残置 | `src/services/retry_decorator.py` | リトライデコレータは横断ユーティリティ |
| 58 | `rrf_fusion.py` | 3 | 移設 | `src/integrations/rag/rrf_fusion.py` | RRF 融合は RAG 系 → integrations |
| 59 | `safe_replace.py` | 3 | ルート残置 | `src/services/safe_replace.py` | 安全置換は横断 |
| 60 | `state_manager.py` | 3 | ルート残置 | `src/services/state_manager.py` | 状態管理は横断 |
| 61 | `style_distiller.py` | 3 | 移設 | `src/publishing/formatters/style_distiller.py` | 文体蒸留は出版系 → publishing |
| 62 | `text_chunker.py` | 3 | 移設 | `src/engine/text_chunker.py` | テキストチャンクは生成系 → engine |

---

## ルート残置 (参照数 0-2)

| # | ファイル | 参照数 | 根拠 |
|---|---------|--------|------|
| 63 | `audit_adapter.py` | 2 | 監査アダプタは engine 側にも shim 経由でアクセス可能 |
| 64 | `cadence_reformatter.py` | 2 | cadence は engine/cadence/ に shim あり |
| 65 | `content_processor.py` | 2 | コンテンツ処理は汎用 |
| 66 | `errors.py` | 2 | エラー定義は横断ユーティリティ |
| 67 | `graphrag_sync_service.py` | 2 | RAG 同期は integrations 側に shim あり |
| 68 | `hybrid_retriever.py` | 2 | ハイブリッド検索は integrations 側に shim あり |
| 69 | `narrative_scoring_service.py` | 2 | ナラティブスコアは汎用 |
| 70 | `pipeline_param_mapper.py` | 2 | パイプラインパラメータマッピングは汎用 |
| 71 | `plot_service.py` | 2 | プロットサービスは汎用 |
| 72 | `preset_loader.py` | 2 | プリセット読み込みは汎用 |
| 73 | `prompt_comparison.py` | 2 | プロンプト比較は汎用 |
| 74 | `report_generator.py` | 2 | レポート生成は汎用 |
| 75 | `reproducibility.py` | 2 | 再現性は横断ユーティリティ |
| 76 | `sparse_retriever.py` | 2 | スパース検索は integrations 側に shim あり |
| 77 | `bias_correction.py` | 1 | バイアス補正は汎用 |
| 78 | `data_loader.py` | 1 | データローダーは汎用 |
| 79 | `foreshadowing_id_generator.py` | 1 | 伏線ID生成は engine 側に shim あり |
| 80 | `foreshadowing_parser.py` | 1 | 伏線パーサは engine 側に shim あり |
| 81 | `hook_templates.py` | 1 | フックテンプレートは汎用 |
| 82 | `novel_producer.py` | 1 | 小説プロデューサーは汎用 |
| 83 | `prompt_caching.py` | 1 | プロンプトキャッシュは汎用 |
| 84 | `prompt_registry.py` | 1 | プロンプトレジストリは汎用 |
| 85 | `script_watcher.py` | 1 | スクリプト監視は汎用 |
| 86 | `series_serializer.py` | 1 | シリーズシリアライザは汎用 |
| 87 | `spice_guard_adapter.py` | 1 | スパイスガードは NSFW 関連 |
| 88 | `ncs_calibration.py` | 0 | 参照なし、削除またはルート残置検討 |

---

## 移動先ディレクトリ一覧 (作成予定)

- `src/engine/audit/` (aggregator, service)
- `src/engine/book_score/` (service, mapping, models)
- `src/engine/` (pipeline_base, pipeline_steps, auto_workflow_pipeline, blind_review, spine_resolver, episode_context, digest_service, pdca_cycle, pdca_directive, conflict_report_service, next_beats_service, hook_diagnoser, text_chunker, chunk_ingestion, default_plot_expander, episode_writer)
- `src/engine/foreshadowing/` (service) ※Step A3 で既に shim 作成済み
- `src/llm/service.py` ※llm_service.py
- `src/publishing/illustration/image_service.py` ※Step A3 で illustration shim 作成済み
- `src/publishing/formatters/style_distiller.py`
- `src/integrations/rag/` (rag_service, reflective_rag, embedding_service, prefetch_service, query_reformulator, reranker, rrf_fusion)
- `src/integrations/semantic_cache.py`
- `src/integrations/age_client.py`
- `src/integrations/cost_guard/` (analytics, budget_guard)
- `src/integrations/marketing/` (marketing.py) ※Step A3 で marketing shim 作成済み
- `src/integrations/learning_data_service.py`

---

## ルート残置ファイル数 (目標)

移設後、`src/services/` ルートに残るファイル数は **約 30-35 個** となる見込み（横断ユーティリティ + 参照数少ファイル）。

---

## Step B1 完了条件

- `docs/SERVICES_ROOT_CLASSIFICATION.md` が上記内容で作成されていること
- 88ファイルすべてが表に記載されていること
