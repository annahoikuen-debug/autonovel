import { useCallback, useEffect } from 'react';

interface EditorKeybindings {
  zenMode: string;
  aiContinue: string;
  aiProofread: string;
  toggleTheme: string;
  toggleManuscriptGrid: string;
}

interface UseEditorKeybindingsProps {
  onZenModeToggle?: () => void;
  onAiContinue?: () => void;
  onAiProofread?: () => void;
  onToggleTheme?: () => void;
  onToggleManuscriptGrid?: () => void;
  /**
   * Ctrl+Shift+E で「かんたん執筆」へ移るためのコールバック。
   *
   * 以前は NovelContext の `mode` state を書き換えていたが、現在地は URL が
   * 単一の情報源なので、当該 state を変えても画面は移動しなかった（ショートカットが
   * 死んでいた）。呼び出し側から遷移を注入できるようにした。
   */
  onNavigateToEasyMode?: () => void;
  isZenMode?: boolean;
}

export const useEditorKeybindings = ({
  onZenModeToggle,
  onAiContinue,
  onAiProofread,
  onToggleTheme,
  onToggleManuscriptGrid,
  onNavigateToEasyMode,
  isZenMode = false,
}: UseEditorKeybindingsProps) => {
  const keybindings: EditorKeybindings = {
    zenMode: 'F11',
    aiContinue: 'Ctrl+Space',
    aiProofread: 'Ctrl+Enter',
    toggleTheme: 'Ctrl+Shift+T',
    toggleManuscriptGrid: 'Ctrl+Shift+G',
  };

  const handleKeyDown = (event: KeyboardEvent) => {
    // Prevent default browser behavior for our shortcuts
    if (isModifierKey(event)) {
      return;
    }

    // Check for Zen Mode toggle (F11 or Ctrl+B)
    if (event.key === 'F11' || (event.ctrlKey || event.metaKey) && event.key === 'b') {
      event.preventDefault();
      onZenModeToggle?.();
    }
    // Check for AI Continue (Ctrl+Space)
    else if ((event.ctrlKey || event.metaKey) && event.key === ' ') {
      event.preventDefault();
      onAiContinue?.();
    }
    // Check for AI Proofread (Ctrl+Enter)
    else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      onAiProofread?.();
    }
    // Check for Toggle Theme (Ctrl+Shift+T)
    else if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 't') {
      event.preventDefault();
      onToggleTheme?.();
    }
    // Check for Toggle Manuscript Grid (Ctrl+Shift+G)
    else if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'g') {
      event.preventDefault();
      onToggleManuscriptGrid?.();
    }
    // Check for Easy Mode navigation (Ctrl+Shift+E)
    else if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'e') {
      event.preventDefault();
      onNavigateToEasyMode?.();
    }
  };

  const isModifierKey = (event: KeyboardEvent): boolean => {
    return event.key === 'Control' || event.key === 'Meta' ||
           event.key === 'Shift' || event.key === 'Alt';
  };

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onZenModeToggle, onAiContinue, onAiProofread, onToggleTheme, onToggleManuscriptGrid, onNavigateToEasyMode]);

  // Mobile device support - show touch-friendly version of keybindings
  const getMobileKeybindings = () => {
    return {
      zenMode: '📖 集中',
      aiContinue: '💭 続き',
      aiProofread: '🔍 校正',
      toggleTheme: '🎨 テーマ',
      toggleManuscriptGrid: '📄 マス目',
    };
  };

  return {
    keybindings,
    getMobileKeybindings,
  };
};