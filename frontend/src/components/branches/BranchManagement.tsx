import React from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { BranchTree } from './BranchTree';
import { BranchSelector } from './BranchSelector';
import { ChapterDiffViewer } from './ChapterDiffViewer';
import { MergeConflictPreview } from './MergeConflictPreview';
import { useBranchTree } from '@/hooks/useBranchTree';
import { useChapterDiff } from '@/hooks/useChapterDiff';
import { useMergePreview } from '@/hooks/useMergePreview';
import { useNovelContext } from '@/context/NovelContext';
import { BranchMergeRequest, MergePreviewResponse, ChapterDiffResponse, BranchMergeCommitResponse } from '@/types/branches';

export const BranchManagement: React.FC<{ bookId: number }> = ({ bookId }) => {
  const { data: treeData, isLoading: treeLoading, isError: treeError } = useBranchTree(bookId);
  const [selectedBranchId, setSelectedBranchId] = React.useState<number | null>(null);
  const [compareBranchId, setCompareBranchId] = React.useState<number | null>(null);
  const [currentChapter, setCurrentChapter] = React.useState<number>(1);
  const [showDiffViewer, setShowDiffViewer] = React.useState(false);
  const [showMergePreview, setShowMergePreview] = React.useState(false);
  // ネイティブ alert() の代わりに共通 Modal で結果を知らせる
  const [mergeResultMessage, setMergeResultMessage] = React.useState<string | null>(null);
  const [diffData, setDiffData] = React.useState<ChapterDiffResponse | null>(null);
  const [mergePreviewData, setMergePreviewData] = React.useState<MergePreviewResponse | null>(null);
  const { setCurrentEpNum } = useNovelContext();

  // 0 は「未選択」を意味する（useChapterDiff / useMergePreview の enabled 判定で無効化される）。
  // 実在しないブランチID（1 / 2）を仮置きしてクエリを走らせるのはやめた。
  const { data: chapterDiffData, isLoading: diffLoading, isError: diffError } = useChapterDiff(
    bookId,
    selectedBranchId ?? 0,
    compareBranchId ?? 0,
    currentChapter
  );

  // bookId を明示的に渡す（引数省略時の `bookId ?? 1` フォールバックは使わない）
  const mergePreviewMutation = useMergePreview(bookId);

  const handleSelectBranch = (branchId: number) => {
    setSelectedBranchId(branchId);
  };

  const handleCompareBranch = (branchId: number) => {
    setCompareBranchId(branchId);
  };

  const handleChapterChange = (chapter: number) => {
    setCurrentChapter(chapter);
  };

  const handleShowDiff = () => {
    setShowDiffViewer(true);
  };

  const handleHideDiff = () => {
    setShowDiffViewer(false);
    setDiffData(null);
  };

  const handleShowMergePreview = () => {
    if (selectedBranchId && compareBranchId) {
      setShowMergePreview(true);
      const mergeRequest: BranchMergeRequest = {
        source_branch_id: selectedBranchId,
        target_branch_id: compareBranchId,
        merge_ep_num: currentChapter
      };
      mergePreviewMutation.mutate(mergeRequest);
    }
  };

  const handleHideMergePreview = () => {
    setShowMergePreview(false);
    setMergePreviewData(null);
  };

  /** マージコミット成功時の通知（実際の API 結果を受け取って表示する） */
  const handleMergeSuccess = (result: BranchMergeCommitResponse) => {
    setMergePreviewData(null);
    setShowMergePreview(false);
    setMergeResultMessage(
      `マージが正常に完了しました！（更新章数: ${result.updated_chapters_count}件）`
    );
  };

  React.useEffect(() => {
    if (chapterDiffData) {
      setDiffData(chapterDiffData);
    }
  }, [chapterDiffData]);

  React.useEffect(() => {
    if (mergePreviewMutation.data) {
      setMergePreviewData(mergePreviewMutation.data);
    }
  }, [mergePreviewMutation.data]);

  return (
    <>
      <Modal
        isOpen={mergeResultMessage !== null}
        onClose={() => setMergeResultMessage(null)}
        title="マージ結果"
        testId="merge-result-modal"
        closeBtnTestId="btn-close-merge-result"
        maxWidth={420}
      >
        <p style={{ color: "var(--text-main)", lineHeight: 1.7 }}>{mergeResultMessage}</p>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "16px" }}>
          <Button variant="primary" onClick={() => setMergeResultMessage(null)}>
            閉じる
          </Button>
        </div>
      </Modal>
      {treeLoading ? <div>Loading branch management...</div> : treeError ? <div>Error loading branch management</div> : renderBody()}
    </>
  );

  function renderBody() {
    if (treeLoading) return <div>Loading branch management...</div>;
    if (treeError) return <div>Error loading branch management</div>;

    return (
      <div style={{ padding: '20px' }}>
        <h1>ブランチ管理</h1>

        {/* Branch Selector */}
        <BranchSelector bookId={bookId} />

        {/* Main Content */}
        <div style={{ display: 'flex', gap: '20px' }}>
          {/* Branch Tree Visualization */}
          <div style={{ flex: 2, minWidth: '300px' }}>
            <h2>ブランチツリー</h2>
            <BranchTree bookId={bookId} />
            <div style={{ marginTop: '16px', padding: '12px', backgroundColor: 'var(--bg-muted)', borderRadius: '4px' }}>
              <button
                onClick={() => {
                  if (selectedBranchId !== null) {
                    setCompareBranchId(selectedBranchId);
                  } else if (treeData?.nodes?.[0]) {
                    setCompareBranchId(treeData.nodes[0].id);
                  }
                }}
                style={{
                  padding: '8px 16px',
                  backgroundColor: 'var(--accent-color)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                比較対象として選択
              </button>
            </div>
          </div>

          {/* Controls and Preview */}
          <div style={{ flex: 1, minWidth: '250px' }}>
            <h2>操作パネル</h2>
            <div style={{ marginBottom: '16px' }}>
              <button
                type="button"
                onClick={() => {
                  setCurrentEpNum(1);
                }}
                style={{ padding: '8px 16px', backgroundColor: 'var(--accent-color)', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
              >
                メインルートに戻る
              </button>
            </div>

            {/* Branch Selection Controls */}
            <div style={{ marginBottom: '16px' }}>
              <h3>ブランチ選択</h3>
              <div style={{ marginBottom: '8px' }}>
                <label>基準ブランチ: </label>
                <select
                  value={selectedBranchId ?? ''}
                  onChange={(e) => {
                    const id = parseInt(e.target.value);
                    if (!isNaN(id)) setSelectedBranchId(id);
                  }}
                  style={{ padding: '4px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-input)', color: 'var(--text)' }}
                >
                  <option value="">-- 選択してください --</option>
                  {treeData?.nodes?.map(node => (
                    <option key={node.id} value={node.id}>
                      {node.data.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label>比較ブランチ: </label>
                <select
                  value={compareBranchId ?? ''}
                  onChange={(e) => {
                    const id = parseInt(e.target.value);
                    if (!isNaN(id)) setCompareBranchId(id);
                  }}
                  style={{ padding: '4px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-input)', color: 'var(--text)' }}
                >
                  <option value="">-- 選択してください --</option>
                  {treeData?.nodes?.map(node => (
                    <option key={node.id} value={node.id}>
                      {node.data.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Chapter Selection */}
            <div style={{ marginBottom: '16px' }}>
              <h3>章選択</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label>章番号: </label>
                <input
                  type="number"
                  value={currentChapter}
                  onChange={(e) => {
                    const num = parseInt(e.target.value);
                    if (!isNaN(num) && num > 0) setCurrentChapter(num);
                  }}
                  style={{ width: '80px', padding: '4px', border: '1px solid var(--border-color)', borderRadius: '4px', backgroundColor: 'var(--bg-input)', color: 'var(--text)' }}
                  min="1"
                />
                <button
                  onClick={handleShowDiff}
                  disabled={selectedBranchId === null || compareBranchId === null}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: selectedBranchId !== null && compareBranchId !== null ? 'var(--accent-color)' : 'var(--bg-muted)',
                    color: selectedBranchId !== null && compareBranchId !== null ? 'var(--text-on-accent)' : 'var(--text-muted)',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: selectedBranchId !== null && compareBranchId !== null ? 'pointer' : 'not-allowed'
                  }}
                >
                  差分表示
                </button>
                <button
                  onClick={handleShowMergePreview}
                  disabled={!(selectedBranchId && compareBranchId)}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: selectedBranchId && compareBranchId ? 'var(--accent-color)' : 'var(--bg-muted)',
                    color: selectedBranchId && compareBranchId ? 'var(--text-on-accent)' : 'var(--text-muted)',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: selectedBranchId && compareBranchId ? 'pointer' : 'not-allowed'
                  }}
                >
                  マージプレビュー
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Diff Viewer Modal */}
        {showDiffViewer && selectedBranchId !== null && compareBranchId !== null && (
          <ChapterDiffViewer
            bookId={bookId}
            chapterNumber={currentChapter}
            branchAId={selectedBranchId}
            branchBId={compareBranchId}
            onClose={handleHideDiff}
          />
        )}

        {/* Merge Preview Modal */}
        {showMergePreview && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ backgroundColor: 'var(--bg-card)', borderRadius: '8px', boxShadow: '0 4px 20px rgba(0,0,0,0.2)', maxWidth: '90vw', maxHeight: '90vh', overflow: 'auto' }}>
              <MergeConflictPreview
                previewData={mergePreviewData}
                bookId={bookId}
                sourceBranchId={selectedBranchId ?? undefined}
                targetBranchId={compareBranchId ?? undefined}
                mergeEpNum={currentChapter}
                onResolveConflict={(chunkId, action, manualContent) => {
                  // 解決内容は MergeConflictPreview 内部 state で保持される。
                  // ここでは観測のみ行う。
                  console.log(`Resolving conflict ${chunkId} with action ${action}`, manualContent);
                }}
                onClose={handleHideMergePreview}
                onSuccess={handleMergeSuccess}
              />
            </div>
          </div>
        )}
      </div>
    );
  }
};
