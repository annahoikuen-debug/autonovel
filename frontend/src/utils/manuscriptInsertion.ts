/**
 * 編集中の本文テキストエリアを DOM から解決する。
 *
 * モバイルクイック操作バー（括弧・省略記号など）は、
 * どの画面のエディタでも「いま入力している本文」に挿入できる必要がある。
 * 候補を优先级順に並べることで、Studio / Easy / Wizard のどの画面でも
 * 同じ導線が同じ挙動になる。
 */
const TEXTAREA_SELECTORS = [
  // Wizard Step3
  '[data-testid="wizard-chapter-textarea"]',
  // Studio Editor（通常 / Zen）
  '#editor-textarea',
  '[data-testid="editor-textarea-zen"]',
  '[data-testid="editor-textarea"]',
  // Easy Mode のプロンプト入力
  'textarea[placeholder*="本文"]',
  'textarea[placeholder*="プロンプト"]',
  // 最後の砦：表示されている最初の textarea
  'textarea',
];

/** テキストエリアが「いま編集対象として使える」状態か（読み取り専用・非表示を除外） */
function isEditable(el: HTMLTextAreaElement): boolean {
  if (el.readOnly || el.disabled) return false;
  // jsdom では offsetParent が常に null になるので、非表示判定は style で行う
  if (el.style && el.style.display === 'none') return false;
  return true;
}

/** 編集中の本文テキストエリアを返す（無ければ null） */
export function findActiveManuscriptTextarea(): HTMLTextAreaElement | null {
  if (typeof document === 'undefined') return null;

  for (const selector of TEXTAREA_SELECTORS) {
    const nodes = Array.from(
      document.querySelectorAll<HTMLTextAreaElement>(selector),
    );
    const found = nodes.find(isEditable);
    if (found) return found;
  }
  return null;
}

/**
 * 編集中の本文へ `text` を挿入する。
 *
 * 挿入位置は「現在の選択範囲」。選択が無い場合はカーソル位置。
 * 選択範囲があれば置換し、なければカーソル位置へ挿入する。
 *
 * @returns 挿入に成功したか（対象テキストエリアが無い場合は false）
 */
export function insertTextIntoActiveManuscript(text: string): boolean {
  const textarea = findActiveManuscriptTextarea();
  if (!textarea) return false;

  const start = textarea.selectionStart ?? textarea.value.length;
  const end = textarea.selectionEnd ?? start;

  // setRangeText は React の onChange を発火させるため、
  // 「公式のブラウザ API 経由で値を書き換える」方針を維持する。
  textarea.setRangeText(text, start, end, 'end');
  textarea.focus();

  // React が購読する input イベントを発火させ、MaterialState へ反映させる
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
}
