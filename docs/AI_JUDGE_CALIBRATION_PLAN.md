# AI 判定器キャリブレーション実装計画(人手評価なし版)

> ステータス: 計画(未着手) / 作成日: 2026-11-09
> 元 document: 提案9「評価基盤の実証的キャリブレーション」→ 人手アノテーション不可のため AI-only 構成へ再設計
> 関連: `docs/OPTIMIZED_AUDITOR_DESIGN.md`(二層ハイブリッド監査), `scripts/ci_lint_ratchet.py`(ratchet 文化)

---

## 1. 目的と非目的

### 目的

1. 本番品質ゲート(`UnifiedAuditor` + `evaluate_gate`)の判定を、**人手アノテーションなしで**継続的に検証・校正できる仕組みを作る
2. 判定器の「擾乱への鈍感さ」「軸の一本化(何を壊しても同じ点数)」「ドリフト(モデル更新で分布が動く)」を機械的に検出する
3. 合格閾値(70.0)・AI定型上限(<3)・重み(定量40%/定性60%)を**ハードコードから SSOT 設定へ移行**し、劣化を CI ratchet で防止する

### 非目的(この計画ではやらない)

- 本番ゲートを毎回マルチモデルパネル化すること(v5.0 で 8 並列オーディターを廃止したコスト方針と矛盾する)
- 絶対スコアの人手相関検証(人手データが将来到達したときの拡張として付録 A に退避)
- 静的指標の学術化(別計画: 改善案6)

### 設計思想

**「AI 評価を品質の証明ではなく、候補の選別と災害の遮断に役割を限定する」。**

| 平面 | 構成 | 実行頻度 |
|---|---|---|
| 本番ゲート(Online) | 静的層 + 軽量 LLM 1 審査(現状維持) | 毎話 |
| 検証平面(Offline) | 擾乱スイート(Judge Validation Suite) | 判定器/プロンプト変更時 + 週次 |
| 検証平面(Offline) | 3 系統判定パネル(JudgePanel) | 週次ドリフト監視 + ゲート境界判定時 |
| 遷移平面(Shadow) | 旧絶対ゲートとペアワイズ判定の並列記録 | 切替前の 2 週間 |

---

## 2. 現状のコード事実(根拠)

| 事実 | 場所 |
|---|---|
| LLM 審査は先頭 3000 字のみ、単回、temp=0.2 | `src/agents/specialists/unified_auditor.py:136, 68` |
| 合格条件 `final >= 70.0 and len(cliches) < 3` が 3 箇所に重複ハードコード | `unified_auditor.py:251`, `src/domain/writing/coordinator.py:116`, `src/engine/auditors/hybrid_auditor.py:49,67` |
| 総合 = 定量 0.4 + 定性 0.6 | `unified_auditor.py:248` |
| ゲート閾値は env 調整可能(`AUDIT_GATE_THRESHOLD`)だが既定値が別管理 | `src/agents/audit_agent/config.py:28` |
| `ScoreCalibrator`(z 正規化+外れ値検出)は実装のみで未接続 | `src/services/score_calibrator.py` |
| `bias_correction` / `ncs_calibration` も未接続 | `src/services/bias_correction.py`, `src/services/ncs_calibration.py` |
| 監査の定量内訳(リズム/会話/クリフハンガー/定型数)は**永続化されない** | `AuditIssue`(`src/infrastructure/database/models/audit_issue.py`)は issue のみ |
| `BookScore` は 8 専門家系の軸で `UnifiedAuditor` の内訳が入らない | `src/infrastructure/database/models/book_score.py` |
| 主要モデルの単価未登録でコスト計上が $0 無言化 | `src/config/cost_optimization.py:5-10` (`MODEL_PRICING`) |
| fail-closed 文化(監査失敗時は不合格) | `unified_auditor.py:113-129` |
| LLM モック基盤がテストに存在 | `tests/mocks/llm_adapter.py` (`LLMMocker`, `MockLLMAdapter`) |
| ratchet スクリプトの先行例 | `scripts/ci_lint_ratchet.py` + `config/ci_lint_baseline.json` |

---

## 3. 全体アーキテクチャ

```
                        ┌──────────────────────────────────────────┐
                        │           Validation Plane               │
                        │                                          │
   原稿コーパス ──► 擾乱変換カタログ(決定的, LLM不使用)              │
                        │   T01..T10(DIR/INV)                      │
                        │        │                                 │
                        │        ▼                                 │
                        │   擾乱ラダー(強度 1x/2x/3x + baseline)     │
                        │        │                                 │
                        │        ▼                                 │
                        │   被験判定器 ──► metrics(ρ/識別性/INV/σ)   │
                        │        ▲                                 │
                        │   JudgePanel(3系統, マスク, 順序スワップ)   │
                        └──────────────────────────────────────────┘
                                     │ 結果 JSON
                                     ▼
                     config/judge_baseline.json (ratchet 基準)
                                     │
   ┌─────────────────────────────────┼─────────────────────────────────┐
   │ Online Plane                    ▼                                 │
   │  UnifiedAuditor ──► evaluate_gate ◄── config/audit_calibration.yaml │
   │  (静的層+LLM1回)      (SSOT: mode/threshold/cliche_max/weights)    │
   │        │                                                        │
   │        └──► AuditRun テーブル(内訳・メタ・本文ハッシュ永続化)        │
   │                                                                 │
   │  [Shadow] ペアワイズ判定(アンカー3話) ──► 判定一致率ログ(影響なし)   │
   │  [Best-of-N] 静的層フィルタ → ペアワイズ決勝(オプトイン)             │
   └─────────────────────────────────────────────────────────────────┘
```

**配置方針**: 新規トップレベルパッケージは作らない(`scripts/check_layer_boundaries.py` に抵触する恐れ)。新規モジュールは既存の `src/audit/` 配下に置く。

---

## 4. フェーズ 0: 計測基盤(M0, 工数 0.5 日)

### 4.1 `AuditRun` ORM モデル(新規)

`src/infrastructure/database/models/audit_run.py` — 既存規約(`audit_issue.py` の `Column` スタイル)に合わせる。

```python
class AuditRun(Base):
    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    ep_num = Column(Integer, nullable=False, index=True)

    # 定量内訳(rule_based_metrics 由来)
    q_rhythm = Column(Float, nullable=False)
    q_dialogue = Column(Float, nullable=False)
    q_cliffhanger = Column(Float, nullable=False)
    q_cliche_count = Column(Integer, nullable=False)

    # 定性内訳(unified_audit_prompt の 4 軸)
    qual_hook = Column(Float, nullable=False)
    qual_emotional = Column(Float, nullable=False)
    qual_character = Column(Float, nullable=False)
    qual_overall = Column(Float, nullable=False)

    final_score = Column(Float, nullable=False, index=True)
    is_passed = Column(Boolean, nullable=False)

    # 再現性のためのメタ
    gate_version = Column(String(50), nullable=False, default="1.0")
    model_name = Column(String(100), nullable=False)
    prompt_version = Column(String(50), nullable=False)
    temperature = Column(Float, nullable=False)
    judge_mode = Column(String(20), nullable=False)  # single | panel | pairwise | shadow

    # 本文スナップショット(リテイクで上書きされるため監査時点の本文を保持)
    text_hash = Column(String(64), nullable=False, index=True)
    text_snapshot = Column(Text, nullable=False)

    created_at = Column(CompatibleDateTime, server_default=func.now())
```

- `alembic/versions` は空であり `Base.metadata.create_all` 前提のため、`Base` 継承で自動作成。`scripts/check_migrations.py` の規約に抵触しないことを確認する
- 書き込みは `UnifiedAuditor.audit()` の最後(`src/agents/specialists/unified_auditor.py:237` の `audit()` 内)に 1 行追加。**監査の成功/失敗に影響させない**(書込失敗はログのみ、fail-open)

### 4.2 モデル単価登録(修正)

`src/config/cost_optimization.py` の `MODEL_PRICING` に追加:

- `gemma-4-31b-it`(writing 既定) / `gemini-3.5-flash-lite`(planning/audit 既定)
- 単価は provider 公開値を記入し、`README.md` のコスト注記と突き合わせる

### 4.3 M0 のテスト

| テスト ID | ファイル | 内容 |
|---|---|---|
| T-M0-1 | `tests/audit/test_audit_run_persistence.py` | `UnifiedAuditor.audit()` 呼び出しで `AuditRun` に全軸が 1 行書かれる。**定性軸の取りこぼし(欠落 0.0)を検出**する |
| T-M0-2 | 同上 | 監査本文の `text_hash` が同一本文で不変、異なる本文で変わる |
| T-M0-3 | 同上 | 書込例外時も `audit()` の戻り値・合否が変わらない(fail-open の回帰防止) |
| T-M0-4 | `tests/regression/test_model_pricing_registered.py` | `model_router._DEFAULTS` の全モデルが `MODEL_PRICING` に正の単価で存在する(**$0 無言化の再発防止**) |

---

## 5. フェーズ ②: 擾乱スイート(検証平面の中核, M1-M2, 工数 5 日)

### 5.1 新規モジュール

```
src/audit/perturbation/
    __init__.py
    transforms.py   # 変換カタログ(決定的・純関数)
    ladder.py       # 強度ラダー構築
    metrics.py      # ρ / 識別性 / INV / 再テスト σ
    suite.py        # オーケストレータ(被験判定器 callable を受ける)
```

### 5.2 変換カタログ仕様

各変換は `PerturbationTransform` dataclass(id, kind, affected_axes, apply, min_chars)として定義。**決定的(seed 固定)**・入力非破壊・出力非空・`\r\n` を含む入力でも正しく動作する(CR/LF は `tests/audit/test_static_rules_crlf.py` の先行例があるため最初から扱う)。

| ID | 変換 | 種類 | 期待応答(軸レベル) | 実装メモ |
|---|---|---|---|---|
| T01 | 末尾フック文削除 | DIR | `hook`↓, 他軸維持 | フックマーカー(`！？`, `」`, 引き語 6 種)を含む末尾文を 1-3 文削る |
| T02 | シーン順序シャッフル | DIR | `overall`↓ | 空行/シーンマーカーで分割し seed 固定シャッフル |
| T03 | キャラ名不整合入替 | DIR | `character_consistency`↓ | 固有名詞 1 種を特定段落のみ別名へ |
| T04 | AI 定型注入 | DIR | `cliche_count`↑, `overall`↓ | `AI_CLICHE_PATTERNS`(`rule_based_metrics.py:63-71`)から 5/10/15 句生成 |
| T05 | 会話→地の文要約 | DIR | 感情・flavor↓ | `「…」`行を要約文へ置換(会話比率が下がることを変換後 assert) |
| T06 | 中盤段落除去 | DIR | `overall`↓ | **3000 字盲検出用**: 先頭 3000 字のみ見る判定器はこれに鈍感なはず→不感なら「判定器が中盤を見ていない」診断シグナル |
| T07 | 段落重複挿入 | DIR | `overall`↓ | n-gram 反復が増えることを変換後 assert |
| T08 | 一貫した固有名詞改名 | INV | 全軸不変(±3 点) | 全出現箇所を一括改名 |
| T09 | 句読点・記号正規化 | INV | 全軸不変(±3 点) | 引用符・ダーシ等 |
| T10 | 再テスト | INV | 同一入力 2 回の σ≤5 | 変換ではないが suite が特別扱い |

**不変条件(各変換に静的 assert を実装)**:
- 出力が空でない / 入力より極端に短くない(≥ 60%)/ 長くない(≤ 150%)
- DIR 変換は「gold 特徴量」を必ず機械的に変化させる(T04 なら正規表現定型数が増える等)。**変換が効かなかった場合はスキップとして記録し、ラダーから除外**

### 5.3 ラダーとメトリクス

- ラダー: baseline(無変換) + 強度 1x/2x/3x(T04 は 5/10/15 句等)→ 各変換 4 点
- 合格基準(判定器 1 体あたり):
  - **ラダー Spearman ρ ≥ 0.8**(各 DIR 変換、baseline 込み 4 点)
  - **識別性**: 期待軸の低下量が他軸の低下量の 1.5 倍以上(「何を壊しても overall だけ下がる」一軸判定器の排除)
  - **INV**: T08/T09 の全軸 |Δ| ≤ 3.0
  - **再テスト**: T10 の全軸 σ ≤ 5.0(同一入力・同一 seed)
  - T06 診断: 中盤除去で `overall` が不変の場合、レポートに「HEAD-ONLY 判定器の疑い」を明記(自動失格にはしないが ratchet に記録)

### 5.4 CLI(新規)

`scripts/judge_perturbation_suite.py`:

```
使い方:
  python scripts/judge_perturbation_suite.py \
      --corpus storage/judge_corpus/*.txt     # 原稿 100 話(案9 P0 の AuditRun スナップショットから輸出)
      --judge unified_auditor                  # src/audit 配下の判定器レジストリ名
      --model <model_name> --prompt-version v1
      --out reports/judge_suite_<model>_<date>.json
オプション: --transforms T01,T04 --corpus-limit 20 (スモーク用)
```

- 出力 JSON: 判定器 ID、各変換×各話の全軸スコア、ρ/識別性/INV/σ、合否、スキップ一覧
- **コスト**: 擾乱 4 点 × 変換 7 種 × 100 話 × 1 審査 ≈ 2,800 LLM 呼び出し。軽量モデル+`--corpus-limit` で段階運用(初回は 20 話でスモーク)

### 5.5 ratchet(新規)

- `scripts/ci_judge_ratchet.py`: `reports/judge_suite_*.json` の最新結果を `config/judge_baseline.json` と比較。**基準キー**: 判定器 ID(model+prompt_version)、各変換 ρ、識別性、INV 最大 |Δ|、再テスト σ。劣化があれば exit 1
- 基準更新は明示的な `--update-baseline` のみ(人手レビュー前提、`ci_lint_ratchet.py` と同一運用)

### 5.6 M1-M2 のテスト(リグレッション防止の中核)

| テスト ID | ファイル | 内容 | 防ぐリグレッション |
|---|---|---|---|
| T-P1-1 | `tests/audit/perturbation/test_transforms_determinism.py` | 同一 seed で 5 回実行 → 出力バイト一致 | 変換の非決定性(ラダー比較が無意味化) |
| T-P1-2 | `tests/audit/perturbation/test_transforms_purity.py` | 入力文字列が mutate されない / 出力非空 / 長さ境界 / `\r\n` 保証 | 変換による原稿破壊、CR/LF 破損 |
| T-P1-3 | `tests/audit/perturbation/test_transforms_catalog.py` | 全変換が kind/affected_axes を宣言。各 DIR 変換が fixture 3 本に対し gold 特徴量を必ず変化させる(T04→定型数増, T05→会話比率減 等) | 「効かない変換」の混入(ラダーが静かに空になる) |
| T-P1-4 | `tests/audit/perturbation/test_ladder_monotonicity_static.py` | ラダー構築が強度順に並び、スキップ変換を除外して記録する(LLM 不使用の静的検証) | ラダー順序バグによる偽の非単調性 |
| T-P1-5 | `tests/audit/perturbation/test_metrics.py` | Spearman: 完全単調→1.0 / 逆順→-1.0 / 同点扱い。識別性・INV・σ の既知ベクトル入力。NaN/欠損時の明示的エラー | メトリクス実装バグによる誤合否 |
| T-P1-6 | `tests/property/test_transforms_never_raise.py` | hypothesis で日本語風ランダムテキスト生成 → 全変換が例外を出さない・非空 | 変形テキストでのクラッシュ(本番コーパスは凸凹) |
| T-P2-1 | `tests/golden/test_judge_suite_golden.py` | `MockLLMAdapter` の固定応答で 3 fixture × 縮小変換セットを実行 → golden JSON と diff | suite 出力形式・集計ロジックの意図しない変更 |
| T-P2-2 | `tests/audit/perturbation/test_suite_failclosed.py` | 判定器が例外/空文字を返した話は「無効」として集計から除外し、**有効数が閾値未満なら suite 全体を不合格**に(サイレント部分集計の禁止) | 失敗話が握り潰され suite が誤って合格 |
| T-P2-3 | `tests/audit/perturbation/test_ratchet.py` | baseline より ρ 低下 → exit 1。`--update-baseline` で更新。judge ID 変更時は「新規判定器」として再登録扱い | ratchet が常に green になる迂回路 |

---

## 6. フェーズ ①: 3 系統判定パネル(M3, 工数 3 日)

### 6.1 `src/audit/judge_panel.py`(新規)

```python
class JudgePanel:
    """3 系統判定パネル。Validation Plane 専用(本番ゲートは変更しない)。"""

    def __init__(self, judges: list[JudgeSpec], gateway: ResilientLLMGateway): ...
    async def score_axis(self, text: str, axis: str) -> PanelScore: ...
    async def pairwise(self, a: str, b: str, axis: str = "overall") -> PairwiseVerdict: ...
```

仕様:
- **JudgeSpec**: family(gemini/anthropic/openai)、model、purpose="audit"。`model_router` で解決し `ResilientLLMGateway` 経由で呼ぶ(フェイルオーバー・サーキットブレーカーを流用)
- **マスキング**: プロンプトに模型名・出力元の痕跡を含めない(**Wang et al. 2023** content loading)
- **自己偏好除外ルール**: 対象原稿の出力元 family が分かる場合、同一 family の judge をその判定から除外(分からない場合は全員参加+flag)
- **順序スワップ**: `pairwise()` は (A,B) と (B,A) を両方評価し、一致しなければ `tie` (**Zheng et al. 2023** 位置バイアス対策)
- **投票**: 各 judge を `ScoreCalibrator` で z 正規化(`src/services/score_calibrator.py` — ここで初めて実結線)→ 中央値採用
- **fail-closed**: 全 judge 失敗時は `PanelUnavailable` を送出。**サイレント合格を禁止**(`unified_auditor.py:113-129` の文化を踏襲)

### 6.2 運用形態(コスト境界)

| 用途 | トリガ | 呼び出し数 |
|---|---|---|
| 判定器選定 | 擾乱スイートを各 judge で 1 回 | suite 依存 |
| 週次ドリフト監視 | `scripts/panel_drift_check.py`(cron / 手動) | 直近 20 話 × 3 judge |
| ゲート境界判定 | `AuditRun.final_score` が閾値 ±5 帯のとき、呼び出し元が opt-in | 3-6 呼び出し |

- パネル有効化は `config/audit_calibration.yaml` の `panel.enabled`(既定 false)

### 6.3 M3 のテスト

| テスト ID | ファイル | 内容 | 防ぐリグレッション |
|---|---|---|---|
| T-J1-1 | `tests/audit/judge_panel/test_masking.py` | judge 送信ペイロードに模型名/出力元メタが含まれない(LLMMocker で検査) | 自己偏好・情報リークの再発 |
| T-J1-2 | `tests/audit/judge_panel/test_cross_family_exclusion.py` | 同一 family 除外が効く。provenance 不明時は全員参加+flag | 除外ロジックの静かな消失 |
| T-J1-3 | `tests/audit/judge_panel/test_order_swap.py` | 位置バイアス mock(常に 1 番目を選ぶ)で両順序評価→ `tie` | 順序スワップの省略による判断の偏り |
| T-J1-4 | `tests/audit/judge_panel/test_median_vote.py` | z 正規化後の中央値。1 judge 障害時は 2 体で継続、**全滅時は `PanelUnavailable`** | サイレント合格(fail-closed 規約) |
| T-J1-5 | `tests/audit/judge_panel/test_drift_check_script.py` | `panel_drift_check.py` が AuditRun 20 件からレポート生成、分布シフト(KS 検定 p<0.05)で exit 1 | ドリフト検知の形骸化 |

---

## 7. フェーズ ③: SSOT 化とペアワイズ移行(M4-M6, 工数 6 日)

### 7.1 SSOT 設定(新規 `config/audit_calibration.yaml`)

```yaml
version: 1
gate:
  mode: absolute            # absolute | percentile
  absolute_threshold: 70.0
  percentile:
    window: 200             # 直近 N 件の AuditRun
    lower_pct: 30           # 下位 30% を不合格帯
  cliche_max: 3
  weights:
    quantitative: 0.4
    qualitative: 0.6
pairwise:
  enabled: false            # Best-of-N 決勝(オプトイン)
  shadow_enabled: false     # 影のみ記録モード
  anchor_count: 3           # アンカー原稿数
panel:
  enabled: false
  judges: []                # M3 で 3 系統を記入
score_calibration:
  priors_source: builtin    # builtin | audit_calibration_priors.yaml
bias_correction:
  enabled: false
```

- 読み込み: `src/audit/calibration_store.py`(新規)。**優先順位: env 変数 > yaml > デフォルト**(既存 `AUDIT_GATE_THRESHOLD` 規約を維持)。`lru_cache` 付き `get_calibration()`、`version` 不一致時は警告
- 修正対象: `unified_auditor.py:251` と `src/agents/audit_agent/config.py` と `src/engine/auditors/hybrid_auditor.py` と `src/domain/writing/coordinator.py:116` の 4 箇所のハードコードを読み込みへ置換

### 7.2 ペアワイズの段階移行

| サブフェーズ | 内容 | リスク遮断 |
|---|---|---|
| 3-A | **Best-of-N 選抜のみ**: 案3 の N=3 生成 → 静的層で上位 2 → `JudgePanel.pairwise` 決勝(順序スワップ付き)。新規コードパスで既存ゲートに触れない | env `ENABLE_PAIRWISE_SELECTION`(既定 off) |
| 3-B | **Shadow**: 旧絶対ゲートと並行し、原稿を「アンカー原稿 3 話(AuditRun 上位から固定)」とペアワイズ比較。2/3 以上に勝てば pairwise-pass。**結果は `AuditRun`(judge_mode=shadow)に記録するのみで、パイプラインの合否に影響しない** | 影響ゼロを T-S2-2 で保証 |
| 3-C | **切替**: 2 週間の shadow ログで一致率を確認後、`gate.mode: percentile` へ。旧絶対ゲートは `gate.mode: absolute` で即復帰可能(キルスイッチ) | 一致率 <80% なら切替中止 |

- パーセンタイル計算: `scripts/recompute_gate_percentile.py` が週次で `AuditRun` 窓から P30 を算出し yaml を更新(手動レビュー前提)

### 7.3 M4-M6 のテスト

| テスト ID | ファイル | 内容 | 防ぐリグレッション |
|---|---|---|---|
| T-S1-1 | `tests/audit/calibration/test_calibration_config_ssot.py` | 優先順位(env>yaml>default)。未知キーの拒否。version 付き読み込み | 設定の静かな無視・優先順位の逆転 |
| T-S1-2 | `tests/audit/calibration/test_gate_reads_ssot.py` | yaml を 75.0 に変えると `unified_auditor` 合否と `evaluate_gate` 閾値の**両方**が追従(統合気味テスト、tmp yaml) | **4 箇所ハードコードへの逆戻り**(本計画最重要の回帰リスク) |
| T-S1-3 | `tests/audit/calibration/test_percentile_gate.py` | 窓計算・コールドスタート(履歴不足→absolute にフォールバック)・同点時の挙動 | パーセンタイル実装バグによる大規模誤不合格 |
| T-S1-4 | `tests/regression/test_judge_threshold_no_hardcode.py` | grep ベース: `>= 70.0` / `< 3` 等のマジックナンバーが `calibration_store.py` 以外の src 配下に現れたら失敗(`tests/regression/test_v5_repo_cleanliness.py` と同一手法) | ハードコード再導入の恒久防止 |
| T-S2-1 | `tests/audit/pairwise/test_pairwise_tournament.py` | 静的フィルタ→決勝。順序スワップ tie 時は静的スコアで決着(決定論) | 非決定的な選抜(再現不能な retake) |
| T-S2-2 | `tests/audit/pairwise/test_shadow_no_side_effect.py` | **shadow ON でも同一 fixture のパイプライン合否・戻り値・書き込み行が完全一致**。差分は `judge_mode=shadow` の AuditRun 行のみ | Shadow が本番合否を汚染(本フェーズ最大のリスク) |
| T-S2-3 | `tests/audit/pairwise/test_kill_switch.py` | `gate.mode: absolute` で即座に旧挙動。percentile→absolute 途中切替でも例外なし | キルスイッチの効かない切替 |
| T-S3-1 | `tests/audit/calibration/test_score_calibrator_wiring.py` | `ScoreCalibrator` への prior 注入経路(カスタム prior yaml → 正規化結果)の回帰 | 未接続コンポーネントの再未接続 |

### 7.4 CI への組み込み

`.github/workflows/ci.yml` に新規 job を追加(既存の `pytest --cov` / lint ratchet に倣う):

```yaml
  judge-ratchet:
    steps:
      - run: pytest tests/audit -k "perturbation or calibration or judge_panel" --timeout=120
      - run: python scripts/ci_judge_ratchet.py --check   # 保存済み suite 結果と baseline の整合
```

- 実 LLM を使う suite 本体は CI から除外(`real_llm` マーカー規約に従い `make judge-suite` で手動/週次実行)。CI は **golden テスト + ratchet チェック + 単体回帰**のみを担う
- `Makefile` に `judge-suite` / `test-judge` ターゲット追加
- カバレッジ: 新規 `src/audit/perturbation*` と `calibration_store.py` は **≥80%** を目標(全体 `fail_under=60` は変更しない)

---

## 8. マイルストーン総括

| M | 内容 | 工数 | 主な成果物 | DoD |
|---|---|---|---|---|
| M0 | 計測基盤 | 0.5 日 | `AuditRun`, `MODEL_PRICING`, T-M0-* | 監査 1 回ごとに内訳 1 行。単価計上 |
| M1 | 変換カタログ | 3 日 | `src/audit/perturbation/`(transforms/ladder/metrics), T-P1-* | 全変換が決定的・有効・テスト済み |
| M2 | suite+ratchet | 2 日 | `suite.py`, CLI, `ci_judge_ratchet.py`, golden | 20 話スモークでレポート出力、ratchet 動作 |
| M3 | 判定パネル | 3 日 | `judge_panel.py`, `panel_drift_check.py`, T-J1-* | 3 系統ドリフト監視が週次で回る |
| M4 | SSOT 化 | 2 日 | `audit_calibration.yaml`, `calibration_store.py`, T-S1-* | ハードコード 4 箇所ゼロ(regression テストで保証) |
| M5 | ペアワイズ | 3 日 | best-of-N 決勝 + shadow, T-S2-* | shadow で合否非汚染をテスト済み |
| M6 | 切替判断 | 1 日 | shadow 一致率分析, 運用 runbook | 一致率 ≥80% で percentile 切替/未達なら absolute 継続 |

合計約 **2 週間**(M0→M2 を先行し、M3 以降は並行可)。

---

## 9. リスクと対策

| リスク | 対策 |
|---|---|
| 擾乱スイート自体が変換バグで「偽の不合格」を出す | 変換は gold 特徴量の機械的 assert(T-P1-3)+決定性テスト(T-P1-1)で二重防壁 |
| suite の LLM コスト(全量で約 2,800 呼び出し) | corpus-limit スモーク→段階拡大。軽量モデル+audit 用単価登録(M0)で追跡可能に |
| パネル全滅時に判定停止 | fail-closed は Validation Plane のみ。**本番ゲートは単審査のまま**なので停止しない |
| percentile ゲートのコールドスタート・小窓 | 履歴 <50 件時は absolute にフォールバック(T-S1-3) |
| Shadow が本番を汚染 | 影響ゼロを T-S2-2 で機械保証+env での即時無効化 |
| 判定器モデルの提供終了 | judge ID は model+prompt_version で管理、baseline は再登録方式(T-P2-3)。3 系統パネルで単一依存を回避 |
| 外部妥当性ゼロ(本設計の限界) | §1 の設計思想を明記済み。将来的な拡張口を附録 A に確保(人手相関・読者シグナル) |

---

## 10. 運用 runbook(要約)

1. 判定プロンプト or モデルを変更したら → `make judge-suite`(スモーク→全量)→ ratchet 基準を `--update-baseline` で人手レビュー更新
2. 週次: `scripts/panel_drift_check.py` → KS 検定 p<0.05 が出たら suite 再実行
3. 月次: `AuditRun` のスコア分布・合格率・静的カナリア(AI 定型命中率)の推移を確認。**合格率上昇とカナリア上昇が並行したら Goodhart 警報**(判定器が定型を許容し始めたサイン)
4. カナリア異常時: `gate.mode: absolute` に戻し、擾乱スイート T04(定型注入)の ρ を確認

---

## 附録 A: 将来の人手相関への拡張口(本計画では実施しない)

- 人手評価が可能になった時点で: 擾乱スイートはそのまま「外部妥当性検証の準備運動」として再利用可
- 相関先の優先順: ① 開発者の週次ペアワイズ(5 分)→ ② なろう/カクヨムのブックマーク・フォロー率(実読者シグナル、最良)→ ③ フルアノテーション(OpenMEVA 方式)
- 公開人手ラベル付き物語評価データ(OpenMEVA: Guan et al. 2020 等)は**判定器ファミリー選定**にのみ使用を推奨(英語圏ドメインギャップのため最終校正には不適)

## 附録 B: 引用文献(計画の根拠)

- Zheng et al. 2023, "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (NeurIPS) — 位置バイアス・順序スワップ・ペアワイズの優位性
- Wang et al. 2023, "Large Language Models are not Fair Evaluators" (ACL 2024) — content masking
- Panickssery et al. 2024, "LLM Evaluators Recognize and Favor Their Own Generations" — 自己偏好の実証
- Ribeiro et al. 2020, "Beyond Accuracy: Behavioral Testing of NLP Models with CheckList" (ACL) — DIR/INV 行動テスト(擾乱スイートの方法論的基盤)
- Liu et al. 2023, "G-Eval" (NeurIPS) — ルーブリック形式の採点安定化
- Guan et al. 2020, "OpenMEVA" (ACL) — 物語評価指標の人手相関検証の標準手法
- Chen et al. 2023, "FrugalGPT" — 軽量本番+強力検証の二層コスト設計
