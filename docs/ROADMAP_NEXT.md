# AutoNovel 次期方向性ロードマップ（2026-11-25 精査）

作成日: 2026-11-25
ステータス: ✅ 承認（2026-11-26 ユーザー裁定）。本書を上位方針とし、機能系ロードマップ（`docs/plans/ROADMAP_PLAYABLE_NOVEL.md`）の実行順序・優先度は本書 §5 に従う。CI 発火は 2026-11-26 に確認済み（HEAD に 16 check runs）。
作成経緯: v7.0.0（2026-11-25 時点）のワークツリー実コードに対する精査に基づく方向性提案。
ルートの `ANALYSIS_AND_PROPOSALS.md`（同日作成・未追跡）の内容を **本書に統合** し、同ファイルは削除済み。
前提ドキュメント: [`docs/STATUS.md`](STATUS.md)（実装状況 SSOT）/ [`docs/plans/ROADMAP_PLAYABLE_NOVEL.md`](plans/ROADMAP_PLAYABLE_NOVEL.md) / [`docs/ROADMAP_IMPROVEMENTS.md`](ROADMAP_IMPROVEMENTS.md)

---

## 0. 一言サマリ

> **コードの品質管理は既に十分な水準にある。次のボトルネックはコードではなく、
> 「作った機能が実際に価値を出しているかを測るループ」である。**
> 機能追加より先に、CI 復活 → 本番デプロイ → 実 LLM での実測でループを閉じる。
> そうしないと、機能を足すほど「OFF のまま眠るコード」が増えるだけになる。

---

## 1. 精査サマリ（実測値）

以下は 2026-11-25 に本ワークツリーで実測した値である（出典を明記。推測値は含まない）。

| 項目 | 実測値 | 出典 |
|:---|:---|:---|
| バージョン | 7.0.0（2026-11-13 リリース） | `pyproject.toml:3` |
| バックエンド | 1,168 ファイル / 約 163,756 行 | `find src -name "*.py"` 実測 |
| フロントエンド | 267 ファイル / 約 52,398 行 | `find frontend/src` 実測 |
| API ルーター | 51 モジュール | `ls src/backend/routers/` |
| ワークフロー | 24 | `ls src/backend/workflows/` |
| テスト | 1,103 ファイル / **10,024 件 collect**（通常実行 9,570 パス・失敗 0） | `pytest --collect-only`（2026-11-25 実測）/ `CHANGELOG.md` |
| 契約テスト | 32 | `ls tests/contract/` |
| ruff / format | 0 エラー（ratchet 維持） | `config/ci_lint_baseline.json` |
| mypy | baseline 450 / 実測約 323（unused-ignore 1） | `CHANGELOG.md`（Q7・2026-11-24 実測） |
| ENABLE/USE/AUDIT 系設定識別子 | **約 89 種**（メトリクス名等の粗カウントを含む） | `grep -rhoE "(ENABLE\|USE\|FORESHADOW\|SPINE\|AUDIT\|RAG)_[A-Z0-9_]+" src` |
| 4層境界違反 | 0（契約1 HARD / 契約2 ratchet とも） | `scripts/check_layer_boundaries.py` 実行 |
| Node（ローカル実測） | v26.13.1（`engines` は `>=20 <23` と不整合） | `node -v` / `frontend/package.json` |

---

## 2. 強み（維持すべき資産）

1. **契約テスト文化** — 「フラグ OFF ならプロンプトがバイト単位で不変」を 32 本の契約テストで常時検証
   （例: `tests/contract/test_spine_prompt_injection_*.py`、`test_structure_gate_off_contract.py`）。
   大規模リファクタを安全に進められる稀な土台。
2. **ラチェット型品質ゲート** — ruff=0 / mypy / format を「劣化のみ検出」（`scripts/ci_lint_ratchet.py`）。
   完璧主義で止まらず退行だけを防ぐ現実的設計。mypy も 1122 → 約 323 へバーンダウン実績あり。
3. **SSOT 文書の規律** — `docs/STATUS.md` が「実装済み／未配線／未確認」を正直に区別し、誇大記載がない。
4. **既に揃った部品** — 分岐コア、Play API + WS、RAG（ハイブリッド / HyDE / リランカー）、
   監査（二層＋外科的スパンリライト）、伏線因果DAG、階層メモリ。**土台は完成している。**

---

## 3. 構造的課題（証拠付き）

### 課題A: ループが閉じていない（最重要）

- 約 89 種の設定識別子のうち、主要改善が**すべて既定 OFF のまま**:
  - 改稿: `ENABLE_AUDIT_QUOTE_PATCH` / `ENABLE_AUDIT_LESSONS`（`docs/STATUS.md` §11・AB 実施済みだが実パイプライン未判定）
  - 伏線: `FORESHADOW_CAUSAL_DAG` 等の全旗艦フラグ（同 §5.8）
  - RAG: HyDE / BM25/RRF / リランカー既定 OFF（`docs/ROADMAP_IMPROVEMENTS.md` §提案5 残務 F1-F3）
  - 構造: `SPINE_QUALITY=off` / `NARRATIVE_STRUCTURE_GATE=off`（同 §9）
- 理由は「実 LLM での AB 測定が未実施」。「機能はあるが ON にしてよいかの判断データがない」状態。
- 実書籍データが存在しない（`scripts/measure_spine_alignment.py` の `book_count = 0`、`docs/STATUS.md` §7）。
  本番デプロイ未実施のため KPI（完走率・伏線回収率・cost/play）がすべて未計測。
- **CI 不発 → 2026-11-26 に復活（解決済み）**: GitHub REST API による無認証読み取りで「`ci.yml` は `state: active`
  だが main の workflow runs 0 件・全 workflow が 2026-11-03 以降不発（fork 由来の設定レベル不発）」と確定していたが、
  **ユーザーが Settings を修正したことで同日中に復活**。空コミット push で main に runs 0 → 3 件（`ci.yml` run #1 が
  史上初めて発火・5 job 起動を確認）。初回 run は format ratchet 1 件のみ fail（`e254d6ac` で修正）。実行計画:
  `plans/PLAN_P0_CLOSE_THE_LOOP_21STEPS.md`（TRACK-A 実施記録参照）

> これが解けない限り、機能を足すほど判断材料のないフラグが増えるだけになる。

### 課題B: 生成コアが二重化している

| 系統 | 入口 | 実体 |
|:--|:--|:--|
| 統合パイプライン | `POST /easy_mode/generate` | `src/backend/workflows/easy_mode_workflow.py` → `src/engine/auto_workflow_pipeline.py`（`src/services/pipeline_steps.py` の Plan/Write/Audit ステップ） |
| 執筆コーディネータ | `POST /api/episodes/generate` | `src/backend/workflows/episode_writing_workflow.py`（`src/backend/routers/episodes.py:203,248`）→ `src/domain/writing/coordinator.py` |
| LangGraph 版 | （実質デッド） | `src/backend/workflows/writing_langgraph.py` — 本体からの参照はコメント 1 箇所のみ（`src/agents/audit_agent/agent.py:889`） |

同じ「1話を書く」処理が 2〜3 系統あり、品質・監査・コストの挙動が入口によって変わり得る。
片方に改善を入れても他方に効かないリスク。

### 課題C: 4層アーキテクチャは「併存」であって「移行完了」ではない

| 配置 | ファイル数 | 行数 |
|:--|---:|---:|
| 正規4層（domain / application / infrastructure / interfaces） | 229 | **約 23,800** |
| 旧モノリス系（backend / services / agents / engine / easy_mode） | 507 | **約 91,400** |

- 境界違反 0 は「新コードが旧モノリスを import していない」ことを示すもので、
  **実行時の本体は依然モノリス**（interfaces 層 10 ファイルに対し routers は 51 本が backend 配下）。
- 「4層化完了」という認識は実態より進んでいる。**移行を続けるのか / 現状で凍結して機能開発を優先するのか、
  明示的な意思決定が必要。**

### 課題D: 未配線・多重実装の残骸

- 挿絵は 3 系統並存（Imagen 本線 `ImageService` / env ファクトリ / 新 Protocol）。
  ADR 003 で「B/C は棚上げ」と決まったが、コードは残存（`docs/adr/003-illustration-mainline.md`）。
- PDCA ループ本体（`src/engine/pdca_cycle.py` `ClosedLoopPDCARunner`）は生成経路に未配線
  （`docs/STATUS.md` §3.6。`src/generation/pdca_controller.py` は coordinator で使用中）。
- なろう公開は `selenium` / `webdriver-manager` が依存宣言されておらず、クリーン環境で ImportError（同 §3.3）。
- GraphRAG 書き込み系はスタブ（`src/backend/routers/graph.py:338,355` の `_graph_write_not_implemented()`）。

### 課題E: 環境の不整合

- ローカル Node は v26.13.1 だが `frontend/package.json` の `engines` は `>=20 <23`。
- 2026-11-25 再現: フロントテストは「11 passed だが unhandled error 1 件」（react-router × undici の
  AbortSignal クロスレルム問題）。テストは通るがノイズが残り、Node バージョン乖離が潜在リスク。

---

## 4. 旧分析（ANALYSIS_AND_PROPOSALS.md）提案の位置づけ

統合前の分析書が挙げた 8 提案を本書の優先度にマッピングした。

| # | 旧提案 | 本書での扱い | 備考 |
|:--|:--|:--|:--|
| 1 | PDCA ループの配線 | **P4（見送り・条件付き）** | 外科的パッチ＋教訓で実用上の改稿は成立済み。実 LLM 計測（P0）が先 |
| 2 | 文体の章への適用 | **P3（棚卸し候補）** | Chapter モデルにスタイル列なし。需要確認後に着手判断 |
| 3 | GraphRAG 書き込み実装 | **P4（見送り）** | 読み取り系は稼働中。書き込みは価値対コストが現時点で不明 |
| 4 | なろう selenium の依存解決 | **P3** | 低コストで着手可能（optional dependency 化） |
| 5 | LLM 呼出 10→4-5 回 | **P2 の一部** | `ENABLE_LIGHTWEIGHT_AUDIT` 構想は実 LLM 計測後に判断 |
| 6 | フロント Node 26 対応 | **P3** | engines 整合 + unhandled error 解消 |
| 7 | easy mode 挿絵配線 | **P1 に吸収** | ADR 003 の Increment 1/2 として進行中 |
| 8 | 契約テスト拡張 | **P3（随時）** | RAG 注入契約は既存（`test_rag_prompt_injection.py`）。新規 endpoint は随時追加 |

---

## 5. 方向性の提案 — 「機能追加」から「価値の実証」へ

### 優先度 P0: ループを閉じる（1〜2 週間）

| アクション | 完了条件 |
|:--|:--|
| **CI を本当に復活させる** | push で check runs が 1 件以上出る。ローカル `make verify` だけでなく CI が緑 |
| **本番 1 環境をデプロイ** | `docker-compose.prod.yml` で起動し、`/health/ready` 200 + 登録→easy mode 生成→ZIP 取得が完走 |
| **実 LLM で 1 作品（20 話）生成** | `book_count > 0` にし、`scripts/measure_spine_alignment.py` と KPI を実測値で埋める |
| **OFF フラグの ON/OFF 判定** | RAG・H8・伏線投票について、既存の AB 手順（`plans/PLAN_H8F_ROLLOUT_12STEPS.md` O7/O8）を実 LLM で 1 回実行し、既定値を決める |

> **これが最優先。** ここを飛ばして機能を足すと、判断材料のないフラグがさらに増えるだけになる。
> CI 復活は GitHub 設定（リポジトリ管理者側の作業）が絡むため、最初に切り分けること。

### 優先度 P1: 進行中の「縦切り」を完成させる（2〜4 週間）

> **2026-11-26 更新**: Increment 1（決定的クエリ API・Play 表示・`/static` 配信・vite proxy）は
> 並行作業セッションにより `8ddfe522`（実装）+ `fa88fe1a`（ドキュメント）として**コミット・push 済み**。
> 実行計画: `plans/PLAN_P1_PLAY_ILLUSTRATION_16STEPS.md`（2026-11-26 起票）

1. ~~挿絵 Increment 1 をコミット~~ → **完了**（`8ddfe522` / `fa88fe1a`）
2. 挿絵 Increment 2（保存経路の修復: DI への `repo` 注入、`get_chapters` 修復、パイプライン接続、コスト上限）を ADR 003 の範囲で実施
3. Play モード Phase 1（`ENABLE_DYNAMIC_BRANCH`）— 「P0 の KPI 基盤ができてから」の前提は P0 のユーザー側ブロッカーにより未達だが、ユーザー指示により**実装を先行**する。KPI 計測（cost/play・完走率等）は P0 再開後に取得（**実装完了・計測待ち**）

理由: Play モードは ADR 002 で本線承認済みで、**唯一「生成物がそのまま遊べる」という市場差別化**を持つ機能。
中途半端に広げず、1 本の体験として完成させる。

### 優先度 P2: 生成コアの一本化を意思決定（4〜8 週間）

- ADR を起票: 「どちらを本線の執筆パイプラインとするか」（課題B 参照）
  - 推奨案: `src/domain/writing/coordinator.py` を本線にし、`auto_workflow_pipeline` を「バッチ編成」に限定。
    `writing_langgraph.py` は削除。
  - 代替案: 「easy mode = バッチ / episodes = 対話」と役割で分けることを明文化（統合しないが共有部品を domain に寄せる）。

いずれにせよ「2 系統が別々に進化する」状態は止める。

### 優先度 P3: 負債の棚卸しと環境整合（継続的）

1. **未配線コードの削除**（ADR 003 の B/C 系統、`writing_langgraph`、未使用 PDCA 経路）。残すなら「なぜ残すか」を ADR に記録。
2. **selenium を optional dependency 化**（`pip install "autonovel[narou]"`）＋ ImportError を 503 に変換。
3. **Node バージョンの整合** — `engines` を実態（20〜26）に合わせるか、CI/開発を 22 LTS に固定。
   react-router/undici の unhandled error を解消。
4. **mypy バーンダウン継続** — 実測約 323。12/31 目標 250（`config/ci_lint_baseline.json` targets）は現実的。
   主山は Column → `Mapped[...]` 移行。

### 優先度 P4: 「やらないこと」を決める

当面**着手しない**ことを明示する:

- **自動改善ループ（PDCA）の新規配線** — 既存の外科的パッチ＋教訓で足りる。ON/OFF 判定（P0）が先。
- **GraphRAG 書き込み** — Play/挿絵より優先度が低い。
- **UGC 公開・収益分配** — `ROADMAP_PLAYABLE_NOVEL.md` の Phase 4 ゲート制を維持。
- **4層アーキテクチャの全面移行** — 機能価値に直結しない。「新規コードのみ 4 層に置く」現状運用を継続。

---

## 6. 推奨シーケンス（90 日）

```
Week 1-2   P0: CI 復活 → 本番デプロイ → 実 LLM で 1 作品生成 → KPI 実測
Week 3-4   P1: 挿絵 Increment 1 コミット → Increment 2（保存経路）
Week 5-8   P2: 執筆コア一本化の ADR と着手 / OFF フラグの ON 判定
Week 9-12  P1: Play Phase 1（動的継続）— KPI を見て GO/NO-GO
随時       P3: 負債削除・Node 整合・mypy バーンダウン
```

**判断ゲート**: Week 2 終了時に「実作品 1 本の KPI が取れたか」で以降を判断。
取れていなければ、機能開発を止めて計測基盤に集中する。

---

## 7. 本書の運用

- 役割分担: `docs/STATUS.md` は「**今どうなっているか**」、本書は「**これから何をするか・なぜか**」。
- 各施策（P0〜P2）が承認されたら、既存パターンに従い `plans/PLAN_<ID>_<主題>_<N>STEPS.md` として
  実行計画書を起票する。本書は施策レベルの合意を記録するのみで、ステップ分解を含まない。
- 進捗が生じた場合は本書 §5 の各表に状態を追記し、`docs/STATUS.md` の該当節も更新する。

---

## 8. 関連ドキュメント

| ドキュメント | 関係 |
|:--|:--|
| [`docs/STATUS.md`](STATUS.md) | 実装状況の SSOT。本書の「現状」列はこれに従う |
| [`docs/plans/ROADMAP_PLAYABLE_NOVEL.md`](plans/ROADMAP_PLAYABLE_NOVEL.md) | プレイアブルノベル構想。本書 P1 の実施対象 |
| [`docs/ROADMAP_IMPROVEMENTS.md`](ROADMAP_IMPROVEMENTS.md) | 品質向上系の 9 提案ロードマップ。本書 P0 の AB 手順を出典 |
| [`docs/adr/002-play-mode-mainline.md`](adr/002-play-mode-mainline.md) | Play モード本線化の決定 |
| [`docs/adr/003-illustration-mainline.md`](adr/003-illustration-mainline.md) | 挿絵本線クライアント決定と Increment 範囲 |
| `plans/PLAN_H8F_ROLLOUT_12STEPS.md` | フラグ ON 判定（AB 検証）の手順書 |

---

## 改訂履歴

| 日付 | 版 | 内容 |
|:--|:--|:---|
| 2026-11-25 | 0.1 | 初版作成（2026-11-25 精査に基づく方向性提案。`ANALYSIS_AND_PROPOSALS.md` の内容を統合し同ファイルは削除） |
