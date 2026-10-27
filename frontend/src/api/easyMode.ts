import {
  EasyModeInput,
  GenerationResponse,
  ExportPackage,
  TaskStatusResponse,
  GachaRequest,
  GachaResponse,
  DigestRequest,
  DigestResponse,
  PromotionRequest,
  PromotionResponse,
  ExportRequestPayload,
} from "../types/easyMode";
import { apiFetch } from "./client";

const BASE = "/easy_mode";

export async function generateContent(input: EasyModeInput): Promise<GenerationResponse> {
  const res = await apiFetch(`${BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function generateContentStream(
  input: EasyModeInput,
  signal?: AbortSignal | null
): Promise<Response> {
  const res = await apiFetch(`${BASE}/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    ...(signal ? { signal } : {}),
  });
  if (!res.ok) {
    // 本文は必ず一度しか読めない。以前は text() で読んだ後に json() を試みていたため
    // 必ず "Body has already been read" で失敗し、try ブロックが死んでいた。
    // clone() を先に取っておき、json() を主、text() を副として使い分ける。
    const fallback = res.clone();
    let errorMessage = "";
    try {
      const errorJson = await res.json();
      errorMessage = errorJson.detail || errorJson.message || "";
    } catch {
      // JSON でなければ clone 側（未消費）の生テキストを使う
      errorMessage = await fallback.text().catch(() => "");
    }
    throw new Error(errorMessage || `HTTP ${res.status} ${res.statusText}`);
  }
  return res;
}

export async function pollGenerationStatus(
  taskId: string,
  signal?: AbortSignal | null
): Promise<TaskStatusResponse> {
  const res = await apiFetch(`${BASE}/status/${taskId}`, { ...(signal ? { signal } : {}) });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelTask(taskId: string): Promise<{ task_id: string; status: string }> {
  const res = await apiFetch(`${BASE}/task/${taskId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportPackage(bookId: number): Promise<ExportPackage> {
  const res = await apiFetch(`${BASE}/export/${bookId}`);
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const contentDisposition = res.headers.get("Content-Disposition");
  // RFC6266 形式: filename="ascii.zip"; filename*=UTF-8''encoded.zip
  const utf8Match = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i);
  const asciiMatch = contentDisposition?.match(/filename="([^"]+)"/i);
  const utf8Filename = utf8Match ? decodeURIComponent(utf8Match[1] as string) : undefined;
  const rawFilename = utf8Filename || asciiMatch?.[1] || `export_${bookId}.zip`;
  const filename: string = rawFilename ?? `export_${bookId}.zip`;
  return { zipBlob: blob, filename };
}

export async function exportPackageWithData(
  bookId: number,
  payload?: ExportRequestPayload
): Promise<ExportPackage> {
  const res = await apiFetch(`${BASE}/export-with-data?book_id=${bookId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const contentDisposition = res.headers.get("Content-Disposition");
  const utf8Match = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i);
  const asciiMatch = contentDisposition?.match(/filename="([^"]+)"/i);
  const utf8Filename = utf8Match ? decodeURIComponent(utf8Match[1] as string) : undefined;
  const rawFilename = utf8Filename || asciiMatch?.[1] || `export_${bookId}.zip`;
  const filename: string = rawFilename ?? `export_${bookId}.zip`;
  return { zipBlob: blob, filename };
}

export async function generateGachaPlans(req: GachaRequest): Promise<GachaResponse> {
  const res = await apiFetch(`${BASE}/gacha`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function generateDigest(req: DigestRequest): Promise<DigestResponse> {
  const res = await apiFetch(`${BASE}/digest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function promoteToStudio(req: PromotionRequest): Promise<PromotionResponse> {
  const res = await apiFetch(`${BASE}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

