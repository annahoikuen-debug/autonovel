import { apiFetch } from "./client";

/**
 * `GET /images/{book_id}/{scene_name}` のレスポンス。
 *
 * 404 ではなく 200 で「未生成」を返す設計にしてある（「未生成」と「障害」を
 * 区別できるようにするため）。契約:
 *   { "found": false, "image_url": null,   "illustration_id": null }
 */
export interface SceneIllustrationLookup {
  found: boolean;
  image_url: string | null;
  illustration_id: number | null;
}

/**
 * シーンに対応する挿絵の URL を取得する。
 *
 * 注意: `routers/illustrations.py` は `APIRouter()` で prefix を持たないため、
 * パスは `/images/...` になる（`/api/illustrations/...` では 404 になる）。
 *
 * @returns 挿絵があれば URL、无ければ `undefined`（例外は投げない）
 */
export async function fetchSceneIllustration(
  bookId: number,
  sceneName: string,
): Promise<string | undefined> {
  if (!bookId || !sceneName) return undefined;

  const res = await apiFetch(
    `/images/${bookId}/${encodeURIComponent(sceneName)}`,
  );
  // 404/500 は「取れなかった」だけなので、例外にせず undefined を返す
  if (!res.ok) return undefined;

  const data = (await res.json()) as SceneIllustrationLookup;
  if (!data?.found || typeof data.image_url !== "string" || !data.image_url) {
    return undefined;
  }
  return data.image_url;
}

/**
 * エピソード番号で挿絵の URL を決定的に取得する(Play モード用)。
 *
 * `GET /images/episode/{book_id}/{episode_number}` — `illustration_type == "episode"`
 * を最優先し、無ければ話数一致の最新行。契約は `fetchSceneIllustration` と同じ
 * (未生成は 200 + found: false。例外は undefined に潰す)。
 */
export async function fetchEpisodeIllustration(
  bookId: number,
  episodeNumber: number,
): Promise<string | undefined> {
  if (!bookId || !episodeNumber || episodeNumber < 1) return undefined;

  const res = await apiFetch(`/images/episode/${bookId}/${episodeNumber}`);
  if (!res.ok) return undefined;

  const data = (await res.json()) as SceneIllustrationLookup;
  if (!data?.found || typeof data.image_url !== "string" || !data.image_url) {
    return undefined;
  }
  return data.image_url;
}
