# 伏線自動設置パイプラインの実装計画書 (PLAN_FORESHADOW_PLANTING.md)

- **作成日**: 2026-10-05
- **対象**: AutoNovel 生成・永続化パイプライン
- **前提条件**: 案1（1話1トランザクション化とリポジトリの commit 責務移譲）の実装完了済み

---

## 1. 背景と目的

現在の AutoNovel は、伏線の**解決側（状態機械・アンサンブル判定・述語解析・リシェジューラー・KPI）**が完璧に構築・テストされている一方で、**「生成時に伏線を設置する側（Planting）」が完全に空洞**となっている。
実測調査により、生成パイプラインから `foreshadowings` テーブルに `INSERT` を行う経路はゼロであり、既存の2つの登録経路（ウィザード保存、EasyMode昇格）はオフラインの補助機能に留まる。そのため、伏線自動回収（`check_and_resolve`）や事実ダイジェストは動く基盤があっても「回収対象の行が0件」のまま空振りしていた。

本計画の目的は、**計画（Plan）およびプロット展開（PlotExpander）の成果物（RoadmapItem の setup/payoff）をシームレスに `foreshadowings` テーブルへ自動設置（Planting）し、プロンプト契約（`contract_foreshadowings`）を通じた LLM メタデータ連携までを一本のパイプラインとして完結させること**である。

---

## 2. 現状の構造的課題（ギャップ分析）

調査で判明した主な問題点：

1. **設置の欠落 (G1)**: 生成パスのどこも `DbForeshadowingRepository.add()` を呼んでいない。
2. **データの死蔵 (G2)**: `RoadmapItem` の `foreshadowing_setup` / `foreshadowing_payoff` (`src/models/plot.py:1035`) は `Bible.settings.full_story_roadmap` にシリアライズされるだけで、伏線機能からは一切読まれていない。
3. **プロンプト契約の断絶 (G3/G4)**: `ContextBuilderAgent` は `contract_foreshadowings` を組み立てるが、生産経路（`generator.py`）はそのコンテキストを構築せず空の dict を渡しているため、プロンプトに `[伏線ID: n]` のアンカーが描画されず、LLM が `foreshadowing_id` を返せない。
4. **キーワード欠落 (G9)**: `ForeshadowingModel` に `keywords` 列がなく、`foreshadowing_service.py:151` の `hasattr(f, "keywords")` が常に False になるため、述語解析器（`PredicateAnalyzer`）はタイトルだけで判定している。
5. **保存時のデータ落ち**: `PlotRepository.save_plot` は `PlotForeshadowing.foreshadowing_refs` を永続化せず捨てる。

---

## 3. 実装フェーズ（全6フェーズ）

### フェーズ 1: データモデル拡張（キーワード列の追加）
- **目的**: 述語解析の精度向上のため、伏線レコードに `keywords`（配列またはカンマ区切り文字列）を持たせる。
- **変更ファイル**:
  - `src/backend/database/models_foreshadowing.py`: `keywords = Column(Text, nullable=True)` 追加。
  - Alembic マイグレーション新設（`0031_add_foreshadowing_keywords.py`）。
  - `src/infrastructure/repositories/foreshadowing_repo.py`: `add()` に `keywords` 引数を追加。
  - `src/services/foreshadowing_service.py`: `_evaluate_one` のキーワード収集で `getattr(f, "keywords", ...)` が正しく拾うようにする。
- **テスト**: `tests/unit/database/test_foreshadowing_repo_keywords.py`

### フェーズ 2: 設置エンジン（Roadmap からの自動プランニング）
- **目的**: 企画（PlanStep）生成時またはプロット展開時に、`full_story_roadmap` の `foreshadowing_setup` / `foreshadowing_payoff` をパースし、決定論的プランナー（`plan_foreshadowing`）と組み合わせて `foreshadowings` 行を自動生成する。
- **設計方針**:
  - **フックポイント**: `BibleService._create_ultra_fast_plan` / `_create_standard_plan` の直後（`save_full_world_bible` の後）。ここで作品全体のロードマップが Pydantic オブジェクトとして確実に揃う。
  - 各 `RoadmapItem` の `foreshadowing_setup` が `"なし"` 以外の場合、`plan_foreshadowing(planted_episode=item.ep_num, total_episodes=target_eps)` を呼び出して `target_episode` と `scope` を決定する。
  - 重複登録を防ぐため、同一 `(book_id, planted_episode, title)` の既存行があればスキップする（冪等性）。
- **変更ファイル**:
  - `src/services/bible_service.py` または新設 `src/services/foreshadowing/planting_service.py`。
  - `src/infrastructure/repositories/foreshadowing_repo.py`: 一括登録ヘルパー `add_many()` の追加。
- **テスト**: `tests/unit/services/test_foreshadowing_planting.py`

### フェーズ 3: 特徴フラグ（`FORESHADOW_PLANTING`）の導入
- **目的**: 本番投入前の段階的ロールバックを可能にするため、既存の `src/services/foreshadowing/flags.py` にフラグを追加する。
- **変更ファイル**:
  - `src/services/foreshadowing/flags.py`: `FORESHADOW_PLANTING = _env_flag("FORESHADOW_PLANTING", True)`（既定有効、問題があれば環境変数でオフにできる）。

### フェーズ 4: 契約プロンプト配線の復活（G3 / G4 解決）
- **目的**: `generator.py` が簡易コンテキストの代わりに `ContextBuilderAgent` の生成する高度なコンテキスト（`foreshadowing_ctx`, `contract_foreshadowings`）を受け取るようにする。
- **詳細**:
  - `generator.py` のエピソード執筆ループ内で、空の dict を渡していた箇所を `await context_builder.execute(agent_ctx)`（または `build_context` 相当）による正しいコンテキスト構築に置き換える。
  - これにより `[伏線ID: n]` アンカーがプロンプトに乗り、LLM が `[METADATA_JSON]` で `foreshadowing_id` を返せるようになる。
- **変更ファイル**:
  - `src/agents/writing/generator.py`
  - `src/agents/writing/episode_writer.py`
- **テスト**: `tests/integration/test_v53_long_form_wiring_e2e.py`（契約伏線プロンプト描画の結合テスト）

### フェーズ 5: KPI とオブザーバビリティ
- **目的**: 設置された伏線数が `foreshadowing_planted_total` メトリクスに正しく反映されることを保証する。
- **詳細**:
  - フェーズ 2 の設置サービスが必ず `DbForeshadowingRepository.add()` を経由して登録することを確認する（raw `insert()` による KPI 抜けを防ぐ）。
- **テスト**: `tests/unit/services/test_foreshadowing_kpi.py`

### フェーズ 6: 結合・E2E 検証
- **目的**: `autonovel generate --provider mock --episodes 10` を実行した際、`foreshadowings` テーブルに自動設置行が作られ、話数進行に伴って `planted → progressed / resolved` に状態遷移し、最終的に `episode_digests` とともに完結することを確認する。
- **テスト**: `tests/integration/test_relational_memory_e2e.py` の拡張（自動設置された行が自動解決されることの検証）。

---

## 4. 依存関係と実装順序

```
[Phase 1: keywords 列追加]
       │
       ▼
[Phase 3: 特徴フラグ追加] ──► [Phase 2: 企画時自動プランニング＆設置]
                                       │
                                       ▼
                              [Phase 4: 契約プロンプト配線 (generator)]
                                       │
                                       ▼
                              [Phase 5: KPI 統合 ＆ Phase 6: E2E 検証]
```

---

## 5. リスクと緩和策

- **リスク A: 企画時に `foreshadowing_setup` が空または一律 `"なし"` である場合**
  - **緩和策**: LLM が roadmap 生成時に setup を埋められなかった場合のフォールバックとして、プロットの `detailed_blueprint` や `one_line_summary` からキーワード抽出して最低 1 本の伏線を自動生成するヒューリスティックをプランナーに持たせる。
- **リスク B: 既存のテスト（特に `test_v53_long_form_integrity.py` のモック前提テスト）への影響**
  - **緩和策**: `FORESHADOW_PLANTING` フラグで切り替え可能にし、テスト環境では必要に応じて無効化できるようにする。
