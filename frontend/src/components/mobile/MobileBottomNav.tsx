import React from 'react';

interface MobileBottomNavProps {
  activeTab: 'books' | 'plots' | 'writing' | 'settings';
  onTabChange: (tab: 'books' | 'plots' | 'writing' | 'settings') => void;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({ activeTab, onTabChange }) => {
  const tabs = [
    { id: 'books', label: '作品一覧', icon: '📚' },
    { id: 'plots', label: 'プロット', icon: '🗺️' },
    { id: 'writing', label: '執筆・推敲', icon: '✍️' },
    { id: 'settings', label: '設定', icon: '⚙️' },
  ] as const;

  return (
    /*
     * 背景・文字・罫線はすべて CSS 変数で指定する。
     * 以前は `bg-slate-950/95` など Tailwind のダーク固定色で、
     * ライト/セピアテーマでも暗いままだった（R8）。
     */
    <nav
      aria-label="モバイルナビゲーション"
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 backdrop-blur-md px-4 pb-[var(--safe-bottom)] shadow-2xl"
      style={{
        background: "var(--surface-2)",
        borderTop: "1px solid var(--border-color)",
      }}
    >
      <div className="flex items-center justify-around h-[var(--mobile-nav-height)]">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              style={{
                color: isActive ? "var(--accent-purple)" : "var(--text-muted)",
                fontWeight: isActive ? 700 : 400,
              }}
              className="flex flex-col items-center justify-center flex-1 h-full touch-target transition-colors hover:opacity-80"
            >
              <span className="text-lg mb-0.5">{tab.icon}</span>
              <span className="text-[10px] tracking-tight">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
