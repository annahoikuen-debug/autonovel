/**
 * AutoNovel OpenAPI 自動生成 TypeScript 型定義
 * このファイルは scripts/generate_ts_types.py によって自動生成されています。
 * 手動での直接編集は行わないでください。
 */

export interface ABTestAutoPromoteRequest {
  skill_name: string;
  auto_promote?: boolean;
}

export interface ABTestRequest {
  skill_name: string;
  version_a: string;
  version_b: string;
  samples?: number;
}

export interface ABTestScheduleRequest {
  skill_name: string;
  version_a: string;
  version_b: string;
  interval_hours: number;
  min_samples?: number;
}

export interface AlertResponse {
  book_id: number;
  alerts: Record<string, unknown>[];
}

/** 世界観バイブル・過去章 Q&A リクエスト */
export interface AskBibleRequest {
  /** 作品ID */
  book_id?: number;
  /** 質問内容 */
  query: string;
  /** 現在の執筆中話数 */
  current_chapter?: number | null;
}

/** 世界観バイブル・過去章 Q&A レスポンス */
export interface AskBibleResponse {
  /** AI編集者からの回答 */
  answer: string;
  /** 回答の根拠となったグラフノード群 */
  evidence_nodes?: GraphEvidenceNode[];
  /** 関連キャラクター名一覧 */
  related_characters?: string[];
}

/** アシスト操作種別 */
export type AssistAction = "describe" | "show_dont_tell" | "rewrite" | "expand";

/** インラインAIアシストリクエスト */
export interface AssistRequest {
  /** 選択・編集対象の本文テキスト */
  text: string;
  /** 実行するアクション */
  action?: AssistAction;
  /** 五感拡張の種別（action=describe時） */
  sensory_type?: SensoryType | null;
  /** 書き換えトーン種別（action=rewrite時） */
  tone_type?: ToneType | null;
  /** 作品ジャンル */
  genre?: string;
  /** 選択箇所の直前の文脈 */
  context_before?: string;
  /** 選択箇所の直後の文脈 */
  context_after?: string;
  /** ユーザー独自の追加指示 */
  custom_instruction?: string;
}

/** インラインAIアシストレスポンス */
export interface AssistResponse {
  /** 元のテキスト */
  original_text: string;
  /** AIによって生成・拡張されたテキスト */
  result_text: string;
  /** 実行されたアクション */
  action: AssistAction;
  /** 変更内容の要約 */
  diff_summary?: string;
}

export interface AuditAggregateTestRequest {
  /** 対象書籍ID */
  book_id: number;
  /** 対象章番号 */
  chapter_number: number;
  /** 監査対象の原稿テキスト */
  draft_text: string;
  world_bible_snapshot?: Record<string, unknown>;
  style_dna?: Record<string, unknown>;
  plot_tree?: string;
  plot_summary?: string;
  illustration_prompts?: string;
  genre?: string;
  phase?: string;
}

export interface AuditAggregateTestResponse {
  overall: number;
  by_specialist: Record<string, number>;
  missing: string[];
  weights_used: Record<string, number>;
  lowest_dimension: string | null;
}

/** 二層ハイブリッド監査リクエスト */
export interface AuditFastHybridRequest {
  /** 監査対象のドラフト本文 */
  draft_text: string;
  /** 登場人物の設定・プロファイル */
  character_profiles?: string;
  /** プロット・構成情報 */
  plot_spec?: string;
}

export interface AuditModelRoutingRequest {
  auditor_name: string;
  new_model: string;
}

/** プラン監査リクエスト（configなし） */
export interface AuditPlanRequest {
  api_key: string;
  genre: string;
  keywords: string;
  trend_memo: string;
  sanctuary?: string;
  originality_score?: number;
  platform?: string;
}

/** バッチUPSERTリクエスト. */
export interface BatchUpsertRequest {
  nodes?: NodeUpsertRequest[];
  edges?: EdgeUpsertRequest[];
  /** 対象グラフ名 */
  graph_name?: string | null;
}

/** バッチUPSERTレスポンス. */
export interface BatchUpsertResponse {
  nodes_created: number;
  edges_created: number;
  errors?: string[];
}

/** 1つの展開バリエーションカード */
export interface BeatCard {
  /** カード識別ID (card_a, card_b, card_c) */
  card_id: string;
  /** 分岐タイプ */
  branch_type: BranchType;
  /** 展開タイトル */
  title: string;
  /** 展開のあらすじ・要約 */
  summary: string;
  /** 生成された次シーンの本文抜粋 (300-600文字) */
  content: string;
  /** 次のエピソードへの引き・クリフハンガー */
  hook_text?: string;
}

/** 感情ビートDTO（API用） */
export interface BeatDTO {
  beat_id?: string | null;
  episode: number;
  scene: number;
  source: string;
  target: string;
  emotion: string;
  delta: number;
  cause: string;
  confidence?: number;
  hidden?: boolean;
  metadata?: Record<string, unknown>;
}

/** 1話分のビート情報 */
export interface BeatItemSchema {
  /** 話数 */
  episode: number;
  /** エピソードタイトル */
  title: string;
  /** あらすじ・ビート内容 */
  outline: string;
  /** クリフハンガー種別 */
  cliffhanger_type: string;
  /** 五感フォーカスタグ */
  sensory_focus?: string[];
  /** 伏線メモ */
  foreshadowing_notes?: string;
}

export interface BeatSheetGenerateRequest {
  book_id?: number | null;
  title: string;
  synopsis: string;
  genre?: string;
  target_episodes?: number;
  pattern_key?: string;
  length_key?: string;
  market_key?: string;
}

export interface BeatSheetItem {
  ep_num: number;
  phase: string;
  mission: string;
  tension_target: number;
  visual_scene_focus: string;
}

export interface BeatSheetResponse {
  items: BeatSheetItem[];
}

/** 新規作品作成リクエスト */
export interface BookCreateRequest {
  /** 作品タイトル */
  title: string;
  /** ジャンル */
  genre: string;
  /** コンセプト */
  concept?: string;
  /** あらすじ */
  synopsis?: string;
  /** 目標話数 */
  target_eps?: number;
}

/** BookScore 履歴の1エントリ */
export interface BookScoreHistoryItem {
  chapter_number: number;
  overall_score: number;
  structure_score: number;
  coherency_score: number;
  factual_grounding_score: number;
  visual_textual_synergy_score: number;
  reader_experience_score: number;
  evaluated_at: string;
  evaluator_version?: string | null;
}

/** BookScore 時系列履歴レスポンス */
export interface BookScoreHistoryResponse {
  success?: boolean;
  error_message?: string | null;
  error_type?: string | null;
  book_id: number;
  history?: BookScoreHistoryItem[];
  /** ジャンル平均ベンチマーク */
  benchmarks?: Record<string, number> | null;
}

export interface BookScoreResponse {
  book_id: number;
  chapter_number: number;
  overall_score: number;
  structure_score: number;
  coherency_score: number;
  factual_grounding_score: number;
  visual_textual_synergy_score: number;
  reader_experience_score: number;
  evaluated_at?: string | null;
  trend_3ch?: Record<string, unknown> | null;
}

/** 新規ブランチ作成用リクエスト. */
export interface BranchDbModelCreate {
  book_id: number;
  name: string;
  parent_id?: number | null;
  fork_ep_num?: number | null;
  graph_json?: Record<string, unknown> | null;
}

/** フォーク（分岐作成）リクエスト.

``parent_id`` は省略可。省略時は「親なしの新規ブランチ」として作られる。
編集画面から分岐を作る場合、正しい親ブランチを特定できない状態で
既定値（従来は 1 固定）が送られ、無関係なブランチの子として作られていた。 */
export interface BranchForkRequest {
  parent_id?: number | null;
  name: string;
  fork_ep_num?: number;
}

/** ブランチ配下の IF グラフ JSON レスポンス. */
export interface BranchGraphResponse {
  branch_id: number;
  graph?: Record<string, unknown>;
}

/** マージ確定コミットリクエスト (Step 49). */
export interface BranchMergeCommitRequest {
  source_branch_id: number;
  target_branch_id: number;
  merge_ep_num: number;
  resolved_chapters: ResolvedChapterPayload[];
  commit_message?: string;
}

/** マージ確定コミッドレスポンス (Step 49). */
export interface BranchMergeCommitResponse {
  success: boolean;
  target_branch_id: number;
  updated_chapters_count: number;
  committed_at: string;
}

/** マージ（合流）リクエスト.

source_branch_id の plot を merge_ep_num で target_branch_id に合流させる。
既存 IF グラフに MERGE ノードを追加する。 */
export interface BranchMergeRequest {
  source_branch_id: number;
  target_branch_id: number;
  merge_ep_num: number;
  name?: string | null;
}

/** 選択肢実行リクエスト. */
export interface BranchPlayChooseRequest {
  choice_id: string;
}

/** セッション終了リクエスト. */
export interface BranchPlayEndRequest {
  status?: string;
}

/** プレイスルー記録レスポンス. */
export interface BranchPlayPlaythroughResponse {
  session_id: string;
  book_id: number;
  branch_id: number;
  history?: unknown[];
  flags?: Record<string, unknown>;
  variables?: Record<string, unknown>;
  final_ending?: string | null;
  saved_at?: string | null;
}

/** セッション開始リクエスト. */
export interface BranchPlayRequest {
  book_id: number;
  branch_id: number;
}

/** セッション作成 / 終了レスポンス. */
export interface BranchPlaySessionResponse {
  session_id: string;
  book_id: number;
  branch_id: number;
  current_node_id?: string | null;
  status?: string;
  updated_at?: string | null;
}

/** 現セッション状態. */
export interface BranchPlayStateResponse {
  session_id: string;
  book_id: number;
  branch_id: number;
  current_node?: Record<string, unknown>;
  current_node_id?: string | null;
  context?: Record<string, unknown>;
  available_choices?: Record<string, unknown>[];
  save_points_count?: number;
  status?: string;
  updated_at?: string | null;
}

/** 単一ブランチのレスポンス. */
export interface BranchResponse {
  id: number;
  book_id: number;
  name: string | null;
  parent_id?: number | null;
  fork_ep_num?: number | null;
  created_at?: string | null;
}

/** 展開分岐タイプ */
export type BranchType = "royal" | "twist" | "psychology";

/** 文章の音律・ケイデンス統計情報 */
export interface CadenceStats {
  total_sentences: number;
  repeated_endings_fixed: number;
  avg_sentence_length: number;
  paragraph_count: number;
}

/** キャッチコピー生成リクエスト */
export interface CatchphraseGenerateRequest {
  api_key: string;
  config?: Record<string, unknown>;
  project_settings: string;
  /** 生成する候補数 */
  candidate_count?: number;
}

export interface ChapterDeleteResponse {
  book_id: number;
  branch_id: number;
  ep_num: number;
  deleted: boolean;
}

/** 章インポートリクエスト */
export interface ChapterImportRequest {
  api_key: string;
  book_id: number;
  ep_num: number;
  import_text: string;
  do_refine: boolean;
}

export interface ChapterSchema {
  created_at?: string;
  updated_at?: string;
  id: number;
  book_id: number;
  episode_number: number;
  title: string;
  content?: string;
  digest?: string;
  word_count?: number;
  status?: string;
  scene_beats?: SceneBeat[];
  cliffhanger?: CliffhangerDef | null;
  emotional_hook?: EmotionalHookSpec | null;
}

/** 1 話を保存/更新するリクエスト。

``ep_num`` はパスで受け取るため、通常は body に入れない。 */
export interface ChapterUpsertRequest {
  title?: string;
  content?: string;
  summary?: string;
  branch_id?: number;
}

export interface ChapterUpsertResponse {
  book_id: number;
  branch_id: number;
  ep_num: number;
  saved: boolean;
  created?: boolean;
}

/** キャラクター設定パラメータ。 */
export interface CharacterParams {
  name?: string;
  personality?: string;
  ability?: string;
  genre?: string;
  /** 適用する文体スタイルID */
  style_id?: string | null;
}

export interface CheckResponse {
  status: HealthStatus;
  latency_ms?: number | null;
  details?: string;
  error?: string;
}

export interface CircuitResetRequest {
  provider_name?: string | null;
}

/** Web小説の離脱を防ぐ引き・クリフハンガー3分類（v4より完全継承） */
export interface CliffhangerDef {
  /** 引きの分類（新たな危機 / 衝撃の真実 / 静かな伏線） */
  type?: "New Crisis" | "Shocking Truth" | "Quiet Foreshadowing";
  /** クリフハンガーの具体的な描写・引きのフック */
  description: string;
}

export interface CommentRequest {
  author_name: string;
  content: string;
  anchor_text?: string;
  parent_id?: number | null;
}

/** 商用化パイプライン設定 */
export interface CommercialConfig {
  series_config?: Record<string, unknown>;
  samples?: Record<string, unknown>[];
  platforms?: string[];
  do_publish?: boolean;
  credentials?: Record<string, Record<string, unknown>> | null;
}

export interface CompareRequest {
  prompt_key: string;
  texts: string[];
  weights?: Record<string, number> | null;
}

export interface ConfigResponse {
  enabled: boolean;
  categories: string[];
}

export interface ConflictItemSchema {
  /** カテゴリ (rhythm, dialogue, cliche, hook, character) */
  category: string;
  /** 重要度 (critical, high, medium, low) */
  severity: string;
  /** 指摘タイトル */
  title: string;
  /** 詳細説明 */
  description: string;
  field_path?: string | null;
  current_value?: string | null;
  suggested_value?: string | null;
  evidence_past?: string;
  evidence_current?: string;
  constraint_for_next?: string;
  confidence?: number;
}

/** リアルタイム設定矛盾診断リクエスト */
export interface ConsistencyAuditRequest {
  /** 作品ID */
  book_id?: number;
  /** 診断対象の本文 */
  content: string;
  /** 現在の話数 */
  current_chapter?: number;
}

/** リアルタイム設定矛盾診断レスポンス */
export interface ConsistencyAuditResponse {
  /** 矛盾が検出されたかどうか */
  has_issues?: boolean;
  /** 検出された矛盾リスト */
  issues?: ConsistencyIssue[];
  /** 診断の信頼度 (0.0 - 1.0) */
  confidence_score?: number;
}

/** 設定矛盾・不整合の検出項目 */
export interface ConsistencyIssue {
  /** 安定した問題 ID。フロントの配列 index ではなく book_id / 章 / issue_type / conflicting_text から決定的に生成する */
  id?: string;
  /** 矛盾の種類 (attribute, relationship, timeline, death_status, location) */
  issue_type: string;
  /** 重要度 (error, warning, info) */
  severity?: string;
  /** 矛盾内容の解説 */
  description: string;
  /** 本文中の該当箇所 */
  conflicting_text?: string;
  /** 修正の提案 */
  suggested_fix?: string;
}

/** 整形リクエスト。 */
export interface CopyFormatRequest {
  title: string;
  body: string;
  foreword?: string;
  afterword?: string;
  platform?: string;
  indent_enabled?: boolean;
}

/** 整形レスポンス。 */
export interface CopyFormatResponse {
  title: string;
  foreword: string;
  body: string;
  afterword: string;
  total_characters: number;
  platform: string;
}

export interface CorrectRequest {
  text: string;
  max_loops?: number;
  score_threshold?: number;
}

export interface CorrectResponse {
  original_text: string;
  corrected_text: string;
  final_score: number;
  iterations: number;
  converged: boolean;
  history: Record<string, unknown>[];
}

/** 任意のCypherクエリ実行リクエスト. */
export interface CypherQueryRequest {
  /** 実行するCypherクエリ */
  query: string;
  /** 対象グラフ名 */
  graph_name?: string | null;
  /** クエリパラメータ */
  parameters?: Record<string, unknown> | null;
  /** 戻り値カラム定義 */
  column_definition?: string;
}

/** Cypherクエリ実行レスポンス. */
export interface CypherQueryResponse {
  records: Record<string, unknown>[];
  summary: Record<string, unknown>;
  execution_time_ms: number;
}

export interface DetectRequest {
  text: string;
}

export interface DetectResponse {
  total_score: number;
  category_scores: Record<string, number>;
  total_violations: number;
  violations: Record<string, unknown>[];
}

export interface DigestRequest {
  /** 元のガチャリクエストID */
  request_id: string;
  /** ユーザーが選択した企画ID */
  selected_plan_id: string;
}

export interface DigestResponse {
  /** 新規作成された作品ID */
  book_id: string;
  /** タイトル */
  title?: string;
  /** 全体あらすじ */
  synopsis?: string;
  /** 第1話の本文テキスト */
  episode_1_text?: string;
  /** クライマックス（見せ場）のプレビューテキスト */
  climax_preview_text?: string;
  /** 生成ステータス */
  status?: DigestStatus;
}

export type DigestStatus = "processing" | "completed" | "failed";

/** 文体蒸留リクエスト */
export interface DistillRequest {
  /** お手本となる小説サンプルテキスト */
  sample_text: string;
  /** スタイル名のヒント */
  name_hint?: string | null;
}

/** 文体蒸留レスポンス */
export interface DistillResponse {
  success?: boolean;
  profile: StyleProfile;
}

/** かんたんモード生成リクエスト入力。 */
export interface EasyModeInput {
  chapter_history?: string[];
  current_chapter?: string;
  character_params?: CharacterParams;
  content_length_limit?: number;
  /** 目標話数 (1〜50) */
  target_episodes?: number;
  /** カスタムStyleProfileの辞書 */
  style_override?: Record<string, unknown> | null;
  /** オプトインのLLM設定 */
  llm_config?: LLMConfigOverride | null;
  /** 既存作品に追加・更新する場合の作品ID。未指定時は新規採番して保存 */
  book_id?: number | null;
  /** 開始話数 */
  start_ep?: number;
  /** 終了話数（未指定時はtarget_episodesまで） */
  end_ep?: number | null;
}

/** eBook エクスポートリクエスト (README 互換: POST /export/ebook)。 */
export interface EbookExportRequest {
  book_id: number;
  formats?: string[];
  author?: string;
  publisher?: string;
}

export interface EbookExportResponse {
  asset_id: number;
  files?: string[];
  formats?: string[];
}

/** エッジUPSERTリクエスト. */
export interface EdgeUpsertRequest {
  /** 始点ノードラベル */
  source_label: string;
  /** 始点ノード名 */
  source_name: string;
  /** 終点ノードラベル */
  target_label: string;
  /** 終点ノード名 */
  target_name: string;
  /** 関係タイプ */
  relation_type: string;
  /** 関係プロパティ */
  properties?: Record<string, unknown> | null;
  /** 対象グラフ名 */
  graph_name?: string | null;
}

/** 読者の感情を揺さぶりカタルシスを生む感情フック（v4より完全継承） */
export interface EmotionalHookSpec {
  /** カタルシス / 共感 / 緊張感 / ギャップ萌え */
  hook_type?: string;
  /** フックを仕掛けるシーン */
  target_scene?: string;
  /** 読者への最大の訴求ポイント */
  appeal_point?: string;
}

export interface EnrichmentMetricsSnapshot {
  enrichment_duration_seconds?: number;
  trivia_insertions_total?: number;
  citations_added_total?: number;
  sensory_expansions_total?: number;
  multimedia_scenarios_total?: number;
  token_usage_avg?: number;
  errors_total?: number;
}

export interface EnrichmentStatusResponse {
  enabled: boolean;
  config: Record<string, unknown>;
  feature_flags: Record<string, boolean>;
}

export interface EnrichmentTestRequest {
  /** エンリッチメント対象の原稿テキスト */
  draft_text: string;
  /** 執筆コンテキスト */
  writing_context?: Record<string, unknown>;
  /** 書籍ID（省略可） */
  book_id?: number | null;
}

export interface EnrichmentTestResponse {
  enriched_text: string;
  enrichment_metadata: Record<string, unknown>;
  elapsed_ms: number;
}

/** エピソード候補生成リクエスト */
export interface EpisodeGenerateCandidatesRequest {
  api_key: string;
  config?: Record<string, unknown>;
  book_id: number;
  write_from: number;
  write_to: number;
  passion: number;
  word_count: number;
  do_refine: boolean;
  env_state?: Record<string, string>;
  pipeline_mode?: boolean;
}

/** エピソード生成リクエスト */
export interface EpisodeGenerateRequest {
  api_key: string;
  config?: Record<string, unknown>;
  book_id: number;
  write_from: number;
  write_to: number;
  passion: number;
  word_count: number;
  do_refine: boolean;
  env_state?: Record<string, string>;
  pipeline_mode?: boolean;
}

/** エピソード一覧取得レスポンス */
export interface EpisodeListResponse {
  success?: boolean;
  error_message?: string | null;
  error_type?: string | null;
  episodes?: Record<string, unknown>[];
}

/** 商業ビート生成リクエスト */
export interface ExpandBeatsRequest {
  /** APIキー（省略可） */
  api_key?: string;
  config?: Record<string, unknown>;
  /** 作品タイトル */
  title: string;
  /** ジャンル */
  genre: string;
  /** あらすじ */
  synopsis?: string;
  /** 目標話数 */
  target_chapters?: number;
  /** チート度 (1-5) */
  cheat_scale?: number;
  /** 成長曲線モデル */
  growth_curve?: string;
  /** システム支援度 (0-100) */
  system_assist?: number;
  /** 代償・リスク過酷度 (1-5) */
  cost_severity?: number;
  /** 構造パターン (空なら exile_rise) */
  pattern_key?: string;
  /** 長さ階層 (空なら web_volume) */
  length_key?: string;
  /** 媒体規格 (空なら web) */
  market_key?: string;
  /** 確定済みビート一覧（wizard-save時） */
  beats?: BeatItemSchema[];
}

/** エクスポート用即時反映ペイロード */
export interface ExportRequestPayload {
  /** タイトル */
  title?: string;
  /** ジャンル */
  genre?: string;
  /** 画面上の最新本文 */
  current_text?: string;
  /** 主人公設定 */
  character?: Record<string, unknown>;
  /** プロット概要リスト */
  plots?: Record<string, unknown>[];
}

export interface FixRequest {
  api_key: string;
  ep_num: number;
}

export interface FormatRequest {
  /** 投稿先プラットフォーム */
  platform?: TargetPlatform;
  /** 話・章のタイトル */
  chapter_title: string;
  /** 元の生成テキスト（マーカーやルビ含む） */
  raw_text: string;
  /** AI利用役割 */
  ai_role?: string;
}

export interface FormattedChapterPayload {
  platform: TargetPlatform;
  /** 章・話のタイトル */
  chapter_title: string;
  /** 前書き（前話のおさらい等） */
  foreword?: string;
  /** プラットフォーム記法適用済み本文 */
  main_content: string;
  /** 後書き（AI利用明記、次回予告） */
  afterword?: string;
  /** 本文・前書き・後書き総文字数または本文文字数 */
  char_count?: number;
  /** AI利用開示文言 */
  ai_disclosure_statement?: string;
  /** 規約やフォーマットに関する警告一覧 */
  validation_warnings?: string[];
}

export interface GachaPlan {
  /** 企画の一意のID */
  plan_id: string;
  /** 企画のタイプ */
  plan_type: GachaPlanType;
  /** タイトル案 */
  title: string;
  /** 1行あらすじ */
  logline: string;
  /** 主人公の簡単な説明 */
  protagonist_summary: string;
  /** この案の最大の魅力（アピールポイント） */
  charm_point: string;
  /** ブラインドピアレビューによる独立監査スコア */
  audit_score?: number | null;
  /** 独立講評・フィードバック */
  critique?: Record<string, unknown> | null;
  /** 推奨理由 */
  recommendation_reason?: string | null;
  /** 推奨案フラグ */
  is_recommended?: boolean;
}

export type GachaPlanType = "royal" | "curveball" | "dark";

export interface GachaRequest {
  /** 対象ジャンル */
  genre: string;
  /** キーワードリスト */
  keywords: string[];
  /** 生成の温度感 */
  temperature?: number;
  /** 既存レビューセッションID（再開用） */
  review_session_id?: string | null;
}

export interface GachaResponse {
  /** ガチャリクエスト全体のID */
  request_id: string;
  /** 3案の企画リスト (王道、変化球、ダーク) */
  plans: GachaPlan[];
  /** 最も推奨される案のID */
  recommended_plan_id?: string | null;
  /** レビューセッションID */
  review_session_id?: string | null;
}

/** かんたんモード生成レスポンス。 */
export interface GenerationResponse {
  task_id?: string | null;
  output?: string;
  completion_time_ms?: number;
  error?: string;
  suggestions?: string[];
}

/** 回答の根拠となったナレッジグラフのノード・事実情報 */
export interface GraphEvidenceNode {
  /** ノードIDまたはエンティティ名 */
  id: string;
  /** ノードラベル (Character, Location, Item, Event) */
  label?: string;
  /** ノード属性情報 */
  properties?: Record<string, unknown>;
  /** 出展情報 (例: 第1章, 世界観バイブル) */
  source_reference?: string;
}

/** グラフ検索リクエスト. */
export interface GraphSearchRequest {
  /** 起点ノード名 */
  node_name: string;
  /** 最大ホップ数 */
  max_depth?: number;
  /** フィルタする関係タイプ */
  relationship_types?: string[] | null;
  /** 方向 */
  direction?: string;
  /** 最大取得件数 */
  limit?: number;
  /** 対象グラフ名 */
  graph_name?: string | null;
}

/** グラフ統計レスポンス. */
export interface GraphStatsResponse {
  node_count: number;
  edge_count: number;
  labels: string[];
  relationship_types: string[];
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

export interface HealthResponse {
  status: HealthStatus;
  version?: string;
  timestamp: string;
  checks: Record<string, CheckResponse>;
}

export type HealthStatus = "ok" | "degraded" | "error" | "not_configured";

/** ハイブリッド検索リクエスト. */
export interface HybridSearchRequest {
  /** 検索クエリ */
  query: string;
  /** グラフ探索の起点エンティティ */
  core_entities?: string[] | null;
  /** 返却件数 */
  top_k?: number;
  /** ベクトル検索の重み */
  alpha?: number;
  /** グラフ検索の重み */
  beta?: number;
  /** 全文検索の重み */
  gamma?: number;
  /** スコープする書籍ID。検索はセッション全体（=全テナント）にまたがるため、通常利用では作品所有権の検証に必要なため指定が必須となる */
  book_id?: number | null;
}

/** 単一挿絵生成リクエスト (`POST /generate`)。 */
export interface IllustrationGenerateRequest {
  /** 対象 Book ID */
  book_id: number;
  /** 挿絵種別 (scene/character/yonkoma 等) */
  illustration_type: string;
  /** 話数 */
  episode_number?: number | null;
  /** 生成モデル (fast/quality/ultra/auto) */
  model?: string;
  /** R15 表現を許可するか */
  enable_r15?: boolean;
}

/** オプトインでフロントエンドから渡されるLLM設定。 */
export interface LLMConfigOverride {
  /** gemini / openai / mock */
  provider?: string | null;
  /** カスタムAPIキー */
  api_key?: string | null;
  /** 全体既定モデル名 (例: gemini-2.5-flash, gpt-4o-mini) */
  model_name?: string | null;
  /** OpenAI互換 Base URL */
  base_url?: string | null;
  /** プロット・構成用モデル (例: gemini-2.5-flash) */
  model_planning?: string | null;
  /** 本文執筆用モデル (例: gpt-4o, claude-3-5-sonnet) */
  model_writing?: string | null;
  /** 校正・監査用モデル (例: gemini-2.5-flash) */
  model_audit?: string | null;
  /** ベクトル検索・Embedding用モデル (例: text-embedding-3-small) */
  model_embedding?: string | null;
}

/** ログアウト時に併せて失効させるリフレッシュトークン (任意)。 */
export interface LogoutRequest {
  refresh_token?: string | null;
}

/** マーケティングエクスポート (POST) リクエスト */
export interface MarketingExportRequest {
  api_key: string;
}

/** マーケティング生成リクエスト */
export interface MarketingGenerateRequest {
  api_key: string;
  book_id: number;
  latest_ep: number;
}

export interface MemberRequest {
  user_name: string;
  role?: string;
}

/** 比喩表現の出現頻度と傾向 */
export interface MetaphorFrequency {
  /** 1000文字あたりの比喩数 */
  per_1000_chars?: number;
  /** 五感比喩の比率 */
  types?: Record<string, number>;
  /** 比喩表現の特徴解説 */
  description?: string;
}

/** Next Beats 3バリエーション生成リクエスト */
export interface NextBeatsRequest {
  /** 作品ID */
  book_id?: number;
  /** 執筆済みの直前本文 */
  current_text: string;
  /** ジャンル */
  genre?: string;
  /** 主人公や登場人物の現在の状況 */
  character_context?: string;
  /** 生成の多様性パラメータ */
  temperature?: number;
}

/** Next Beats 3バリエーション生成レスポンス */
export interface NextBeatsResponse {
  /** 3つの展開カード */
  beats?: BeatCard[];
  /** 参照した直前本文の末尾抜粋 */
  original_tail?: string;
}

/** ノードUPSERTリクエスト. */
export interface NodeUpsertRequest {
  /** ノードラベル */
  label: string;
  /** ノード名（ユニークキー） */
  name: string;
  /** 追加プロパティ */
  properties?: Record<string, unknown> | null;
  /** 対象グラフ名 */
  graph_name?: string | null;
}

/** 制作レポート取得レスポンス */
export interface NovelReportResponse {
  success?: boolean;
  error_message?: string | null;
  error_type?: string | null;
  /** レポートデータ */
  report?: Record<string, unknown> | null;
}

/** 作品ステータス取得レスポンス */
export interface NovelStatusResponse {
  success?: boolean;
  error_message?: string | null;
  error_type?: string | null;
  project_id: number;
  status: string;
  current_episode: number;
  total_episodes: number;
  progress_percent: number;
  message: string;
  completed_episodes?: number[];
}

/** オーケストレーション版生成リクエスト。 */
export interface OrchestratedGenerateRequest {
  /** 作品ID */
  book_id?: number;
  /** ブランチID */
  branch_id?: number;
  /** エピソード番号 */
  ep_num?: number;
  /** 作品タイトル */
  title: string;
  /** あらすじ */
  synopsis?: string;
  /** 目標総話数 */
  target_eps?: number;
  /** コンセプト */
  concept?: string;
  /** ジャンル */
  genre?: string;
  /** キーワード */
  keywords?: string;
  /** 目標文字数 */
  target_word_count?: number;
  /** 文体タグ */
  style_tag?: string | null;
  /** LLM設定 */
  llm_config?: Record<string, unknown> | null;
}

/** 生成起動レスポンス。 */
export interface OrchestratedGenerateResponse {
  task_id: string;
  status: string;
  message: string;
}

/** PDCAサイクル実行結果のスナップショット */
export interface PDCACycleSnapshot {
  book_id: number;
  chapter_number: number;
  cycle_number: number;
  initial_score: number;
  final_score: number;
  score_delta: number;
  improved_percentage: number;
  lowest_dimension: string;
  directives?: WritingDirectiveSchema[];
  history?: PDCAHistoryItem[];
  converged: boolean;
  created_at?: string;
}

/** PDCAサイクル内の一ステップ履歴 */
export interface PDCAHistoryItem {
  cycle: number;
  draft_chars: number;
  score: number;
  scores_by_specialist?: Record<string, number>;
  calibrated_scores?: Record<string, number>;
  lowest_dimension?: string | null;
  directives_count: number;
  delta: number;
}

export interface PDCAReportResponse {
  book_id: number;
  plan: Record<string, unknown>;
  do: Record<string, unknown>;
  check: Record<string, unknown>;
  act: Record<string, unknown>;
}

export interface ParagraphPatchRequest {
  paragraph_index: number;
  directive: string;
}

/** アノテーション永続化リクエスト */
export interface PersistRequest {
  book_id: number;
  episode: number;
  beats: BeatDTO[];
}

/** 永続化レスポンス */
export interface PersistResponse {
  persisted: number;
  errors?: string[];
}

/** パイプラインバッチ処理リクエスト. */
export interface PipelineBatchRequest {
  chapters: PipelineProcessRequest[];
  /** エラー時に継続 */
  continue_on_error?: boolean;
}

/** パイプライン処理リクエスト. */
export interface PipelineProcessRequest {
  /** チャプターID */
  chapter_id: number;
  /** チャプターテキスト */
  chapter_text: string;
  /** 冪等性キー */
  idempotency_key?: string | null;
}

/** 企画生成リクエスト */
export interface PlanGenerationRequest {
  api_key: string;
  config?: Record<string, unknown>;
  params: Record<string, unknown>;
}

/** プロット候補展開リクエスト */
export interface PlotExpandCandidatesRequest {
  api_key: string;
  config?: Record<string, unknown>;
  book_id: number;
  gen_from: number;
  gen_to: number;
}

/** プロット展開リクエスト */
export interface PlotExpandRequest {
  api_key: string;
  config?: Record<string, unknown>;
  book_id: number;
  gen_from: number;
  gen_to: number;
}

/** プロット再構築リクエスト */
export interface PlotRebuildRequest {
  api_key: string;
  config?: Record<string, unknown>;
  params: Record<string, unknown>;
}

export interface ProcessRequest {
  /** Dialogue text to process */
  text: string;
  /** rule, template, token, hybrid, off */
  mode?: string;
  context?: SubtextContext | null;
  seed?: number | null;
}

export interface ProcessResponse {
  original: string;
  processed: string;
  mode: string;
}

/** 作品全話生成リクエスト */
export interface ProduceNovelRequest {
  /** 作品タイトル */
  title: string;
  /** ジャンル */
  genre: string;
  /** あらすじ */
  synopsis?: string;
  /** キーワード */
  keywords?: string[];
  /** 目標話数 */
  target_episodes?: number;
  /** 1話目標文字数 */
  target_word_count?: number;
  /** スタイルキー */
  style_key?: string;
  /** エンジンキー */
  engine_key?: string;
}

/** 作品生成レスポンス */
export interface ProduceNovelResponse {
  success?: boolean;
  error_message?: string | null;
  error_type?: string | null;
  /** プロジェクトID */
  project_id: number;
  /** ステータス */
  status?: string;
  /** メッセージ */
  message?: string;
  /** 推定トークン使用量 */
  token_usage_estimate?: Record<string, number> | null;
}

export interface ProjectSchema {
  created_at?: string;
  updated_at?: string;
  id: number;
  name: string;
  description?: string;
  books?: src__domain__schemas__project__BookSchema[];
}

export interface PromotionEligibilityResponse {
  book_id: number;
  eligible: boolean;
  avg_score: number;
  trend_slope: number;
  chapters_evaluated: number;
  reason?: string | null;
}

export interface PromotionRequest {
  /** 対象の作品ID */
  book_id: string;
}

export interface PromotionResponse {
  /** 昇格処理の成功有無 */
  success: boolean;
  /** フロントエンドが遷移すべき上級者モードのURLパス */
  redirect_url: string;
  /** 引き継ぎ用の状態トークン */
  state_token: string;
}

export interface PublicationScheduleCreate {
  book_id: number;
  platform: string;
  episode_range: unknown[];
  scheduled_at: string;
  credentials_override?: Record<string, unknown> | null;
}

export interface PublicationScheduleResponse {
  id: number;
  book_id: number;
  platform: string;
  episode_range: unknown[];
  scheduled_at: string;
  status: string;
  error_message?: string | null;
  created_at: string;
}

export interface PublishExportRequest {
  book_id: number;
  branch_id?: number | null;
}

/** Supported novel publishing platforms. */
export type PublishPlatform = "narou" | "kakuyomu" | "alphapolis" | "kdp_epub" | "aozora";

/** 投稿実行リクエスト */
export interface PublishRequest {
  /** 書籍ID */
  book_id: number;
  /** 投稿先プラットフォーム */
  platforms?: string[];
  /** 投稿対象話数範囲 (from, to) */
  episode_range?: unknown[] | null;
  /** 投稿対象エピソードIDリスト */
  episode_ids?: number[] | null;
  /** 定期投稿スケジュール設定 */
  schedule?: Record<string, unknown> | null;
  /** プラットフォーム別認証情報（環境変数優先） */
  credentials?: Record<string, Record<string, unknown>> | null;
}

/** 投稿ステータス取得リクエスト */
export interface PublishStatusRequest {
  book_id: number;
  platform: string;
  post_id: string;
}

export interface QualitativeAudit {
  /** 読者引き込み度 */
  hook_score: number;
  /** 感情曲線の自然さ */
  emotional_score: number;
  /** キャラ言動の一貫性 */
  character_consistency: number;
  /** 定性総合評価 */
  overall_score: number;
  /** 主要講評 */
  critique?: string;
  /** 推奨局所修正パッチ */
  actionable_patch?: string | null;
}

/** RAGコンテキスト生成リクエスト. */
export interface RagContextRequest {
  /** 現在のプロンプト/クエリ */
  current_prompt: string;
  /** 主人公名 */
  character_name: string;
  /** 追加エンティティ */
  additional_entities?: string[] | null;
  /** 対象書籍ID。コンテキストキャッシュのキー的重要组成部分（未指定時はキャッシュを読み書きしない） */
  book_id?: number | null;
}

export interface ReadinessResponse {
  status: string;
  dependencies: Record<string, string>;
  timestamp: string;
}

export interface ReflectionStatsResponse {
  book_id: number | null;
  total_calls: number;
  avg_iterations: number;
  convergence_rate: number;
  avg_threshold_filtered: number;
}

export interface ReflectionTestRequest {
  /** 検索クエリ */
  query: string;
  /** 書籍ID */
  book_id?: number | null;
  top_k?: number;
  max_iter?: number;
  relevance_threshold?: number;
}

export interface ReflectionTestResponse {
  iterations: number;
  converged: boolean;
  original_query: string;
  refined_queries: string[];
  final_doc_count: number;
  initial_doc_count: number;
  history: Record<string, unknown>[];
  elapsed_ms: number;
}

/** 音律・リズム整形リクエスト */
export interface ReformatRequest {
  /** 整形対象の小説本文 */
  text: string;
}

/** 音律・リズム整形レスポンス */
export interface ReformatResponse {
  reformatted_text: string;
  stats: CadenceStats;
}

/** 課題解決リクエスト */
export interface ResolveIssueRequest {
  api_key: string;
  config?: Record<string, unknown>;
  action: string;
}

/** コンフリクト解決済み章コンテンツ (Step 49). */
export interface ResolvedChapterPayload {
  chapter_number: number;
  resolved_content: string;
  /** base | source | target | manual */
  resolution_strategy?: string;
}

/** 失敗エピソード再試行リクエスト */
export interface RetryFailedRequest {
  api_key: string;
  config?: Record<string, unknown>;
  book_id: number;
  passion: number;
  word_count: number;
}

/** 逆算プロット生成リクエスト（APIキー不要のかんたんモード・UI用） */
export interface ReversePlotGeneratePayload {
  /** 4ステップ回答 */
  answers?: Record<string, unknown>;
  /** 目標話数 */
  targetEpisodes?: number;
  /** ジャンル */
  genre?: string;
  /** オプトインのLLM設定 */
  llm_config?: LLMConfigOverride | null;
}

/** 逆算プロット生成リクエスト */
export interface ReversePlotGenerateRequest {
  api_key: string;
  config?: Record<string, unknown>;
  answers: Record<string, unknown>;
  target_episodes: number;
  genre: string;
}

export interface ReviewActionRequest {
  reviewer_id?: string | null;
  comment?: string;
}

export interface ReviseReviewRequest {
  proposed_content: string;
  reviewer_id?: string | null;
  comment?: string;
}

/** Serializable specification of a rewrite rule. */
export interface RewriteRuleModel {
  /** Unique rule ID */
  id: string;
  /** Human-readable rule name */
  name?: string;
  /** Regular expression pattern */
  pattern: string;
  /** Replacement pattern or template */
  replacement?: string;
  /** Execution priority (lower executes earlier) */
  priority?: number;
  /** Whether matching stops subsequent rules */
  final?: boolean;
  /** Skip if specific context tags already matched */
  skip_if_matched?: boolean;
  /** Enable or disable the rule */
  enabled?: boolean;
  /** Rule tags for categorization */
  tags?: string[];
  /** Detailed description */
  description?: string;
}

export interface RunRequest {
  task_type?: string;
  prompt_version?: string;
  model_name?: string;
  params?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  output_preview?: string;
  trace_id?: string;
  chapter_ep?: number | null;
}

/** プロットから分解された物理動作・五感ビート（v4より完全継承） */
export interface SceneBeat {
  /** ビート番号 */
  beat_num: number;
  /** 肉体的な動作描写 */
  physical_action: string;
  /** 五感タグ: smell(嗅覚), sound(聴覚), touch(触覚), taste(味覚), sight(視覚) */
  sensory_tags?: string[];
  /** 感情フェーズ: buildup(助走) / explosion(爆発) / aftermath(余韻) */
  emotion_phase?: string;
  /** このビートに配分する目標文字数 */
  word_budget?: number;
}

/** 五感・描写拡張タイプ */
export type SensoryType = "visual" | "auditory" | "olfactory" | "tactile" | "gustatory" | "metaphor";

/** 文末出現比率 */
export interface SentenceEndDistribution {
  /** です・ます調の割合 */
  desu_masu?: number;
  /** だ・である調の割合 */
  da_dearu?: number;
  /** 体言止めの割合 */
  nominal?: number;
  /** 感嘆符（！）の割合 */
  exclamatory?: number;
  /** 疑問符（？）の割合 */
  interrogative?: number;
  /** 文末リズムの特徴解説 */
  description?: string;
}

/** 文長分布パラメータ */
export interface SentenceLengthModel {
  /** 平均文長（文字数） */
  avg?: number;
  /** 標準偏差 */
  std_dev?: number;
  /** 最小文長 */
  min?: number;
  /** 最大文長 */
  max?: number;
  /** 文長の特徴解説 */
  description?: string;
}

export interface SkillVersionSwitchRequest {
  version: string;
}

export interface SpecialistInfo {
  name: string;
  version?: string;
  llm_required: boolean;
}

/** カテゴリ情報 */
export interface StyleCategory {
  id: string;
  label: string;
  style_ids: string[];
}

/** スタイル定義エントリ */
export interface StyleEntry {
  id: string;
  name: string;
  category: string;
  instruction: string;
  dialogue_ratio: string;
  syntax_rhythm: string;
  metaphor_dna: string;
  noise_dna: string;
  is_light: boolean;
}

/** 文体プリセット概要 */
export interface StylePresetSummary {
  id: string;
  name: string;
  genre: string;
  description: string;
  tone: string;
  profile?: StyleProfile | null;
}

/** 作家性DNA（Style DNA）プロファイル */
export interface StyleProfile {
  /** スタイルID */
  id?: string;
  /** スタイル表示名 */
  name?: string;
  /** ジャンルヒント */
  genre_hint?: string;
  /** カテゴリ: tempo/heavy/dark/elegant */
  category?: string;
  /** 語り口・トーンの概要 */
  tone_description?: string;
  sentence_length?: SentenceLengthModel;
  sentence_end_distribution?: SentenceEndDistribution;
  metaphor_frequency?: MetaphorFrequency;
  /** ケレン味・ハッタリ・誇張表現の強度 (0.0〜1.0) */
  kerenmi_intensity?: number;
  /** 避けるべきAI手癖パターン */
  forbidden_patterns?: string[];
  /** 必須の文体パターン */
  required_patterns?: string[];
  /** 文体のお手本となる代表的パラグラフ（100〜300文字） */
  few_shot_sample?: string;
  /** 蒸留元の生サンプルテキスト */
  raw_sample?: string;
}

/** Context information supplied to subtext rules, templates, and token expanders. */
export interface SubtextContext {
  /** Scene identifier */
  scene_id?: string;
  /** Dialogue turn index in scene */
  turn_index?: number;
  /** Speaking character name */
  speaker?: string;
  /** Addressed character name */
  target_speaker?: string;
  /** Primary emotional state (e.g. betrayal, grief, anger) */
  emotion?: string;
  /** inferior, equal, superior */
  power_dynamic?: string;
  /** former_ally, enemy, lover, subordinate, stranger */
  relationship?: string;
  /** low, medium, high */
  intensity?: string;
  /** Genre modifier (e.g. fantasy, horror, romance) */
  genre?: string;
  /** Tone modifier (e.g. dark, ironic, light) */
  tone?: string;
  /** Recent conversation turns or subtext history */
  history_summary?: string[];
  /** Inter-character relationship properties */
  relationship_graph?: Record<string, unknown>;
  /** Arbitrary extension parameters */
  custom?: Record<string, unknown>;
}

export type TargetPlatform = "kakuyomu" | "narou" | "alphapolis" | "kindle";

export interface TemplateCreateRequest {
  id: string;
  category?: string;
  content: string;
  weight?: number;
  tags?: string[];
}

/** 生成されたタイトル候補とCTR予測結果 */
export interface TitleCandidate {
  /** 生成されたタイトル文字列 */
  title: string;
  /** 文字数 */
  char_count: number;
  /** 構文パターン名 (追放ざまぁ, 勘違い無双 等) */
  syntax_type: string;
  /** CTR予測スコア (0-100) */
  predicted_ctr_score: number;
  /** 含まれるフック要素 */
  hooks?: string[];
}

export interface TokenPreviewRequest {
  text: string;
  context?: SubtextContext | null;
  seed?: number | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in: number;
}

/** トーン書き換えタイプ */
export type ToneType = "tension" | "erotic" | "fast_paced" | "formal" | "lyrical";

export interface UnifiedAuditReport {
  is_acceptable: boolean;
  final_score: number;
  quantitative_score: number;
  qualitative: QualitativeAudit;
  detected_cliches?: string[];
  dialogue_ratio?: number;
  conflicts?: ConflictItemSchema[];
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface UserProfileResponse {
  id: number;
  email: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
  credits: number;
  plan_tier: string;
  created_at: string;
}

export interface UserRegisterRequest {
  /** メールアドレス */
  email: string;
  /** パスワード */
  password: string;
  /** 作家名/表示名 */
  display_name: string;
}

export type UserRole = "user" | "pro" | "admin";

export type UserStatus = "active" | "suspended" | "pending";

export interface ValidationError {
  loc: string | number[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

/** バズタイトル生成リクエスト */
export interface ViralTitleRequest {
  /** ジャンル (ファンタジー, 現代ドラマ 等) */
  genre: string;
  /** 作品の核心設定・独自性 */
  core_concept: string;
  /** 主人公の圧倒的強み・実利 */
  protagonist_benefit: string;
  /** 敵・元仲間へのざまぁ/見下し要素 */
  antagonist_misfortune?: string;
  /** 生成候補数 */
  candidate_count?: number;
}

/** バズタイトル生成レスポンス */
export interface ViralTitleResponse {
  /** CTR最上位候補 (1-5案) */
  top_recommendations: TitleCandidate[];
  /** 全生成候補 */
  all_candidates: TitleCandidate[];
  /** 最上位タイトルに連動して生成されたあらすじ */
  selected_synopsis?: string;
}

/** PDCA執筆指示のスキーマ */
export interface WritingDirectiveSchema {
  dimension: string;
  severity: string;
  target_location: string;
  current_issue: string;
  mandatory_instruction: string;
  rationale: string;
  specialist_name?: string | null;
}

/** 4コマ漫画生成リクエスト (`POST /yonkoma`)。 */
export interface YonkomaGenerateRequest {
  /** 対象 Book ID */
  book_id: number;
  /** 1話分の本文 */
  episode_text?: string;
  /** コマ数 (3〜6) */
  panels?: number;
  /** 生成モデル (fast/quality/ultra/auto) */
  model?: string;
  /** R15 表現を許可するか */
  enable_r15?: boolean;
  /** 話数 */
  episode_number?: number | null;
  /** 作品の補助情報 */
  book_context?: Record<string, unknown>;
  /** 画像生成を伴うか (False ならプロンプトのみ) */
  yonkoma_enabled?: boolean;
}

/** ロールバックリクエスト */
export interface src__backend__routers__annotations__RollbackRequest {
  book_id: number;
  episode: number;
  beat_id: string;
}

export interface src__domain__schemas__project__BookSchema {
  created_at?: string;
  updated_at?: string;
  id: number;
  project_id: number;
  title: string;
  genre?: string;
  synopsis?: string;
  total_words?: number;
  target_chapters?: number;
  /** チート度（1:微チート〜5:理不尽無双） */
  cheat_scale?: number;
  /** 成長曲線モデル */
  growth_curve?: string;
  /** ステータス・システム関与度% */
  system_assist?: number;
  /** 能力の代償・世界のリスク過酷度 */
  cost_severity?: number;
  /** 物語の根底にあるテーマ・哲学的問い */
  thematic_core?: string;
}

/** 作品情報スキーマ */
export interface src__models__api_schemas__BookSchema {
  id: number;
  title: string;
  genre: string;
  concept?: string | null;
  synopsis?: string | null;
  target_eps?: number;
  cumulative_stress?: number | null;
  created_at?: string | null;
}

/** プロンプトロールバックリクエスト */
export interface src__models__api_schemas__RollbackRequest {
  api_key: string;
  config?: Record<string, unknown>;
  version_id: number;
  reason?: string | null;
}
