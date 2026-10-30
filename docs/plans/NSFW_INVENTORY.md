# NSFW 機能モジュール インベントリ

TRACK-N（NSFW 分離・ガードレール）N1 担当。`config/erotic_*.py` 8 ファイルの参照先と有効化状態を一覧化する。

## 調査方針

- 参照元の再確認: `grep -rn "config\.erotic\|from config\.erotic\|import config\.erotic" src/ tests/ --include="*.py"`（追加で `erotic_*` モジュール名単体の参照も併走確認）
- 各 `config/erotic_*.py` の中身を読み、クラス名・関数名・定数名（主要エクスポート）を把握
- 有効化フラグ: 「有効 / 無効 / 未確認」。デフォルトは「未確認」

## 全体サマリ

| 項目 | 内容 |
|---|---|
| 対象モジュール数 | 8 (`config/erotic_*.py`) |
| src 内参照あり | 7（`erotic_vocabulary_ext` 除く） |
| テスト内参照あり | 2 ファイル（`tests/test_erotic_workflow.py`, `tests/unit/easy_mode/test_erotic_specialist_prompts.py`） |
| 中心となる消費元 | `src/engine/prompts/erotic_specialist.py`（6 モジュールを import） |
| マスター有効化スイッチ | `config/erotic_parameters.py` の `EroticParameters.enabled`（デフォルト `False` → 規定では無効化） |

> **注意**: `EroticParameters.enabled` のデフォルトは `False` であり、官能/NSFW 機能全体は**規定では無効化**されている。個別モジュールがソースコード上で import・配線されていても、このマスタースイッチが `False` の間は機能として動作しない可能性がある（`erotic_pacing.create_from_parameters` 等で `enabled` を参照）。

## インベントリ一覧

| モジュール | ファイル | 主要エクスポート | 参照元（import するファイル） | 有効化フラグ |
|---|---|---|---|---|
| `config.erotic_direct_mappings` | `config/erotic_direct_mappings.py` | `DIRECT_TO_METAPHOR`, `EXTRA_ABSTRACTIONS`, `get_combined_mappings()` | `src/engine/prompts/erotic_specialist.py` | 有効 |
| `config.erotic_pacing` | `config/erotic_pacing.py` | `EroticBeat`, `EroticCurve`, `HAS_EROTIC_PARAMETERS` | `src/backend/workflows/refine_erotic_workflow.py`, `src/engine/prompts/erotic_specialist.py`, `tests/test_erotic_workflow.py`, `tests/unit/easy_mode/test_erotic_specialist_prompts.py` | 有効 |
| `config.erotic_parameters` | `config/erotic_parameters.py` | `EroticParameters`, `DEFAULT_SENSORY_WEIGHTS`, `DEFAULT_PACE_RATIOS` | `src/agents/erotic/curve.py`, `src/engine/prompts/erotic_specialist.py`, `config/erotic_pacing.py` | 無効 |
| `config.erotic_platform_presets` | `config/erotic_platform_presets.py` | `PLATFORM_PRESETS`, `get_preset()`, `get_preset_names()` | `src/engine/prompts/erotic_specialist.py`, `tests/test_erotic_workflow.py` | 有効 |
| `config.erotic_thresholds` | `config/erotic_thresholds.py` | `DIVERSITY_SCORE_PASS/WARN/FAIL`, `INTENSITY_R15/SAFE_MAX/EXTREME`, `AFTERGLOW_MIN_PARAGRAPHS`, `AFTERGLOW_MIN_CHARS`, `MAX_CONSECUTIVE_PEAK_EPISODES` | `src/services/audit/service.py`, `src/services/erotic_afterglow_evaluator.py`, `src/services/erotic_diversity_score.py` | 有効 |
| `config.erotic_video_patterns` | `config/erotic_video_patterns.py` | `VideoPattern`, `VIDEO_PATTERNS`, `get_pattern()`, `get_patterns_for_intensity()`, `get_patterns_by_sensory_focus()`, `get_literary_instructions_for_pattern()`, `get_all_pattern_instructions()` | `src/engine/prompts/erotic_specialist.py` | 有効 |
| `config.erotic_vocabulary` | `config/erotic_vocabulary.py` | `METAPHOR_BANK`, `ONOMATOPOEIA_BANK`, `PSYCHOLOGY_TEMPLATES`, `INTENSE_METAPHORS`, `INTENSE_ONOMATOPOEIA`, `INTENSE_PSYCHOLOGY`, `VOCABULARY_TIERS`, `get_vocabulary_for_tier()` | `src/engine/prompts/erotic_specialist.py`, `tests/test_erotic_workflow.py` | 有効 |
| `config.erotic_vocabulary_ext` | `config/erotic_vocabulary_ext.py` | `get_vocabulary_for_tier_ext()` | `tests/test_erotic_workflow.py` | 未確認 |

## モジュール別詳細

### config/erotic_direct_mappings.py
直接表現 → 比喩表現のマッピング定義。`get_combined_mappings()` で全マッピングを統合辞書にして返す。`erotic_specialist.metaphor_filter()` で使用され、過剰な直接表現を比喩に置換するガードレールの一端を担う。

### config/erotic_pacing.py
官能ビート・カーブのデータモデル。`EroticBeat`（フェーズ/欲望レベル/感覚焦点/同意状態）と `EroticCurve`（ビートリスト/目標強度）。`create_default()` / `create_from_parameters()` で曲線を生成。`erotic_parameters` を条件付き import し、未存在時は `Any` フォールバック。

### config/erotic_parameters.py
官能エージェントの調整パラメータ。`EroticParameters` dataclass。`enabled: bool = False` が**マスター有効化スイッチ**（デフォルト無効）。`base_intensity` (0-5), `sensory_weights`, `pace_ratios`, `metaphor_density`, `psychology_depth`, `use_video_patterns` 等を保持。`from_dict`/`to_dict`/`default_for_intensity` などファクトリを備える。

### config/erotic_platform_presets.py
プラットフォーム別プリセット（kakuyomu_romance / nocturn_novel / adult_selfhost）。`max_intensity`, `allowed_vocabulary_tier`, `censorship_mode` 等を base64 エンコード済み名称とともに定義。`get_preset()` / `get_preset_names()` を提供。

### config/erotic_thresholds.py
官能関連スコア閾値。多様性スコア（PASS/WARN/FAIL）、強度閾値（R15/SAFE_MAX/EXTREME）、afterglow 品質閾値（最小段落数/最小文字数）、衣装整合性閾値（連続ピーク話数上限）を `Final` 定数で定義。audit サービス・afterglow 評価・多様性スコアで使用。

### config/erotic_video_patterns.py
動画映像パターン → 文学技法の変換テーブル。`VideoPattern` dataclass と `VIDEO_PATTERNS` 辞書（接写/POV/体位変化/リズム編集/音強調/緊張と解放/多角撮影/スロー/フェード/液体/温度/呼吸同期/侵入/事後/鏡映 等 16 パターン）。各パターンに推奨強度・感覚焦点・比喩ヒントを持つ。`get_all_pattern_instructions()` 等でプロンプト用指示文を生成。

### config/erotic_vocabulary.py
官能ボキャブラリ定義。`METAPHOR_BANK` / `ONOMATOPOEIA_BANK` / `PSYCHOLOGY_TEMPLATES` と強度別拡張（INTENSE_*）、ティ어別辞書 `VOCABULARY_TIERS`（mild/moderate/full/intense）。`get_vocabulary_for_tier()` で指定ティアの語彙を返す（未知ティアは mild フォールバック）。

### config/erotic_vocabulary_ext.py
語彙拡張のスタブモジュール。`erotic_vocabulary.get_vocabulary_for_tier()` に委譲する `get_vocabulary_for_tier_ext()` のみを定義。src 側からの import は検出されず、テスト（`tests/test_erotic_workflow.py`）でのみ参照。実質未使用に近い。

## 有効化フラグの判断根拠

- **有効**: `src/` 内の実際の処理フロー（ワークフロー・プロンプトエンジン・サービス等）で import・参照され、機能として組み込まれている。
- **無効**: `config.erotic_parameters` の `EroticParameters.enabled` がデフォルト `False` であり、官能機能全体のマスタースイッチとして規定ではオフ。
- **未確認**: src 側での使用が検出されず、テストのみ参照、あるいはスタブにつき実効性が不明なモジュール。

## 補足：参照元の内訳（src / tests）

**src/**
- `src/engine/prompts/erotic_specialist.py`: erotic_direct_mappings / erotic_pacing / erotic_parameters / erotic_video_patterns / erotic_platform_presets / erotic_vocabulary（6 モジュール）
- `src/backend/workflows/refine_erotic_workflow.py`: erotic_pacing
- `src/agents/erotic/curve.py`: erotic_parameters
- `src/services/audit/service.py`: erotic_thresholds
- `src/services/erotic_afterglow_evaluator.py`: erotic_thresholds
- `src/services/erotic_diversity_score.py`: erotic_thresholds

**tests/**
- `tests/test_erotic_workflow.py`: erotic_pacing / erotic_platform_presets / erotic_vocabulary / erotic_vocabulary_ext
- `tests/unit/easy_mode/test_erotic_specialist_prompts.py`: erotic_pacing
