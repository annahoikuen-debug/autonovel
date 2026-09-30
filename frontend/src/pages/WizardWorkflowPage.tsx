import React, { useState, useCallback, useRef } from 'react';
import { Step1PlotInput } from '../components/wizard/Step1PlotInput';
import { Step2StructureReview, OutlineItem } from '../components/wizard/Step2StructureReview';
import { Step3InteractiveWriting } from '../components/wizard/Step3InteractiveWriting';
import { BeatSheetViewer } from '../components/planning/BeatSheetViewer';
import { saveWizardBook, BeatItem, WizardBookData } from '../api/wizard';

type PlotData = {
  title: string;
  genre: string;
  synopsis: string;
  targetChapters: number;
  cheatScale: number;
  growthCurve: string;
  systemAssist: number;
  costSeverity: number;
  beats: BeatItem[];
  patternKey?: string;
};

const STEPS = [
  { n: 1 as const, label: '方針を決める', hint: 'どんな物語にするか' },
  { n: 2 as const, label: '構成を確かめる', hint: '各話の骨組みを点検' },
  { n: 3 as const, label: '執筆する', hint: '本文をつくる' },
];

export interface WizardWorkflowPageProps {
  /**
   * 別ページへ移るための関数。
   * 既定は window.location による遷移で、Router なしでも動く（単体テスト 대응）。
   */
  onNavigate?: (path: string) => void;
}

export const WizardWorkflowPage: React.FC<WizardWorkflowPageProps> = ({ onNavigate }) => {
  // Router が必要にならないよう、既定は通常のページ遷移を使う。
  const navigate = useCallback(
    (path: string) => {
      if (onNavigate) onNavigate(path);
      else if (typeof window !== 'undefined') window.location.assign(path);
    },
    [onNavigate]
  );
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [plotData, setPlotData] = useState<PlotData | null>(null);
  const [outlines, setOutlines] = useState<OutlineItem[]>([]);
  const [bookId, setBookId] = useState<number | null>(null);
  const [branchId, setBranchId] = useState<number>(1);
  const [currentEpisode, setCurrentEpisode] = useState(1);
  const [chapterContent, setChapterContent] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 生成済み章の累积（Studio へ引き継ぐときの下書きとして使う） */
  const [generatedChapters, setGeneratedChapters] = useState<Record<number, string>>({});
  const generationTokenRef = useRef(0);

  const convertBeatsToOutlines = (beats: BeatItem[]): OutlineItem[] => {
    return beats.map((beat) => ({
      episode: beat.episode,
      title: beat.title,
      outline: beat.outline,
      cliffhangerType: beat.cliffhanger_type as OutlineItem['cliffhangerType'],
      sensoryFocus: beat.sensory_focus || [],
      foreshadowingNotes: beat.foreshadowing_notes || '',
    }));
  };

  const handleStep1Complete = (data: PlotData) => {
    setPlotData(data);
    // Convert the API-generated beats into outline items for Step 2
    setOutlines(convertBeatsToOutlines(data.beats));
    setCurrentStep(2);
  };

  const handleStep2Confirm = async (confirmedOutlines: OutlineItem[]) => {
    if (!plotData) return;
    setIsSaving(true);
    setError(null);

    try {
      // Save the book data to DB and transition to Step 3
      const wizardData: WizardBookData = {
        title: plotData.title,
        genre: plotData.genre,
        synopsis: plotData.synopsis,
        target_chapters: plotData.targetChapters,
        cheat_scale: plotData.cheatScale,
        growth_curve: plotData.growthCurve,
        system_assist: plotData.systemAssist,
        cost_severity: plotData.costSeverity,
        beats: confirmedOutlines.map((outline) => ({
          episode: outline.episode,
          title: outline.title,
          outline: outline.outline,
          cliffhanger_type: outline.cliffhangerType || 'New Crisis',
          sensory_focus: outline.sensoryFocus || [],
          foreshadowing_notes: outline.foreshadowingNotes || '',
        })),
      };

      const result = await saveWizardBook(wizardData);
      setBookId(result.book_id);
      setBranchId(result.branch_id);
      setOutlines(confirmedOutlines);
      setCurrentStep(3);
      setCurrentEpisode(1);
      setChapterContent('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '書籍データの保存に失敗しました';
      setError(message);
      // Still allow proceeding to Step 3 in offline/demo mode
      setCurrentStep(3);
      setCurrentEpisode(1);
      setChapterContent('');
    } finally {
      setIsSaving(false);
    }
  };

  /**
   * 次の一話を執筆する。
   *
   * 以前は「話数をインクリメントするだけ」で本文が state に入らず、
   * Step3 が dead-end（本文が画面に出ないまま話数だけ進む状態）になっていた。
   * ここでは「執筆中」を立てて次の話へ進み、本文の到着は
   * {@link handleContentChange}（SSE の `content` を受け取る側）が面倒を見る。
   */
  const handleGenerateNext = useCallback(async () => {
    setIsGenerating(true);
    setChapterContent('');
    generationTokenRef.current += 1;
    setCurrentEpisode((prev) => prev + 1);
  }, []);

  /** Step3 から、完成した本文を受け取る（生成完了時にだけ確定させる） */
  const handleContentChange = useCallback((content: string, done: boolean) => {
    setChapterContent(content);
    if (!done) return;
    setIsGenerating(false);
    setGeneratedChapters((prev) => {
      const next = { ...prev };
      next[currentEpisode] = content;
      return next;
    });
  }, [currentEpisode]);

  /** 同じ話をもう一度書き直す */
  const handleRegenerate = useCallback(() => {
    generationTokenRef.current += 1;
    setChapterContent('');
    setIsGenerating(true);
  }, []);

  /**
   * Step3 のストリームが失敗したときの復旧。
   *
   * ここでは `isGenerating` を必ず落とす。落とさないと
   * 「執筆＆二層監査中...」オーバーレイが永久に回り続け、
   * リテイク／次の一話を執筆する の両方が disabled のまま
   * ページリロードでしか復帰できなくなる。
   */
  const handleStreamError = useCallback(() => {
    setIsGenerating(false);
  }, []);

  /** Step1/2 に戻る（生成済み章は保持する） */
  const handleBack = useCallback(() => {
    if (currentStep === 3) {
      setCurrentStep(2);
    } else if (currentStep === 2) {
      setCurrentStep(1);
    }
  }, [currentStep]);

  const totalSteps = STEPS.length;
  const writtenCount = Object.values(generatedChapters).filter((c) => c.trim().length > 0).length;
  const lastWrittenEpisode = Object.keys(generatedChapters)
    .map(Number)
    .sort((a, b) => b - a)[0];

  return (
    <div className="wizard-page" data-testid="wizard-workflow-page">
      {/* 進捗インジケータ：いまどこにいるかが常に分かる */}
      <nav className="wizard-progress" aria-label="ウィザードの進行状況">
        <ol className="wizard-progress__list">
          {STEPS.map((step) => {
            const state = step.n < currentStep ? 'done' : step.n === currentStep ? 'current' : 'todo';
            return (
              <li
                key={step.n}
                className={`wizard-progress__item wizard-progress__item--${state}`}
                aria-current={state === 'current' ? 'step' : undefined}
                data-testid={`wizard-progress-step-${step.n}`}
              >
                <span className="wizard-progress__dot" aria-hidden>
                  {state === 'done' ? '✓' : step.n}
                </span>
                <span className="wizard-progress__text">
                  <span className="wizard-progress__label">{step.label}</span>
                  <span className="wizard-progress__hint">{step.hint}</span>
                </span>
              </li>
            );
          })}
        </ol>
        <div className="wizard-progress__meta">
          <span data-testid="wizard-progress-count">
            {currentStep} / {totalSteps} ステップ
          </span>
          {writtenCount > 0 && (
            <span data-testid="wizard-written-count">執筆済み {writtenCount} 話</span>
          )}
        </div>
      </nav>

      {/* ヘッダー行：戻る・タイトル・工况切换の導線 */}
      <div className="wizard-toolbar">
        <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
          {currentStep > 1 && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleBack}
              data-testid="wizard-back-btn"
            >
              ← 前のステップ
            </button>
          )}
          <h1 className="wizard-toolbar__title">
            {plotData?.title || "3ステップ共創ウィザード"}
          </h1>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate("/")}
            data-testid="wizard-exit-easy-btn"
          >
            かんたん執筆へ
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(bookId ? `/studio/${bookId}` : '/studio')}
            data-testid="wizard-exit-studio-btn"
          >
            Studio で編集を続ける →
          </button>
        </div>
      </div>

      {error && (
        <div className="wizard-error" role="alert" data-testid="wizard-error">
          {error}
        </div>
      )}

      {currentStep === 1 && <Step1PlotInput onNext={handleStep1Complete} />}
      {currentStep === 2 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <BeatSheetViewer
            bookId={bookId ?? 1}
            patternKey={plotData?.patternKey || 'exile_rise'}
          />
          <Step2StructureReview
            outlines={outlines}
            onBack={() => setCurrentStep(1)}
            onConfirm={handleStep2Confirm}
            onUpdateOutlines={setOutlines}
            isSaving={isSaving}
          />
        </div>
      )}
      {currentStep === 3 && (
        <>
          <Step3InteractiveWriting
            book_id={bookId ?? 0}
            ep_num={currentEpisode}
            branch_id={branchId}
            chapterTitle={outlines[currentEpisode - 1]?.title || '第1話'}
            chapterContent={chapterContent}
            isGenerating={isGenerating}
            onGenerateNext={handleGenerateNext}
            onRegenerate={handleRegenerate}
            onContentChange={handleContentChange}
            onStreamError={handleStreamError}
          />

          {/* 出口：ここが「書き終えたらどうする」の答えになる */}
          {lastWrittenEpisode && (
            <section className="wizard-exit" data-testid="wizard-exit-panel">
              <h2 className="wizard-exit__title">ここまでの執筆をまとめる</h2>
              <p className="wizard-exit__lead">
                第{lastWrittenEpisode}話まで書き上がりました。内容はこのまま作品に蓄積されているので、
                次の作業場所を選んでください。
              </p>
              <div className="wizard-exit__actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleGenerateNext}
                  disabled={isGenerating}
                  data-testid="wizard-continue-btn"
                >
                  もう 1 話書く
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => navigate(bookId ? `/studio/${bookId}` : '/studio')}
                  data-testid="wizard-go-studio-btn"
                >
                  Studio で細部を手入れする →
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
};
