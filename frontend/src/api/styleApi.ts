import {
  DistillRequest,
  DistillResponse,
  ReformatResponse,
  StylePresetSummary,
  StyleEntry,
  StyleCategory,
} from "../types/style";
import { apiFetch } from "./client";

const BASE = "/api/styles";

/**
 * スタイル API クライアント。
 *
 * 以前は素の fetch を使っていたため Authorization ヘッダが付かず、
 * 認証を追加したルートでは常に 401 になっていた。apiFetch に統一済み。
 */
export async function fetchStylePresets(): Promise<StylePresetSummary[]> {
  const res = await apiFetch(`${BASE}/presets`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchAllStyles(): Promise<StyleEntry[]> {
  const res = await apiFetch(`${BASE}/all`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchStyleCategories(): Promise<StyleCategory[]> {
  const res = await apiFetch(`${BASE}/categories`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * スタイル仕様（instruction / dialogue_ratio / syntax_rhythm / metaphor_dna /
 * noise_dna）を取得する。GET /api/styles/{style_id}/preview は StyleEntry を返す。
 */
export async function fetchStylePreview(styleId: string): Promise<StyleEntry> {
  const res = await apiFetch(`${BASE}/${styleId}/preview`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function distillStyleFromText(request: DistillRequest): Promise<DistillResponse> {
  const res = await apiFetch(`${BASE}/distill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function reformatCadence(text: string): Promise<ReformatResponse> {
  const res = await apiFetch(`${BASE}/reformat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
