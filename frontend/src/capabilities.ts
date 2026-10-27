/**
 * 機能の実装状況を宣言するレジストリ。
 *
 * v5 のレビューで判明した欠陥は「バックエンドに何があるかを待たずに
 * UI が書いてしまう」類のものだった（例: 自動改善ループ。
 * 実際にはループが存在せず、無限スピナーだけを出していた）。
 *
 * ここに宣言することで、UI 側は
 *  - 実装済みなら本物を出す
 *  - 未実装なら理由付きで無効化する
 * という二択を強制でき、「押せるのに何も起きない」操作が
 * 後から誰かが再実装することがなくなる。
 *
 * backend 側が実装したら status を 'wired' に変えるだけでよい。
 */

export type CapabilityStatus = "wired" | "planned";

export interface Capability {
  status: CapabilityStatus;
  /** status が 'planned' のとき、UI に出る説明 */
  reason?: string;
  /** 実装を見込む PR などのメモ（UI には出さない） */
  note?: string;
}

export const CAPABILITIES = {
  /** スタイル比較: 実測値（クライアント計算）とスタイル仕様（GET /styles/{id}/preview）の比較は実装済み */
  styleCompare: {
    status: "wired",
  } as Capability,
  /** スタイルを章节に適用する。Chapter モデルにスタイル列が無いため未実装 */
  styleApply: {
    status: "planned",
    reason: "スタイル適用は未実装です（章节にスタイルを保存する項目が無い）",
    note: "Chapter へのカラム追加 + 生成パイプラインへの反映が必要",
  } as Capability,
  /** スカラー値や文をスタイル文として書き換える。該当する backend endpoint が無い */
  styleRewrite: {
    status: "planned",
    reason: "文体の書き換えは未実装です（スタイル指定の書き換え endpoint が無い）",
    note: "GET /styles/{id}/preview は StyleEntry（仕様情報）を返すだけで本文は返さない",
  } as Capability,
  /** スコアに基づく自動書き換えループ。ループは未実装で、採点のみ実装済み */
  autoImproveLoop: {
    status: "planned",
    reason: "自動改善ループは未実装です（採点と傾向分析のみ実装済み）",
    note: "GET /books/{book_id}/chapters/{n}/score と novel.py の alerient 診断は使える",
  } as Capability,
} as const satisfies Record<string, Capability>;

export type CapabilityName = keyof typeof CAPABILITIES;

/** 機能が実装済みかどうか。 */
export function isWired(name: CapabilityName): boolean {
  return CAPABILITIES[name].status === "wired";
}

/** 未実装機能の UI に出す理由文。実装済みなら null。 */
export function plannedReason(name: CapabilityName): string | null {
  const cap = CAPABILITIES[name];
  return cap.status === "planned" ? (cap.reason ?? "未実装") : null;
}
