/**
 * HTML エスケープの共通ユーティリティ。
 *
 * `dangerouslySetInnerHTML` に載せる **原稿本文（LLM 出力・ユーザー入力）** は
 * 信用できない。認証トークンが localStorage に載っているため、ここを
 * 素通りすると XSS からトークン窃取につながる。
 *
 * ## 適用順序（重要）
 *
 *   1. まず `escapeHtml()` で元テキスト全体をエスケープする。
 *   2. その後、ルビ / カタカナのタグ置換 transform を掛ける。
 *
 * 逆順（タグ置換してからエスケープ）だと生成した `<ruby>` や `<span>` まで
 * 数値エンティティにされ、ルビもハイライトも壊れる。
 *
 * エスケープは変換の「前」に行う。ただし `｜` `《` `》` `ー` `ァ-ヶ` は
 * ASCII ではないためエスケープ対象（`& < > " '`）に含まれず、
 * ルビ記法 `｜親文字《ルビ》` の構文解析はそのまま正しく動く。
 * ASCII の `& < >` だけが守られるので、LLM が `<script>` を出力しても無害になる。
 */

/** HTML の特殊文字を数値文字参照へ */
const HTML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/**
 * HTML テキストをエスケープする。
 * 境界（レンダリングの手前）で **ちょうど 1 回** 呼ぶこと。二重エスケープは避ける。
 */
export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

/**
 * HTML 属性値をエスケープする。
 *
 * `escapeHtml` だけでは不十分。属性値内でスペース・改行・`=`・`/`・`` ` `` などが
 * エスケープされないと、属性抜け出し (attribute break-out) XSS の原因になる。
 * 例: `data-value="` + `"><img src=x onerror=alert(1)>` → 属性を閉じて新しいタグを注入可能。
 *
 * 安全側に倒し、アルファベット・数字・`-`・`_`・`.` 以外をすべて
 * 16進数文字参照 (&#xHH;) でエスケープする。
 *
 * @param value エスケープ対象の属性値
 * @returns HTML 属性値として安全に埋め込める文字列
 */
export function escapeAttribute(value: string): string {
  return value.replace(/[^A-Za-z0-9\-_.]/g, (ch) =>
    `&#x${ch.codePointAt(0)!.toString(16).padStart(4, "0")};`
  );
}