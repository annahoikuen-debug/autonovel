# AutoNovel 改善案1・2・8：実装順序と統合チェックリスト

## 1. 実装順序（推奨）

| 順序 | 項目 | 内容 | 所要時間目安 |
|:---|:---|:---|:---|
| 1 | **案1 パート1**（バックエンド配線） | `settings.py` 設定追加、`seq_hook.py` モデル、`hooks.py` フック制御、`easy_mode/pipeline.py` 配線、`easy_mode.py` API応答拡張 | 半日〜1日 |
| 2 | **案1 パート2**（フロントエンドUI） | `EasyModePage.tsx` に `HookMetricsPanel` 追加 | 半日 |
| 3 | **案2 パート1**（バックエンド配線） | `settings.py` 設定追加、`CTRMetrics` モデル、`hooks.py` CTR関数追加、`easy_mode.py` API応答拡張 | 半日〜1日 |
| 4 | **案2 パート2**（フロントエンドUI） | `EasyModePage.tsx` に `CTROptimizationPanel` 追加 | 半日 |
| 5 | **案8 パート1**（バックエンド導線） | `settings.py` 設定追加、`kakuyomu_ranking_presets.py` プリセットデータ、オンボーディングエンドポイント | 半日 |
| 6 | **案8 パート2**（フロントエンドUI） | `WelcomePage.tsx` モード選択、`EasyModePage.tsx` チェックリスト・投稿URL誘導 | 1日 |
| 7 | **統合テスト** | `make verify` 実行、`make frontend-test` 実行、E2E確認 | 半日〜1日 |

**合計目安**: 3.5〜5.5日（1名の場合）

## 2. 統合チェックリスト（実装前に確認）

### 2.1 設定・モデル

- [ ] `src/infrastructure/config/settings.py` に `ENABLE_SEQ_HOOK_WIRING` / `ENABLE_CTR_WIRING` / `ENABLE_ONBOARDING_KAKUYOMU_MODE` を追加（既定すべて `False`）
- [ ] `src/models/seq_hook.py` に `HookMetrics` / `CTRMetrics` を追加

### 2.2 バックエンド配線

- [ ] `src/easy_mode/hooks.py` に `should_apply_hook` / `evaluate_and_maybe_rewrite` / `build_hook_directive` / `evaluate_ctr` / `generate_ctr_suggestions` を実装
- [ ] `src/easy_mode/pipeline.py` にフック配線・CTR配線を追加
- [ ] `src/backend/routers/easy_mode.py` の `GenerationResponse` に `hook_metrics` / `ctr_metrics` / `ctr_suggestions` を追加
- [ ] `src/config/kakuyomu_ranking_presets.py` に 3ジャンル以上のプリセットを実装
- [ ] `src/backend/routers/easy_mode.py` に `GET /easy_mode/onboarding-presets` を追加
- [ ] `src/backend/routers/platform_export.py` にカクヨム整形エクスポートエンドポイントを追加

### 2.3 フロントエンドUI

- [ ] `frontend/src/pages/EasyModePage.tsx` に `HookMetricsPanel` 追加
- [ ] `frontend/src/pages/EasyModePage.tsx` に `CTROptimizationPanel` 追加
- [ ] `frontend/src/pages/WelcomePage.tsx` に「カクヨムランキング上位を狙う」モード選択追加
- [ ] `frontend/src/pages/EasyModePage.tsx` に投稿チェックリスト・整形→投稿URL誘導追加

### 2.4 テスト

- [ ] `tests/unit/easy_mode/test_seq_hook_wiring.py` 作成・緑
- [ ] `tests/contract/test_seq_hook_contract.py` 作成・緑
- [ ] `tests/unit/easy_mode/test_ctr_wiring.py` 作成・緑
- [ ] `tests/contract/test_ctr_contract.py` 作成・緑
- [ ] `tests/unit/test_kakuyomu_ranking_presets.py` 作成・緑
- [ ] `tests/contract/test_onboarding_contract.py` 作成・緑
- [ ] `frontend/src/components/easy_mode/__tests__/HookMetricsPanel.test.tsx` 作成・緑
- [ ] `frontend/src/components/easy_mode/__tests__/CTROptimizationPanel.test.tsx` 作成・緑
- [ ] `frontend/src/components/onboarding/__tests__/KakuyomuModeButton.test.tsx` 作成・緑
- [ ] `frontend/src/components/easy_mode/__tests__/SubmissionChecklistInline.test.tsx` 作成・緑

### 2.5 品質ゲート

- [ ] `make test`（pytest）が緑
- [ ] `make test-unit` が緑
- [ ] `make test-contract` が緑
- [ ] `make frontend-test` が緑
- [ ] `make frontend-lint` が緑
- [ ] `make verify` が緑（ci-parity → lint-layers → typecheck → test-contract → test-migration）

## 3. リグレッション防止のポイント

| リスク | 対策 |
|:---|:---|
| フラグON時に既存生成プロンプトが変わる | フラグOFF契約テストでバイト同一を保証。ONは新規分岐のみ |
| EasyModePipeline のレスポンス schema 変更で既存クライアントが壊れる | 新規フィールドはすべて `Optional` / `default=None` にし、後方互換を維持 |
| フロントエンド型不一致 | `make frontend-type:sync` で OpenAPI 型を再生成後、TS 型を同期 |
| カクヨム整形エクスポートで既存エクスポートが壊れる | 新規エンドポイントを追加。既存 `GET /easy_mode/export/{book_id}` は変更しない |

## 4. 完了定義（全案統合）

- [ ] 案1・2・8 の全パート実装完了
- [ ] 全テスト（バックエンド単体・契約・フロントエンド単体・lint）が緑
- [ ] `make verify` が緑
- [ ] フラグOFFでは現行挙動とバイト単位同一（契約テストで保証）
- [ ] ドキュメント `docs/improvement_plan_case*.md` が実装と整合

---

以上で案1・2・8の実装計画書（パート1・2 + 統合チェックリスト）が完了します。案3〜9も同様の形式で順次作成可能です。次のステップをお知らせください。