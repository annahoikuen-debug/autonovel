# PLAN_H8F: H8 フラグ運用ロールアウト計画 — Shadow 計測・AB 検証・既定値判定(リグレッション防止テスト整備込み)

- **文書ID**: PLAN_H8F_ROLLOUT_12STEPS
- **作成日**: 2026-11-10
- **対象**: AutoNovel v6.0.0
- **位置づけ**: 改善提案8「改稿ループの部分編集統一とフィードバック永続化」の**最終フェーズ(F1-F3)の運用詳細計画**。PLAN_H8_SPAN_REVISION_26STEPS.md の Phase A-E(実装)は完了済み(コミット `717b2afa`/`f7059cbc`)であり、本計画はフラグ `ENABLE_AUDIT_QUOTE_PATCH` / `ENABLE_AUDIT_LESSONS` を既定 OFF から安全に ON へ移行するまでの運用手順を定める
- **前提**: 提案9(評価キャリブレーション基盤, `config/audit_calibration.yaml` + `src/audit/calibration_store.py`)実装済み。PLAN_M1(階層記憶, pinned_head/pinned_tail)と同一テンプレートを共有しているため、テンプレート変更時は両 golden(`rag_prompt_baseline` / `lessons_prompt_baseline`)を同時に更新する
- **原則**: PLAN_F1B の D7(推測禁止・行番号は実装時に grep で再確認)を引き継ぐ。本書の行番号は 2026-11-10 実査による

---

## 0. TL;DR

H8 の実装は完了し、全テスト緑(363 passed / 1 skipped)である。残る作業は**運用判断**のみである。

| # | 決定事項 | 判定材料 | 本計画の対応 |
|:---|:---|:---|:---|
| **D1** | `ENABLE_AUDIT_QUOTE_PATCH` を既定 ON にするか | quote_patch 採用率 ≥ 60%・再合格率現行以上・コスト増 ≤ +5% | Phase O3 |
| **D2** | `ENABLE_AUDIT_LESSONS` を既定 ON にするか | 同 dimension 再発率の有意な低下・プロンプト増分 ≤ 800字・監査スコア劣化なし | Phase O3 |
| **D3** | 教訓注入閾値 `AUDIT_LESSON_MIN_OCCURRENCES` を 1 か 2 にするか | occurrences=1 vs 2 での再発率・誤汚染率比較 | Phase O3(O8) |

**最重要契約**: どのフラグも判定を通過しなければ**既定 OFF のまま**とし、その根拠を `docs/STATUS.md` §10 に文書化する(PLAN_R5 F3 と同型)。OFF 維持は「失敗」ではなく「安全側の決定」である。

---

## 1. 現状の正確な記録(2026-11-10 実査)

### 1.1 実装済み(触らない)

| 資産 | 実体 | 状態 |
|:---|:---|:---|
| quote 置換コア | `src/audit/span_revision.py` — `QuotePatch` / `find_quote_span` / `apply_quote_patches`(純関数・LLM 0 回・`SpanPatchApplier.validate` 付き) | 完了・単体テスト 18 件緑 |
| 教訓メモリ | `src/audit/lesson_store.py` — `AuditLessonRepository` / `AuditLessonService`(upsert 加算・graduate・active 上限エビクション) | 完了・単体テスト 10 件緑 |
| DB | `src/backend/database/models_lessons.py` + `src/backend/alembic/versions/0035_audit_lessons.py` | 完了 |
| agent 統合 | `src/agents/audit_agent/agent.py` — `_try_quote_patch` / `try_local_patch` 統合 / `_record_lessons` / `_graduate_lessons` / `STANDARD_AUDIT_IDS` / `_unified` 内 `last_unified_report` 設定 | 完了 |
| 監査出力 structured 化 | `src/models/unified_audit.py`(`actionable_quote`/`actionable_replacement`) / `src/agents/prompts/unified_audit_prompt.py` / `src/agents/specialists/unified_auditor.py` | 完了 |
| fail-closed | `src/agents/writing/prose_refiner_agent.py`(LLM 欠如時 `RuntimeError` → 原文返却) | 完了・テスト 3 件緑 |
| 注入配線 | `src/agents/context_builder_agent.py`(`audit_lessons_ctx`) → `src/agents/prompt_composer.py`(`lessons_block`/`_format_audit_lessons`) → `prompts/manager.py` → `final_writing_prompt.j2`(`{% if lessons_block %}` ガード) | 完了・テスト 3 件緑 |
| メトリクス | `src/backend/observability/metrics.py` — `audit_revision_total{strategy,outcome}` / `audit_revision_duration_seconds` / `audit_lessons_total{action,dimension}` / `audit_lessons_injected_chars{book_id}` | 完了 |
| テンプレート golden | `tests/contract/fixtures/{rag,lessons}_prompt_baseline/final_writing_prompt.j2.golden`(3416 bytes, R5+H8+M1 同期済) | 完了・バイト同一契約緑 |

### 1.2 フラグ一覧(`src/agents/audit_agent/config.py` 実査)

| 設定 | 既定 | 役割 |
|:---|:---|:---|
| `ENABLE_AUDIT_QUOTE_PATCH` | `False` | quote 置換戦略の总スイッチ(OFF=追記互換) |
| `ENABLE_AUDIT_LESSONS` | `False` | 教訓記録・注入の总スイッチ |
| `AUDIT_QUOTE_MAX_CHARS` | `400` | 置換対象 quote の長さ上限 |
| `AUDIT_QUOTE_MAX_PATCHES` | `3` | 1 監査あたり置換件数上限 |
| `AUDIT_LESSON_ACTIVE_MAX` | `20` | book あたり active 上限 |
| `AUDIT_LESSON_INJECT_MAX_ITEMS` | `5` | 注入件数上限 |
| `AUDIT_LESSON_BLOCK_MAX_CHARS` | `800` | 注入ブロック文字数上限 |
| `AUDIT_LESSON_MAX_CHARS` | `200` | 教訓 1 件の文字数上限 |
| `AUDIT_LESSON_MIN_OCCURRENCES` | `1` | 注入に必要な最少発生回数(D3 の対象) |

### 1.3 提案9 評価基盤(`config/audit_calibration.yaml` 実査)

- `gate`: mode / absolute_threshold(70.0) / advisory_threshold(80.0) / percentile / cliche_max / weights
- `pairwise`: enabled / shadow_enabled / anchor_count
- `score_calibration` / `bias_correction` / `evaluator_version`
- 本計画では `revision:` セクションを**新規追加せず**、判定基準は本書に記載し、結果のみ `docs/STATUS.md` に記録する(設定ファイル肥大化の防止)

---

## 2. 設計原則(本計画の拘束)

| # | 原則 | 機械的保証 |
|:---|:---|:---|
| **P1** | **判定不通なら既定 OFF 維持** — ON 化は「実測による改善証明」が前提。根拠のない ON 化を禁止 | O9 の判定表を `docs/STATUS.md` に記録 |
| **P2** | **Shadow 先行** — 本番影響ゼロの状態でメトリクスを先に観測する。計測できない判断はしない | O4/O5 |
| **P3** | **同一データセット比較** — AB は同一原稿群で旧/新を実行し、提案9の評価基盤でスコア比較する | O6 |
| **P4** | **段階解禁** — off → shadow → 一部書籍 ON → 全書籍 ON の 4 段階。各段階の解禁ゲートを満たさないと次へ進まない | 各 Phase のゲート定義 |
| **P5** | **即時ロールバック** — flag 1 本で旧挙動に戻せることを各段階で再確認する | O2/O3 各ステップ末尾 |
| **P6** | **M1 とのテンプレート共有** — j2 変更は禁止(本計画でテンプレートに触れない)。両 golden は現状維持 | 本書に j2 編集ステップを置かない |

---

## 3. 実装ステップ(Phase O1-O4 / 12 ステップ)

### Phase O1: 事前健全性確認(O1-O3)

- **O1 全テスト緑確認** — 以下を実行し、363 passed / 1 skipped であることを記録:
  ```bash
  .venv/bin/python -m pytest \
    tests/unit/test_quote_replacer.py tests/unit/audit/ \
    tests/unit/agents/test_audit_lesson_hooks.py \
    tests/unit/writing/test_prose_refiner_fail_closed.py \
    tests/contract/test_h8_lessons_prompt_injection.py \
    tests/contract/test_v6_audit_surgical_patch.py \
    tests/contract/test_v6_audit_gate_thresholds.py \
    tests/contract/test_v6_audit_parallel_equivalence.py \
    tests/contract/test_rag_prompt_injection.py tests/audit/ -q
  ```
  1 件でも赤なら本計画を中断し PLAN_H8 に戻る。
- **O2 マイグレーション適用確認** — 本番相当 DB で `alembic upgrade head` を実行し、`audit_lessons` テーブル生成と `ix_audit_lessons_book_status_dim` インデックスを確認。 downgrade(`0034` へ)も一度実行して再適用できることを確認。
- **O3 メトリクス露出確認** — `/metrics` エンドポイントに `audit_revision_total` / `audit_lessons_total` / `audit_lessons_injected_chars` が露出していることを curl で確認。flag OFF 状態でカウンタが増え**ない**(無音)ことも確認。

### Phase O2: Shadow 計測(O4-O5)

- **O4 lessons 記録の shadow 有効化** — `ENABLE_AUDIT_LESSONS=true` のみ設定し、`AUDIT_LESSON_MIN_OCCURRENCES=99`(事実上注入なし)として**記録のみ**を 1-2 作品分走らせる。観測項目:
  - `audit_lessons_total{action="record"}` の話あたり発生件数
  - dimension 別の分布(`group by (dimension)`)
  - `occurrences` 分布(同一教訓の再発頻度 → D3 の材料)
  - `audit_lessons` テーブルの行数が `AUDIT_LESSON_ACTIVE_MAX=20` で頭打ちになるか
  - **fail-open 動作確認**: DB を一時的に停止させ、監査フローが継続し warning ログのみで止まらないこと(P2)
  - 完了後 `ENABLE_AUDIT_LESSONS` を OFF に戻す。
- **O5 quote_patch 影響面の静的確認** — `ENABLE_AUDIT_QUOTE_PATCH=true` で**テスト環境のみ**既存 contract テストを再実行し、追記互換経路(`strategy="actionable_patch"`)が quote_patch 経路に置き換わっても `test_v6_audit_surgical_patch.py` のマトリクスが緑であることを確認。**本番ではまだ ON にしない**。

### Phase O3: AB 検証(O6-O8)

- **O6 検証データセット構築** — 提案9の評価データセットと同一原稿群を使用:
  - 3 プリセット × 20 話 = 60 話分の bluepirnt/draft ペア
  - 各話に `failed_audits` を含む監査失敗シードを付与(quote_patch 用: `original_quote` が本文に存在する structured 差分 / lessons 用: 不合格履歴)
  - データセットは `tests/contract/fixtures/` ではなく `var/ab_datasets/h8/` に配置し、コミット対象外とする
- **O7 quote_patch AB 実施(D1)** — 同一データセットで 2 条件を実行:
  - 条件 A: `ENABLE_AUDIT_QUOTE_PATCH=0`(追記互換)
  - 条件 B: `ENABLE_AUDIT_QUOTE_PATCH=1`
  - 計測指標:
    1. **採用率** = `quote_patch applied / (applied + rejected + not_found)` ← PromQL: `sum(rate(audit_revision_total{strategy=~"quote_patch.*",outcome="applied"}[1h])) / sum(rate(audit_revision_total{strategy=~"quote_patch.*"}[1h]))`
    2. **再監査合格率**: パッチ適用後に再監査した話のうち `gate.aggregate_score >= 70` の割合
    3. **全文再生成回数**: `audit.regeneration.full` イベント数(追記型は末尾講評混入で不合格→再生成が増える)
    4. **LLM コスト**: `llm_api_tokens_total` 差分(増分 ≤ +5% を目標)
  - **記録**: 結果表を `docs/STATUS.md` §10 に追記
- **O8 lessons AB 実施(D2/D3)** — 同一データセットで 3 条件を実行:
  - 条件 A: `ENABLE_AUDIT_LESSONS=0`
  - 条件 B: `ENABLE_AUDIT_LESSONS=1, AUDIT_LESSON_MIN_OCCURRENCES=1`
  - 条件 C: `ENABLE_AUDIT_LESSONS=1, AUDIT_LESSON_MIN_OCCURRENCES=2`
  - 計測指標:
    1. **同 dimension 再発率**: 教訓記録済 dimension の 5 話窓再発生件数(B/C vs A)
    2. **監査スコア劣化**: `book_score_overall` の平均差(劣化 ≤ -2.0 点なら NG)
    3. **プロンプト増分**: `audit_lessons_injected_chars` の p95(≤ 800 字)
    4. **汚染率**: 教訓注入により新規に不合格となった dimension の数(B/C で新規出現した失敗)
  - D3 は B vs C の比較で決定: C が B と同等の再発率低減を示しつつ汚染率が低ければ `MIN_OCCURRENCES=2`

### Phase O4: 判定・ロールアウト(O9-O12)

- **O9 判定基準の適用(D1/D2/D3)** — 以下の表に従い判定する:

  | フラグ | ON 条件(全て満たすこと) | 不達時の処理 |
  |:---|:---|:---|
  | `ENABLE_AUDIT_QUOTE_PATCH` | 採用率 ≥ 60% / 再合格率 ≥ 現行 / コスト増 ≤ +5% / 段落潰れ 0 件(`SpanPatchApplier` reject による本文破壊なし) | 既定 OFF 維持 + 不達理由を `docs/STATUS.md` §10 に記録 |
  | `ENABLE_AUDIT_LESSONS` | 再発率が有意に低下 / スコア劣化 ≤ -2.0 点 / プロンプト増分 ≤ 800 字 / 汚染率 0 件 | 既定 OFF 維持 + 同上 |
  | `AUDIT_LESSON_MIN_OCCURRENCES` | B vs C の比較結果 | 既定 1 維持 |

- **O10 flag 既定変更(条件付き)** — 判定通過フラグのみ:
  1. `src/agents/audit_agent/config.py` の該当既定値を `True` に変更(コード 1 行)
  2. `.env.example` にコメント付きで追記(既定値と挙動の説明)
  3. 対応 contract テストの「既定 OFF」assert を既定 ON に更新(`test_new_flags_default_on` 系)
  4. **段階解禁**: まずステージング 1 作品 → 3 日観測 → 全書籍。観測中に `audit_revision_total{outcome="rejected"}` の急増や P95 レイテンシ悪化があれば即 OFF ロールバック
- **O11 ドキュメント更新** — `docs/STATUS.md` §10 に AB 結果表・判定・既定値を記録。`plans/PLAN_H8_SPAN_REVISION_26STEPS.md` §10 実施記録の F 行を「✅ 完了」に更新。`docs/ROADMAP_IMPROVEMENTS.md` の提案 8 行に AB 結果サマリを追記。
- **O12 完了報告・残課題整理** — 実施記録をコミット。未達フラグがある場合は「再挑戦条件」(例: 監査プロンプト改善後に再測定)を文書化し、PLAN_H8 系をクローズ。

---

## 4. リグレッション防止テスト計画(運用フェーズ)

| ID | 対象 | 内容 | Phase |
|:---|:---|:---|:---|
| **V1** | 全 H8 テスト群 | O1 の緑確認を毎回実施。1 件でも赤なら運用中断 | O1 |
| **V2** | マイグレーション | `alembic upgrade head` → `downgrade 0034` → `upgrade head` の往復 | O2 |
| **V3** | メトリクス無音性 | flag OFF で `audit_*` カウンタが増加しないこと | O1 |
| **V4** | fail-open | DB 停止時に監査フローが継続すること | O4 |
| **V5** | バイト同一契約 | flag ON 化**後も** `test_rag_prompt_injection` / `test_h8_lessons_prompt_injection` が緑(テンプレート不変であること) | O10 |
| **V6** | ロールバック演習 | flag ON → OFF で旧挙動(追記互換)に戻ることをステージングで実施 | O10 |

---

## 5. リスクと緩和

| リスク | 影響 | 緩和 |
|:---|:---|:---|
| AB データセットが本番分布と乖離し、採用率が過大/過小評価される | 中 | 提案9の実データセットを使用。乖離疑い時は本番 shadow 計測で再検証 |
| 教訓の汚染(誤指摘が次話の文体を歪める) | 中 | 条件 C(MIN_OCCURRENCES=2)を必ず比較。汚染率 0 件を ON 条件に含める |
| `audit_lessons` テーブル肥大化 | 低 | `AUDIT_LESSON_ACTIVE_MAX=20` のエビクション + graduated/archived レコードの定期クリーニング(将来課題として文書化) |
| flag ON 後のレイテンシ悪化(quote 検索の O(n) スキャン) | 低 | `AUDIT_QUOTE_MAX_CHARS=400` で quote 長を制限済み。P95 を O10 で観測し悪化時は即ロールバック |
| M1(PLAN_M1)との同時ロールアウトによる交絡 | 中 | H8 フラグと M1 フラグ(`pinned_edges_enabled`)を別タイミングで解禁し、交絡を回避 |
| 判定不通時のモチベーション低下による根拠省略 | 低 | P1 原則: OFF 維持も「決定」として必ず根拠を文書化 |

---

## 6. 受け入れ条件(Definition of Done)

1. O1-O12 が完了し、V1-V6 全て記録済み
2. D1/D2/D3 の判定結果と根拠が `docs/STATUS.md` §10 に記録されている(ON 化・OFF 維持のいずれでも)
3. ON 化したフラグは contract テストの既定値 assert が更新され、CI で常時検証されている
4. ロールバック手順(flag 1 本で旧挙動)が V6 で実演済み
5. `docs/ROADMAP_IMPROVEMENTS.md` の提案 8 行に AB 結果サマリが追記され、提案 8 が完全クローズしている

---

## 7. 工数見積(人日)

| Phase | 実装(運用) | テスト/計測 | 小計 |
|:---|:---:|:---:|:---:|
| O1 事前確認 | 0.5 | 0.5 | 1.0 |
| O2 Shadow | 1.0 | 1.0 | 2.0 |
| O3 AB 検証 | 1.5 | 2.0 | 3.5 |
| O4 判定・ロールアウト | 1.0 | 1.0 | 2.0 |
| **合計** | **4.0** | **4.5** | **8.5** |

実コード変更は O10 の flag 既定 1 行(+テスト assert 更新)のみ。大部分は運用・計測である。

---

## 8. 実施記録

| Phase | ステップ | 状態 | 実施結果 |
|:---|:---|:---:|:---|
| O1 | O1-O3 | ⬜ | 未着手 |
| O2 | O4-O5 | ⬜ | 未着手 |
| O3 | O6-O8 | ⬜ | 未着手 |
| O4 | O9-O12 | ⬜ | 未着手 |
