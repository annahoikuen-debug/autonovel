# Phase 3 事前調査: 挿絵生成の配線状況サーベイ

**作成日:** 2026-11-24
**ステータス:** 📋 調査完了(実装は Phase 3 で着手)
**目的:** Play モード(`frontend/src/pages/PlayModePage.tsx`)のシーンに挿絵を表示するための現状把握(`docs/plans/ROADMAP_PLAYABLE_NOVEL.md` §4 Phase 3 の「着手前に配線精査」要件)
**方法:** コードの静的精査(編集なし)。行番号は 2026-11-24 時点。

---

## 0. 要点(TL;DR)

- 挿絵生成の**実装は大幅に存在する**(Imagen 直叩きの `ImageService`、`IllustrationAgent`、DB テーブル、Studio 表示 UI まで)
- ただし**未配線・スタブ・二重実装が多い**: ポート `IIllustrationService` のアダプタ不在、`/generate` API が画像を生成せずプロンプトのみ、easy_mode パイプラインの `enable_illustration=False` ハードコード、`/static` 配信の不在
- Play モード表示に必要な最小ギャップは **(1) ノード⇔挿絵の紐付け(episode_number 検索)、(2) フロント表示とフォールバック、(3) 画像 HTTP 配信、(4) 実画像生成経路の接続** の 4 点
- プロバイダ選択機構が 3 系統並存しており、Phase 3 の設計で「本線を 1 本に定める」意思決定が必要(ADR 推奨)

---

## 1. 実装が存在するもの(実装済み・配線済み)

### 1.1 生成サービス層 `src/publishing/illustration/`

| 実装 | 場所 | 説明 |
|---|---|---|
| `SceneExtractor` | `src/publishing/illustration/scene_service.py:25` | 本文から挿絵シーン抽出(ヒューリスティック :56 / LLM :69、LLM 失敗時ヒューリスティックへフォールバック :89) |
| `SceneIllustrator` | `scene_service.py:92` | 1 シーン→プロンプト構築(:100)→`ImageService.generate`(:103)→`IllustrationResult` |
| `SceneIllustrationService` | `scene_service.py:119` | 抽出+生成の高レベル統合(:127 `generate()`、最大 3 シーン)。**`src/cli/illustration_cli.py:69` からのみ呼ばれる(本番配線なし)** |
| `YonkomaPlanner` / `YonkomaIllustrator` | `scene_service.py:141` / `:214` | 6 コマ要約→1 枚画像 |
| `ImageService` | `src/publishing/illustration/image_service.py:18` | **事実上の唯一の実画像生成経路**。Google GenAI SDK(Imagen)直呼び(:54-57 遅延 `genai.Client`、:88-92 `models.generate_images`)。保存先 `static/illustrations`、戻り値 `/{filepath}`(:121-132) |
| `CoverGenerator` / `CharacterIllustrator` | `cover_service.py:14` / `character_service.py:14` | 表紙・立ち絵生成(ImageService 依存) |
| `resolve_request_model` 等 | `model_selector.py:47` | tier(auto/fast/quality/ultra)→実モデル ID。カタログは `src/config/imagen_models.py:32-42`(`imagen-4.0-*-generate-001`) |
| プロンプト構築 | `prompts.py:63`(scene)/`:107`(safety)/`:150`(yonkoma) | ジャンル別スタイルヒント(:9-17) |

### 1.2 外部画像生成 API クライアント(3 系統が並存)

| 系統 | ファイル | 種類 |
|---|---|---|
| **現行本線** | `image_service.py:18`(google-genai SDK / Imagen) | SDK 型。キー必須(:36-40) |
| 旧インターフェース | `base.py:27` `ImageGeneratorClient` ABC + `sd_client.py:9`(SD WebUI)+ `dalle_client.py:12`(DALL·E)+ `mock_client.py:16` | ファクトリ `factory.py:58 get_image_client`(`IMAGE_PROVIDER` 環境変数、comfyui→Mock フォールバック :74-76)。**src 本体から未使用** |
| v5.0 アダプタ | `adapters/base.py:39` + `dalle3_adapter.py:20`($0.04/枚)+ `fal_adapter.py:20`(fal.ai Flux/SDXL)+ `mock_adapter.py:23` | ファクトリ `factory.py:24 get_image_adapter`(raw env 参照 :37-49)。**src 本体から未使用** |
| 新プロトコル(未配線) | `clients/base.py:48` `ImageClientProtocol` + `clients/gemini_image_client.py:31` `GeminiImageClient`(キーなし/`mock_mode` で疑似 PNG へ自動退避 :57-60/:168)+ `clients/legacy_imagen_client.py:26` | docstring 言及の `UnifiedIllustrationGenerator` は**リポジトリ内に存在しない** |

### 1.3 エージェント層

- `src/agents/illustration_agent.py:24` `IllustrationAgent(SkillAgent)`:
  - `execute`(:44): request なし→正常 no-op(:61-75)。**`run`/`generate_prompt_only`(:119)は画像生成せず `image_url=""`(:141)で永続化**(:158、警告 :150-156)
  - 実画像を生成する経路は 3 つ: `_generate_episode`(:176、ただし `run` から呼ばれない)、`generate_episode_yonkoma`(:412、実画像+永続化)、`generate_episode_scenes`(:438 → `SceneIllustrationService.generate` :440 + 永続化 :441-443)
- `src/agents/skills/v1/illustration_skill.py:7` `IllustrationSkill`: 薄いラッパー(=プロンプトのみ)
- `src/agents/skills/v2/illustration_skill.py:13` `IllustrationSkillAgent`: v1+visual_textual_synergy の前後処理
- `src/agents/skills/v1/easy_mode_illustration.py:15` `EasyModeIllustrationSkill`: **スタブ**(常時空リスト、MARKETING へ)

### 1.4 呼び出しパイプライン

| 経路 | 場所 | 実画像の有無 |
|---|---|---|
| Router API(同期) | `src/backend/routers/illustrations.py:51-102` `POST /generate` → `workflow.illustration_agent.run()`(:93) | **無し(プロンプトのみ)**。5 クレジット消費(:66-72) |
| Router API(4コマ) | `illustrations.py:105-185` `POST /yonkoma` → `generate_episode_yonkoma`(:172-176) | **有り**。20 クレジット(:135-141) |
| Router API(バッチ) | `illustrations.py:188-224` `POST /batch` → Huey タスク | ワークフロー経由(下記) |
| Huey ワーカー | `src/backend/tasks/illustration_tasks.py:73-93` `illustrate_batch_task` → `IllustrationWorkflow.execute` | 下記の通り |
| `IllustrationWorkflow` | `src/backend/workflows/illustration_workflow.py:17`。表紙 :87-99・話数 :102-127 は `agent.run()`(=**プロンプトのみ**)+yonkoma :184-207 は実画像 | 混在 |
| Orchestrator(manifest) | `src/backend/tasks/generation_tasks.py:220-239`(`image_service` を dependencies に注入 :227)、スキル DI フォールバック `src/agents/skill_base.py:237-253`(キー無ければ `"dummy-key"` or `_DummyImageService`) | プロンプトのみ |
| エンジンパイプライン | `src/services/pipeline_steps.py:489-535` `IllustrationStep`(`enable_illustration` ゲート :493-501、失敗でも本編継続 :535) | Workflow 依存 |
| EasyMode パイプライン | `src/easy_mode/pipeline.py:84-85` **`enable_illustration=False` ハードコード** | 無効 |
| DI コンテナ | `src/core/container/app.py:167-204`(`image_service` / `illustration_agent` / `illustration_workflow`)、engine へ注入 :182 | — |
| FastAPI DI | `src/dependencies.py:30-34` `get_illustration_workflow`(GEMINI キーを override :18-27) | — |
| CLI | `src/cli/illustration_cli.py:29-32`、`:69`(`generate_episode_scenes` の唯一の呼び出し元) | 有り |

### 1.5 DB 層

- モデル: `src/infrastructure/database/models/illustration.py:15` `Illustration` — テーブル `illustrations`。カラム: `id`(:18)、`book_id`(FK :19)、`illustration_type`(:20、既定 "cover")、`episode_number`(:21)、`character_id`(:22)、`model`(:23)、`safety_level`(:24)、`prompt`(:25 Text)、`image_url`(:26 NOT NULL)、`generation_time_ms`(:27)、`created_at`(:28)。インデックス :30-33
- リポジトリ: `src/infrastructure/repositories/illustration.py:14` `IllustrationRepository`(`create_illustration` :17-43、`list_illustrations` :45-52)
- 互換 shim: `src/backend/database/repositories/illustration.py:1-3`、モデル再エクスポート `src/backend/database/models.py:60`
- **テーブル作成は `0000_initial_migration.py:29` の `Base.metadata.create_all` 依存(illustrations 固有の revision なし)**
- 取得 API: `routers/illustrations.py:227-279` `GET /images/{book_id}/{scene_name}` — `image_url != ""` の行を新順取得し、**`scene_name` が `prompt` に部分一致するか**で照合、無ければ最新フォールバック(:250-270)。未生成は 200+`found:false`

### 1.6 フロント(既存表示箇所)

- API クライアント: `frontend/src/api/illustrations.ts:24` `fetchSceneIllustration`(→ `/images/{bookId}/{sceneName}`)
- **表示中の UI は Studio のみ**: `frontend/src/components/studio/StudioWorkspace.tsx:290-311`(シーン画像解決)、`:774-776`(`MultimediaPreviewPanel` へ `imageUrl`)、`frontend/src/components/editor/MultimediaPreviewPanel.tsx:56-66`(`<img>` 描画)
- シーン名の供給源: 本文埋め込みマーカー `[[img:xxx]]` — `frontend/src/utils/multimedia.ts:5/:12/:36`、`frontend/src/components/editor/Editor.tsx:25/:211/:280`
- ルーティング: `src/backend/wiring.py:124` `RouterMount(illustrations.router)`(**prefix 無し=ルート直下マウント**)。vite プロキシ `/generate /batch /status /images /yonkoma`(`frontend/vite.config.ts:29-33`)

---

## 2. ポートのみ / スタブ / 未配線のもの

| 項目 | 場所 | 状態 |
|---|---|---|
| **挿絵の生成・保存経路が実質存在しない** | 複数箇所(下記 3 行) | (a) 標準生成パイプラインは `ctx.artifacts["request"]` をセットする箇所が src 内にゼロ → `IllustrationAgent.execute` は常に no-op(`illustration_agent.py:62-75`)。(b) `POST /generate` は DI コンテナが `repo` を注入しない(`src/core/container/app.py:171-174`)ため `_persist:447` が常にスキップ=**DB 非保存**。(c) `POST /batch`(Huey)は `IllustrationWorkflow.repo=None`(`app.py:201-204` + `base_workflow.py:84-86`)で `assert self.repo is not None`(`illustration_workflow.py:76`)に失敗する**推測** |
| **`multimedia_service` の illustrations フォールバック SQL が死にコード** | `src/backend/multimedia_service.py:350-356` | `file_path/chapter_number/caption/position` 列を要求するが ORM に存在しない(`models/illustration.py:21-27`)→ 常に例外握りつぶし(**推測**) |
| **router は prefix 無しでルート直下マウント** | `src/backend/wiring.py:124`、`routers/illustrations.py:27` | 実パスは `/generate` `/images/...` 等。router 内 docstring の `GET /api/illustrations/status/...`(`:198`)は誤記 |
| `IIllustrationService` ポート | `src/application/ports/illustration_service.py:14` | **infrastructure アダプタが存在しない**(実装クラス 0 件。事実上の実装は 4 層外のレガシー構成でポートと非互換) |
| 3 つのユースケース | `src/application/use_cases/illustration_use_cases.py:18/:36/:53` | 定義+export のみで**どこからもインスタンス化されない(未配線)** |
| `EasyModeIllustrationSkill` | `src/agents/skills/v1/easy_mode_illustration.py:15` | スタブ(常に空リスト)。参照元 `config/manifests/easy_mode.yaml` 自体がロードされていない(**推測**: 遺物) |
| `UnifiedIllustrationGenerator` | `clients/base.py:5` の docstring のみ | 実体なし |
| `GeminiImageClient` | `clients/gemini_image_client.py:31` | src 内に呼び出し元なし(未配線・テストのみ) |
| `get_image_adapter` / `get_image_client` ファクトリ | `factory.py:24` / `:58` | src 本体からは未使用(テストのみ)。**本線 `ImageService` はファクトリを経由しない** |
| `IllustrationModal` | `frontend/src/components/illustrations/IllustrationModal.tsx:22` | **import している箇所が無い未配線 UI** |
| エディタの「画像生成」ボタン | `frontend/src/components/editor/InlineAiToolbar.tsx:96-111` | **モック**(setTimeout→マーカー挿入のみ、API 呼び出し無し)。`MultimediaPreviewPanel` の `onGenerateImage` も Studio から未接続で非表示 |
| `multimedia_artifacts` の illustration 書き込み | `src/backend/multimedia_service.py:303-423` | **読み取り専用**。`asset_type='illustration'` を書き込む経路が存在しない |
| `/static` 配信 | `image_service.py:121-132` が返す `/static/illustrations/img_x.png` | **`StaticFiles` マウントが src 全体に存在せず、vite プロキシにも無い**→ブラウザからの `<img>` は 404 の可能性(要確認) |
| Play モード | `frontend/src/pages/PlayModePage.tsx` | **illustration 参照ゼロ**。`BranchPlayNode` に画像/scene フィールド無し |
| `IllustrationRepository` の取得 API | `src/infrastructure/repositories/illustration.py:14` | `create_illustration`/`list_illustrations`(book+type)のみ。**episode_number や scene での取得 API が無い**(ルーターが prompt 部分一致で代用) |
| alembic | `src/backend/alembic/versions/*` | illustrations を扱う revision なし(create_all 依存) |
| `docs/STATUS.md` | — | 本調査で追記済み(2026-11-24) |

---

## 3. Play モードに挿絵を表示するためのギャップリスト(優先度順)

1. **P0 — 挿絵が生成・保存される経路がほぼ無い**: パイプラインは常に no-op、`/generate` は DB 非保存、`/batch` は assert 失敗の推測(§2 参照)。実画像が DB に積み上がるのは yonkoma 経路と CLI(`illustration_cli.py:69` → `generate_episode_scenes`)のみ。**まず「保存される経路」を直すことが前提**
2. **P0 — ノード⇔挿絵の紐付けが無い**: `BranchPlayNode`(`types/branches.ts:187-196`)は `episode_num`/`content` のみ。`illustrations` テーブルに `branch_id`/`node_id` カラムは無い。既存照合 API は「prompt 部分一致+最新フォールバック」で Play モードには不適。**`episode_number` ベースの決定的クエリ(新規エンドポイント or 既存 API 拡張)が最小構成**
3. **P0 — フロント表示面**: `PlayModePage.tsx` に画像取得/描画が無い。`found:false` 時のフォールバック表示(ロードマップ受入基準「挿絵なしでもフォールバック動作」)を実装する必要
4. **P1 — 画像の HTTP 配信**: `/static/illustrations/...` がバックエンドでマウントされず vite プロキシにも無い。`StaticFiles` マウント or バイト配信 API(`multimedia.py:461` の `/files/{filename}` パターン流用候補)が必要
5. **P1 — 生成トリガ**: 標準パイプラインでは easy_mode が `enable_illustration=False`、「生成済み小説に挿絵が無い」のがデフォルト。既存 `POST /batch` + Huey を Play 準備フローから叩く配線が候補(repo 注入の修正が前提)
6. **P2 — アーキテクチャ整合**: `IIllustrationService` のアダプタ不在。既存 `IllustrationAgent`/`ImageService` を包むアダプタを置くか、既存経路(`AppContainer`)を直接使う判断(レイヤーチェック `scripts/check_layer_boundaries.py` に注意)
7. **P2 — クレジット**: `/generate` 5cr、`/yonkoma` 20cr。Play 準備での一括生成は課金 UX 設計が別途必要
8. **P2 — multimedia 側の列不一致解消**: EPUB/asset_pack で挿絵を出すなら `multimedia_service.py:350-356` の SQL 修正が要る(商業 EPUB と Play モードで挿絵ソースを統一)

---

## 4. 外部 API 依存と必要な環境変数

| プロバイダ | 実装場所 | モデル | 必要なキー/変数 |
|---|---|---|---|
| **Google Imagen(本線)** | `image_service.py:54-92` | `imagen-4.0-fast/quality/ultra-generate-001` | `GEMINI_API_KEY` / `GOOGLE_GENAI_API_KEY`(`settings.py:280-283`、`get_gemini_api_key` :416-420、`.env.example:111`) |
| Gemini 画像(未配線) | `clients/gemini_image_client.py:31` | `gemini-3.1-flash-lite-image` | `GEMINI_API_KEY` 等。無キー時は mock PNG 自動退避 |
| DALL·E 3(未配線) | `adapters/dalle3_adapter.py:20` | dall-e-3 | `OPENAI_API_KEY`。※`IMAGE_PROVIDER=dalle3` 時の警告は `settings.DALL_E_API_KEY` を見るがファクトリ本体は `OPENAI_API_KEY` を見る(**不整合**) |
| fal.ai(未配線) | `adapters/fal_adapter.py:20` | `fal-ai/flux/schnell` 等 | `FAL_KEY` or `FAL_AI_API_KEY` |
| SD WebUI(未配線) | `sd_client.py:9` | — | `SD_WEBUI_URL`(既定 `http://localhost:7860`) |
| モック | 複数 | — | 不要。`IMAGE_PROVIDER` 既定 `mock`(`settings.py:360`) |

**設計上の注意**: `IMAGE_PROVIDER` は未配線の factory 系のみ参照し、**本線 `ImageService` は常に GenAI/Imagen**。プロバイダ選択機構が 2 重に存在する

---

## 5. 不明点・要確認事項(Phase 3 設計時に確認)

1. **`/static` 配信の実体**: src 内に `StaticFiles` マウント無し。prod の nginx(`docker-compose.prod.yml`)で配信されるのか、現状 404 なのか要確認(**推測含む**)
2. **`/batch` Huey 経路の実運用動作**: repo 未注入で `assert self.repo is not None` に落ちるはず(要ランタイム検証。テストはモック経由の可能性)
3. **`src/agents/skills/manifest.yaml` の active 配線状況**(未読。v1 IllustrationSkill は終端ノード)
4. **`ImageService.generate` の同期 SDK 呼び出し**(`models.generate_images` は同期)— イベントループブロックの可能性。Play 中のオンデマンド生成を考える場合のレイテンシ要確認(**推測**)
5. **alembic drift**: illustrations テーブルが create_all 依存(固有 revision 無し)
6. **本線クライアントの決定**: Imagen 直叩き(`ImageService`)と未配線の `GeminiImageClient` のどちらを Phase 3 の正にするか → **ADR 推奨**(併せて 3 系統のファクトリ/アダプタの整理も)
7. 同期 `/generate` がクレジット消費後にプロンプトしか返さないのは仕様か実装途上か(コード上は「画像生成は将来実装」コメント、`illustration_agent.py:29`/:120)
8. **`WritingService` への `illustration_agent` 注入**(`app.py:223`)は保持されるだけで呼ばれない(**推測**: 死に配線)
9. **R15/NSFW と挿絵の組み合わせ**: `ENABLE_NSFW=false` 既定と `safety_level` の関係は Play 表示時のフィルタ要件として要確認

---

## 6. Phase 3 実装計画への示唆

- **最初に「保存される経路」を直す**: DI への `repo` 注入(またはアダプタ実装)→ 実画像生成経路の接続 → 決定的クエリ API → Play 表示、の順が依存の自然な順序
- 最小価値経路は「**生成済み(または Studio/CLI で挿絵生成済み)の illustrations を、episode_number 決定的クエリで Play シーンに表示**」。生成側の新規実装よりも**表示配線**が先行価値になる
- 生成側を触るなら「ワークフローの話数生成を `run()`(プロンプトのみ)→ `generate_episode_scenes`(実画像)に差し替える」のが 1 行変更に近いが、**コスト・レイテンシ・フォールバック設計**が要る(失敗時も本編継続は既存方針 `pipeline_steps.py:535` と整合)
- 挿絵なしフォールバックは既存 UI パターン(`found:false` → 画像非表示)で自然に実現可能

---

## 改訂履歴

| 日付 | 版 | 内容 |
|:--|:--|:---|
| 2026-11-24 | 0.1 | 初版作成(調査完了・実装未着手) |
| 2026-11-25 | 0.2 | 二次精査の結果を反映(repo 未注入による永続化欠落、`/batch` assert、パイプライン no-op、multimedia SQL 列不一致、router prefix 誤記、取得 API 不在)。ギャップリストに「保存される経路の修復」を P0 追加 |
