# PLAN_S1: 物語構造制御の一本化と本番配線計画 — narrative_balancer・テンション曲線・伏線LLM投票・段階解禁

- **文書ID**: PLAN_S1_STRUCTURE_CONTROL_WIRING_27STEPS
- **作成日**: 2026-11-09
- **対象**: AutoNovel v6.0.0
- **位置づけ**: 精査レポート改善提案 **#7「物語構造制御の一本化と本番配線」** の実装計画。
  Spine の執筆経路への注入は [PLAN_F1B_SPINE_COMPLETION_18STEPS.md](PLAN_F1B_SPINE_COMPLETION_18STEPS.md)（**2026-11-09 実装済み** — `build_drafting_prompt` の spine 引数 `prompts/manager.py:622-708`、`resolve_spine` 呼び出し `src/engine/default_plot_expander.py:91,174`、契約テスト `tests/contract/test_spine_prompt_injection_drafting.py` 等）が担うため、**本計画は残り 4 本柱**を扱う:
  1. **narrative_balancer（DSP/CSP/Grammar）の本番配線**（CLI のみ・かつ import 壊れの状態を解消）
  2. **プリセット tension curve の配線**（`get_tension_curve` が呼び出し元 0 件）
  3. **伏線回収判定への LLM 第 4 投票**（改善 #9 で実装した判定器キャリブレーション基盤を再利用）
  4. **SPINE_QUALITY の段階解禁**（F1B §8-2 で「非目標」とされた既定変更を、証拠ゲート付きで実行する手順）
- **関連**:
  - [docs/AI_JUDGE_CALIBRATION_PLAN.md](../docs/AI_JUDGE_CALIBRATION_PLAN.md)（改善 #9 = M0-M6 完了。マスキング判定・SSOT・shadow モードの設計を流用する）
  - [docs/STATUS.md](../docs/STATUS.md) §5（Spine 配線の SSOT）・§7（K1-K3 実測）
  - [docs/narrative_balancer_guide.md](../docs/narrative_balancer_guide.md)
- **原則**: F1B §2（P1-P5）を引き継ぐ。特に **D7（推測禁止 — 行番号は実装時に必ず grep で再確認）**

---

## 0. TL;DR

物語構造制御の資産（STORY_SPINE 38 パターン、narrative_balancer 数理エンジン、9 ジャンルのテンション曲線）は
**実装・単体テスト済みだが、本番パイプラインに効いていない**。残るギャップは次の 4 つ。

| # | ギャップ | 現状の証拠（2026-11-09 実査） | 影響 | 本計画の対応 |
|:---|:---|:---|:---|:---|
| **G-1** | narrative_balancer が**本番未配線**。src 内の消費は CLI のみで、かつ CLI は存在しないモジュールを import して即 `ImportError` | `src/cli/main.py:46-60` が `src.narrative_balancer.dsp_balancer`（実体は `src/narrative_balancer/dsp/` パッケージ）を import | **高** | Phase N |
| **G-2** | `get_tension_curve()`（9 ジャンル分の丁寧な curve_points / catharsis_spikes）が**呼び出し元 0 件** | `src/services/preset_loader.py:127-147`。src 内参照なし | 中 | Phase O |
| **G-3** | 伏線回収判定が**自己申告だけで RESOLVED 到達可能**（metadata 自己申告 40pt + 契約 35pt = 75pt ≧ 閾値 75pt） | `src/engine/foreshadowing/ensemble_judge.py:41-59,63`。閾値 75/35/55/15 はハードコード | **高** | Phase P |
| **G-4** | F1B の H6（設定 SSOT）/ H7（per-book 選択 UI）が未完。`SPINE_QUALITY` は env のみ、frontend に `spine_quality` 参照 0 件 | `docs/STATUS.md:307`（env のみ）。`grep -rln spine_quality frontend/src` → 0 件 | 中 | Phase R |

**最重要契約（F1B P1 を全柱に拡張）**:
`NARRATIVE_STRUCTURE_GATE=off`（既定）・`ENABLE_FORESHADOW_LLM_VOTE=off`（既定）のとき、
**執筆パイプラインの全出力（プロンプト・DB 保存内容・判定結果）が現行とバイト単位で完全一致**する。
既存書籍の再生成結果を変えない。off で配線だけをリリースし、証拠（Phase R）が揃ってから段階解禁する。

---

## 1. 現状の正確な記録（2026-11-09 実査）

### 1.1 実装済み（触らない・壊さない）

| 層 | 実体 | 状態 |
|:---|:---|:---|
| Spine 配線 | F1B Phase H/I 完結（drafting / macro / micro への注入 + 契約テスト群） | 完了 |
| 判定器基盤（改善 #9） | `src/audit/judge_panel.py`（マスキング付き 3 系統判定・z 正規化中央値投票・fail-closed）、`config/audit_calibration.yaml`（SSOT、ハードコード再導入防止テスト付き）、`src/audit/shadow_audit.py`（影監査）、`scripts/analyze_shadow_agreement.py`、`AuditRun` ORM | 完了 |
| balancer 本体 | `src/narrative_balancer/` — DSP（FFT 中だるみ検知+畳み込み補正）、CSP（OR-Tools CP-SAT、`csp/tension_constraints.py:11-29` の物理則）、Grammar（Earley+DP）、Arbitrator（**優先度 Grammar > CSP > DSP**、`arbitrator/balancer.py:38` `orchestrate()`、`arbitrator/models.py:58` `IntegratedResult`、`arbitrator/applier.py:12` `CorrectionApplier.apply()`） | 完了（未配線） |
| 伏線投票（LLM 0 回） | `ensemble_judge.py` 3 票（契約 35 / metadata 自己申告 40 / 構文解析 25）、`PredicateScorer`、KPI `kpi.py` | 完了 |
| 既存テスト | `tests/unit/narrative_balancer/`（6 ファイル — CLI/単体）、`tests/unit/story_spine_wiring/`（10 ファイル）、`tests/contract/test_spine_prompt_injection_*.py`、`tests/config/test_spine_quality_setting.py`、`tests/unit/story_spine/test_spine_alignment_measure.py` | 完了 |

### 1.2 壊れている / 未配線（本計画の対象）

| 事実 | 証拠（file:line） |
|:---|:---|
| CLI が壊れた import | `src/cli/main.py:46,50,54` — `src.narrative_balancer.dsp_balancer` / `csp_balancer` / `grammar_balancer` は**実在しない**（実体は `dsp/` `csp/` `grammar/` パッケージ） |
| ドメイン整合チェックが本番未接続 | `src/domain/domain_services/plot_domain_service.py:114-116` — tension jump > 50 のみ。`check_episode_continuity` の本番呼び出し元 0 件（export のみ）。**本番パイプラインはドメイン `Plot` を永続化しない**（`auto_workflow_pipeline.py` / `generation_tasks.py` / `episode_writing_workflow.py` に plot_repo 参照なし） |
| 本番のプロット入口 | macro 一括生成 = `src/services/pipeline_steps.py:150-152` → `DefaultPlotExpander.expand_macro_skeletons`（`src/engine/default_plot_expander.py:59-`、spine 解決 `:91`）。micro JIT = `src/agents/writing/episode_writer.py:206-208` → `ensure_detailed_plot` |
| tension スケールの 2 重規格 | macro スキーマは **0-100**（`src/models/plot.py:370-376`、テンプレ `macro_plot_skeleton.j2:45`「0〜100の整数」）、balancer の `Beat` は **0-10**（`src/narrative_balancer/models.py:27-29`）。CSP 物理則は `max_step_delta=4`・3 話ローリング合計 ≥ 6（0-10 基準、`csp/tension_constraints.py:22-29`） |
| curve 資産が遊んでいる | `get_tension_curve`（`preset_loader.py:127-147`、既定曲線付き）。`src/presets/zarma/tension/tension_curve_zarma.yaml` — curve_points（進行度×0-1 テンション）/ stress_threshold / catharsis_spikes |
| 伏線自己申告バイパス | `ensemble_judge.py:41-59` — metadata `resolved` 申告 40pt + 契約 35pt = 75pt で閾値到達。LLM 投票なし。閾値・配点はハードコード |
| 依存関係 | `ortools>=9.10.0` は必須依存（`requirements.txt:100`、`pyproject.toml:49`）— 欠落は異常環境のみだが gate は fail-open で備える |

---

## 2. 設計原則（本計画の拘束）

| # | 原則 | 機械的保証 |
|:---|:---|:---|
| **P1** | **off で差分ゼロ**。`NARRATIVE_STRUCTURE_GATE=off`（既定）・`ENABLE_FORESHADOW_LLM_VOTE=off`（既定）で、プロンプト・DB 保存・判定結果が現行と完全一致 | Phase Q1 / Q4 / Q8 / Q9 |
| **P2** | **balancer 経路は LLM 0 回・決定論**。CP-SAT は固定シードで同入力→同出力。gate 内で LLM を呼ばない | Q2 / Q4 |
| **P3** | **fail-open**。gate・投票・曲線解決のいかなる例外も執筆を止めない（off 挙動へフォールバック）。監査（fail-closed）と逆方針であることを docs に明記 | Q3 / Q8 |
| **P4** | **パラメータは SSOT**。配点・閾値・mode は `config/narrative_structure.yaml` と `config/audit_calibration.yaml` に置き、ハードコード再導入を AST/grep テストで禁止（改善 #9 M4 パターン踏襲） | Q6 / Q9 |
| **P5** | **再実装禁止**。補正は `GlobalNarrativeBalancer.orchestrate` + `CorrectionApplier` を使い、投票は `judge_panel` のマスキング設計・`shadow_audit` の影モード設計を流用する。新アルゴリズムを作らない | 各ステップの diff レビュー |
| **P6** | **enforce の補正対象は tension のみ**。beat_type 変換（MIDPOINT_DISASTER 等）・summary 書き換えは禁止（LLM が設計した物語構造を数理エンジンが上書きしない）。SSOT に上書き禁止フィールドを明記 | Q4 / Q6 |
| **P7** | **品質ゲートの悪化禁止**。`config/ci_lint_baseline.json`（burn-down: ruff 85 / mypy 952、README の 1122 は陳腐）・coverage `fail_under=60` を悪化させない | 各ステップで `make lint && make typecheck` |

---

## 3. 実装ステップ（依存順・27 ステップ）

> 行番号は **実装時に必ず grep で再確認**（原則 D7）。

### Phase N: narrative_balancer 本番配線（G-1 の解消）

| Step | 対象 | 内容 | 検証コマンド | 伴うリグレッションテスト |
|:---|:---|:---|:---|:---|
| **N1** | `src/cli/main.py:44-60` | 存在しないモジュール import を実パッケージに修正（`DspTensionBalancer` / `CSPNarrativeBalancer` / `GrammarNarrativeBalancer` の**実在する公開クラス名を grep で確認**してから書く）。`cmd_balance` の出力も実行結果（違反検出数等）を表示するよう最小修正 | `python -m src.cli.main balance --type dsp --input <fixture>` で import error が出ないこと ＋ **Q-CLI** | Q1（CLI は gate 配線と独立して動くこと） |
| **N2** | `src/engine/structure_gate.py`（**新設**） | ① `BeatMapper`: `EpisodeMacroSkeleton`（tension 0-100、`src/models/plot.py:370-376`）→ `Beat`（tension 0-10、`models.py:25-41`）変換。÷10、範囲外クランプ、欠損/NaN は None 許容（`Beat.tension: Optional[float]`）。beat_type マッピング表は `config/narrative_structure.yaml` に置く（コードにハードコードしない）。② `NarrativeStructureGate`: mode（off/warn/enforce）に応じ `PlotState.from_beats()` → `GlobalNarrativeBalancer.orchestrate()` → `IntegratedResult` の `validation_report`/`conflicts` を violations として抽出。warn: ログ+ reporter 報告のみ。enforce: `CorrectionApplier.apply()` 結果の **tension フィールドのみ**を batch へ逆変換（×10 して round）。全例外を catch し off と同一の戻り値（fail-open）。`NARRATIVE_STRUCTURE_GATE` env + SSOT yaml を読む loader も同ファイルに置く | `pytest tests/unit/narrative_balancer -q` ＋ **Q2/Q3** | Q2 / Q3 |
| **N3** | `src/engine/default_plot_expander.py` `expand_macro_skeletons`（`:59-`） | batch パース直後・DB 保存前に gate 実行。**mode=off（既定）では gate を呼ばない**（挙動同一）。warn: violations を reporter に報告。enforce: 補正済み beats を `PlotMacroBatch.episodes` に反映してから保存。spine と同様に **例外は logger.debug で握り fail-open**（`default_plot_expander.py:92-94` の既存パターンに合わせる） | `pytest tests/unit/engine -q -k plot_expander` ＋ **Q1/Q4** | Q1 / Q4 |
| **N4** | `src/engine/default_plot_expander.py` `ensure_detailed_plot` / `expand_single_micro`（`:100-191`） | micro 経路の軽量検証: 直前話 tension との \|Δ\| を SSOT の `max_step_delta`（0-100 換算）で確認。違反時かつ warn 以上のとき、micro プロンプトに「直前話テンション X → 本話は X±40 以内に設計」の**補正指示 1 行**を追記（enforce での無理やりな数値固定はしない）。off では追記しない（バイト同一） | `pytest tests/unit/engine -q -k plot_expander` ＋ **Q5** | Q5 |
| **N5** | `src/domain/domain_services/plot_domain_service.py:114-116` | 閾値 50 のハードコードを N2 の制約定数（SSOT）へ寄せ、`check_episode_continuity` が**本番未接続であること**を docstring に明記（誤配線防止）。動作変更はしない（ドメイン層の本番配線は §8 非目標） | `pytest tests/unit -q -k plot_domain` | Q1（ドメイン層の挙動不変） |
| **N6** | `config/narrative_structure.yaml`（**新設**） + loader | SSOT: `mode: off` / `max_step_delta: 4`（0-10 基準） / `rolling_min_sum: 6` / `enforce_overwrite_forbidden: [beat_type, summary, characters]` / `beat_type_mapping`。loader は env で mode を上書き可能（env > yaml）。**未知 mode は off に倒す**（`get_spine_quality()` の `prompts.py:111-112` パターン踏襲）。改善 #9 M4 と同型の**ハードコード再導入防止テスト**を伴う | `pytest tests/config -q` ＋ **Q6** | Q6 |

### Phase O: プリセット tension curve 配線（G-2 の解消）

| Step | 対象 | 内容 | 検証コマンド | 伴うリグレッションテスト |
|:---|:---|:---|:---|:---|
| **O1** | `src/services/pipeline_steps.py:67-106`（PlanningStep 付近） | `load_preset_for_pipeline()` で取得した preset に対し `get_tension_curve(preset)` を呼び、`engine.plot_expander` に**既定 None の引数**で渡す（curve 未指定なら現行と完全同一）。preset 未選択書籍は None（`get_tension_curve` 内蔵の既定曲線を出さない — 既定曲線の出所が不明瞭になるため、None 通しを本計画の契約とする） | `pytest tests/unit -q -k pipeline_steps` ＋ **Q7** | Q7 |
| **O2** | `prompts/manager.py` `build_macro_plot_skeleton_prompt`（`:1178` 付近） | 署名に `tension_curve: Optional[list[list[float]]] = None` を追加（既定値付き・後方互換）。None なら何も連結しない（**バイト同一**）。指定時は「【目標テンション曲線（参考）】進行度 0.0 → tension 30 …」形式の参考テーブルを spine セクションの**後に**連結（spine との衝突時は spine duty を優先する注記を添える） | `pytest tests/contract -q -k spine` ＋ **Q7** | Q7 |
| **O3** | `src/engine/structure_gate.py`（N2 の gate に接続） | enforce 時の CSP soft constraint 参照曲線として curve_points を渡す（0-1 → 0-10 換算、`total_episodes` で進行度→話数に展開）。curve 未指定時は spine の `beat.tension` を参照（`resolve_spine` が既に供給）。**参照曲線は soft のみ** — hard 制約（物理則）を curve で上書きしない | `pytest tests/unit/narrative_balancer -q` ＋ **Q2** | Q2 |

### Phase P: 伏線回収 LLM 第 4 投票（G-3 の解消 — shadow → 本線の 2 段階）

| Step | 対象 | 内容 | 検証コマンド | 伴うリグレッションテスト |
|:---|:---|:---|:---|:---|
| **P1** | `src/engine/foreshadowing/llm_voter.py`（**新設**） | 入力: 伏線 1 本あたり description + 契約文 + 本文（該当キーワード前後 ±500 字ウィンドウ、全体 ≤ 3000 字）。出力: `{"action": "resolved"\|"progressed"\|"unmentioned", "evidence_quote": str}`（JSON、temp 0.2、軽量モデル tier1）。**マスキング原則**（`judge_panel._build_judge_prompt` と同一方針: 出力元の痕跡をプロンプトに含めない）。例外・JSON パース失敗・タイムアウトは **None 投票**（fail-open、fail-closed にしない — 回収判定は監査ゲートではなく補完情報のため） | `pytest tests/unit/engine -q -k foreshadowing` ＋ **Q8** | Q8 |
| **P2** | `src/engine/foreshadowing/service.py:35-41` + `src/agents/writing/episode_writer.py:377` | `ForeshadowingService.__init__` に `llm_voter: Optional[...] = None` を追加（**既定 None = LLM 0 回・現行配点で完全後方互換**）。構築箇所では `_is_episode_digest_enabled()`（`episode_writer.py:32-43`）と同型の `_is_foreshadow_llm_vote_enabled()`（env `ENABLE_FORESHADOW_LLM_VOTE`、**既定 off**）で注入。`context_builder_agent.py:510` / `graph.py:276` は変更しない（None のまま） | `pytest tests/unit/engine -q -k foreshadowing` ＋ **Q9** | Q9 |
| **P3** | `src/engine/foreshadowing/ensemble_judge.py:14-102` + `config/audit_calibration.yaml` | `EnsembleJudge.evaluate` に `llm_vote: Optional[...] = None` 引数追加（既存 3 引数の呼び出し互換維持）。配点を SSOT へ: `config/audit_calibration.yaml` に `foreshadowing:` セクション（`weights: {contract: 35, metadata: 30, syntax: 20, llm_vote: 15}` / `thresholds: {resolved: 75, progressed: 35}` / `no_metadata_thresholds: {resolved: 55, progressed: 15}`）。**shadow 期間中は現行配点（metadata 40 / syntax 25）を維持**し、本線切替（R3）時に新配点へ切替。既定値（yaml 欠落時）は現行値 | `pytest tests/unit/engine -q -k ensemble` ＋ **Q9** | Q9 |
| **P4** | `src/engine/foreshadowing/` に shadow 記録 + `scripts/analyze_foreshadow_vote_agreement.py`（**新設**） | LLM 投票を**本線判定に加算せず記録**（改善 #9 `shadow_audit.py` パターン踏襲 — JSONL ログ `logs/foreshadow_vote_shadow.jsonl`、DB スキーマ変更なし）。分析 CLI で「LLM 票と現行判定の一致率」「metadata 過大申告率（metadata=resolved かつ llm=unmentioned の割合）」を出す | `python -m scripts.analyze_foreshadow_vote_agreement --json` ＋ **Q10** | Q10 |

### Phase Q: リグレッション防止テスト（詳細仕様は §4）

| Step | 作成物 | 検証コマンド |
|:---|:---|:---|
| **Q1** | `tests/contract/test_structure_gate_off_contract.py` | `pytest tests/contract/test_structure_gate_off_contract.py -q` |
| **Q2** | `tests/unit/narrative_balancer/test_structure_gate_wiring.py` | `pytest tests/unit/narrative_balancer -q` |
| **Q3** | `tests/unit/narrative_balancer/test_structure_gate_failopen.py` | 同上 |
| **Q4** | `tests/unit/engine/test_structure_gate_macro_hook.py` | `pytest tests/unit/engine -q` |
| **Q5** | `tests/unit/engine/test_micro_tension_delta.py` | 同上 |
| **Q6** | `tests/config/test_narrative_structure_setting.py` | `pytest tests/config -q` |
| **Q7** | `tests/contract/test_tension_curve_injection.py` | `pytest tests/contract/test_tension_curve_injection.py -q` |
| **Q8** | `tests/unit/engine/foreshadowing/test_llm_voter.py` | `pytest tests/unit/engine/foreshadowing -q` |
| **Q9** | `tests/unit/engine/foreshadowing/test_ensemble_four_votes.py` | 同上 |
| **Q-CLI** | `tests/unit/narrative_balancer/test_cli_balance_imports.py` | `pytest tests/unit/narrative_balancer -q` |
| **Q10** | `tests/unit/engine/foreshadowing/test_vote_shadow_recording.py` | 同上 |

### Phase R: 段階解禁と計測（G-4 の解消）

| Step | 対象 | 内容 | 検証コマンド |
|:---|:---|:---|:---|
| **R1** | `docs/STATUS.md` §7 付近 | **解禁ゲートの定義**（全て満たさないと次の段階に行かない）: (a) F1B J1-J3 の K1-K3 合成書籍実測が維持、(b) Q1 契約テスト緑、(c) `scripts/ci_judge_ratchet.py`（改善 #9）緑、(d) gate warn モードでの**違反率実測**（1 作品 40 話で違反話数 10% 以下を解禁目安とし、実測値を STATUS.md に記録） | 目視レビュー ＋ 既存 ratchet |
| **R2** | `src/backend/config.py` + frontend | F1B H6/H7 の完結: `SPINE_QUALITY` を backend config SSOT に明文化（既定 off）し、Studio/wizard に per-book 選択（off/soft/hard 3 択・既定 off・「テンプレートは初期値」注記）を追加。API は既存 payload `spine_quality`（`easy_mode.py:160`）を流用 | `pytest tests/config -q` ＋ `cd frontend && npx vitest run` |
| **R3** | 運用手順（docs/STATUS.md に runbook として記載） | **解禁順序（各段階で R1 ゲートを通ること）**: ① spine soft（新規書籍のみ）→ ② gate warn（全書籍・副作用ゼロ）→ ③ gate enforce（新規書籍のみ、tension のみ補正）→ ④ 伏線 LLM 投票本線（P3 の新配点へ切替）。**spine hard 既定化は本計画のスコープ外**（§8） | 目視レビュー |
| **R4** | `docs/STATUS.md` §5/§7 | 配線経路一覧（macro gate / micro delta / curve / 伏線投票）と実測値（違反率・一致率・KPI collection_rate の推移）を SSOT として記録 | 目視レビュー |

---

## 4. リグレッション防止テスト計画（詳細仕様）

### 4.1 全体方針

1. **既存テスト資産を壊さない**: `tests/unit/narrative_balancer/`（6 ファイル）・`tests/unit/story_spine_wiring/`（10 ファイル）・F1B の契約テスト群は**変更しない**。新規テストは空白を埋めるのみ。
2. **off 差分ゼロ契約を全柱に拡張**: F1B が spine でやったのと同じ契約を gate / curve / 伏線投票に適用。
3. **全部高速**: balancer 経路は LLM 0 回・CP-SAT は小規模（≤ 100 話）で p99 < 100ms。伏線投票テストは gateway をモック。CI 増分 1 分以内。
4. **壊れ方を指定してテストする**: 各テスト docstring に「壊れ方」を明記（§4.3 対応表）。

### 4.2 主要テストの仕様

#### Q1: `tests/contract/test_structure_gate_off_contract.py`（最重要）

```python
"""gate 配線の off 契約。

壊れ方: off なのに expand_macro_skeletons が gate を呼んで tension を変える /
DB 保存内容が変わる → この契約が赤になる。
"""

def test_off_mode_skips_gate_entirely():
    """mode=off で NarrativeStructureGate が**呼び出されない**こと
    （モックで呼び出し回数 0 を assert。off 時のオーバーヘッドもゼロにする）。"""

def test_off_mode_db_content_identical():
    """同一 bible + 同一 LLM 応答（モック固定）で、off と gate 導入前の
    保存内容（PlotMacroBatch → DB）が完全一致すること。"""

def test_env_missing_defaults_to_off():
    """NARRATIVE_STRUCTURE_GATE 未設定 = off であること（既定契約）。"""

def test_domain_layer_unchanged():
    """PlotIntegrityChecker.check_episode_continuity の戻り値が
    N2 前後で同一であること（SSOT 寄せが挙動変更を伴わないこと）。"""
```

#### Q2: `tests/unit/narrative_balancer/test_structure_gate_wiring.py`

```python
"""BeatMapper と gate の配線単体。

壊れ方: 0-100 ↔ 0-10 の換算ずれ / クランプ漏れ / 決定論崩れ → 赤。
"""

def test_beat_mapper_scale_conversion():
    """tension 100 → 10.0, 55 → 5.5, 0 → 0.0（×10 逆変換も同様）。"""

def test_beat_mapper_clamps_and_tolerates_missing():
    """tension 150 → 10.0, -5 → 0.0, None/NaN → Beat.tension=None で落ちないこと。"""

def test_gate_detects_csp_violations():
    """|Δtension|=6（0-10 基準）の 2 話を入れると violations に検出されること
    （CSP 物理則 tension_constraints.py:22-29 との整合）。"""

def test_gate_is_deterministic():
    """同入力で orchestrate を 2 回呼び、balanced_beats と applied_actions が
    完全一致すること（CP-SAT 固定シード契約）。"""

def test_gate_makes_no_llm_calls():
    """LLMGateway をモック化し、gate 実行中の呼び出し回数 0 を assert（P2）。"""

def test_enforce_only_touches_tension():
    """enforce 補正後も beat_type / summary / characters が不変であること（P6）。"""
```

#### Q3: `tests/unit/narrative_balancer/test_structure_gate_failopen.py`

```python
"""fail-open 契約（P3）。

壊れ方: gate の例外で執筆が落ちる / ortools 欠落環境で macro 生成が失敗 → 赤。
"""

def test_orchestrate_exception_falls_back_to_off_behavior():
    """GlobalNarrativeBalancer.orchestrate を例外を投げるモックにすると、
    gate は元の batch をそのまま返すこと（logger.debug のみ）。"""

def test_missing_ortools_degrades_to_warn():
    """ortools import を monkeypatch で失敗させ、gate が warn 報告のみで
    執筆パイプラインを継続すること（ImportError が外に漏れないこと）。"""

def test_malformed_integrated_result_is_tolerated():
    """IntegratedResult の is_valid=False や空 beats も落とさないこと。"""
```

#### Q4: `tests/unit/engine/test_structure_gate_macro_hook.py`

```python
"""expand_macro_skeletons への hook 回帰。

壊れ方: warn/enforce で gate が呼ばれない / enforce の補正が保存されない /
off でも reporter にノイズが出る → 赤。
"""

def test_warn_reports_violations_without_modifying_batch():
    """warn で reporter へ違反報告のみ・保存 batch は LLM 応答のまま。"""

def test_enforce_saves_corrected_tension():
    """enforce で補正済み tension（×10 復元・int）が DB 保存されること。"""

def test_gate_failure_does_not_stop_expansion():
    """gate が例外を投げても expand_macro_skeletons が正常完了すること（P3）。"""
```

#### Q5: `tests/unit/engine/test_micro_tension_delta.py`

```python
"""micro 経路の tension_delta 補正指示回帰。

壊れ方: off でもプロンプトに補正指示が混入 / 閾値を超えても指示が出ない → 赤。
"""

def test_off_byte_identical_micro_prompt():
    """mode=off で micro プロンプトがバイト単位で同一であること。"""

def test_warn_injects_delta_directive_on_violation():
    """直前 tension 90 → 本話 10（Δ80 > 40）のとき指示 1 行が入ること。"""

def test_no_directive_within_budget():
    """Δ40 以内では指示が入らないこと（過剰指示の防止）。"""
```

#### Q6: `tests/config/test_narrative_structure_setting.py`

```python
"""narrative_structure 設定の SSOT 契約（改善 #9 M4 パターン踏襲）。

壊れ方: ハードコード再導入 / 未知 mode が例外 / 既定値変更 → 赤。
"""

def test_default_mode_is_off(): ...
def test_unknown_mode_falls_back_to_off():
    """NARRATIVE_STRUCTURE_GATE=typo → off に倒すこと。"""
def test_env_overrides_yaml():
    """env 優先（env > config/narrative_structure.yaml）。"""
def test_no_hardcoded_thresholds_in_src():
    """src/engine/structure_gate.py 内に 75 / 0.9 / 40 等の
    マジックナンバーが SSOT loader を経由せず現れないことを AST で検査。"""
```

#### Q7: `tests/contract/test_tension_curve_injection.py`

```python
"""tension curve 注入の契約。

壊れ方: curve None でもプロンプトが変わる / spine との併用で衝突 → 赤。
"""

def test_curve_none_byte_identical():
    """tension_curve=None で build_macro_plot_skeleton_prompt がバイト同一。"""

def test_curve_injected_as_reference_after_spine():
    """指定時、参考テーブルが spine セクションより後ろに位置し、
    spine duty 優先の注記が入ること（O2 契約）。"""

def test_get_tension_curve_none_passthrough():
    """O1 契約: preset 未選択 → curve を計算せず None を通すこと
    （get_tension_curve 内蔵の既定曲線を出さない）。"""

def test_existing_call_sites_unaffected():
    """新引数を渡さない既存呼び出しが従来どおり動くこと。"""
```

#### Q8: `tests/unit/engine/foreshadowing/test_llm_voter.py`

```python
"""伏線 LLM 投票の fail-open とマスキング契約。

壊れ方: 投票の例外が check_and_resolve を止める / プロンプトに
出力元の痕跡が混入 / temp が変わる → 赤。
"""

def test_voter_exception_returns_none_vote():
    """gateway 例外・JSON 不正・タイムアウトのいずれも None 投票に倒れ、
    check_and_resolve が正常完了すること（P3）。"""

def test_prompt_is_masked():
    """構築プロンプトに model 名・provider 痕跡が含まれないこと
    （judge_panel のマスキング原則と同一検証）。"""

def test_windowed_excerpt_and_token_budget():
    """本文 ≤3000 字・キーワード前後 ±500 字に圧縮されること（コスト上限）。"""

def test_temperature_is_low():
    """LLM 呼び出しに temp=0.2 が渡ること（gateway モックで検証）。"""
```

#### Q9: `tests/unit/engine/foreshadowing/test_ensemble_four_votes.py`

```python
"""EnsembleJudge の第 4 票と配点 SSOT 契約。

壊れ方: llm_vote=None の現行判定が変わる / shadow 期間中に判定が変わる /
配点ハードコードが復活 → 赤。
"""

def test_legacy_signature_unchanged():
    """llm_vote を渡さない既存呼び出しで、judgment が現行と完全一致すること。"""

def test_weights_read_from_calibration_yaml():
    """config/audit_calibration.yaml の foreshadowing 配点が使われ、
    yaml 欠落時は現行値（35/40/25、閾値 75/35/55/15）にフォールバックすること。"""

def test_shadow_mode_does_not_change_verdict():
    """ENABLE_FORESHADOW_LLM_VOTE=shadow で、LLM 票が**判定に影響せず**
    記録のみされること（本線判定のバイト同一性）。"""

def test_llm_vote_counts_when_mainline_enabled():
    """本線切替（mode=mainline 相当）で第 4 票が加算されること
    （新配点 35/30/20/15 で合計 100 点設計になること）。"""
```

#### Q10 + Q-CLI

```python
# tests/unit/engine/foreshadowing/test_vote_shadow_recording.py
def test_shadow_log_written_and_analyzable():
    """shadow 記録が JSONL に書かれ、分析 CLI が一致率・過大申告率を
    再現可能な数値で返すこと（空ログで例外にしない）。"""

# tests/unit/narrative_balancer/test_cli_balance_imports.py
def test_cli_balance_imports_resolve():
    """src/cli/main.py の 3 balancer import が実在し、
    subprocess で `balance --help` が ImportError なしで起動すること。"""
```

### 4.3 壊れ方 → 赤になるテストの対応表（レビュー用チェックリスト）

| 想定される破壊 | 赤になるテスト |
|:---|:---|
| off なのに gate が動いて tension が変わる | Q1（全件） |
| 0-100 ↔ 0-10 換算ずれ・クランプ漏れ | Q2(`test_beat_mapper_*`) |
| gate 例外で執筆が落ちる / ortools 欠落で macro が失敗 | Q3（全件） |
| enforce が beat_type や summary を書き換える | Q2(`test_enforce_only_touches_tension`) / Q6 |
| warn/enforce で hook が呼ばれない・補正が保存されない | Q4 |
| off で micro プロンプトに補正指示が混入 | Q5 |
| ハードコード再導入（閾値・配点） | Q6(`test_no_hardcoded_thresholds_in_src`) / Q9(`test_weights_read_from_...`) |
| curve None でプロンプトが変わる・spine と衝突 | Q7 |
| 伏線投票の例外が回収処理を止める | Q8(`test_voter_exception_returns_none_vote`) |
| shadow 期間中に回収判定が変わる | Q9(`test_shadow_mode_does_not_change_verdict`) |
| CLI が再び ImportError | Q-CLI |
| CP-SAT の決定論崩れ | Q2(`test_gate_is_deterministic`) |

### 4.4 既存テストの棚卸し（本計画では変更しない）

- `tests/unit/narrative_balancer/` 6 ファイル — 変更不要（N1 の CLI 修正で `test_csp_cli` 等が緑になる**効果**を受けるのみ）。
- `tests/unit/story_spine_wiring/` 10 ファイル — 変更不要。N3 は `test_default_plot_expander_spine.py` が守る経路と同じ関数に触れるため、**このテストが先に赤になったら off 契約を疑う**。
- `tests/contract/test_spine_prompt_injection_drafting.py` / `_plotelements.py` — 変更不要（O2 の curve 注入が off 契約を守ることの検証もこれで二重化される）。

---

## 5. 効果測定

1. **テンション物理則違反率**: gate warn モードで 1 作品（40 話）生成し、`violations 話数 / 総話数` を STATUS.md §7 に記録（R1 の (d)）。解禁判断はこの実測で行う。
2. **伏線判定の品質**: P4 の一致率・metadata 過大申告率（llm=unmentioned かつ metadata=resolved の割合）を測定。**過大申告率が有意でなければ LLM 投票は導入しない**（コスト対効果が negative になるため）。
3. **KPI**: 既存 `ForeshadowingKpi`（`kpi.py`）の collection_rate / overdue を shadow 前後で比較。
4. **コスト**: balancer = **0 円**（LLM 0 回、Q2 で恒常保証）。伏線投票 = 1 話あたり回収判定対象 N 本 × 軽量モデル 1 回（shadow 中も同額、本線化しても増えない）。
5. **目標値**: テンション違反率 ≤ 10%（40 話中 ≤ 4 話）/ 一致率 ≥ 0.70 / K1-K3 維持（F1B 実測: 合成書籍 K1 ≥ 0.80、K2/K3 = 100%）。

---

## 6. リスクと対策

| リスク | 影響 | 対策 |
|:---|:---|:---|
| **enforce 補正が LLM の物語設計を壊す**（数理が正しくても物語が不自然に） | High | **P6**: 補正対象は tension のみ。beat_type 変換（MIDPOINT_DISASTER 等）・summary 書き換えは SSOT の `enforce_overwrite_forbidden` で禁止。enforce は新規書籍のみに段階解禁（R3） |
| **CSP の求解時間**が macro 一括（最大 40 話バッチ）で増大 | Medium | 既存 `PartialPlotState`（`csp/partial_state.py:8`）で確定話を固定。`benchmark_csp.py` のベースライン（p99 < 5ms/話）を踏襲し、gate 実行時間をログに残す。タイムアウト（SSOT で規定、案 2 秒）超過は fail-open |
| **伏線投票のコスト増**（1 話あたり N 本 × 1 呼出） | Medium | shadow 期間中に過大申告率を測り、**有意でなければ本線化しない**（§5-2）。ウィンドウ圧縮 ≤ 3000 字（Q8）と tier1 軽量モデルで単価を抑える |
| **off 差分ゼロの漏れ**で既存書籍の再生成結果が変わる | High | P1 契約を Q1/Q5/Q9 で機械保証。env 未設定 = off を Q1(`test_env_missing_defaults_to_off`) で固定 |
| `prompts/manager.py` / `service.py` への引数追加で既存呼び出しが壊れる | High | **既定値付き引数のみ**。Q7(`test_existing_call_sites_unaffected`) / Q9(`test_legacy_signature_unchanged`) で直接検証 |
| 設定の二重管理（env と yaml が食い違う） | Medium | env > yaml の優先順位を Q6(`test_env_overrides_yaml`) で固定し、STATUS.md に優先順位を明記（F1B H6 と同型） |
| 品質ゲート（ruff/mypy/format ratchet・coverage 60）の悪化 | Medium | 各ステップで `make lint && make typecheck && pytest -q` を通してから次へ（P7）。baseline は `config/ci_lint_baseline.json`（burn-down） |

---

## 7. 完了条件（Definition of Done）

- [ ] N1-N6・O1-O3・P1-P4 の全ステップが完了し、対応する検証コマンドが緑
- [ ] **Q1-Q10 + Q-CLI の全テストが緑**（off 差分ゼロ契約が gate / curve / 伏線投票の全柱に拡張されている）
- [ ] `python -m src.cli.main balance --type dsp` が ImportError なしで動く（N1）
- [ ] SSOT（`config/narrative_structure.yaml` + `config/audit_calibration.yaml` の foreshadowing セクション）が作られ、ハードコード再導入防止テストが緑
- [ ] shadow モードで 1 作品分の伏線投票が記録され、一致率・過大申告率が分析 CLI から取得できる（P4）
- [ ] `docs/STATUS.md` §5/§7 に配線経路一覧・解禁ゲート定義・実測値が記録されている（R1/R4）
- [ ] `make verify`（全品質ゲート一括）が通る
- [ ] 既定状態（env 未設定）での既存書籍再生成結果が変わっていないことの確認（Q1/Q5/Q9 の緑をもって代える）

---

## 8. 非目標（明確にやらないこと）

1. **ドメイン層 `PlotIntegrityChecker` の本番配線** — 本番パイプラインはドメイン `Plot` を永続化しないため、本番の構造ゲートは `DefaultPlotExpander` 経路（N3/N4）が正。ドメイン側は閾値 SSOT 寄せと文書化のみ（N5）
2. **narrative_balancer のアルゴリズム変更** — DSP/CSP/Grammar/Arbitrator のロジック・優先度（Grammar > CSP > DSP）は凍結。本計画は配線のみ
3. **`SPINE_QUALITY=hard` の既定化・全書籍強制適用** — F1B §8-2 を引き継ぐ。soft 解禁までを本計画のスコープとし、hard は R3 の runbook に記すのみ
4. **伏線投票の fail-closed 化** — 回収判定は監査ゲートではないため、投票失敗で執筆・回収を止めない（P3）。fail-closed は改善 #9 の監査文脈に限定
5. **semantic_cache・prefetch への新規統合** — 既存キャッシュ機構の変更はしない
6. **GraphRAG（改善提案 #1）・出力スキーマ等の他提案** — 別計画

---

## 9. 実施順序の目安（所要の概算）

| 順序 | ステップ | 前提 | 概算 |
|:---|:---|:---|:---|
| 1 | **N1 ＋ Q-CLI** | なし | 0.5h |
| 2 | **N2 ＋ N6 ＋ Q2/Q3/Q6** | なし（実在クラス名の確認含む） | 4h |
| 3 | **N3 ＋ Q1/Q4** | 2 | 2h |
| 4 | **N4 ＋ Q5** | 2-3 | 1.5h |
| 5 | **N5** | 2 | 0.5h |
| 6 | **O1 ＋ O2 ＋ Q7** | なし（N と独立） | 2h |
| 7 | **O3** | 2, 6 | 1h |
| 8 | **P1 ＋ Q8** | なし（N/O と独立） | 3h |
| 9 | **P2 ＋ P3 ＋ Q9** | 8 | 2.5h |
| 10 | **P4 ＋ Q10** | 8-9 | 2h |
| 11 | **R1-R4**（shadow 1 作品分の計測は別途運用時間） | 3-10 | 1.5h |

> **推奨の最初の一歩**: N1（CLI import 修正）＋ Q-CLI。副作用ゼロで着手でき、
> 存在しないモジュール import の除去は N2 以降の「実在クラス名の確認」ウォームアップになる。
> 並行作業は **Phase O（curve 配線）と Phase P（伏線投票）は Phase N に依存しない**ため、
> N2-N4 完了待ちの間に着手可能。

---

## 附録 A: 改善 #9 基盤との対応表（再利用の証拠）

| 本計画の要素 | 改善 #9（M0-M6）で実装済みの基盤 | 再利用の仕方 |
|:---|:---|:---|
| 伏線 LLM 投票のマスキング | `src/audit/judge_panel.py` `_build_judge_prompt`（出力元痕跡をプロンプトに含めない） | 設計踏襲（コード直接 import はしない — 監査 Validation Plane 専用クラスのため）。Q8 で同一検証を適用 |
| 配点・閾値の SSOT | `config/audit_calibration.yaml` + `src/audit/calibration_store.py`（ハードコード再導入防止テスト付き） | 同一ファイルに `foreshadowing:` セクションを追加（P3）。loader パターンを流用 |
| shadow モード | `src/audit/shadow_audit.py` + `scripts/analyze_shadow_agreement.py` | JSONL 影記録 + 一致率分析 CLI のパターンを踏襲（P4） |
| 段階解禁のゲート | `scripts/ci_judge_ratchet.py`（ratchet）+ `scripts/recompute_gate_percentile.py` | R1 の解禁ゲート (c) として ratchet を流用 |
| 計測の SSOT | `docs/STATUS.md` §7（K1-K3） | R4 で同一テーブルに追記 |

---

## 附録 B: 実装記録（2026-11-10 実装完了時点）

### B.1 完了ステップ

| Phase | ステップ | 状態 | 主な成果物 |
|:---|:---|:---|:---|
| N1 | CLI import 修正 | ✅ | `src/cli/main.py` 委譲実装 + `--input/--output/--config` 引数。ghost import 解消 |
| N2 | 構造ゲート本体 | ✅ | `src/engine/structure_gate.py`（BeatMapper / NarrativeStructureGate / detect_tension_violations / build_batch_balancer） |
| N3 | macro hook | ✅ | `default_plot_expander.expand_macro_skeletons` に off 短絡 hook（保存前に実行） |
| N4 | micro 差分指示 | ✅ | `expand_single_micro` に補正指示注入（off でバイト同一） |
| N5 | ドメイン層 SSOT 統合 | ✅ | `PlotIntegrityChecker` 閾値を SSOT に寄せ + 本番未接続を docstring 明記 |
| N6 | 設定 SSOT | ✅ | `config/narrative_structure.yaml` + loader（env > yaml > default、未知値は off 倒し） |
| O1 | curve 取得 | ✅ | `pipeline_steps.py` PlanStep で `get_tension_curve(preset)` → expander へ（preset 実質空なら None 通し） |
| O2 | curve プロンプト注入 | ✅ | `build_macro_plot_skeleton_prompt(tension_curve=...)`（None でバイト同一・spine 後ろに連結・duty 優先注記） |
| O3 | curve 逸脱指標 | ✅ | `compute_curve_deviation`（advisory。**下記 B.2 の逸脱 1 参照**） |
| P1 | LLM voter | ✅ | `src/engine/foreshadowing/llm_voter.py`（マスキング / temp 0.2 / ±500字窓 ≤3000字 / fail-open） |
| P2 | service 注入 | ✅ | `ForeshadowingService(llm_voter=...)` 任意引数 + `episode_writer.py` で `_resolve_foreshadow_voter`（既定 None = LLM 0 回） |
| P3 | 配点 SSOT | ✅ | `config/audit_calibration.yaml` `foreshadowing:` セクション + `vote_config.py` + `EnsembleJudge` 第 4 票対応（legacy シグネチャ完全互換） |
| P4 | shadow 記録 | ✅ | `vote_shadow.py`（JSONL）+ `scripts/analyze_foreshadow_vote_agreement.py`（一致率・過大申告率 CLI） |
| Q1-Q10 + Q-CLI | テスト | ✅ | 計 60+ テスト追加（全て LLM 0 回）。§4.3 の壊れ方対応表どおり |
| R1/R4 | 解禁ゲート定義・STATUS | ✅ | `docs/STATUS.md` §9 に配線経路・解禁ゲート・残作業を記録 |
| R2 | backend SSOT 確認 | ✅（backend部分） | SPINE_QUALITY の SSOT は F1B I5 で `src/llm/adapters/prompts.py` に確定済み。**frontend 選択 UI（H7）は残作業**（§B.3） |
| R3 | 解禁手順 | ✅（定義まで） | `docs/STATUS.md` §9.2 に runbook 化。実運用の shadow/warn 計測は運用タスク |

### B.2 計画からの逸脱（実装時に判明した理由付き）

1. **O3 の CSP soft constraint 化を断念** → advisory 逸脱指標 + プロンプト注入で代替。
   理由: 既存 CSP ソルバーに参照曲線型の soft 制約は存在せず、追加は P5（narrative_balancer
   のロジック凍結）違反になる。意図（enforce 時の curve 参照）は O2 のプロンプト注入が主経路。
2. **N5 の閾値を 50 → 40 に統合**（計画は「動作変更なし」記載）。
   理由: 一本化の趣旨は SSOT 統合であり、`check_episode_continuity` は本番未配線
   （ドメイン `Plot` は本番が永続化しない）のため実影響ゼロ。既存テスト
   （`test_plot_domain_service.py`）は Δ85 を使っており全パス。
3. **バッチ長スケール CSPConfig**（`_scaled_csp_config`）を新設。
   理由: `config/csp_balancer.yaml` は 40 話前提で、それ未満のバッチでは
   midpoint/climax 制約が実行不可能になり RuntimeError になる（実測）。
   設定の派生でありアルゴリズム変更ではない。CP-SAT は決定論保証のため
   `num_search_workers=1` に固定（P2）。
4. **off / None 時の kwarg 非送信**。`tension_curve=None` のときプロンプトビルダーと
   gate に kwarg 自体を渡さない。理由: duck-typed な PM 実装（F1B のテストフェイクを含む）
   との後方互換（F1B H2-H4 の「既定値付き追加で既存呼び出しを壊さない」パターン準拠）。
5. **YAML 1.1 の bare `off` ブール化対策**。`mode: "off"` をクォート必須にし、
   loader もブールを正規化（Q6 で契約固定）。

### B.3 残作業（本計画のスコープ内だが未実施）

1. ~~**F1B H7 の frontend 部分**: Studio/wizard への per-book spine 選択 UI~~
   → **2026-11-10 実装完了**。`SimpleModePanel.tsx` に 3 択セレクタ
   （`data-testid="spine-quality-select"`、既定 off、「テンプレートは初期値」注記付き）を追加。
   状態は `NovelContext` (`spineQuality`) で共有し、`useNovelGeneration` /
   `useStreamingWriter` の両ペイロードに反映（**off は送信しない = 差分ゼロ**）。
   バックエンドは `EasyModeInput.spine_quality`（Literal 検証付き）→
   `params["spine_quality"]` → `execute_generation` の `payload.get("spine_quality")` で消費
   （`None` は env 既定 `SPINE_QUALITY` に倒れる = 従来互換）。
   テスト: `SimpleModePanel.test.tsx`（I6 4 件）+ `test_easy_mode_router.py`（透過・検証 3 件）。
2. **R1 の実測運用**: gate warn で 1 作品（40話）生成し違反率を記録 /
   `ENABLE_FORESHADOW_LLM_VOTE=shadow` で shadow 記録を蓄積し一致率 ≥ 0.70 を確認。
   いずれも運用タスク（コード変更なし）。
3. **R3 の段階解禁実行**: §9.2 のゲート通過後に env を段階的に変更（運用タスク）。

### B.4 実装時に追加した回帰テストの実行コマンド

```bash
pytest tests/contract/test_structure_gate_off_contract.py \
       tests/contract/test_tension_curve_injection.py \
       tests/unit/narrative_balancer/test_structure_gate_wiring.py \
       tests/unit/narrative_balancer/test_structure_gate_failopen.py \
       tests/unit/narrative_balancer/test_cli_balance_imports.py \
       tests/unit/engine/test_structure_gate_macro_hook.py \
       tests/unit/engine/test_micro_tension_delta.py \
       tests/unit/engine/foreshadowing/ \
       tests/config/test_narrative_structure_setting.py -q
```
