## 4. 4層圧縮モジュール (Compression Module)

AutoNovel の中核機能の一つとして、LLM プロンプト・過去文脈・キャラクター情報・世界観設定などを階層的に圧縮する `FourLayerCompressor` が実装されています。このモジュールは、プロンプトサイズの削減と重要情報の保持を両立し、コスト削減と生成品質の維持を目的としています。

### 4.1 構造

FourLayerCompressor は以下の4層から構成されます：

1. **Layer 1: キーワード抽出層**  
   - 入力テキストから重要キーワード（固有名詞・専門用語）を抽出し、重み付けを行います。
   - 出力: `RawTextLayerOutput`（抽出キーワード・スコア・元文字数等）

2. **Layer 2: サブグラフ層**  
   - 抽出キーワードをノードとし、共起関係や依存関係をエッジとしたサブグラフを構築します。  
   - プルーニングにより関係の薄いエッジを除去し、核となる関係構造を保持します。  
   - 出力: `SubgraphLayerOutput`（ノード・エッジ・シードエンティティ・統計情報）

3. **Layer 3: 抽象化層**  
   - サブグラフを概念レベルに変換し、カテゴリ化・概念の圧縮を行います。  
   - 出力: `AbstractionLayerOutput`（抽象概念・事実の分類・カテゴリマッピング・メタデータ）

4. **Layer 4: トリミング層**  
   - 抽象化結果を最終的なプロンプトテキストに変換し、不要な記述を除去しつつ、重要なエンティティ・事実・伏線を保持します。  
   - シーンタイプ（一般・戦闘・日常・心理・政治・ロマンス・ミステリー・フラッシュバック・サバイバル）に応じたトリミング戦略を適用します。  
   - 出力: `TrimmedContextOutput`（圧縮テキスト・トークン数・保持エンティティ・圧縮率・保持率等）

4. **品質メトリクス**  
   - 各層の出力から、キャラクター保持率・伏線保持率・固有名詞保持率・意味密度スコア・全体整合性スコアなどの品質指標を算出します（`CompressionQualityMetrics`）。

### 4.2 依存性注入 (DI)

- `FourLayerCompressor` は `src/core/container/app.py` の `AppContainer` にてシングルトンプロバイダーとして登録されています。
- `compression_config` プロバイダーにて `CompressionConfig` インスタンスを提供し、これを用いて `FourLayerCompressor` を生成します。
- 主なサービス・エージェントはコンストラクタ経由で `compressor: Any = None` を受け取り、DI コンテナから提供されたインスタンスを使用します。
  - `WritingService.__init__(..., compressor: Any = None)`
  - `ContextBuilderAgent.__init__(..., compressor: Any = None)`
  - `EpisodeWriter.__init__(..., compressor: Any = None)`
  - `create_easy_mode_pipeline(..., compressor: Any = None)`

### 4.3 主な利用箇所

- **WritingService**  
  - `_build_context_with_compression` メソッドにて、コンテキストに `compressor` を設定し、`ContextBuilderAgent.execute` を呼び出します。  
  - これにより、執筆品質評価プロセスで圧縮コンテキストが生成され、`writing_context` に `compressed_context` と `compression_stats` が格納されます。

- **ContextBuilderAgent**  
  - `execute` メソッドにて、`artifacts` から `compressor` を取得（または自分の `self.compressor` を使用）し、`_build_full_writing_context_internal` 内部で圧縮を適用します。  
  - 圧縮結果は `CompressedContextResult` として得られ、最終的に `writing_context` に格納されます。

- **EpisodeWriter**  
  - `build_context` メソッドにて、自身の `self.compressor` を `artifacts` に設定し、`ContextBuilderAgent.execute` を呼び出します。  
  - 圧縮コンテキストは同様に `writing_context` に格納されます。

- **EasyMode パイプライン**  
  - `create_easy_mode_pipeline` 関数にて、引数 `compressor` を受け取り、内部で `CompressionPipelineStep` または各ステップに渡します（実装詳細は `src/services/auto_workflow_pipeline.py` 参照）。

### 4.4 使用例（DI コンテナから取得）

```python
from src.core.container.app import AppContainer
container = AppContainer()
compressor = container.compressor()  # FourLayerCompressor インスタンス
# またはサービス経由で取得
writing_service = container.writing_service()
# writing_service.compressor 経由でアクセス可能
```

### 4.5 設定

`CompressionConfig` インスタンスにて以下のパラメータを調整可能です（デフォルト値は `src/services/compression/models.py` 参照）：

- `max_tokens`: 最大出力トークン数（デフォルト 1500）
- `target_reduction_ratio`: 目標圧縮率（デフォルト 0.6）
- `top_keywords`: 抽出するキーワード数上限（デフォルト 20）
- `max_hops`: サブグラフ探索の最大ホップ数（デフォルト 2）
- `relevance_threshold`: エッジ保持の関連性閾値（デフォルト 0.5）
- `scene_type`: デフォルトシーンタイプ（デフォルト "general"）
- `cache_enabled`: 結果キャッシュの有無（デフォルト True）
- `cache_ttl_seconds`: キャッシュ有効時間（秒、デフォルト 3600）
- `preserve_categories`: 優先保持するカテゴリリスト（デフォルト ["主要キャラ", "核心設定", "伏線"]）

### 4.6 テスト

- 単体テスト: `tests/unit/test_four_layer_compression.py`
- 契約テスト: `tests/contract/test_compression_output_schema.py`
- プロパティベーステスト: `tests/property/test_compression_invariants.py`
- 性能ベンチマーク: `tests/performance/test_compression_benchmark.py`
- E2E テスト: `tests/e2e/test_full_novel_with_compression.py`

全テストは CI パイプラインで自動実行されます。

---

## 5. 階層的逐次要約メモリ (Hierarchical Sequential Summary Memory)

AutoNovel の長編執筆（30話〜）において、Layer2 の「1話ごとの独立100字ダイジェスト＋中間省略マーカー」が中盤の確定事実を失う問題を解消するため、**話→章(ブロック)→巻のツリー状逐次要約**を導入しました。さらに重要情報をプロンプト両端へ配置し、Lost in the Middle 対策を行います。

### 5.1 概要

| 項目 | 現行 (flag off) | 改修後 (flag on) |
|---|---|---|
| Layer2 の構成 | flat な1話要約リスト + 中間省略マーカー | 巻要約 > 章要約 > 直近話ダイジェスト |
| 中盤の事実 | 話数>10 で省略され永久喪失 | 章要約に圧縮され保持 |
| 重要情報の位置 | プロンプト中央 | 先頭(必守) + 末尾(再確認) の両端 |
| 要約密度 | 1 pass、100字固定 | Chain-of-Density 型 (2 pass 選択可能) |
| ロールアップ生成 | なし | 章境界(+1 LLM call/10話)・巻境界(+1/50話) |

### 5.2 フィーチャーフラグ

すべて `src/engine/context_compression/rollup_config.py` (SSOT) で管理：

| 設定 | 環境変数 | 既定 | 意味 |
|---|---|---|---|
| `rollup_enabled` | `ENABLE_DIGEST_ROLLUP` | `0` | ロールアップ全体の ON/OFF |
| `episodes_per_block` | `DIGEST_EPISODES_PER_BLOCK` | `10` | 章(ブロック)境界の話数 |
| `blocks_per_volume` | `DIGEST_BLOCKS_PER_VOLUME` | `5` | 巻境界 (50話/巻) |
| `pinned_edges_enabled` | `ENABLE_PINNED_FACTS_EDGES` | `0` | 両端配置 ON/OFF (Lost in the Middle 対策) |
| `cod_rounds` | `DIGEST_COD_ROUNDS` | `1` | 要約パス数 (1=現行, 2=CoD) |
| `block_digest_chars` | `DIGEST_BLOCK_MAX_CHARS` | `300` | 章要約上限 |
| `volume_digest_chars` | `DIGEST_VOLUME_MAX_CHARS` | `800` | 巻要約上限 |
| `pinned_max_chars` | `PINNED_FACTS_MAX_CHARS` | `300` | pinned head 最大文字数 |
| `pinned_tail_max_chars` | `PINNED_FACTS_TAIL_MAX_CHARS` | `300` | pinned tail 最大文字数 |

### 5.3 アーキテクチャ

```
Layer 1 (バイブル): キャラクター・世界観設定（不変）
Layer 2 (階層要約):
  ├─ 巻要約 (level=volume): 全巻の確定事実
  ├─ 章要約 (level=block): 現在巻の確定事実
  └─ 直近ダイジェスト: 現在章の1話 + 最初2話
Layer 3 (直前文脈): 直前1エピソードの生テキスト
```

### 5.4 フェーズ別リリース計画 (PLAN_M1 Step 27)

1. **Week 1**: `ENABLE_DIGEST_ROLLUP=1` — rollup 生成のみ有効化。Layer2 は現行参照。
2. **Week 2**: `ENABLE_PINNED_FACTS_EDGES=1` — 両端配置有効化。
3. **Week 3**: `ENABLE_DIGEST_ROLLUP=1` で Layer2 階層組立を本体有効化。
4. **Week 4**: `DIGEST_COD_ROUNDS=2` の A/B 結果を見て採否判断。

各段階で1週間バーンし、監査スコアの劣化を監視。ロールバックは該当 env を 0 に戻すだけ。

### 5.5 テスト

| # | テストファイル | 種別 | 守るもの |
|---|---|---|---|
| T1 | `tests/perf/test_long_form_token_stability.py` | perf | 実経路の文字数不変性 |
| T2 | `tests/regression/test_hierarchical_memory_golden.py` | golden | flag off で現行プロンプトとバイト同一 |
| T3 | `tests/unit/engine/context_compression/test_rollup_config.py` | unit | 設定 SSOT・env 上書き |
| T4 | `tests/regression/test_no_hardcoded_thresholds.py` | regression | マジックナンバー再導入禁止 |
| T6 | `tests/unit/engine/context_compression/test_rollup_repository.py` | unit | upsert 冪等・UNIQUE |
| T7 | `tests/unit/engine/context_compression/test_rollup_generator.py` | unit | 境界判定・tier1・fail-open |
| T10 | `tests/unit/services/test_episode_context_hierarchy.py` | unit | 層順序・優先クランプ・legacy 同一 |
| T11 | `tests/unit/engine/context_compression/test_rollup_staleness.py` | unit | retake 追従 (stale→再生成→解消) |
| T12 | `tests/unit/engine/context_compression/test_pinned_facts.py` | unit | 両端事実の抽出順・上限 |
| T13 | `tests/unit/agents/test_pinned_facts_placement.py` | regression | プロンプト内位置不変 |
| T14 | `tests/e2e/test_hierarchical_memory_e2e.py` | e2e | rollup/pinned が実プロンプトへ届く |
| T15 | `tests/unit/engine/context_compression/test_rollup_cod.py` | unit | Cod rounds=1 現行同一 / rounds=2 呼び出し回数 |
| T16 | `tests/unit/engine/context_compression/test_fact_density.py` | unit | 圧縮後の情報密度 |
| T17 | `tests/perf/test_v6_llm_call_budget.py` | perf | コスト予算 +1/10話 上限 |
| T18 | `tests/regression/test_long_form_fact_retention.py` | regression | **中盤の事実保持 (提案4 の価値)** |

ベンチマーク: `benchmarks/hierarchical_memory_bench.py` (flag off/on の事実保持率・Layer2 文字数・LLM コストを比較)