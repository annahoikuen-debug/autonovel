export interface ToastNotification {
  id: string;
  type: "success" | "error" | "info";
  message: string;
  durationMs?: number;
}

export interface CharacterParams {
  name: string;
  personality: string;
  ability: string;
  genre: string;
  style_id?: string;
  style_profile?: any;
}

export interface Chapter {
  id?: number;
  ep_num: number;
  title: string;
  content: string;
}

export interface ChapterItem {
   id?: number;
   ep_num: number;
   title: string;
   summary?: string;
   content: string;
   is_catharsis?: boolean;
   status?: "draft" | "writing" | "completed" | "polished";
}

export interface GenerationState {
  isGenerating: boolean;
  statusText: string;
  progressPercent?: number;
  suggestions: string[];
  currentTaskId: string | null;
  error: string | null;
}

export interface UnifiedStreamingState {
  mode: GenerationMode;
  isActive: boolean;
  output: string;
  agentProgress: Record<string, any>;
  error: string | undefined;
}

export type GenerationMode = "standard" | "orchestrated" | "reverse" | "simple" | "easy";

// --- API 型の再エクスポート ---
// OpenAPI 自動生成（api.generated）を API 契約の単一情報源とし、手書き
// モジュール（editor / orchestrated）と同名の型は生成物を優先する。
// （`export *` を並べると同名エクスポートで TS2308 エラーになるため、
//  重複しない型のみを明示的に再エクスポートする）
export * from "./api.generated";
export type {
  ActiveAuditHighlight,
  ResolveIssueResponse,
  DiffChunk,
  ConflictItem,
} from "./editor";
export * from "./history";
export * from "./graphInspector";
export * from "./styleComparison";
export * from "./marketingShowcase";
export * from "./books";
export * from "./editorSettings";
export type {
  OrchestratedTaskStatus,
  AgentName,
  AgentEvent,
  AgentProgress,
} from "./orchestrated";
// marketing.ts の型 (TitleCandidate / ViralTitleRequest / ViralTitleResponse) は
// api.generated と同名のため、再エクスポートは生成物側に一本化している。
