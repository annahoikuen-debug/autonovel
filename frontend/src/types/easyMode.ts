export interface CharacterParams {
  name: string;
  personality: string;
  ability: string;
  genre: string;
  style_id?: string;
  style_profile?: any;
}

export interface LLMConfigOverride {
  provider?: "gemini" | "openai" | "mock" | string;
  api_key?: string;
  model_name?: string;
  base_url?: string;
  model_planning?: string;
  model_writing?: string;
  model_audit?: string;
  model_embedding?: string;
}

/**
 * PLAN_S1 R2 / F1B H7: STORY_SPINE 構造テンプレートの適用レベル。
 *
 * バックエンドの `EasyModeInput.spine_quality`（Literal["off","soft","hard"]）と対応。
 * 既定 "off" = 構造指示を注入しない（生成プロンプト差分ゼロ契約）。
 */
export type SpineQualityLevel = "off" | "soft" | "hard";

export interface EasyModeInput {
    chapter_history: string[];
    current_chapter: string;
    character_params: CharacterParams | Record<string, unknown>;
    content_length_limit: number;
    target_episodes?: number;
    /**
     * 文体プリセットの指定。
     *
     * 画面（Easy Mode の「文体の雰囲気」選択）で選んだ値を生成処理まで届けるために使う。
     * API 側は `style_override` として受け取る。
     */
    style_override?: Record<string, unknown>;
    llm_config?: LLMConfigOverride;
    book_id?: number;
    /**
     * PLAN_S1 R2 / F1B H7: STORY_SPINE 構造テンプレートの適用レベル。
     *
     * - "off"（既定）: 構造指示を注入しない（プロンプト差分ゼロ）
     * - "soft": 構造の参考として注入
     * - "hard": その話で果たすべき duty として注入
     *
     * 未指定（undefined）はバックエンドで None になり、注入なしと同じ扱い。
     */
    spine_quality?: SpineQualityLevel | null;
}

export interface GenerationResponse {
  task_id?: string;
  output: string;
  completion_time_ms: number;
  error: string;
  suggestions: string[];
}

export interface ExportPackage {
  zipBlob: Blob;
  filename: string;
}

export interface ExportRequestPayload {
  title?: string;
  genre?: string;
  current_text?: string;
  character?: CharacterParams | Record<string, unknown>;
  plots?: Array<{ ep_num: number; title: string; one_line_summary: string }>;
}

export type TaskStatus = "pending" | "running" | "completed" | "failed";

export interface TaskStatusResponse {
  task_id: string;
  status: TaskStatus;
  result?: unknown;
  error?: string;
}

export type GachaPlanType = "royal" | "curveball" | "dark";

export interface GachaPlan {
  plan_id: string;
  plan_type: GachaPlanType;
  title: string;
  logline: string;
  protagonist_summary: string;
  charm_point: string;
  audit_score?: number;
  critique?: Record<string, unknown>;
  recommendation_reason?: string;
  is_recommended?: boolean;
}

export interface GachaRequest {
  genre: string;
  keywords: string[];
  temperature?: number;
  review_session_id?: string;
}

export interface GachaResponse {
  request_id: string;
  plans: GachaPlan[];
  recommended_plan_id?: string;
  review_session_id?: string;
}

export interface DigestRequest {
  request_id: string;
  selected_plan_id: string;
}

export interface DigestResponse {
  book_id: string;
  title: string;
  synopsis: string;
  episode_1_text: string;
  climax_preview_text: string;
  status: "processing" | "completed" | "failed";
}

export interface PromotionRequest {
  book_id: string;
}

export interface PromotionResponse {
  success: boolean;
  redirect_url: string;
  state_token: string;
}

