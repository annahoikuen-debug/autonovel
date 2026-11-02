# 機能提案 F1: 構造テンプレート層（STORY_SPINE）の導入

## ― 「売れ筋プロット・テンプレート」を、媒体・長さ・ジャンルに通用的なFWへ再設計する ―

- **文書ID**: PROPOSAL_F1_PLOT_TEMPLATE_SYSTEM
- **作成日**: 2026-09-29
- **対象**: AutoNovel v6.0.0 →
- **位置づけ**: 機能提案（実装計画ではない）。実装分解は §9 以降を参照
- **関連**: [PLAN_V53_V6_INTEGRATED_36STEPS.md](PLAN_V53_V6_INTEGRATED_36STEPS.md), [PLAN_T6_REMEDIATION_18STEPS.md](PLAN_T6_REMEDIATION_18STEPS.md)

---

## 0. TL;DR

### 0.1 元提案の総評

元提案は**方向は正しいが、3つの構造的欠陥**がある。

| # | 欠陥 | 影響 |
|:---|:---|:---|
| L1 | **「プロット・テンプレート」と「媒体仕様」を同一視している** | 「3話以内のつかみ」「1巻ラストの引き」は *Web連載* の仕様であって、構造そのものではない。短編・単行本・一般文芸にそのまま_apply できない |
| L2 | **長さ（短編/中編/長編）の概念が体系的に存在しない** | 同じテンプレートを1話と300話のどちらにも適用できない |
| L3 | **既存コードが持つ資産を一切使っていない** | 既に31パターン・9張りのテンション曲線・6種の文字数プリセット・構造検証器があるのに、全部未接続・相互矛盾 |

### 0.2 本提案の要約

元提案を **「構造核（STORY_PATTERN）× 長さ階層（LENGTH_PROFILE）× 媒体規格（MARKET）」** の直交分解に置き換える。

- **構造核 31→38 種**（既存 `config/data/archetypes.json` の31種を昇格・再編＋不足7種を新規追加）
- **長さ階層 6 段**（短編 / 中編 / 単行本1巻 / Web1巻 / 長編連載 / シリーズ）
- **媒体規格 4 種**（Web連載 / ライトノベル単行本 / 単発・投稿 / 一般文芸）
- **展開は決定論**（テンプレート展開は **LLM 呼出 0 回**。既に `reverse_plot_workflow.py` が証明済み）
- **相対位置で表現**（絶対話数バグを根絶）
- **追加ではなく置換**（既に壊れている5系統を置き換える。委任的钱は増えない）

---

## 1. 現状の診断（根拠つき）

### 1.1 「構成」に閉する4つの独立サブシステム

現状、リポジトリ内に**互いに接続されていない4系統**の「構造」データが存在する。

| # | 系統 | 実体 | 件数 | 本番到達 |
|:---|:---|:---|:---|:---|
| S1 | 構造テンプレート（検証のみ） | `src/services/structure_validator.py:16-48` `STRUCTURE_DEFINITIONS` | 3 | **生成時に一度も参照されない**（`GET /api/structure/templates` のみ） |
| S2 | Web1巻=40話 ビート表 | `src/config/commercial_beat_sheet.py:5-59` `COMMERCIAL_40EP_BEATS` | 7 phase / 40話 | `beat_sheet_generation.j2` 経由のみ |
| S3 | 逆プロット決定論 | `src/backend/workflows/reverse_plot_workflow.py:97-223` | 3 arcs | `/easy_mode/reverse-generate` 経由のみ |
| S4 | アーキタイプ | `config/archetypes_new.py:50-446` `STORY_ARCHETYPES` | 47 key（うち12は空） | UIから**到達不能** |

さらに**未ロードの5番目の資産**がある。

| 資産 | 実体 | 件数 | 状態 |
|:---|:---|:---|:---|
| `config/data/archetypes.json` の `PLOT_STRUCTURES` | `:9-258` | **31パターン**（`hook` / `mid_crisis` / `climax_type` / `ending` / `key_tropes` 付き） | ローダが**どこにも無い**（`grep archetypes.json` 0件） |
| 同 `ARCHETYPE_ENGINES` | `:259-280` | 4 engine | 同上 |
| テンション曲線YAML | `src/presets/{9 genre}/tension/tension_curve_*.yaml` | 9種 × 20点 + `density_by_phase` 7 phase | `preset_loader.get_tension_curve()` 経由で**部分的に**到達 |
| 文字数プリセット | `frontend/src/constants/manuscript.ts:3-48` | 6種（1.2万/2万/4万/10万字） | **エディタ内字数カウンタ専用**。backend に送られない |
| 逆プロット質問バンク | `frontend/src/data/reversePlotSteps.ts:54-73` | 4質問 × 4選択肢 | backend に**逐語重複**（`reverse_plot_workflow.py:31-57`） |

### 1.2 絶対話数バグ（構造が破綻している直接原因）

「3話以内のつかみ」「1巻ラスト」を**絶対話数で書いてある**ため、長さ Changingと即座に壊れる。

| 箇所 | 内容 | 破綻 |
|:---|:---|:---|
| `src/backend/engine_narrative.py:74-86` | `elif ep_num == 5:` / `elif 24 <= ep_num <= 26:` | `total_eps=20` でも `total_eps=100` でも**第1の爆発は第5話・クライマックスは第24-26話のまま**。`mid_twist_ep`/`late_twist_ep` だけは相対化済（`:39-40`）で**同一関数内で方式が混在** |
| `config/constants.py:18-22` | `EP_HUMILIATION=2, EP_TRIGGER=3, EP_MUSOU_START=4, EP_FINAL=8, EP_CLIMAX=7` | **8話固定**の前提。40話構成にそのまま適用すると第2話で殴り合い開始 |
| `src/models/beat_sheet.py:16` | `ep_num: int = Field(..., ge=1, le=40)` | 40話より長い構成が**Pydantic で弾かれる** |
| `src/backend/routers/commercial_planning.py:112` | 4幕をハードコード | `COMMERCIAL_40EP_BEATS`（7 phase）と**真逆**の構造。同じ「商業構成」に2つの答え |
| `src/services/pipeline_base.py:72` | `current_volume: int = 1` | **増加箇所が無い**。「1巻」を扱う系譜が存在しない |

### 1.3 ジャンル語彙が4系統ある

| 系統 | 場所 | 値 |
|:---|:---|:---|
| G1 | `frontend/src/components/generate/SimpleModePanel.tsx:91-103` | `fan / sf / romance / mystery / horror / other` |
| G2 | `frontend/src/constants/genres.ts:10-18` | 日本語7ラベル（`ハイファンタジー (R15)` 等） |
| G3 | `frontend/src/components/wizard/Step1PlotInput.tsx:132-136` | `fantasy / modern_fantasy / romance / scifi` |
| G4 | `config/archetypes_new.py:476` `WIZARD_GENRE_OPTIONS` | 日本語6ラベル |

**そして3系統の genre→preset マッピング表が競合**している。

| 表 | 場所 | 方式 |
|:---|:---|:---|
| T1 | `src/backend/routers/easy_mode.py:35-57` `resolve_genre_to_preset` | 日本語キーワードの**部分一致** |
| T2 | `src/services/preset_loader.py:43-60` | 辞書の**完全一致** |
| T3 | `src/services/spice_guard_adapter.py:47-54` | T1 の部分重複 |

**実害**: 既定の EasyMode 経路（`SimpleModePanel`）が送る `"fan"` は、T1 の日本語キーワードに**1つも一致しない** → `None` → `StyleProfile` にフォールスルー。**スタイルプリセットが1つも効かない状態でEasyModeが走る**。

### 1.4 構造情報がプロンプトに入らない

| 信号 | EasyMode | 統合Pipeline | Wizard |
|:---|:---|:---|:---|
| `genre` | ✅ | ✅ | ✅ |
| `archetype_key` | ❌ | ✅（メタデータのみ） | ❌ |
| **`plot_pattern`** | ❌ | ❌ **完全死んでいる** | ❌ |
| **構造（3幕/起承転結/…）** | ❌ | ❌ | ❌ |
| `target_eps` | ❌（`easy_mode.py:141` で `_` に捨てられる） | ✅ | ✅ |

`plot_pattern` は `preset_loader.py:100` でマージされ、`get_plot_pattern()`（`:164-166`）で読まれるが、**その関数を呼ぶ箇所が0件**。**プロンプトテンプレートも1つも参照しない**。

**結論**: 現在のEasyModeは「プロットを一切考えずに1話だけ書く」状態にある。元提案が指摘した「起伏の弱い作品になりがち」は、コードから裏付けられる。

### 1.5 API の事実上の破損

`src/backend/routers/misc.py:91` は `from config.constants import PLANNING_PRESETS` を行うが、`config/constants.py` に **`PLANNING_PRESETS` は定義されていない**（`grep` 0件）。→ `ImportError` → **このエンドポイントは常に HTTP 500**。

これは「ジャンル・アーキタイプをUIに配る」唯一のAPIであり、**現在壊れている**。

---

## 2. 設計原則

元提案が持たなかった部分を設計原則として固定する。

| # | 原則 | 理由 | 機械的根拠 |
|:---|:---|:---|:---|
| **D1** | **相対位置で構造を表す**（0.0-1.0）。絶対話数は禁止 | 長さが変わっても構造が壊れない | 解消: §1.2 の5箇所 |
| **D2** | **テンプレート展開は決定論。LLM 呼出 0 回** | 長さ変更・再生成・A/B 比較が即座に可能。コスト増えない | `reverse_plot_workflow.py` が既に `_calc_tension` を純算術で実装済 |
| **D3** | **直交分解**（構造 × 長さ × 媒体 × ジャンル座標） | 組合せ爆発を「列挙」ではなく「遴選」で封じる | 38×6×4×12 を列挙しない |
| **D4** | **追加ではなく置換** | 既に5系統が競合している。7つ目を足すのは害悪 | §1.1 / §1.3 |
| **D5** | **検証は両方向**（生成前 + 生成後） | 生成前の整合性と生成後の乖離を同じ道具で測る | `structure_validator.validate()` は既に両方向で使える形 |
| **D6** | **閉じたボキャブラリ**（約30ビート）に寄せる | パターンがbeatsの id を参照するだけで、説明文を重複定義しない | 31パターンが既に `hook` / `mid_crisis` / `climax_type` を持つ |
| **D7** | **推測禁止**。行番号は grep で確認してから書く | 本提案の `file:line` も実装時に再確認すること | `PLAN_T6` 原則 P6 |

---

## 3. 中核データモデル

### 3.1 正規化: すべての位置は「相対」

```python
# config/story_spine/beat.py
from dataclasses import dataclass

@dataclass(frozen=True)
class BeatDef:
    key: str                  # 閉じた語彙の id（例: "midpoint_reversal"）
    label: str                # 日本語表示名（例: "中点反転"）
    role: str                 # "hook" | "engine" | "reversal" | "climax" | "close" | "filler"
    span: tuple[float, float] # 相对位置 [開始, 終了) 0.0-1.0。長さ非依存
    duty: str                 # このビートが「必ず果たすこと」1文（プロンプトに注入される）
    tension: float            # 目標テンション 0.0-1.0
    artifact: str             # "scene" | "reversal" | "reveal" | "hook"
    optional: bool = False
```

> `span` は **相対**。`total_eps=1` でも `total_eps=300` でも同じ値を使う。

### 3.2 閉じたビート語彙（34語）

`pattern` からは説明文を書かず、`key` だけを参照する（原則 D6）。

| role | key | label | artifact | tension |
|:---|:---|:---|:---|:---|
| hook | `cold_open` |  expositions | scene | 0.15 |
| hook | `inciting` | 発端 | scene | 0.45 |
| hook | `humiliation` | 理不尽な不遇 | scene | 0.80 |
| hook | `revelation` | 能力・事実の提示 | reveal | 0.55 |
| engine | `promise` | 約束・取引の提示 | scene | 0.50 |
| engine | `first_win` | 初の成功 | scene | 0.70 |
| engine | `rising_tension` | 抵抗の高まり | scene | 0.60 |
| engine | `foreshadow` | 伏線の設置 | scene | 0.40 |
| engine | `deepening` | 関係の深化／深掘り | scene | 0.45 |
| engine | `comic_relief` | 息抜き | scene | 0.20 |
| engine | `failure` | 手直しへの失敗 | scene | 0.65 |
| reversal | `midpoint_reversal` | 中点反転 | reversal | 0.90 |
| reversal | `stakes_raise` | 状況の悪化 | scene | 0.75 |
| reversal | `betrayal` | 裏切り・離反 | reveal | 0.85 |
| reversal | `dark_night` | 闇夜・絶望 | scene | 0.70 |
| reversal | `decision` | 決断 | scene | 0.60 |
| reversal | `turn_of_tide` | 追い込みの破綻 | reversal | 0.95 |
| reversal | `all_is_lost` | 全面的な敗北 | scene | 0.50 |
| climax | `last_stand` | 最後の戦い | scene | 0.98 |
| climax | `truth_reveal` | 黒幕・真相の提示 | reveal | 0.92 |
| climax | `final_choice` | 最終選択 | scene | 0.90 |
| climax | `climax` | クライマックス | scene | 1.00 |
| close | `aftermath` | aftermath | scene | 0.40 |
| close | `payoff` | 約束の回収 | scene | 0.60 |
| close | `residue` | 伏線の残存処理 | scene | 0.30 |
| close | `denouement` | 結末 | scene | 0.25 |
| close | `volume_hook` | 次の引き | hook | 0.55 |
| close | `coda` | 最終話のみ・余韻 | scene | 0.10 |
| engine | `daily_loop` | 日常的反復 | scene | 0.25 |
| engine | `training` | 訓練・習得 | scene | 0.35 |
| engine | `expansion` | 領域・基盤の拡大 | scene | 0.50 |
| engine | `gossip` | 噂・情報の流通 | scene | 0.40 |
| engine | `stream_reaction` | 配信・反応 | scene | 0.55 |
| close | `interlude` | 幕間・視点切替 | scene | 0.20 |

### 3.3 `STORY_PATTERN` — 構造核 38種

**由来**: `config/data/archetypes.json:9-258` の **31種を正式採用**（キーは維持）＋ §3.3.2 の 7種を新規追加。
4軸に再編し、`beats`（閉じた語彙 id 列）と `curve`（ 外枠）を持つ。

#### 3.3.1 4軸分類

| 軸 | 駆動源 | 読者Delimiter | 既存31種の帰属 |
|:---|:---|:---|:---|
| **A. 外圧型** | 外部からの力で追い詰められる | 「逃げられない」 | exile_rise, dungeon_conqueror, tournament_champion, guild_rebuilder, army_rational, shadow_organization, peerless_reincarnation, reincarnation_cheat, space_odyssey, onmyo_exorcism, bottom_up_growth, avenger_dark |
| **B. 内面型** | 主人公の内面が駆動する | 「変わる」 | slow_life, doted_saint, master_disciple, secret_identity, death_loop |
| **C. 関係型** | 人との関係が駆動する | 「好きになる／嫌われる」 | villainess_destruction_avoid, contract_marriage, academy_cinderella, love_comedy_density, pet_tamer |
| **D. 情報型** | 知識・記録・情報が駆動する | 「知る」 | modern_knowledge, alchemy_workshop, gourmet_conqueror, territory_management, craftsman_legend, detective_mystery, brain_battle, vr_streamer, summon_hero_betrayal |

#### 3.3.2 既存31種に無い 7種（新規追加）— 「もっと多くのジャンル」の具体化

| key | 名称 | 軸 | なぜ必要か |
|:---|:---|:---|:---|
| `court_intrigue` | 宮廷・陰謀 | A | `guild_rebuilder` の外部版だが、目的が势力消滅ではなく**中枢の掌握**で構造が異なる（周辺から中心への移動が要る） |
| `professional_procedure` | 職業手続き（医療/法曹/ journalism） | D | 既存は「一般人→到達」を前提。**その分野の有能人が手順で積み上げる**構造は別。`brain_battle` と近いが解決手段が法律/医学知識である点で別物 |
| `sports_growth` | スポーツ/競技 | A | 大会単位の区切りが自然で、`tournament_champion` の区切り方（トーナメント vs シーズン）と別 |
| `horror_dread` | 恐怖（全容不明が主駆動） | B | 既存31種には**「不明瞭さ」を主駆動にできない**パターンがない。`coda` で真相を出さない分岐が要るため、duty が逆 |
| `healing_care` | 癒し・ケア | B | `doted_saint` は「愛玩される側」。**与える側**（癒し手/支援職/衛生兵）で構造の重点（蓄積→放出）が逆 |
| `ensemble_fracture` | 群像の崩壊と再統合 | C | 単一主人公を前提とする全31種に対し、**複数視点の均衡維持→破綻→再統合**は別 |
| `transformation_isekai` | 身体/性の変容 | B | `reincarnation_cheat` は能力中心。**変容そのものを軸にする**（変容→適応→受容）で、climax の中身が異なる |

#### 3.3.3 定義例（3種）

既存 JSON の `hook` / `mid_crisis` / `climax_type` / `ending` を そのまま `beats` に翻訳する（例: `exile_rise`）。

```yaml
key: exile_rise
name: 追放→成り上がり（王道ざまぁ）
axis: A
market_hint: [web, light_novel]
beats:
  - {key: humiliation,    span: [0.00, 0.05], tension: 0.90, artifact: scene}
  - {key: revelation,     span: [0.05, 0.10], tension: 0.60, artifact: reveal}
  - {key: first_win,      span: [0.10, 0.25], tension: 0.75, artifact: scene}
  - {key: expansion,      span: [0.25, 0.45], tension: 0.55, artifact: scene}
  - {key: midpoint_reversal, span: [0.45, 0.52], tension: 0.92, artifact: reversal}
  - {key: dark_night,     span: [0.52, 0.65], tension: 0.70, artifact: scene}
  - {key: truth_reveal,   span: [0.75, 0.82], tension: 0.95, artifact: reveal}
  - {key: climax,         span: [0.82, 0.94], tension: 1.00, artifact: scene}
  - {key: volume_hook,    span: [0.94, 1.00], tension: 0.60, artifact: hook}
endings: [complete_reversal, open_escalation]
engine: conflict
```

```yaml
key: detective_mystery
name: 事件追跡・犯人究明
axis: D
market_hint: [general, light_novel]
beats:
  - {key: inciting,       span: [0.00, 0.08], tension: 0.55, artifact: reveal}   # 事件の発見
  - {key: failing,        span: [0.08, 0.30], tension: 0.50, artifact: scene}    # 誤った推理
  - {key: deepening,        span: [0.30, 0.48], tension: 0.60, artifact: scene}    # 調査の再設計
  - {key: midpoint_reversal, span: [0.48, 0.56], tension: 0.85, artifact: reversal}
  - {key: dark_night,     span: [0.56, 0.70], tension: 0.65, artifact: scene}    # 証拠の無効化
  - {key: truth_reveal,   span: [0.70, 0.90], tension: 0.95, artifact: reveal}
  - {key: climax,         span: [0.90, 0.97], tension: 0.90, artifact: scene}     # 究明の瞬間
  - {key: coda,           span: [0.97, 1.00], tension: 0.20, artifact: scene}
endings: [closed_solution, partial_solution]
engine: enigma
```

```yaml
key: healing_care                      # 新規7種のうち1つ
name: 癒し手・支援者の蓄積と放出
axis: B
market_hint: [web, general]
beats:
  - {key: inciting,     span: [0.00, 0.10], tension: 0.40, artifact: scene}  # 赋值される/任される
  - {key: daily_loop,   span: [0.10, 0.35], tension: 0.25, artifact: scene}  # ケアの反復・信頼の蓄積
  - {key: deepening,    span: [0.35, 0.52], tension: 0.45, artifact: scene}  # 自分の傷 incidentally 露出
  - {key: midpoint_reversal, span: [0.52, 0.60], tension: 0.70, artifact: reversal}  # 恩返し
  - {key: all_is_lost,  span: [0.60, 0.72], tension: 0.55, artifact: scene}  # mérit が枯渇
  - {key: final_choice, span: [0.72, 0.85], tension: 0.85, artifact: scene}  # 自分の。心まで差し出すか
  - {key: payoff,       span: [0.85, 0.95], tension: 0.80, artifact: scene}
  - {key: coda,         span: [0.95, 1.00], tension: 0.15, artifact: scene}
endings: [warm_resolution, bittersweet]
engine: comfort
```

> `engine` は既存 `archetypes.json:259-280` の **4値**（`conflict` / `comfort` / `connection` / `enigma`）をそのまま再利用する。**新規概念ではない**。

### 3.4 `LENGTH_PROFILE` — 長さ階層 6段

**出典**: 文字数は `frontend/src/constants/manuscript.ts:3-48` の実在プリセットを**昇格**したもの（新規の数字を作らない）。

| key | 名称 | 目標字数 | 話数 | 1話字数 | 出典 |
|:---|:---|:---|:---|:---|
| `short` | 単発短編 | 12,000字 | 1-3 | 4,000-12,000 | `shousetsu-gekkan` |
| `novella` | 中編 | 20,000-40,000字 | 4-10 | 3,000-4,000 | `shousetsu-subaru` / `dengeki-bunko` |
| `single_volume` | 単行本1巻 | 40,000-70,000字 | 15-20 | 3,000-4,000 | `dengeki-bunko` |
| `web_volume` | Web連載1巻 | 100,000字 | 40 | 2,500 | `kakuyomu` |
| `long_serial` | 長編連載 | 250,000字+ | 100-300 | 2,000-2,500 | `narou` |
| `series` | シリーズ | 1,000,000字+ | 不定 | 2,000-2,500 | 新規（既存プリセット外） |

各プロファイルが持つ属性：

```python
@dataclass(frozen=True)
class LengthProfile:
    key: str
    label: str
    eps_range: tuple[int, int]
    chars_per_ep: tuple[int, int]
    arc_count: tuple[int, int]          # 部(arc)の数の範囲
    min_beats: int                      # これ未満のビート数なら pattern を圧縮する
    foreshadow_scopes: tuple[str, ...]  # ("short",) / ("short","mid") / ("short","mid","long")
    hook_window_eps: int                # つかみは何話までに必須か
    ending_contract: str                # この長さで守るべき締め方
```

**長さ階層の追加が意味を持つ理由**（=元提案への直接の答え）:

| 階層 | `hook_window_eps` | 最低ビート数 | 收紧规则 |
|:---|:---|:---|:---|
| `short` | 1 | 5 | 3幕以上入らない → **圧縮モード**（§4.3） |
| `novella` | 1 | 8 | 1部構成 |
| `single_volume` | 1 | 12 | 2-3部 |
| `web_volume` | **3** | 18 | 3-4部 + **毎話末尾フック必須** |
| `long_serial` | 3 | 24 | 4部以上 + **中期伏線**が有効化 |
| `series` | 5 | 30 | 5部以上 + **巻単位のarquivo と持ち越し** |

`web_volume` の `hook_window_eps=3` が、元提案の「3話以内の掴み」の**一般化**である。他の長さでは 1、1、1、3、3、5 と**異なる**。

### 3.5 `MARKET` — 媒体規格 4種

元提案が「Web小説向けの話」として書いていたものの、正体は**媒体規格**である。

| key | 名称 | つかみの位置 | 毎話フック | 章/部の要求 | 伏線規律 | 締め方 |
|:---|:---|:---|:---|:---|:---|:---|
| `web` | Web連載（なろう/カクヨム） | 冒頭3行 | **必須** | なし（区切りなし） | 短期のみ・長期なし | 話末フック必須 |
| `light_novel` | ライトノベル単行本 | 第1話冒頭 | 任意 | 3-4部 | 1巻内で長期伏線回収 | 1巻末の引き |
| `single_shot` | 単発・投稿（新人賞/雑誌） | **冒頭1,000字** | なし | 4部（起承転結） | 短期のみ | 400字×枚数で頭打ち |
| `general` | 一般文芸・長編 | 序盤1章 | なし | 4部＋幕間 | 長期可 | 閉じた結末 |

**これは「構造」ではなく「提出物の契約」**。同じ `exile_rise` でも `web` と `general` では同じ `beats` で**締め方**と**伏線管理**が変わる。

### 3.6 テンプレートカード（ユーザーの選択単位）

原則 D3 の「組合せ爆発を列挙で封じる」ための装置。**ユーザーは座標を組み立てない。**

```python
@dataclass(frozen=True)
class TemplateCard:
    card_id: str
    label: str            # "⚔️ 追放ざまぁ（Web連載・1巻40話）"
    blurb: str            # 1行の説明
    pattern: str          # STORY_PATTERN key
    length: str           # LENGTH_PROFILE key
    market: str           # MARKET key
    genre_coord: dict     # §3.7 の座標
    style_key: str        # 既存 style_key（archetypes_new.py の style_key を流用）
    source: str           # 出典（既存キー / 新規）
```

**カードの初版は 24枚**（＝構造核を「代表的なパターン」に絞ったもの）。全38×6×4を最初から公開しない。

| # | card_id | パターン | 長さ | 媒体 |
|:---|:---|:---|:---|:---|
| 1 | `tpl_exile_web` | exile_rise | web_volume | web |
| 2 | `tpl_exile_ln` | exile_rise | single_volume | light_novel |
| 3 | `tpl_reinc_cheat_web` | reincarnation_cheat | web_volume | web |
| 4 | `tpl_villainess_ln` | villainess_destruction_avoid | single_volume | light_novel |
| 5 | `tpl_isekai_dungeon` | dungeon_conqueror | long_serial | web |
| 6 | `tpl_modern_knowledge` | modern_knowledge | single_volume | light_novel |
| 7 | `tpl_stream_web` | vr_streamer | long_serial | web |
| 8 | `tpl_misunderstanding` | love_comedy_density | single_volume | light_novel |
| 9 | `tpl_mystery_short` | detective_mystery | novella | general |
| 10 | `tpl_mystery_ln` | detective_mystery | single_volume | general |
| 11 | `tpl_slow_life_web` | slow_life | long_serial | web |
| 12 | `tpl_cooking` | gourmet_conqueror | short | general |
| 13 | `tpl_craft` | craftsman_legend | novella | general |
| 14 | `tpl_territory` | territory_management | long_serial | web |
| 15 | `tpl_guild` | guild_rebuilder | long_serial | light_novel |
| 16 | `tpl_military` | army_rational | long_serial | light_novel |
| 17 | `tpl_horror_short` | horror_dread | short | single_shot |
| 18 | `tpl_healing_web` | healing_care | web_volume | web |
| 19 | `tpl_procedure_ln` | professional_procedure | single_volume | light_novel |
| 20 | `tpl_isekai_court` | court_intrigue | long_serial | general |
| 21 | `tpl_isekai_isekai_short` | transformation_isekai | novella | general |
| 22 | `tpl_ensemble_ln` | ensemble_fracture | single_volume | light_novel |
| 23 | `tpl_sports_web` | sports_growth | web_volume | web |
| 24 | `tpl_deathloop_ln` | death_loop | single_volume | light_novel |

> カード 12 / 13 / 17 / 21 は **短編・中編**であり、元提案に存在しなかった層。

### 3.7 ジャンル座標（`genre_coord`）

「もっと多くのジャンル」を**4軸タプルの座標**として表現する。これにより 38×6×4 の列挙を回避する。

```python
GENRE_COORD = {
    # domain: 舞台・領域
    "domain":   ["fantasy", "sf", "modern", "history", "mystery", "horror",
                 "romance", "youth", "workplace", "medical", "legal",
                 "sports", "game", "food", "craft", "apocalypse", "other"],
    # driver: 何が駆動するか
    "driver":   ["power", "knowledge", "emotion", "relation", "mystery", "survival"],
    # stake: 失い得るもの
    "stake":    ["life", "status", "relationship", "identity", "sanity", "boring"],
    # tone: Mandatory な感情色
    "tone":     ["hot-blooded", "healing", "dark", "comedy", "cool-headed", "romantic"],
    # rating: 表現上限
    "rating":   ["general", "r15", "r18"],
}
```

- 既存 `archetypes_new.py:50-446` の `style_key` / `cheat_scale` / `growth_curve` / `system_assist` / `cost_severity` は、**この座標の表示ラベルと初期値**として再解釈する（**新規スキーマではない**）。
- 座標は **LLM への注入語彙**としてのみ使い、構造判定には **使わない**（原則 D1/D3）。

---

## 4. 展開アルゴリズム（LLM 0回の決定論処理）

### 4.1 署名

```python
def resolve_spine(
    pattern_key: str,     # STORY_PATTERN
    length_key: str,      # LENGTH_PROFILE
    market_key: str,      # MARKET
    total_eps: int | None = None,   # 未指定なら length.eps_range の中央
) -> Spine
```

### 4.2 通常の展開（`min_beats <= total_eps`）

```
1. beats = STORY_PATTERN[pattern_key].beats        # span は相対
2. eps   = total_eps or 長さプロファイルの中央値
3. 量子化: 各 beat に [floor(span[0]*eps)+1, ceil(span[1]*eps)] の話数区間を割当
   - 区間が 0 話になる beat は、直前の beat と併合する
   - 区間が 2話以上になる beat は、前半を engine / 後半を payoff に自動分裂
4. 長さの強制: MARKET.hook_window_eps 以内の最初 N 話に、pattern の先頭 hook beat を寄せる
5. 末尾: eps == length.eps_range 上限なら coda を読む、market=web なら volume_hook を必ず残す
6. foreshadow_scopes で pattern の long_term beat を filter（短編では long_term を落とす）
```

**完全に整数演算。LLM を呼ばない。**

**例: `exile_rise` × `web_volume` × `web` × 40話**

| ep | beat | tension | duty（例） |
|:---|:---|:---|:---|
| 1 | `humiliation` | 0.90 | 理不尽な追放を五感で描け。能力の片鱗hintで終わらせるな |
| 2-3 | `revelation` | 0.60 | 能力の覚醒。ただし無双にはしない |
| 4-9 | `first_win` | 0.75 | 最初のカタルシス。敵を一体倒すまで |
| 10-17 | `expansion` | 0.55 | 基盤の獲得。黒幕の布を短期で1つ |
| 18-20 | `midpoint_reversal` | 0.92 | 前提の覆し |
| 21-25 | `dark_night` | 0.70 | 再起の苦肉 |
| 30-32 | `truth_reveal` | 0.95 | 長期伏線（1巻もの）の完全回収 |
| 33-37 | `climax` | 1.00 | 決戦。短期＋長期を一気に |
| 38-39 | `aftermath` | 0.40 | 凱旋 |
| 40 | `volume_hook` | 0.60 | **2巻への引き**（`web` 契約で必須） |

`COMMERCIAL_40EP_BEATS`（`src/config/commercial_beat_sheet.py:5-59`）を**この出力で置き換える**。7 phase = 上表の区切りに対応している（差異は「導入 (1-3) / 初期成功 (4-10) / 第1の試練 (11-18) / Midpoint (19-25) / 最大危機 (26-32) / 決戦 (33-38) / 凱旋 (39-40)」）。

### 4.3 圧縮モード（`min_beats > total_eps`）― **短編の核心**

ここが元提案に**最も欠けていた機能**。1話短編に 9ビートは入らない。

**圧縮ポリシー（長さの区分けごとに定義）**:

| 元の beat | `short`(1話) | `novella`(5話) |
|:---|:---|:---|
| `humiliation` + `revelation` | → `inciting` に**併合**（1 scenes 内で「理不尽→異変」を連続描写） | → ep1 に**連続2场景** |
| `first_win` + `expansion` | → `first_win` に**縮小** | → ep2 |
| `midpoint_reversal` | **保持**（短編の core であり削れない） | → ep3 |
| `dark_night` | → `all_is_lost` に**置換**（別 beat なので「問われる」になる） | → ep3後半 |
| `truth_reveal` + `climax` | → `climax` に**併合**（1 scene で真相提示＋解決） | → ep4 |
| `volume_hook` | **削除**（短編に「次」は無い） | → ep5（`general` なら `coda`） |

**不変条件**（圧縮後も必ず残る3つ）:
1. `inciting` 相当が最初
2. `midpoint_reversal` 相当が中盤
3. `climax` 相当が最後

この不変条件をテストで固定する（§7.1）。

### 4.4 検証（原則 D5）

同じ `structure_validator` を **2回**使う。

| タイミング | 何を測るか | 失敗時 |
|:---|:---|:---|
| **生成前** | `Spine` が自分の `pattern.beats` を満たすか（自己整合） | テンプレ側のバグ。ログ + テスト |
| **生成後** | 実際の `Plot.tension` 列が `Spine.tension_target` に乗るか | ユーザーへ「**構成テンプレート充足度**」として提示 |

`structure_validator.validate(chapters, structure)` は既に `missing_beats` / `climax` / `pacing` を返す（`structure_validator.py:118-134`）。**`structure` 引数に `pattern_key` を渡せるように拡張するだけ**で両方に使える。

**これがユーザー価値の本体**: 生成後に「この作品は『追放ざまぁ Web1巻』テンプレの充足度 87%」と出る。**それ奥林だけではないが、これが唯一の定量的フィードバック**。

---

## 5. 既存コードとの結線表（追加ではなく置換）

| 新設 | 置き換える既存物 | 处置 |
|:---|:---|:---|
| `config/story_spine/patterns.yaml`（38件） | `config/data/archetypes.json:9-258` `PLOT_STRUCTURES`（31件・未ロード） | **昇格**。キー維持で移設。ロード可能な唯一のソースにする |
| 同 | `config/archetypes_new.py:44-48` `PLOT_STRUCTURES`（3件のみ） | **削除**（死んでいる） |
| `config/story_spine/lengths.yaml`（6件） | `frontend/src/constants/manuscript.ts:3-48` の6プリセット | **昇格**。FE は API 参照に変更し二重管理をやめる |
| `config/story_spine/markets.yaml`（4件） | `src/config/commercial_beat_sheet.py:5-59` | `web` プロファイルの実装として再定義 |
| `config/story_spine/cards.yaml`（24件） | `config/archetypes_new.py:485-530` `EASY_GENRES`（8件・空アーキタイプ参照） | **置換**。`EASY_GENRES` が `overcoming_the_monster`（空 dict）を指している問題も解消 |
| `src/services/spine_resolver.py`（新規） | `src/backend/workflows/reverse_plot_workflow.py:97-223` | 薄いラッパーに縮小。中身は `_calc_tension` の算術を `Spine` へ移す |
| — | `src/backend/routers/commercial_planning.py:112` の4幕ハードコード | `web_volume` プロファイルに置換 |
| — | `src/backend/routers/plots.py:342-378` の12ビート（Save the Cat）ハードコード | `Spine` から生成。`short` なら12ビート全部が1話に潰れる |
| — | `src/backend/engine_narrative.py:74-86` の `ep_num == 5` / `24 <= ep_num <= 26` | **相対位置に置換**（`span` から導出） |
| — | `config/constants.py:18-22` の `EP_*`（8話固定） | `Spine` へ置換。定数を削除 |
| — | `src/models/beat_sheet.py:16` の `le=40` | `ge=1` のみに緩める（上限制約を構造データ側に移す） |
| — | `src/services/pipeline_base.py:72` `current_volume`（増加なし） | `Spine` に `volume_index` を持たせ、実際に増えるようにする |
| — | `src/services/structure_validator.py:16-48` `STRUCTURE_DEFINITIONS`（3件） | `Spine` の `pattern.beats` を渡す形に**拡張**。三幕/起承転結は `pattern` の**特殊ケース**として保持 |
| — | `src/backend/routers/misc.py:91` `PLANNING_PRESETS`（ImportError） | **修正**。新レジストリを返す（現状は常に500） |
| — | `frontend/src/data/reversePlotSteps.ts:54-73` | backend と逐語重複。API 化 |
| — | `config/archetypes_new.py:476-530` の死んだ定数群 | `resolve_spine()` へ統合または削除 |

### 5.1 ジャンル語彙の統合

4系統（G1-G4）と3系統のマッピング表（T1-T3）を **単一の `GENRE_REGISTRY`** に置き換える。

```python
# config/story_spine/genre_registry.py
GENRE_REGISTRY: dict[str, dict] = {
    "HighFantasy": {
        "label": "ハイファンタジー",
        "aliases": ["fan", "fantasy", "ハイファンタジー (R15)", "ファンタジー", "ハイファンタジー"],
        "domain": "fantasy",
        "preset_key": "cheat_tensei",       # T1/T2/T3 を一本化
        "rating": "r15",
    },
    ...
}
```

- `resolve_genre_to_preset`（`easy_mode.py:35-57`）、`preset_loader.py:43-60`、`spice_guard_adapter.py:47-54` の3表を**この1書に寄せる**。
- `"fan"` が**必ず**解決されるようになる（現状は `None` に落ちる）。
- FE の `SimpleModePanel.tsx:97-102` のハードコード select は `value` を `HighFantasy` 等に直し、選択肢は API 取得に変更。

---

## 6. UI 設計（3階層）

原則 D3 を守るため、**階層ごとに選択肢を減らす**。

### 6.1 Tier 1: カード選択（既定・3クリック完了）

`EasyModePage` / Wizard Step1 の先頭に、24枚のテンプレートカードを**グリッド表示**。
カードを選ぶと、以降の設定が**すべて自動入力**される（ジャンル select / 話数 / 1話字数 / style_key / チート度）。

```
┌─────────────────────────────────────────┐
│  【金庸の模板から選ぶ】                 │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │⚔️ 追放ざまぁ│ │🌸悪役令嬢   │ │🎮ダンジョン│ │
│  │Web1巻40話   │ │単行本1巻  │ │長編連載  │ │
│  └──────────┘ └──────────┘ └────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │🔍 事件の謎  │ │🍲 まったり飯テロ│ │…        │ │
│  │中編・文芸  │ │短編     │ │         │ │
│  └──────────┘ └──────────┘ └────────┘ │
│  →「カスタムで組み立てる」             │
└─────────────────────────────────────────┘
```

### 6.2 Tier 2: 微調整（カード選択後、自動入力された値の上書き）

- 話数（`length.eps_range` 内にクランプ）
- 1話字数（`length.chars_per_ep` 内にクランプ）
- 結末（`pattern.endings` から選択）
- テンポ（`curve` の `tension` を -0.15 / +0.15 で上下させる）

**注記:** テンプレートは「初期値」であり、強制ではない。** ユーザーが全項目を変更した場合は `spine_quality="off"` として尊重する（§8.1）。

### 6.3 Tier 3: 座標編集（上級者・`?advanced=1`）

§3.7 の5軸 + 34ビート語彙の表示。テンプレート JSON の直接編集も可能。

---

## 7. テスト計画

### 7.1 構造不変条件（最重要）

```python
def test_short_form_preserves_three_critical_beats():
    """1話短編でも 発端・中点反転・クライマックス の3つは必ず残る。"""
    spine = resolve_spine("exile_rise", "short", "general", total_eps=1)
    keys = [b.key for b in spine.beats]
    assert "inciting" in keys
    assert "midpoint_reversal" in keys
    assert "climax" in keys
    assert spine.beats[-1].key == "climax", "最後がクライマックスでないと結末が無い"


def test_every_pattern_resolves_at_every_length():
    """38パターン × 6長さ で必ず例外なく解決できる（組合せ網羅テスト）。"""
    for p in STORY_PATTERNS:
        for l in LENGTH_PROFILES:
            for m in MARKETS:
                for eps in (l.eps_range[0], sum(l.eps_range) // 2, l.eps_range[1]):
                    spine = resolve_spine(p, l, m, eps)
                    assert spine.beats, f"{p}×{l}×{m}@{eps} が空"


def test_all_spans_are_relative_not_absolute():
    """絶対話数が混入していないことの構造テスト。"""
    for p, pat in STORY_PATTERNS.items():
        for b in pat.beats:
            assert 0.0 <= b.span[0] < b.span[1] <= 1.0, f"{p}.{b.key} の span が相対でない"
```

### 7.2 既存バグの回帰固定

```python
def test_pacing_graph_is_length_independent():
    """話数を変えても『第1の爆発』の相対位置が変わらない。"""
    a = PacingGraph.get_instruction(2, total_eps=20)
    b = PacingGraph.get_instruction(10, total_eps=100)
    assert a["instruction"] == b["instruction"]   # 同一の相対位置→同一の指示


def test_episode_beat_allows_long_serial():
    """100話の構成が Pydantic で弾かれない。"""
    EpisodeBeat(ep_num=100, phase="x", mission="y", tension_target=0.5,
                visual_scene_focus="z")       # 旧: ValidationError


def test_fan_resolves_to_a_preset():
    assert resolve_genre_to_preset("fan") is not None    # 旧: None
```

### 7.3 効果測定（§8）

---

## 8. 効果（測定可能な形で定義）

元提案の「效果好」は定性語のみ。本提案は**計測可能なKPI**に落とす。

| # | KPI | 現状（想定） | 目標 | 測定方法 |
|:---|:---|:---|:---|:---|
| K1 | **構成充足度**（生成後 `structure_validator` スコア） | 計測不能 | 全書籍で算出可能 | `Spine` 導入後、既存書籍を再評価 |
| K2 | **中点反転の絶対位置**の散らばり | 未知 | 0.40-0.60 に 90% 収束 | `Spine` vs 実 `Plot.current_chain_phase` |
| K3 | **Climax 位置**の散らばり | 未知 | 0.75-0.92 に 90% 収束 | 同上 |
| K4 | **LLM 追加コスト** | — | **0 円** | 展開は `resolve_spine()` の純算術 |
| K5 | 話数 100 の構成が完走する | 不可（`le=40`） | 可能 | §7.2 |
| K6 | 1話短編に構造が入る話数 | 0 | 100% | `resolve_spine(x, "short", ...)` |
| K7 | genre→preset 解決率 | `"fan"` が `None` | 100% | §7.2 |
| K8 | `/api/config/planning_options` 応答 | HTTP 500 | 200 | 直接 curl |

> K1-K3 は**実施前の実測**を先に取る必要がある（**本提案は実装計画だが、その前に `structure_validator.validate()` を既存書籍に一度当てるだけの計測作业**を推奨）。K1 のベースライン無しでは効果证明ができない。

### 8.1 互換性と段階適用

| 段階 | `spine_quality` | 挙動 | 既定 |
|:---|:---|:---|:---|
| 計測のみ（Structure-free） | `off` | Spine を生成するが**一切プロンプトに入れない**。KPI だけ採る | **Yes** |
|  Soft 適用 | `soft` | `spine.duty` をプロンプト末尾に**参考情報**として追加（既存プロンプトは壊さない） | No |
| Hard 適用 | `hard` | `spine` が本文生成の**主構造**。話ごとの `duty` を必須とする | No |

**既定を `off` にすることで、既存書籍の再生成結果が変わり格式化れない。** §9 の Phase A-C は `off` のまま進められる。

---

## 9. 実装フェーズ（依存順）

各ステップは「1ファイル主担当＋検証コマンド1本」。行番号は**必ず grep で再確認**すること（原則 D7）。

### Phase A: 相対位置化の先行（他フェーズ的自立条件）

| Step | 対象 | 内容 | 検証コマンド |
|:---|:---|:---|:---|
| **A1** | `src/backend/engine_narrative.py` | `PacingGraph.get_instruction` の `ep_num == 5` / `24 <= ep_num <= 26` を**相対位置**に置換。`mid_twist_ep` と同じ方式に統一 | `pytest tests/unit/test_pacing_graph.py -q` |
| **A2** | `config/constants.py:18-22` | `EP_*` 定数を**削除**。呼び出し元を `Spine` へ移行（Phase B 後）。当面は退避 | `pytest tests/unit/test_constants.py -q` |
| **A3** | `src/models/beat_sheet.py:16` | `le=40` を撤去。`EpisodeBeat` の上限制約を削除 | `pytest tests/unit/test_beat_sheet.py -q` |

> Phase A は**単独で価値があり**、Spine 導入を待たずに適用可能。

### Phase B: データ層の構築（0 LLM・0 リスク）

| Step | 対象 | 内容 |
|:---|:---|:---|
| **B1** | `config/story_spine/beat.py` + `tests/unit/test_spine_beats.py` | 34語の閉じた語彙の定義。`span` 相対性の不変条件をテストで固定 |
| **B2** | `config/story_spine/patterns.yaml` + `tests/unit/test_spine_patterns.py` | 31種（既存JSONから移設）＋ 7種（新規）。全 beat key が語彙に存在することをテスト |
| **B3** | `config/story_spine/lengths.yaml` / `markets.yaml` / `cards.yaml` | 6 / 4 / 24。`manuscript.ts` の数字を**転記**（改変しない） |
| **B4** | `config/story_spine/genre_registry.py` | §5.1。`"fan"` 解決テストを**先に**作る |

### Phase C: 展開エンジン（LLM 0回）

| Step | 対象 | 内容 |
|:---|:---|:---|
| **C1** | `src/services/spine_resolver.py` | §4.2 通常展開。`resolve_spine()` |
| **C2** | 同 | §4.3 **圧縮モード**。3不変条件をテストで固定（§7.1 の1本目） |
| **C3** | `src/services/structure_validator.py` | `pattern_key` を受け取れるよう拡張（§4.4） |
| **C4** | `src/backend/workflows/reverse_plot_workflow.py` | `_calc_tension` の算術を `Spine` へ移し、本体はラッパーに縮小 |

### Phase D: 配線（`spine_quality=off` で）

| Step | 対象 | 内容 |
|:---|:---|:---|
| **D1** | `src/backend/routers/easy_mode.py:35-57` | `resolve_genre_to_preset` を `GENRE_REGISTRY` 経由に変更 |
| **D2** | `src/services/preset_loader.py:43-60` / `src/services/spice_guard_adapter.py:47-54` | 3表の統合 |
| **D3** | `src/backend/routers/misc.py:91` | `PLANNING_PRESETS` の **ImportError を修正**し、`/cards` `/patterns` `/lengths` を返す |
| **D4** | `src/backend/routers/plots.py:342-378` | 12ビートハードコードを `Spine` 生成に置換 |
| **D5** | `src/backend/routers/commercial_planning.py:112` | 4幕ハードコードを `web_volume` に置換 |
| **D6** | `src/llm/prompts.py:57-78` ＋ `prompts/templates/narrative/plot_stage1.j2` 等 | `spine_quality=soft/hard` で `duty` を注入。**`off` では差分ゼロ** |
| **D7** | `src/services/preset_loader.py:164-166` `get_plot_pattern()` | 死んでいる呼び出し元を `Spine` に結線、または削除 |

### Phase E: UI

| Step | 対象 | 内容 |
|:---|:---|:---|
| **E1** | `frontend/src/constants/manuscript.ts` | 6プリセットを**削除**し、`/api/config/planning_options` 参照に変更（二重管理を解消） |
| **E2** | `frontend/src/components/generate/SimpleModePanel.tsx` | カードグリッド（Tier 1）＋ 微調整（Tier 2）。ジャンル select のハードコードを廃止 |
| **E3** | `frontend/src/components/wizard/Step1PlotInput.tsx` | 同上。`growth_curve` の4値（`archetypes_new.py` と不一致）を `GENRE_REGISTRY` 参照に置換 |
| **E4** | `frontend/src/components/planning/` | **構成充足度**の表示（K1）。現状 `BeatSheetViewer.tsx`（12行のplaceholder） |

### Phase F: 計測

| Step | 対象 | 内容 |
|:---|:---|:---|
| **F1** | `scripts/measure_spine_alignment.py`（新規） | 既存書籍に `Spine` を当てて K1-K3 のベースラインを作る |
| **F2** | `docs/STATUS.md` | 効果測定表に K1-K8 を追記（[PLAN_T6 Step 15](PLAN_T6_REMEDIATION_18STEPS.md) の形式に準拠） |

---

## 10. リスク

| リスク | 影響 | 対策 |
|:---|:---|:---|
| **38パターンの `duty` 文が全部 LLM 任せの文法になる**（文面の品質低下） | High | `duty` は**1文・命令形**に限定。生成は**人間＋少数サンプル**で初期化。LLM生成は**禁止**（[PLAN_T6 原則 P6](PLAN_T6_REMEDIATION_18STEPS.md) と同じ方針） |
| 38×6×4 の組合せで**1つも検証していない崩れ**が残る | High | §7.1 の網羅テスト（38×6×4×3 = 2,736 ケース）を**必ずCIに入れる**。德数 100ms 未満で走る |
| `spine` を入れると**既存書籍の再生成結果が変わる** | High | 既定を `off` に。`soft`/`hard` は**新規書籍のみ**デフォルト許可 |
| `100-300話`の中長編で `resolve_spine` が O(n) でない | Medium | 量子化は**区間境界のみ**を計算する。beat 数（≤34）だけがループする。話数に比例しない |
| **7新規パターンの構造的妥当性が未検証** | Medium | 7種は `docs/` に **duty 付き設計理由**を残す。**1話短編で実生成**して妥当性を確認してから `hard` を解禁 |
| `bible_service._create_ultra_fast_plan`（`:318-411`）との二重構造 | Medium | `Spine` は **プロット（ep単位）** を、bible は**世界/人物**を扱う。責務が重複しないこと。既に `macro_skeletons` があるので、`Spine` はその**上流**に置く |
| 営業上の期待値が違う（「ヒット作出」系でない） | Medium | §6.2 でテンプレートを**初期値**として明示。ユーザーの全上書きを尊重する |

---

## 11. 非目標（明確にやらないこと）

1. **LLM による構成の創作** — 構成は決定論。これは原則 D2。LLM が**埋めるのは `duty` の具体化**だけ
2. **全38×6×4の即時公開** — Tier 1 は 24枚に限定（原則 D3）
3. **既存プロンプトの書き換え** — `spine_quality=off` で**差分ゼロ**であること
4. **新たなジャンル語彙の追加** — 既存 4 系統の**統合**が先
5. **販売/収益の予測** — 本提案は構成品質のみを扱う

---

## 12. 元提案への対応表

| 元提案の記述 | 本提案での扱い |
|:---|:---|
| 「追放ざまぁ/悪役令嬢/現代ダンジョン配信/勘違い英雄譚の4テンプレート」 | カード 1,4,5,8 に収録。**加えて 20枚を追加**（短編・中編・文芸・ horror・職業もの…) |
| 「第1話：理不尽な追放 / 第2話：チート覚醒 / 第3話：カタルシスとヒロイン遭遇」 | `exile_rise` の `humiliation`/`revelation`/`first_win` beat の `duty` に落ちる。**相対位置**で定義されるので 1話短編では 1話に圧縮される |
| 「三幕構成」 | `MARKET.single_shot` の `ending_contract` として規定。既存の `structure_validator` の `three_act` は保持し、`pattern` の特殊ケースとして扱う |
| 「1巻ラストの引き」 | `MARKET.web` の `ending_contract` ＋ `LENGTH_PROFILE.web_volume`。**media 別のルール**として分離 |
| 「話数ごとに黄金ビートを自動プリセット」 | §4.2。`spans` の量子化として一般化。**3話固定ではない** |
| （未記載） | **短編・中編・長編・シリーズ**の 6階層を追加（§3.4） |
| （未記載） | **1話短編の圧縮モード**（§4.3）— 元提案の最大の穴 |
| （未記載） | **文体/媒体軸**（§3.5）— 「Web小説特化」の言葉の罠を回避 |
| （未記載） | **生成後の構成充足度**による定量フィードバック（§4.4） |
| （未記載） | **LLM コスト 0** の設計（原則 D2） |
| （未記載） | 既存5システムからの**移行**（§5）— 追加ではない |

---

## 13. 次のアクション

| # | アクション | 所要 | 前提 |
|:---|:---|:---|:---|
| 1 | `structure_validator.validate()` を**既存書籍に当てて K1-K3 のベースライン**を取る | 0.5h | なし（即着手可） |
| 2 | 本提案の**対象範囲**を決める（Phase A-C までか、全フェーズか） | 10min | なし |
| 3 | Phase A（A1-A3）の実装 | 2h | なし（Spine 非依存） |
| 4 | 7新規パターンの**設計理由書**を `docs/` に作成 | 2h | 2 の決定 |
| 5 | Phase B（データ層）の実装 | 4h | 3 |
| 6 | 実装計画書の作成（本提案は提案であり、実装分解ではない） | 1h | 2-5 |

> **推奨**: アクション 1（ベースライン計測）を**今日中に**実施する。K1 の現状値が無いまま実装着手すると、効果证明ができず、[PLAN_T6 Step 15](PLAN_T6_REMEDIATION_18STEPS.md) と同じ「数値を推測で埋める」失敗CENする。
