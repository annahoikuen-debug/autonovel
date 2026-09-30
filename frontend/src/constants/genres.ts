/**
 * バックエンド GENRE_REGISTRY (config/story_spine/genre_registry.py) と整合する UI ジャンル選択肢。
 */
export interface GenreOption {
  value: string;
  label: string;
  presetKey: string | null;
}

export const FALLBACK_GENRE_OPTIONS: GenreOption[] = [
  { value: "HighFantasy", label: "ハイファンタジー", presetKey: "cheat_tensei" },
  { value: "Scifi", label: "SF", presetKey: "cheat_tensei" },
  { value: "Romance", label: "恋愛・悪役令嬢", presetKey: "aku_reijo" },
  { value: "Mystery", label: "ミステリー・頭脳戦", presetKey: "zarma" },
  { value: "Horror", label: "ホラー・ダーク", presetKey: "cheat_tensei" },
  { value: "Modern", label: "現代・日常", presetKey: "modern_cheat" },
  { value: "History", label: "歴史・戦記", presetKey: "cheat_tensei" },
  { value: "Youth", label: "青春・学園", presetKey: "slow_life" },
];

export const GENRE_OPTIONS: GenreOption[] = FALLBACK_GENRE_OPTIONS;

export async function fetchGenreOptions(): Promise<GenreOption[]> {
  try {
    const res = await fetch("/api/config/planning_options");
    if (!res.ok) return FALLBACK_GENRE_OPTIONS;
    const data = await res.json();
    if (data.genres && typeof data.genres === "object") {
      const entries = Array.isArray(data.genres) ? data.genres : Object.values(data.genres);
      return entries.map((g: any) => ({
        value: g.key || g.value,
        label: g.label || g.name || g.key,
        presetKey: g.preset_key ?? null,
      }));
    }
    return FALLBACK_GENRE_OPTIONS;
  } catch {
    return FALLBACK_GENRE_OPTIONS;
  }
}

// ==========================================
// ジャンルバッジ設定
// ==========================================

export interface GenreBadgeConfig {
  bg: string;
  text: string;
  border: string;
  emoji: string;
}

export const GENRE_BADGE_CONFIG: Record<string, GenreBadgeConfig> = {
  HighFantasy: { bg: "rgba(167, 139, 250, 0.2)", text: "#a78bfa", border: "#a78bfa", emoji: "🏰" },
  "ハイファンタジー": { bg: "rgba(167, 139, 250, 0.2)", text: "#a78bfa", border: "#a78bfa", emoji: "🏰" },
  "ハイファンタジー (R15)": { bg: "rgba(167, 139, 250, 0.2)", text: "#a78bfa", border: "#a78bfa", emoji: "🏰" },
  Scifi: { bg: "rgba(6, 182, 212, 0.2)", text: "#06b6d4", border: "#06b6d4", emoji: "🚀" },
  SF: { bg: "rgba(6, 182, 212, 0.2)", text: "#06b6d4", border: "#06b6d4", emoji: "🚀" },
  Romance: { bg: "rgba(236, 72, 153, 0.2)", text: "#ec4899", border: "#ec4899", emoji: "👑" },
  "恋愛・悪役令嬢": { bg: "rgba(236, 72, 153, 0.2)", text: "#ec4899", border: "#ec4899", emoji: "👑" },
  "悪役令嬢・婚約破棄": { bg: "rgba(236, 72, 153, 0.2)", text: "#ec4899", border: "#ec4899", emoji: "👑" },
  Mystery: { bg: "rgba(249, 115, 22, 0.2)", text: "#f97316", border: "#f97316", emoji: "🔍" },
  "ミステリー・頭脳戦": { bg: "rgba(249, 115, 22, 0.2)", text: "#f97316", border: "#f97316", emoji: "🔍" },
  Horror: { bg: "rgba(124, 58, 237, 0.2)", text: "#7c3aed", border: "#7c3aed", emoji: "🌑" },
  "ホラー・ダーク": { bg: "rgba(124, 58, 237, 0.2)", text: "#7c3aed", border: "#7c3aed", emoji: "🌑" },
  "ダークファンタジー (R15)": { bg: "rgba(124, 58, 237, 0.2)", text: "#7c3aed", border: "#7c3aed", emoji: "🌑" },
  Modern: { bg: "rgba(34, 197, 94, 0.2)", text: "#22c55e", border: "#22c55e", emoji: "📱" },
  "現代・日常": { bg: "rgba(34, 197, 94, 0.2)", text: "#22c55e", border: "#22c55e", emoji: "📱" },
  History: { bg: "rgba(234, 179, 8, 0.2)", text: "#eab308", border: "#eab308", emoji: "📜" },
  "歴史・戦記": { bg: "rgba(234, 179, 8, 0.2)", text: "#eab308", border: "#eab308", emoji: "📜" },
  Youth: { bg: "rgba(59, 130, 246, 0.2)", text: "#3b82f6", border: "#3b82f6", emoji: "🎒" },
  "青春・学園": { bg: "rgba(59, 130, 246, 0.2)", text: "#3b82f6", border: "#3b82f6", emoji: "🎒" },
  "追放後スローライフ": { bg: "rgba(234, 179, 8, 0.2)", text: "#eab308", border: "#eab308", emoji: "🍃" },
  "VRMMO・ゲーム世界": { bg: "rgba(6, 182, 212, 0.2)", text: "#06b6d4", border: "#06b6d4", emoji: "🎮" },
  "デフォルト": { bg: "rgba(161, 161, 170, 0.2)", text: "#a1a1aa", border: "#a1a1aa", emoji: "📚" },
};

export function getGenreBadgeConfig(genre: string): GenreBadgeConfig {
  return GENRE_BADGE_CONFIG[genre] ?? GENRE_BADGE_CONFIG["デフォルト"]!;
}