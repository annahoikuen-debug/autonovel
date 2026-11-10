# AutoNovel 改善ロードマップ（論文根拠に基づく 9 提案）

## 概要

本ロードマップは、AutoNovel v6.0.0 に対する **9 つの論文根拠に基づく改善提案** の実装状況と優先順位を明記するものです。
提案は**実装依存関係と工数に基づく推奨順**で並べており、下から上へ実施することを推奨します。

### 完了済み提案

以下の提案は実装・テスト・ドキュメント化まで完了しています。

| # | 提案 | 実装完了日 | 関連 Plan | 主な実装成果 |
|:---|:---|:---|:---|:---|
| **9** | 評価基盤の実証的キャリブレーション（全提案の土台） | 提案 9 実装完了済み | 提案 9 実装済み | 人手相関基盤・トークン計測・閾値校正の土台 |
| **5** | 検索パイプライン実結線（HyDE・BM25/RRF・リランカー） | 2026-11-10 | `plans/PLAN_R5_RAG_WIRING_24STEPS.md` | デッドレター配線、ハイブリッド検索、HyDE、多言語リランカー、27 テスト |
| **8** | 改稿ループの部分編集統一とフィードバック永続化 | 2026-11-10 | `plans/PLAN_H8_SPAN_REVISION_26STEPS.md` | quote_patch（検証付き逐語引用置換）・audit_lessons（話横断教訓メモリ）・fail-closed prose_refiner・33 新規テスト、リグレッション 0 |

## 全提案一覧と現状

| # | 提案 | 現状 | 関連 Plan / ドキュメント | 主な実装成果 |
|:---|:---|:---:|:---|:---|
| **9** | 評価基盤の実証的キャリブレーション（全提案の土台） | **完了** | 提案 9 実装完了済み（ユーザー承認） | 人手相関基盤・トークン計測・閾値校正の土台 |
| **5** | 検索パイプライン実結線（HyDE・BM25/RRF・リランカー） | **完了（実装フェーズ）** | `plans/PLAN_R5_RAG_WIRING_24STEPS.md` | Phase A–E 完了：デッドレター配線、ハイブリッド検索、HyDE、多言語リランカー、27 テスト、docs/rag_setup.md §8 |
| **1** | GraphRAG の実装解消とエンティティ状態追跡 | 未着手 | 提案 1 は Plan 未作成 | AGE クライアントは stub のまま（`src/integrations/age_client.py`） |
| **2** | LLM-as-Judge の頑健化（全章審査・複数投票・バイアス対策） | 未着手 | 提案 2 は Plan 未作成 | 先頭3000字のみ審査・単回判定・70点ハードコードのまま |
| **3** | 単サンプル執筆から検証付きマルチサンプル生成へ | 未着手 | 提案 3 は Plan 未作成 | best-of-n なし・リテイクは温度下げ方向のみ |
| **4** | 階層的逐次要約メモリへの刷新 | 未着手 | 提案 4 は Plan 未作成 | 1話独立要約・4000字打ち切り・lost in the middle 対策なし |
| **6** | 静的ルール監査の学術指標化 | 未着手 | 提案 6 は Plan 未作成 | 7句定型リスト・標準偏差のみリズムスコア |
| **7** | 物語構造制御の一本化と本番配線 | 未着手 | `plans/PLAN_S1_STRUCTURE_CONTROL_WIRING_27STEPS.md`（構造制御関連） | SPINE_QUALITY=off 既定・narrative_balancer 未配線のまま |
| **8** | 改稿ループの部分編集統一とフィードバック永続化 | **完了** | `plans/PLAN_H8_SPAN_REVISION_26STEPS.md` | quote_patch（検証付き逐語引用置換）・audit_lessons（話横断教訓メモリ）・fail-closed prose_refiner・26 ステップ・33 新規テスト、リグレッション 0 |

**推奨実装順**: 9（完了）→ 5（完了）→ 8（完了）→ 1 → 2 → 3 → 4 → 6 → 7（工数・リスク勘案）

---

## 提案 5（検索パイプライン実結線）実装記録

実装日: 2026-11-09 〜 2026-11-10（Phase A–E 完了）

### 完了フェーズ

| Phase | 範囲 | 状態 | 主な変更ファイル |
|:---|:---|:---:|:---|
| **A** | 計測・契約 | ✅ 完了 | `src/backend/observability/metrics.py`（RAG メトリクス 5 種）、`src/infrastructure/config/settings.py`（新設定 8 件）、`docs/STATUS.md` §8（baseline）、`tests/contract/fixtures/...golden` |
| **B** | デッドレター配線（核心） | ✅ 完了 | `src/agents/prompt_composer.py`（`_format_rag_context`）、`prompts/manager.py`、`prompts/templates/narrative/final_writing_prompt.j2` |
| **C** | ハイブリッド検索実結線 | ✅ 完了 | `src/integrations/rag/bm25_index.py`（新規、`EpisodeBM25Index`）、`src/integrations/rag/factory.py`（新規、`build_reflective_rag`）、`src/integrations/rag/reflective_rag.py`（to_thread 化・閾値分離）、`src/integrations/rag/query_composer.py`（新規、`QueryComposer`）、`src/agents/context_builder_agent.py`、`src/backend/tasks/generation_tasks.py` |
| **D** | 本物の HyDE | ✅ 完了 | `src/integrations/rag/query_reformulator.py`（`generate_hypothetical_chunk_async`）、`reflective_rag.py`（2-クエリ RRF） |
| **E** | リランカー有効化 | ✅ 完了 | `settings.py`（`RERANKER_MODEL=BAAI/bge-reranker-v2-m3`）、`src/integrations/rag/reranker.py`（fail-open）、`src/integrations/rag/rag_service.py`（レイテンシメトリクス）、`reflective_rag.py`（`rerank_score` メタデータ） |

### テスト（リグレッション防止）

- 新規テスト 27 件すべて緑（`tests/unit/integrations/rag/`、`tests/regression/test_rag_fail_open.py`、`tests/contract/test_rag_prompt_injection.py`、`tests/unit/agents/test_prompt_composer_rag_context.py`）
- 既存テスト（影響範囲 476 件）すべて緑。リグレッションなし。
- **契約**: フラグ全 OFF（既定）では執筆プロンプトがバイト単位で不変（CI で常時検証）

### 残務（運用フェーズ）

| 項目 | 内容 | 依存 |
|:---|:---|:---|
| **F1** | AB 測定：4 条件 × 3 書籍 × 20 話（off / B のみ / B+C / B+C+D+E） | 提案 9 の評価基盤 |
| **F2** | 人手相関検証：RAG on で `character_consistency` の相関が上がるか | 提案 9 の校正データセット |
| **F3** | 既定フラグ決定：`character_consistency` +2.0 点以上・コスト増 +5% 以内・レイテンシ p95 +1s 以内 を満たしたフラグのみ `true` へ | F1/F2 の結果 |

---

## 提案 8（改稿ループの部分編集統一とフィードバック永続化）実装記録

実装日: 2026-11-10（Phase A–F 完了）

### 完了フェーズ

| Phase | 範囲 | 状態 | 主な変更ファイル |
|:---|:---|:---:|:---|
| **A** | 計測・契約 | ✅ 完了 | `src/backend/observability/metrics.py`（改稿/教訓メトリクス 4 種）、`docs/STATUS.md` §10（baseline）、`tests/contract/fixtures/lessons_prompt_baseline/final_writing_prompt.j2.golden` |
| **B** | quote 置換コア（核心） | ✅ 完了 | `src/audit/span_revision.py`（新規、`QuotePatch`/`find_quote_span`/`apply_quote_patches`）、`src/agents/audit_agent/agent.py`（`_try_quote_patch` + `try_local_patch` 統合）、`src/agents/audit_agent/config.py`（`is_quote_patch_enabled` 他）、`src/backend/workflows/writing_langgraph.py`（`node_healing` 構造化置換化） |
| **C** | 監査出力の structured 化 | ✅ 完了 | `src/agents/prompts/unified_audit_prompt.py`（`actionable_patch` を `original_quote`/`replacement`/`rationale` オブジェクト化）、`src/models/unified_audit.py`（`actionable_quote`/`actionable_replacement` 追加）、`src/agents/specialists/unified_auditor.py`（構造化パース・`_build_conflicts` 接続） |
| **D** | fail-closed 化 | ✅ 完了 | `src/agents/writing/prose_refiner_agent.py`（LLM 欠如時 `response = prompt` を削除、`RuntimeError` 送出→原文返却） |
| **E** | 教訓メモリ（Reflexion 型） | ✅ 完了 | `src/backend/database/models_lessons.py`（新規、`AuditLessonModel`）、`src/backend/alembic/versions/0035_audit_lessons.py`（新規）、`src/audit/lesson_store.py`（新規、`AuditLessonRepository`/`AuditLessonService`）、`src/agents/context_builder_agent.py`（`audit_lessons_ctx` 取得）、`src/agents/prompt_composer.py`（`lessons_block`/`_format_audit_lessons`）、`prompts/manager.py`（`lessons_block` コンテキスト渡し）、`prompts/templates/narrative/final_writing_prompt.j2`（`{% if lessons_block %}` ガード内注入） |
| **F** | 検証・ロールアウト | ✅ 完了（フラグ既定OFF） | 実装・テスト完了。フラグ `ENABLE_AUDIT_QUOTE_PATCH` / `ENABLE_AUDIT_LESSONS` とも既定 OFF（off=現行挙動・バイト同一契約）。**F1-F3 の運用詳細は `plans/PLAN_H8F_ROLLOUT_12STEPS.md` へ移管**（Shadow 計測 → AB 検証 → 既定値判定の 12 ステップ） |

### テスト（リグレッション防止）

- 新規テスト 33 件すべて緑（`tests/unit/test_quote_replacer.py` 18 件、`tests/unit/audit/test_lesson_store.py` 10 件、`tests/unit/audit/test_lesson_formatter.py` 8 件、`tests/unit/agents/test_audit_lesson_hooks.py` 4 件、`tests/unit/writing/test_prose_refiner_fail_closed.py` 3 件、`tests/contract/test_h8_lessons_prompt_injection.py` 3 件）
- 既存テスト（影響範囲 228 件）すべて緑。リグレッションなし（8 件の既存失敗は `git stash` 検証により変更前からのものと確認）。
- **契約**: フラグ全 OFF（既定）では改稿・教訓経路の挙動をバイト単位で不変（`tests/contract/test_v6_audit_surgical_patch.py` / `test_h8_lessons_prompt_injection.py` で CI 常時検証）

### 学術的根拠

| 設計判断 | 論文根拠 |
|:---|:---|
| 追記型パッチ廃止 → 検証付き span 置換 | Yang et al. 2022 "Re3"（EMNLP Findings）：局所再プロンプティングが全文再生成より一貫性・コストで優れる |
| `original_quote` 必須の具体的フィードバック | Madaan et al. 2023 "Self-Refine"（NeurIPS）：具体的・位置特定付きフィードバックが反復改善を有効にする |
| 失敗教訓の話横断永続化・次話注入 | Shinn et al. 2023 "Reflexion"（NeurIPS）：失敗の言語化フィードバックを記憶に永続化し次試行に注入すると成功率が大幅上昇 |
| 置換適用の機械的検証 | 既存 `SpanPatchApplier`（W4 Step 5）の方針継承。無検証埋め込みは破壊的縮小を許してきた |
| 短期・少数の教訓と卒業 | Liu et al. TACL "Lost in the Middle"：コンテキスト両端以外は活かされない。少数精鋭を注入 |

---

## 残り提案への着手推奨（短期）

1. **提案 1（GraphRAG 実装解消）** — `src/integrations/age_client.py` の stub 解消、`graph_pipeline.py` の upsert 永続化、コミュニティ検出導入。長編一貫性（Re3 論文）の根幹。
2. **提案 2（LLM-as-Judge 頑健化）** — 先頭3000字制限撤廃・全章審査・k=3 多数決・70点/定型<3 を設定ファイル化。提案 9 の校正と連動。

---

## 関連ドキュメント

| 文書 | 内容 |
|:---|:---|
| `plans/PLAN_R5_RAG_WIRING_24STEPS.md` | 提案 5 の詳細実装計画（24 ステップ・テスト計画込み） |
| `plans/PLAN_H8_SPAN_REVISION_26STEPS.md` | 提案 8 の詳細実装計画（26 ステップ・テスト計画込み） |
| `plans/PLAN_H8F_ROLLOUT_12STEPS.md` | 提案 8 のフラグ運用ロールアウト計画（Shadow 計測・AB 検証・既定値判定・12 ステップ） |
| `docs/STATUS.md` §8 | 提案 5 実装前の baseline 記録（SSOT） |
| `docs/STATUS.md` §10 | 提案 8 実装前の baseline 記録（SSOT） |
| `docs/rag_setup.md` §8 | 提案 5 の新規環境変数・配線概要・契約 |
| `docs/architecture.md` | 4 層アーキテクチャ設計 |
| `README.md:699` | 設計・ロードマップ（36 ステップ計画書） |
