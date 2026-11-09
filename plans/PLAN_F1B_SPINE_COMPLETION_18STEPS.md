# PLAN_F1B: STORY_SPINE 完結計画 — 残ギャップの配線とリグレッション防止テストの整備

- **文書ID**: PLAN_F1B_SPINE_COMPLETION_18STEPS
- **作成日**: 2026-11-08
- **対象**: AutoNovel v6.0.0
- **位置づけ**: 実装計画。親提案 [PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md](archived/PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM.md)（アーカイブ済み・大部分実装済み）の**残ギャップを完結させる**もの
- **関連**: [docs/STATUS.md §7](../docs/STATUS.md)（K1-K8 実測の SSOT）
- **原則**: 親提案 §2 の D1-D7 を引き継ぐ。特に **D7（推測禁止・行番号は実装時に grep で再確認）**

---

## 0. TL;DR

STORY_SPINE（構造テンプレート層）は **2026-11-08 実査の時点で大部分が実装・テスト済み**である。
残るギャップは次の **3つ + 1つの補強**のみ。

| # | ギャップ | 影響 | 本計画の対応 |
|:---|:---|:---|:---|
| **G1** | `src/services/preset_loader.py:150-152` `get_plot_pattern()` が**呼び出し元 0 件のデッドコード**のまま（親提案 D7 Step 未完） | 低（負債のみ） | Phase H1 |
| **G2** | 執筆パイプライン本体（`prompts/manager.py` `build_drafting_prompt` / `build_macro_plot_skeleton_prompt` / `build_micro_scene_expander_prompt`、`src/engine/auto_workflow_pipeline.py` / `default_plot_expander.py` 経路）に **spine 注入が無い**。easy_mode 経由の `NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE` にのみ配線済み。full_auto / wizard / Studio で本編を書く経路では構造指示が効かない | **高（本計画の核心）** | Phase H2-H5 |
| **G3** | K1-K3 が **`null`（対象書籍 0 件）**（`docs/STATUS.md §7`）。`measure_spine_alignment.py` は DB の `Plot` テーブルが対象で、実測可能な書籍が存在しない | 中 | Phase J1-J3 |
| **G4** | 既存 19 テストは「Spine 単体」と「easy_mode 配線」をほぼ覆うが、**G2 配線後の経路**と**執筆経路全体の off 差分ゼロ**を守る契約テストが未整備 | 高（G2 と一体） | Phase I1-I7 |

**最重要契約は変わらない**: `SPINE_QUALITY=off`（既定）では**既存プロンプトがバイト単位で完全一致**する。
既存書籍の再生成結果を変えない。これは G2 の配線にもそのまま適用する。

---

## 1. 現状の正確な記録（2026-11-08 実査）

### 1.1 実装済み（触らない・壊さない）

| 層 | 実体 | 状態 |
|:---|:---|:---|
| データ層 | `config/story_spine/` — `beat.py`(34ビート語彙) / `loader.py`(PATTERNS・LENGTHS・MARKETS・CARDS) / `patterns.yaml`(38) / `lengths.yaml`(6) / `markets.yaml`(4) / `cards.yaml`(24) / `genre_registry.py`(旧4系統統合) | 完了 |
| 解決エンジン | `src/services/spine_resolver.py` `resolve_spine()` — LLM 0回・決定論・圧縮モード（3不変条件 `_ALWAYS_KEEP`）・全 2,736 組合せで例外 0 | 完了 |
| 検証 | `src/services/structure_validator.py` — `validate_spine()`（生成前）＋ `validate(pattern_key=...)`（生成後・`alignment` スコア） | 完了 |
| プロンプト注入 | `src/llm/adapters/prompts.py` — `get_spine_quality()`（`SPINE_QUALITY` 環境変数、off/soft/hard、未知値は off に倒す）＋ `build_spine_section()`（off は常に空文字）＋ `build_spine_summary()` | 完了 |
| 配線（easy_mode 系） | `src/backend/routers/easy_mode.py`（`GENRE_REGISTRY` 委譲 `:39-52`、spine 注入 `:156-175`）／ `plots.py` `expand-beats`（`resolve_spine` `:353`）／ `misc.py` `/api/config/planning_options`（cards/lengths/patterns `:130-133`）／ `commercial_planning.py`（4幕ハードコード廃止 `:133-134`）／ `reverse_plot_workflow.py` | 完了 |
| 配線（その他） | `engine_narrative.py` `PacingGraph` 相対位置化（`BEAT_VOCABULARY` から span 取得 `:34-50`）／ `beat_sheet.py` 上限制約撤去（`:16-19`）／ `spice_guard_adapter.py`・`preset_loader.py` の `GENRE_REGISTRY` 委譲 | 完了 |
| UI | `frontend/src/components/generate/SimpleModePanel.tsx`（カードグリッド `SpineTemplateCard`）／ `Step1PlotInput.tsx` ／ `manuscript.ts`（lengths.yaml を SSOT とする注記）＋ `SimpleModePanel.test.tsx` | 完了 |
| 計測 | `scripts/measure_spine_alignment.py`（K1-K3 出力） | 完了（実測は G3） |

### 1.2 既存テスト資産（19 ファイル — 重複作成を避けるために必ず参照）

| ディレクトリ | ファイル | 被覆 |
|:---|:---|:---|
| `tests/unit/story_spine/` (11) | `test_beat_vocabulary.py` / `test_datasets.py` / `test_removed_definitions.py` / `test_resolver_combinatorial.py`(2,736網羅) / `test_resolver_compression.py` / `test_resolver_market_contracts.py` / `test_resolver_no_llm.py` / `test_resolver_no_silent_drop.py` / `test_resolver_relative.py` / `test_validator_pattern.py` / `test_validator_span_source.py` | Spine 単体・データ整合・LLM 0回・圧縮不変条件 |
| `tests/unit/story_spine_wiring/` (7) | `test_commercial_planning_spine.py` / `test_dto_and_volume.py` / `test_genre_pattern_mapping.py` / `test_genre_tables_merged.py` / `test_plots_beat_expansion.py` / `test_reverse_plot_arc_ranges.py` / `test_reverse_plot_uses_spine.py` | easy_mode 系・逆プロット・商業構成の配線 |
| `tests/contract/` (1) | `test_spine_prompt_injection.py` | **off でバイト同一**（GraphRAG テンプレ経路のみ） |
| `tests/e2e/` (1) | `test_spine_end_to_end.py` | カード→Spine→プロンプトの通し・off 差分ゼロ |

> **注意**: G2 で新規配線する経路（drafting / macro / micro）は、上記のどのテストも被覆していない。
> Phase I の新規テストはこの空白を埋めるものであり、既存テストとの重複を作らない。

---

## 2. 設計原則（本計画の拘束）

| # | 原則 | 機械的保証 |
|:---|:---|:---|
| **P1** | **off で差分ゼロ**。`SPINE_QUALITY=off` のとき、新規配線経路を含む**全プロンプトがバイト単位で従来と完全一致** | Phase I1-I2 の契約テスト |
| **P2** | **LLM 0回**。spine の解決・展開に LLM を呼ばない（`build_spine_*` は文字列処理のみ） | 既存 `test_resolver_no_llm.py` ＋ Phase I3 |
| **P3** | **追加ではなく配線**。新データ・新スキーマ・新語彙は作らない。既存 `config/story_spine/` と `build_spine_section()` を使う | 各ステップの diff レビュー |
| **P4** | **既定は off**。UI・環境変数・DB のいずれでも、明示指定がない限り off | `get_spine_quality()` の既存挙動を流用 |
| **P5** | **品質ゲートを通す**。`ruff` ratchet（100）/ `mypy` ratchet（1122）/ `format`（759）/ `pytest --cov fail_under=60` を悪化させない | 各ステップの検証コマンド |

---

## 3. 実装ステップ（依存順・18ステップ）

> 行番号は **実装時に必ず grep で再確認**（原則 D7）。

### Phase H: 配線（G1・G2 の解消）

| Step | 対象 | 内容 | 検証コマンド | 伴うリグレッションテスト |
|:---|:---|:---|:---|:---|
| **H1** | `src/services/preset_loader.py:150-152` | `get_plot_pattern()` を**削除**（呼び出し元 0 件を再確認のうえ）。`__init__.py` の re-export があれば併せて削除 | `grep -rn "get_plot_pattern" src/ tests/` → 0 件を確認してから削除。`pytest tests/unit -q -k preset_loader` | **I7**（削除後の import 整合） |
| **H2** | `prompts/manager.py` `build_drafting_prompt`（`:612` 付近） | 署名に `spine=None, spine_quality=None, ep_num=1` を**追加（既定値付き・後方互換）**。本文テンプレートの末尾に `build_spine_section(spine, quality, ep_num)` の結果を連結。off / None なら**何も連結しない**（出力バイト同一） | `pytest tests/contract/test_spine_prompt_injection.py -q` ＋ **I1** | **I1**（drafting 経路の off 差分ゼロ） |
| **H3** | `prompts/manager.py` `build_macro_plot_skeleton_prompt`（`:1162` 付近） | H2 と同様の注入。Macro 骨子生成は「各話の役割」を決める工程なので、`build_spine_summary(spine)` を**構造ヒントとして**注入（soft/hard で出し分け）。off は不変 | `pytest tests/unit/engine -q -k plot_expander` ＋ **I3** | **I3**（macro 経路の差分ゼロ） |
| **H4** | `prompts/manager.py` `build_micro_scene_expander_prompt`（`:1224` 付近） | H2 と同様（`build_spine_section` で当該話の duty を注入）。既定値付き追加で既存呼び出し側を壊さない | `pytest tests/unit/engine -q -k plot_expander` ＋ **I3** | **I3** |
| **H5** | `src/engine/default_plot_expander.py` ＋ `src/engine/auto_workflow_pipeline.py` | 執筆パイプラインから Spine を解決して渡すフック。(1) 書籍作成時に `pattern_key`/`length_key`/`market_key` を bible（または book メタ）に保存（未選択なら null）。(2) `DefaultPlotExpander.expand_*` で `resolve_spine` を呼び（例外時は **None にフォールバック＝fail-open**）、プロンプトビルダーに渡す。**spine が null なら現行と完全同一の動作** | `pytest tests/unit/engine tests/integration/test_full_pipeline.py -q` ＋ **I4** | **I4**（パイプライン配線の回帰） |
| **H6** | `src/backend/config.py`（または同等の設定SSOT） | `SPINE_QUALITY` を設定項目として明文化（既定 `off`）。`get_spine_quality()`（`src/llm/adapters/prompts.py:107`）と**単一の真実源**に寄せる（重複定義を作らない） | `pytest tests/config -q` | **I5**（設定キーの契約） |
| **H7** | `frontend`（Studio / wizard の設定画面） | per-book の spine 適用レベル選択（off/soft/hard の 3 択、既定 off）。API は既存 payload `spine_quality`（`easy_mode.py:160`）を流用。**表示ラベルには「テンプレートは初期値」であることを明記**（親提案 §10 の対策） | `cd frontend && npx vitest run` | 既存 `SimpleModePanel.test.tsx` の拡張（**I6**） |
| **H8** | `docs/STATUS.md` §5 付近 | `SPINE_QUALITY` の挙動と配線経路一覧（easy_mode / drafting / macro / micro / expand-beats）を追記 | 目視レビュー | — |

### Phase I: リグレッション防止テスト（G4 の解消 — §4 に詳細仕様）

| Step | 作成物 | 検証コマンド |
|:---|:---|:---|
| **I1** | `tests/contract/test_spine_prompt_injection_drafting.py` | `pytest tests/contract/test_spine_prompt_injection_drafting.py -q` |
| **I2** | `tests/contract/test_spine_prompt_injection_plotelements.py`（macro/micro 経路） | 同上 |
| **I3** | `tests/unit/story_spine_wiring/test_prompt_builder_no_llm.py` | `pytest tests/unit/story_spine_wiring -q` |
| **I4** | `tests/unit/story_spine_wiring/test_default_plot_expander_spine.py` | `pytest tests/unit/story_spine_wiring -q` |
| **I5** | `tests/config/test_spine_quality_setting.py` | `pytest tests/config -q` |
| **I6** | `frontend/src/components/generate/SimpleModePanel.test.tsx` 拡張 | `cd frontend && npx vitest run` |
| **I7** | `tests/unit/story_spine_wiring/test_preset_loader_no_dead_code.py` | `pytest tests/unit/story_spine_wiring -q` |

### Phase J: 計測・運用（G3 の解消）

| Step | 対象 | 内容 | 検証コマンド |
|:---|:---|:---|:---|
| **J1** | `tests/integration/test_spine_alignment_synthetic.py`（新規） | 合成書籍（Spine に忠実に生成した tension 列 / 故意に崩した tension 列の 2 種フィクスチャ）を DB に投入し、`measure_spine_alignment.py` が K1-K3 を**再現可能な数値**として出すことを保証する。これで「対象書籍 0 件 → null」の状態を機械的に検知できる | `pytest tests/integration/test_spine_alignment_synthetic.py -q` |
| **J2** | `scripts/measure_spine_alignment.py` | `--check` モード追加（閾値未達時に exit 1）。CI 常設化は**合成書籍のみ**対象（実書籍の数値は運用で別途見る） | `python -m scripts.measure_spine_alignment --check` |
| **J3** | `docs/STATUS.md` §7 | K1-K3 の列に「合成書籍での実測値」と「実書籍 0 件であること」を明記し、null の意味を更新。実書籍が溜まったら `--json` で再計測 | 目視レビュー |

---

## 4. リグレッション防止テスト計画（詳細仕様）

### 4.1 全体方針

1. **既存 19 ファイルを壊さない**。新規テストは既存テストの空白を埋めるのみ（§1.2 の被覆表と照合）。
2. **最重要契約（off 差分ゼロ）を新規配線経路へ拡張**する。既存 `test_spine_prompt_injection.py` が GraphRAG テンプレ経路のみを守っているのに対し、I1-I2 は drafting / macro / micro 経路を守る。
3. **全部高速**。LLM 呼び出し 0 回、DB は SQLite インメモリまたは mock。CI 全体 1 分以内を維持。
4. **壊れ方を指定してテストする**。「壊れたらどのテストが赤になるか」を各テストに明記する（§4.3 の表）。

### 4.2 新規テストの仕様

#### I1: `tests/contract/test_spine_prompt_injection_drafting.py`（最重要）

```python
"""drafting 経路の spine 注入契約。

壊れ方: build_drafting_prompt が off でも spine セクションを連結する /
spine あり・soft/hard で注入漏れ → この契約が赤になる。
"""

def test_off_byte_identical_drafting_prompt():
    """spine_quality=off（既定）で、spine 解決の有無に関わらず
    build_drafting_prompt の出力がバイト単位で同一であること。
    - spine=None と spine=resolve_spine(...) を渡して同一文字列を assert
    - SPINE_QUALITY 環境変数を off / 未設定 の両方で確認（monkeypatch）
    """

def test_off_with_spine_object_is_still_byte_identical():
    """spine オブジェクトが渡されていても off なら空文字連結であること
    （build_spine_section の off 短絡 `prompts.py:122-123` に依存）。"""

def test_soft_injects_reference_and_hard_injects_duty():
    """soft: 「【構造の参考】」ラベル＋duty。
    hard: 「【この話で必ず果たすこと】」ラベル＋テンション＋duty。
    off: 空文字。3レベルの差分を golden 文字列で固定。"""

def test_ep_num_beat_mapping_respected():
    """ep_num=1 と ep_num=20 で異なるビートが注入されること
    （spine.at(ep_num) の話数→ビート対応の回帰）。"""

def test_exception_in_at_falls_back_to_empty():
    """spine.at() が例外を投げても空文字に倒れ、プロンプト生成自体は
    壊れないこと（fail-open、prompts.py:124-127 の契約）。"""
```

#### I2: `tests/contract/test_spine_prompt_injection_plotelements.py`

```python
"""macro/micro プロット展開経路の spine 注入契約（I1 と同型）。

壊れ方: build_macro_plot_skeleton_prompt / build_micro_scene_expander_prompt
が off でも注入する / 既定値付き引数の追加で既存呼び出しが壊れる → 赤。
"""

def test_off_byte_identical_macro_prompt(): ...
def test_off_byte_identical_micro_prompt(): ...
def test_existing_call_sites_unaffected():
    """既存の呼び出し形（新引数を渡さない）で従来どおり動くこと。
    H2-H4 の既定値付き追加が後方互換であることの直接検証。"""
def test_summary_injected_only_when_soft_or_hard():
    """build_spine_summary が macro にのみ入り、micro には当該話 duty が
    入ること（両方に summary を入れる実装ミスを防ぐ）。"""
```

#### I3: `tests/unit/story_spine_wiring/test_prompt_builder_no_llm.py`

```python
"""プロンプトビルダーが LLM を呼ばないこと（原則 P2）。

壊れ方: ビルダー内で誤って llm.generate_json を呼ぶ → 赤。
"""

def test_drafting_prompt_build_makes_no_llm_calls():
    """LLMGateway をモック化し、build_drafting_prompt 実行中に
    呼び出し回数 0 を assert（spine あり・なし両方）。"""

def test_macro_micro_prompt_build_makes_no_llm_calls(): ...
```

#### I4: `tests/unit/story_spine_wiring/test_default_plot_expander_spine.py`（G2 配線の回帰）

```python
"""DefaultPlotExpander / AutoWorkflowPipeline の spine フック回帰。

壊れ方: resolve_spine 例外で執筆が落ちる（fail-closed 化）/
off でもプロンプトに構造指示が混入する / bible に pattern_key が
無い書籍で KeyError → この回帰が赤になる。
"""

def test_no_pattern_key_behaves_exactly_as_before():
    """pattern_key 未保存の書籍は、spine 解決を試みず、
    プロンプトも DB 書き込みも現行と同一であること。"""

def test_resolve_spine_exception_falls_back_to_none():
    """resolve_spine が例外を投げても None にフォールバックし、
    執筆パイプラインが継続すること（fail-open、H5 の契約）。"""

def test_soft_hard_propagates_to_prompt_builder():
    """pattern_key 保存書籍 + SPINE_QUALITY=soft/hard で
    drafting プロンプトに該当話の duty が入ること。"""

def test_off_propagates_nothing():
    """同一書籍で SPINE_QUALITY=off のとき、生成プロンプトが
    pattern_key なし書籍とバイト同一であること（最重要）。"""

def test_spine_resolution_is_deterministic_across_calls():
    """同一書籍で expand を 2 回呼んでも、注入される構造指示が同一
    （決定論。LLM 出力差分と混同しないよう文字列レベルで比較）。"""
```

#### I5: `tests/config/test_spine_quality_setting.py`

```python
"""SPINE_QUALITY 設定の契約。

壊れ方: 設定キーの名前衝突・既定値の変更・未知値の扱い変更 → 赤。
"""

def test_default_is_off(): ...
def test_unknown_value_falls_back_to_off():
    """SPINE_QUALITY=typo のとき off に倒すこと（prompts.py:111-112）。"""
def test_config_key_matches_env_reader():
    """src/backend/config.py の設定名と get_spine_quality() が
    同一の環境変数名（SPINE_QUALITY）を参照すること（H6 の契約）。"""
```

#### I6: `frontend` テスト拡張（既存 `SimpleModePanel.test.tsx` に追加）

```typescript
// 壊れ方: 選択レベルが payload に乗らない / 既定が off でない → 赤。
// - 既定選択が "off" であること
// - soft/hard 選択時に payload.spine_quality に反映されること
// - 「テンプレートは初期値」の注記が表示されること（H7）
```

#### I7: `tests/unit/story_spine_wiring/test_preset_loader_no_dead_code.py`

```python
"""H1（get_plot_pattern 削除）の回帰。

壊れ方: 削除漏れ・他機能の偶発破壊 → 赤。
"""

def test_get_plot_pattern_is_gone():
    """preset_loader に get_plot_pattern が存在しないこと（AttributeError）。"""

def test_preset_loader_public_api_intact():
    """load_preset / get_preset_value / validate_preset / get_tension_curve が
    従来どおり動くこと（削除の副作用ゼロ）。"""

def test_no_call_sites_remain():
    """src/ tests/ 全体を AST でスキャンし get_plot_pattern の
    参照が 0 件であること（文字列 grep より堅牢）。"""
```

#### J1: `tests/integration/test_spine_alignment_synthetic.py`

```python
"""K1-K3 計測の再現性回帰（G3）。

壊れ方: measure_spine_alignment.py が空 DB で静かに null を返す /
合成データの tension 列を正しく読めない → 赤。
"""

def test_faithful_book_scores_high_alignment():
    """exile_rise × web_volume × web で忠実に合成した 40 話書籍の
    alignment が閾値以上であること（K1 の機械的下限）。"""

def test_broken_book_scores_low_and_is_detected():
    """中点反転を意図的に消した書籍が problems に検出されること
    （検出器が「何でも合格」になっていないことの逆張りテスト）。"""

def test_check_mode_exit_code():
    """--check が閾値未達合成データで exit 1、達成データで exit 0（J2）。"""
```

### 4.3 壊れ方 → 赤になるテストの対応表（レビュー用チェックリスト）

| 想定される破壊 | 赤になるテスト |
|:---|:---|
| off なのにプロンプトに構造指示が混入（執筆経路） | I1 / I2 / I4(`test_off_propagates_nothing`) |
| soft/hard で注入漏れ・ラベル誤り | I1(`test_soft_injects...`) |
| spine 解決例外で執筆が落ちる | I4(`test_resolve_spine_exception_falls_back_to_none`) / I1(`test_exception_in_at_falls_back_to_empty`) |
| pattern_key 未保存書籍の挙動変化 | I4(`test_no_pattern_key_behaves_exactly_as_before`) |
| プロンプトビルダーが LLM を呼ぶ | I3 |
| resolve_spine の決定論崩れ | 既存 `test_resolver_determinism` 系（`test_resolver_combinatorial.py`）＋ I4(`test_spine_resolution_is_deterministic_across_calls`) |
| 既定値の変更・未知値の扱い変更 | I5 |
| UI 選択が payload に乗らない | I6 |
| H1 削除の副作用 | I7 |
| K1-K3 計測器の静かな劣化 | J1 |

### 4.4 既存テストの棚卸し（本計画では変更しない）

- `tests/contract/test_spine_prompt_injection.py` — 変更不要（GraphRAG 経路の契約として残す）。
- `tests/e2e/test_spine_end_to_end.py` — 変更不要。G2 配線後、`test_off_quality_produces_byte_identical_prompt` が**より強い意味**を持つ（執筆経路にも同じ契約が波及）。
- `tests/unit/story_spine/` 11 本 — 変更不要。データ層・解決エンジンは触らないため。

---

## 5. 効果測定（G3 の解消手順）

1. **合成書籍の投入**: J1 のフィクスチャで `Plot` テーブルに忠実/崩壊の 2 種 40 話書籍を作る。
2. **実測**: `python scripts/measure_spine_alignment.py --json` で K1-K3 を取得し、`docs/STATUS.md §7` に「合成書籍実測値」として記入（null の理由を更新）。
3. **CI 常設**: `--check` を合成書籍に対してのみ実行（J2）。実書籍は運用環境で別途 `--json` 計測し、数値が揃い次第 STATUS.md を更新。
4. **目標値**: K2（中点反転 0.40-0.60 収束率）・K3（クライマックス 0.75-0.92 収束率）ともに **90%**（親提案 §8 を踏襲）。K4（LLM 追加コスト）は **0 円維持**（I3 で恒常保証）。

---

## 6. リスクと対策

| リスク | 影響 | 対策 |
|:---|:---|:---|
| **G2 配線で既存書籍の再生成結果が変わる** | High | **P1（off 差分ゼロ）を I1/I2/I4 で機械保証**。既定 off のまま、配線自体は off でリリースし、効果確認後に soft 解禁 |
| `prompts/manager.py` 3 関数への引数追加で既存呼び出しが壊れる | High | **既定値付き引数のみ**（H2-H4）。I2(`test_existing_call_sites_unaffected`) で直接検証 |
| `resolve_spine` の例外が執筆を止める | High | fail-open（None フォールバック、H5）。I4 で回帰固定 |
| マイグレーション追加（pattern_key 保存）の失敗 | Medium | 新規カラムを避け、bible JSON の既存スロットに格納する方針を優先。スキーマ変更が不可避な場合のみ Alembic マイグレーション＋ `tests/contract/test_db_schema.py` 更新 |
| テスト追加による CI 時間増 | Medium | 全新規テストは LLM 0 回・インメモリ DB。目安 1 分以内 |
| 品質ゲート（ruff/mypy/format ratchet）の悪化 | Medium | 各ステップで `make lint && make typecheck && make format-check` を通してから次へ |
| UI 変更（H7）で既存フローが壊れる | Medium | 選択肢追加のみ。既存 `SimpleModePanel.test.tsx` を壊さず拡張（I6） |

---

## 7. 完了条件（Definition of Done）

- [ ] H1-H8 の全ステップが完了し、対応する検証コマンドが緑
- [ ] **I1-I7 の全テストが緑**（off 差分ゼロ契約が執筆経路全体に拡張されている）
- [ ] J1-J3 により、K1-K3 が `null` ではなく**再現可能な実測値**として STATUS.md に記録
- [ ] `make verify`（全品質ゲート一括）が通る
- [ ] `SPINE_QUALITY` 既定値が `off` のまま、既存書籍の再生成結果が変わっていないことの確認（I1/I2/I4 の緑をもって代える）
- [ ] `docs/STATUS.md` §5・§7 が更新され、配線経路一覧と実測値の SSOT になっている

---

## 8. 非目標（明確にやらないこと）

1. **データ層・解決エンジンの変更** — 34ビート/38パターン/6長さ/4媒体/24カードの値は凍結（契約凍結 2026-09-29 を引き継ぐ）。語彙追加は別提案
2. **`SPINE_QUALITY=hard` の既定化・全書籍への強制適用** — 既定 off 維持。soft/hard は明示選択のみ
3. **LLM による構成の創作** — LLM が埋めるのは duty の具体化のみ（原則 D2）
4. **semantic_cache への新規統合** — 現状のキャッシュ機構はそのまま。spine 注入プロンプトはキャッシュ対象になるが、キャッシュ側の変更はしない
5. **実書籍の大量再計算・再生成** — 計測のみ（J2/J3）。書き換えはしない

---

## 9. 実施順序の目安（所要の概算）

| 順序 | ステップ | 前提 | 概算 |
|:---|:---|:---|:---|
| 1 | H1 ＋ I7 | なし | 0.5h |
| 2 | H2 ＋ I1 | なし | 1.5h |
| 3 | H3/H4 ＋ I2/I3 | H2 の型合わせ | 1.5h |
| 4 | H5 ＋ I4 | 2-3 | 2h |
| 5 | H6 ＋ I5 | 2-4 | 0.5h |
| 6 | H7 ＋ I6 | 2-5（API 確定後） | 1.5h |
| 7 | H8 | 2-5 | 0.5h |
| 8 | J1/J2/J3 | H5 完了（合成書籍が執筆経路を通ること） | 2h |
| 9 | `make verify` ＋ STATUS.md 最終更新 | 全体 | 0.5h |

> **推奨の最初の一歩**: H1（デッドコード除去）＋ I7。副作用ゼロで着手でき、
> H2 以降の「off 差分ゼロ契約の拡張」作業のウォームアップになる。
