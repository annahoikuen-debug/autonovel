import React from 'react';
import { ChapterDiffResponse } from '@/types/branches';
import { fetchChapterDiff } from '@/api/branches';

type ChapterDiffViewerProps = {
  chapterNumber: number;
  branchAId: number;
  branchBId: number;
  bookId: number;
  onClose: () => void;
};

export const ChapterDiffViewer: React.FC<ChapterDiffViewerProps> = ({
  chapterNumber,
  branchAId,
  branchBId,
  bookId,
  onClose
}) => {
  const [diffData, setDiffData] = React.useState<ChapterDiffResponse | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isError, setIsError] = React.useState(false);
  const [viewMode, setViewMode] = React.useState<'unified' | 'side-by-side'>('unified');

  // バックエンドは [left, right] のタプル配列を返す。想定外の payload で
  // .map が例外を投げると画面が真っ白になるため、必ず配列であることを保証する。
  const sideBySide: [string, string][] = React.useMemo(() => {
    const raw = diffData?.diff_side_by_side;
    if (!Array.isArray(raw)) return [];
    return raw.map((pair) => {
      if (Array.isArray(pair)) {
        return [String(pair[0] ?? ''), String(pair[1] ?? '')] as [string, string];
      }
      // 旧来の {left, right} 形式に后备する
      const legacy = pair as unknown as { left?: unknown; right?: unknown };
      return [String(legacy.left ?? ''), String(legacy.right ?? '')] as [string, string];
    });
  }, [diffData]);

  React.useEffect(() => {
    const loadDiff = async () => {
      setIsLoading(true);
      setIsError(false);
      try {
        const data = await fetchChapterDiff(bookId, branchAId, branchBId, chapterNumber);
        setDiffData(data);
      } catch (err) {
        console.error('Error fetching chapter diff:', err);
        setIsError(true);
      } finally {
        setIsLoading(false);
      }
    };

    void loadDiff();
  }, [bookId, chapterNumber, branchAId, branchBId]);

  if (isLoading) return <div>Loading diff...</div>;
  if (isError) return <div>Error loading diff</div>;
  if (!diffData) return <div>No diff data available</div>;

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: '8px', boxShadow: '0 4px 20px rgba(0,0,0,0.2)', maxWidth: '90vw', maxHeight: '90vh', overflow: 'auto' }}>
        <div style={{ padding: '16px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>第${chapterNumber}章の差分</h3>
          <div>
            <button
onClick={() => setViewMode('unified')}
               style={{
                 padding: '4px 8px',
                 marginRight: '4px',
                 backgroundColor: viewMode === 'unified' ? 'var(--accent-color)' : 'var(--bg-muted)',
                 border: 'none',
                 borderRadius: '4px',
                 color: viewMode === 'unified' ? 'white' : 'var(--text)',
                 cursor: 'pointer'
               }}
            >
              Unified
            </button>
            <button
onClick={() => setViewMode('side-by-side')}
               style={{
                 padding: '4px 8px',
                 backgroundColor: viewMode === 'side-by-side' ? 'var(--accent-color)' : 'var(--bg-muted)',
                 border: 'none',
                 borderRadius: '4px',
                 color: viewMode === 'side-by-side' ? 'white' : 'var(--text)',
                 cursor: 'pointer'
               }}
            >
              Side-by-Side
            </button>
            <button
onClick={onClose}
               style={{
                 padding: '4px 8px',
                 marginLeft: '8px',
                 backgroundColor: 'var(--accent-color)',
                 color: 'white',
                 border: 'none',
                 borderRadius: '4px',
                 cursor: 'pointer'
               }}
            >
              閉じる
            </button>
          </div>
        </div>
        <div style={{ padding: '16px' }}>
          {viewMode === 'unified' ? (
            <pre style={{ backgroundColor: 'var(--bg-muted)', padding: '12px', borderRadius: '4px', overflow: 'auto' }}>
              {diffData.diff_unified}
            </pre>
          ) : (
            <div style={{ display: 'flex', gap: '16px' }}>
              <div style={{ flex: 1, borderRight: '1px solid var(--border-color)' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>ブランチ A</div>
                <pre style={{ backgroundColor: 'var(--bg-muted)', padding: '12px', borderRadius: '4px', height: '400px', overflow: 'auto' }}>
                  {sideBySide.map((pair, index) => (
                    <div key={index}>{pair[0]}</div>
                  ))}
                </pre>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>ブランチ B</div>
                <pre style={{ backgroundColor: 'var(--bg-muted)', padding: '12px', borderRadius: '4px', height: '400px', overflow: 'auto' }}>
                  {sideBySide.map((pair, index) => (
                    <div key={index}>{pair[1]}</div>
                  ))}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
