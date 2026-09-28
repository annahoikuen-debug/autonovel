# PLAN_V6_COST_LATENCY_OPTIMIZATION

**「コスト・レイテンシの極限最適化」v6 設計案（実測根拠版）**

- 作成日: 2026-09-28
- 対象: AutoNovel v5.3.0（`pyproject.toml` の `project.version`）
- 種別: 設計文書（進捗 SSOT ではない。現行の SSOT は `docs/STATUS.md`）
- 前提: 本書の行番号・ファイルパスは作成時点のワークツリー実コードを静的に読み解いて確定した。差異があれば本書のほうが誤り。

---

## 0. 要約

コスト・レイテンシ最適化の提案を**実測根拠で書き直した**案。

当初の提案は「8専門オーディター並列」「Reflective RAG 3回ループ」「Coarse-to-Fine 二段階」を主因と診断されたが、
**いずれも本番経路に存在しない**ことを確認した。実際の主因は以下である。

1. `AuditAgent.execute` の **5つの LLM 監査が直列実行**され、**いずれか1つでも失敗すると全文再執筆**にフォールバックする
2. `UnifiedAuditor` が**本番監査ノードに接続されていない**
3. 3層モデルルーティングが**実装済みだが本番未配線**

**新規設計は不要**。既存モジュールの配線と設定変更が中心であり、優先度順に 4 ステップで完了できる。

---

## 1. 診断の訂正

### 1.1 当初提案との差分

| 当初提案の前提 | 実測結果 | 根拠 |
|---|---|---|
| 8専門オーディター並列がコスト主因 | **本番経路に存在しない**。既定マニフェストは `v1/audit_skill`。8並列 aggregator は `v2` 専用で、`AuditAggregatorNode` はマニフェスト不在時のフォールバック分岐のみ | `src/agents/skills/manifest.yaml:48` / `src/backend/tasks/generation_tasks.py:208` |
| Reflective RAG 3回ループがコスト主因 | 本番 `execute_generation` 経路には不在 | `src/backend/routers/easy_mode.py` |
| Unified Auditor を新規実装する | **既に実装済み**。静的ルール＋単一LLMコール | `src/agents/specialists/unified_auditor.py:78-96` |
| モデルルーティングを新規実装する | **既に実装済み**。ただし 3層版は本番未配線 | `src/llm/model_router.py:96-133` |

### 1.2 当初評価（「Unified Auditor は本番稼働」）の訂正

`UnifiedAuditor` は `src/domain/writing/coordinator.py:92-94` から呼び出されるが、
**本番の監査ノード `AuditAgent.execute` は使用していない**。
代わりに 5 つの監査エージェントを直列実行している。

したがって「統合削減」は未使用コードへの投資ではなく、**本番経路への適用作業**である。

---

## 2. 実測したコスト構造（1話あたり）

経路:
```
POST /api/easy-mode/generate
  → generate_chapter_orchestrated_task
    → Orchestrator.from_manifest
      → v1 スキル群（下記）
```

根拠: `src/backend/routers/easy_mode.py:282` / `src/backend/tasks/generation_tasks.py:280-282`

| # | スキル | LLM回数 | 備考・根拠 |
|---|---|---:|---|
| 1 | PlanningSkill | 1 | `src/agents/skills/v1/planning_skill.py` |
| 2 | BibleSkill | 1 | `src/agents/skills/v1/bible_skill.py` |
| 3 | ContextBuilderSkill | 1+ | ReflectiveRAG ループを含む |
| 4 | HistoricalAccuracyChecker | **0** | 静的リストのみ `src/agents/skills/v1/historical_accuracy.py:82-91` |
| 5 | **WritingSkill** | 1（最大） | 主出力。コスト最大の単一呼び出し |
| 6 | EnrichmentSkill | 1 | `src/agents/skills/v1/enrichment_skill.py` |
| 7 | **AuditSkill** | **5（直列）** | `src/agents/audit_agent.py:135,153,175,198,219` |
| 8 | CulturalComplianceChecker | **0** | 静的のみ `src/agents/skills/v1/cultural_compliance.py:32-36` |
| 9 | IllustrationSkill | 0（エラー即終了） | 下記 §2.2 |
| 10 | MarketingCopySkill | **0** | テンプレートのみ `src/agents/skills/v1/marketing_copy.py:65-88` |

**合計: 最小 10 回の直列 LLM 呼び出し。**

### 2.1 発見 A：全滅バックトラックによるコスト爆弾（最重要）

`AuditAgent.execute` は 5 監査の**いずれかが 1 つでも失敗すると**
`should_retry=True, next_agent=AgentName.WRITING` を返す
（`src/agents/audit_agent.py:296-310`）。

Orchestrator の既定 `max_backtracks_per_node=3`（`src/agents/orchestrator.py:74`）により、
**最悪ケースで 1 話あたり本文生成 4 回 ＋ 監査 20 回**となる。

さらに 5 監査は独立しているが直列であり、各監査の独立失敗率が 20% とすると
5 つ全通過率は `0.8^5 ≈ 33%` となる。つまり**約 67% の話で、少なくとも 1 回の全文再執筆が発生する**計算である。

### 2.2 発見 B：IllustrationSkill がチェーンを断っている

`IllustrationAgent.execute` は `ctx.artifacts["request"]` を要求するが
（`src/agents/illustration_agent.py:46-55`）、前段スキルは誰も設定しない。
常に `error` を返し `next_agent=None`。

Orchestrator は `current = result.next_agent`（`src/agents/orchestrator.py:806`）でループを終了するため、
**IllustrationSkill 以降のスキルは実行されない**。IllustrationSkill 自身が常にエラーとなるため実害は限定的だが、
チェーン契約が破れている。

### 2.3 発見 C：全スキルが執筆用モデルで走る

`generation_tasks.py:174-182` の `dependencies` は
全スキルに `llm: llm_adapter`（＝執筆用モデル）を渡している。
`planning_llm` / `audit_llm` は別キーとして渡されるが、読むスキルは限られる。

結果として **5 回の監査が執筆用の高価格モデルで実行**されている。

---

## 3. ワークストリーム

### WS-A：監査の並列化と集約（最大効果・低リスク）

| # | 作業 | 根拠・備考 |
|---|---|---|
| A-1 | 5 監査を `asyncio.gather` で並列化 | 入力が独立: `screen_plot(blueprint)` / `logical(blueprint)` / `deai(drafted_text)` / `ability(settings)` / `plot_monitor(keywords)`。品質影響ゼロ |
| A-2 | `UnifiedAuditor` を `AuditAgent.execute` の定性的判定フェーズに統合 | 既に `audit_quantitative` で静的評価済み。統合は差分注入 |
| A-3 | **全滅式ゲート → スコア集約式へ変更**。5 監査を 0-100 に正規化し、閾値未満のときだけ再執筆 | `audit_agent.py:296` の `should_retry` 条件。A-1 と A-3 が本 WS の主役 |
| A-4 | 再執筆は全文ではなく該当箇所のパッチ | `ActionableDiff` / `local_polisher` / `safe_replace` は既に存在 |

**目標効果**: 監査レイテンシ約 1/5、本文再生成比率 67% → 10% 未満。

### WS-B：モデルルーティングの生存化

`resolve_optimized_model` と `ROUTING_TIERS`（`src/config/cost_optimization.py:10-14`）は
**完成済みだが本番未配線**（現状テストからのみ参照）。

| # | 作業 | 備考 |
|---|---|---|
| B-1 | `generation_tasks.py:174-182` の `dependencies` で監査・構成系を tier1 に付け替え | 現状 5 回の監査が執筆用モデルで走る（§2.3） |
| B-2 | tier3（climax 時のみ上位モデル）を `is_climax` で実効化 | `resolve_optimized_model(task_type, is_climax, user_plan)` は未使用 |
| B-3 | `src/services/token_tracker.py` を全スキルに注入し、スキル別トークン/コストを計測 | 最適化前の可視化。**Step 0 として最優先** |

### WS-C：パイプライン契約修復と Prefetch

| # | 作業 | 備考 |
|---|---|---|
| C-1 | `IllustrationSkill` に `request` を生成する前段を追加、または `IllustrationAgent` が要求なしで no-op 終了する契約に修正 | §2.2 |
| C-2 | 監査を「fast_screener のみ」に縮退した軽量モードを既定に | 5 監査全部を毎話回す必要はない |
| C-3 | 投機的プリフェッチ: 次話執筆プロンプトの事前生成 | 次の話提案は生成済み（`easy_mode.py:208-218`, `max_tokens=300`） |

---

## 4. 実行順序

```
Step 0  計測 (B-3)            ← ここを飛ばすと効果検証ができない
Step 1  A-1 監査並列化        ← 1日で完了・リスクゼロ・即効果
Step 2  A-3 ゲート集約        ← 最大の費用削減
Step 3  B-1 / B-2 ルーティング配線 ← 既存コードの有効化
Step 4  A-2 Unified統合 / C-1 契約修復 ← 構造改善
```

**期待される総効果**: LLM 10 回 → **4-5 回**、レイテンシ約 1/3 短縮、最悪ケースの 4 回再生成を**原則 1 回**に。

---

## 5. リスク

| リスク | 影響 | 緩和 |
|---|---|---|
| A-1 並列化でイベント順序が変わる | 低 | 各監査は独立。イベントに `audit_id` を付与して追跡可能にする |
| A-3 集約化で品質ゲートが緩む | **中** | 閾値を明示設定し、既存回帰テストで検証。段階的に閾値を調整する |
| A-2 統合で判定項目が欠落 | 中 | 5 監査の判定項目を事前に棚卸しし、`UnifiedAuditor` の出力項目と 1 対 1 対応させる |
| B-1 モデル変更で出力品質低下 | 中 | tier 選択を機能フラグ化。ロールバック可能にする |

---

## 6. 未検証事項

以下は**実測していない**。Step 0 で計測すること。

- 1 話あたりの実測コスト（トークン計測が未配線のため算出不可）
- 5 監査それぞれの実際の失敗率（実データ無し。§2.1 の 20% は仮定値）
- `EnrichmentSkill` / `ContextBuilderSkill` 内部の正確な LLM 回数
- `WritingSkill` の出力トークン量（コスト支配因子と推定しているが未計測）

---

## 7. 関連文書

| 文書 | 内容 |
|---|---|
| `docs/STATUS.md` | 現行の実装状況 SSOT |
| `CHANGELOG.md` | v5.3.0 変更履歴 |
| `src/config/cost_optimization.py` | `MODEL_PRICING` / `ROUTING_TIERS` 定義 |
| `src/llm/model_router.py` | モデル解決関数群 |
| `src/agents/specialists/unified_auditor.py` | 統合監査エンジン |
| `src/agents/audit_agent.py` | 本案の主対象（5 監査直列 + 全滅バックトラック） |
