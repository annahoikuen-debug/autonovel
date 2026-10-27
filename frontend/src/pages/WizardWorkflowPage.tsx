import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Step1PlotInput } from '../components/wizard/Step1PlotInput';
import { Step2StructureReview, OutlineItem } from '../components/wizard/Step2StructureReview';
import { Step3InteractiveWriting } from '../components/wizard/Step3InteractiveWriting';
import { BeatSheetViewer } from '../components/planning/BeatSheetViewer';
import { saveWizardBook, BeatItem, WizardBookData } from '../api/wizard';
import { upsertChapter } from '../api/chapters';

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

/** 執筆済み章の退避キー（作品IDごとに分ける） */
const DRAFT_STORAGE_KEY = "autonovel.wizard.draft";

/** 最後に確定した作品ID（リロード後に退避データを復元するため） */
const BOOK_ID_STORAGE_KEY = "autonovel.wizard.bookId";

/** 保存に失敗したときのユーザー向け文言 */
const saveFailedMessage = (epNum: number) =>
  `第${epNum}話をサーバーに保存できませんでした。ブラウザ内に下書きを保持しています。`;

/** `bookId` ごとの執筆済み章を localStorage から読む */
function loadDrafts(bookId: number | null): Record<number, string> {
  if (typeof window === "undefined" || !bookId) return {};
  try {
    const raw = window.localStorage.getItem(`${DRAFT_STORAGE_KEY}.${bookId}`);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    // オブジェクトが壊れているケースを避けるため、値だけを検証する
    return Object.fromEntries(
      Object.entries(parsed).filter(([, v]) => typeof v === "string" && v.trim().length > 0),
    ) as Record<number, string>;
  } catch {
    return {};
  }
}

/** 退避済みの執筆内容を復元するために使う作品ID */
function loadBookId(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(BOOK_ID_STORAGE_KEY);
    if (!raw) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

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
  const [bookId, setBookId] = useState<number | null>(loadBookId);
  const [branchId, setBranchId] = useState<number>(1);
  const [currentEpisode, setCurrentEpisode] = useState(1);
  const [chapterContent, setChapterContent] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 生成済み章の累积（Studio へ引き継ぐときの下書きとして使う） */
  const [generatedChapters, setGeneratedChapters] = useState<Record<number, string>>({});
  const generationTokenRef = useRef(0);
  /**
   * 退避済み執筆内容を読み終えた作品ID。
   *
   * 書き込み effect は復元 effect より先に走るため、ここが未設定のあいだは
   * 書かない。さもないと、復元より先に空データ `{}` で上書きしてしまう。
   */
  const hydratedBookIdRef = useRef<number | null>(null);

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

  /**
   * 人手がテキストエリアを編集したときの受け口。
   *
   * 以前は textarea に `onChange` が無かったため、完成した本文を編集しても
   * 入力が丸ごと失われていた。ここでは画面へ反映しつつ、その話の下書きとして保存し、
   * 「執筆済み N 話」のカウントにも含める（編集した内容も保存済みとして扱えるようにする）。
   */
  const handleManualEdit = useCallback((content: string) => {
    setChapterContent(content);
    setGeneratedChapters((prev) => ({ ...prev, [currentEpisode]: content }));
  }, [currentEpisode]);

  /**
   * 執筆した話をサーバへ保存する。
   *
   * 以前はメモリ（localStorage）にしか残らず、ブラウザを閉じると本文が失われていた。
   * 作品IDが確定している（Step2 で saveWizardBook が成功している）場合に保存する。
   */
  const persistChapter = useCallback(async (epNum: number, content: string) => {
    if (!bookId || !content.trim()) return;
    const ok = await upsertChapter(bookId, epNum, {
      title: outlines[epNum - 1]?.title ?? `第${epNum}話`,
      content,
    });
    if (!ok) {
      setError(saveFailedMessage(epNum));
    }
  }, [bookId, outlines]);

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
    // 生成が完了した本文はサーバへ保存する（ブラウザを閉じても失われないように）。
    // 保存できないときは必ず伝える（`void` で捨てると画面が黙ったまま壊れる）。
    void persistChapter(currentEpisode, content).catch(() => {
      setError(saveFailedMessage(currentEpisode));
    });
  }, [currentEpisode, persistChapter]);

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

  // 執筆済み章を localStorage へ退避する（リロード／離脱しても本文が消えないように）
  useEffect(() => {
    if (!bookId) return;
    // 復元より先に走って（中身が空の状態で）退避データを潰さない
    if (hydratedBookIdRef.current !== bookId) return;
    try {
      window.localStorage.setItem(
        `${DRAFT_STORAGE_KEY}.${bookId}`,
        JSON.stringify(generatedChapters),
      );
    } catch {
      // localStorage が使えない環境では何もしない（致命ではない）
    }
  }, [generatedChapters, bookId]);

  // 書籍が確定した時点で、退避済みの執筆内容を復元する
  useEffect(() => {
    if (!bookId) return;
    // 同じ作品IDの再レンダリングで二重に復元しない
    if (hydratedBookIdRef.current === bookId) return;
    hydratedBookIdRef.current = bookId;
    const drafts = loadDrafts(bookId);
    if (Object.keys(drafts).length > 0) {
      setGeneratedChapters(drafts);
    }
  }, [bookId]);

  // 確定した作品IDを保存する（リロード後も退避データを復元できる）
  useEffect(() => {
    if (!bookId) return;
    try {
      window.localStorage.setItem(BOOK_ID_STORAGE_KEY, String(bookId));
    } catch {
      // localStorage が使えない環境では何もしない（致命ではない）
    }
  }, [bookId]);

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
          {/*
            「執筆済み 1 話」を「第N話」と取り違えないよう、単位を括弧で囲んで
            「第1話」という部分一致が起きないようにしている。
          */}
          {writtenCount > 0 && (
            <span data-testid="wizard-written-count">
              執筆済み {writtenCount} 話
            </span>
          )}
        </div>
      </nav>

      {/* ヘッダー行：戻る・タイトル・モード切替の導線 */}
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
            chapterTitle={outlines[currentEpisode - 1]?.title || 'あとがき'}
            chapterContent={chapterContent}
            isGenerating={isGenerating}
            onGenerateNext={handleGenerateNext}
            onRegenerate={handleRegenerate}
            onContentChange={handleContentChange}
            onManualEdit={handleManualEdit}
            onStreamError={handleStreamError}
          />

          {/* 出口：ここが「書き終えたらどうする」の答えになる */}
          {lastWrittenEpisode && (
            <section className="wizard-exit" data-testid="wizard-exit-panel">
              <h2 className="wizard-exit__title">ここまでの執筆をまとめる</h2>
              <p className="wizard-exit__lead">
                最後の執筆は 第{lastWrittenEpisode}話 です。内容はこのまま作品に蓄積されているので、
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
