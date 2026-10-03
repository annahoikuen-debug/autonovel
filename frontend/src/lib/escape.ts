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
 * 引用符を含む属性値をエスケープする。
 * `style="..."` や `data-xxx="..."` をテンプレートリテラルで組み立てる箇所で使う。
 */
export function escapeAttribute(value: string): string {
  return escapeHtml(value);
}