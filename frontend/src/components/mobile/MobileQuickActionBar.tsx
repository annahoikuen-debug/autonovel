import React from 'react';

interface MobileQuickActionBarProps {
  onInsertText: (text: string) => void;
  onAiContinue?: () => void;
  onProofread?: () => void;
}

interface QuickAction {
  label: string;
  /** 本文へ差し込む文字列 */
  insert?: string;
  /** 発火時に呼び出す実処理（未提供なら描画しない） */
  action?: () => void;
  isSpecial?: boolean;
  /** テスト用の識別子 */
  testId: string;
}

/**
 * モバイル下部のクイック操作バー。
 *
 * **描画する操作は必ず実処理を持つ。**
 * 以前は `onAiContinue` / `onProofread` が未接続でもボタンを描画していたため、
 * 押しても本文も状態も何も変わらずトーストだけが出ていた（＝嘘の導線）。
 * ここではコールバックが渡されていない操作は **描画しない** ことで、
 * 「押せるのに何も起きない」状態を構造的に排除している。
 */
export const MobileQuickActionBar: React.FC<MobileQuickActionBarProps> = ({
  onInsertText,
  onAiContinue,
  onProofread,
}) => {
  const actions: QuickAction[] = [
    { label: '「」', insert: '「」', testId: 'quick-insert-brackets' },
    { label: '……', insert: '……', testId: 'quick-insert-ellipsis' },
    { label: '――', insert: '――', testId: 'quick-insert-dash' },
    { label: '　全角空', insert: '　', testId: 'quick-insert-ideographic-space' },
  ];

  // 実処理が渡されたものだけを並べる
  if (onAiContinue) {
    actions.push({ label: '🤖 続き', action: onAiContinue, isSpecial: true, testId: 'quick-ai-continue' });
  }
  if (onProofread) {
    actions.push({ label: '✨ 校正', action: onProofread, isSpecial: true, testId: 'quick-proofread' });
  }

  return (
    // 背景・罫線は CSS 変数で指定し、ライト/セピアテーマでも読めるようにする（R8）。
    // 以前は Tailwind のダーク固定色を使っていた。
    <div
      className="md:hidden fixed bottom-[var(--mobile-nav-height)] left-0 right-0 z-30 backdrop-blur-md px-3 py-1.5 flex items-center gap-1.5 overflow-x-auto shadow-lg"
      style={{
        background: "var(--surface-2)",
        borderTop: "1px solid var(--border-color)",
      }}
    >
      {actions.map((act) => (
        <button
          key={act.testId}
          type="button"
          data-testid={act.testId}
          onClick={() => {
            if (act.action) {
              act.action();
            } else if (act.insert) {
              onInsertText(act.insert);
            }
          }}
          style={{
            background: act.isSpecial ? "var(--accent-purple)" : "var(--surface-1)",
            color: act.isSpecial ? "#fff" : "var(--text-main)",
            border: act.isSpecial ? "none" : "1px solid var(--border-color)",
            fontWeight: act.isSpecial ? 600 : 500,
          }}
          className="px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap touch-target transition-colors shadow-sm hover:opacity-85"
        >
          {act.label}
        </button>
      ))}
    </div>
  );
};
