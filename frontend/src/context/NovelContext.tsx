import React, { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from "react";
import { CharacterParams, GenerationState, ChapterItem, ActiveAuditHighlight, BookItem } from "../types";
import { LineScore } from "../types/quality";
import { LLMConfigOverride } from "../types/easyMode";
import { GeneratedPlotStructure } from "../types/reversePlot";
import { fetchBooks, fetchBookById } from "../api/books";
import { fetchChapters, StoredChapter } from "../api/chapters";

interface NovelContextType {
  character: CharacterParams;
  setCharacter: React.Dispatch<React.SetStateAction<CharacterParams>>;
  currentChapterText: string;
  setCurrentChapterText: React.Dispatch<React.SetStateAction<string>>;
  generationState: GenerationState;
  setGenerationState: React.Dispatch<React.SetStateAction<GenerationState>>;
  selectedBookId: number;
  setSelectedBookId: React.Dispatch<React.SetStateAction<number>>;
  plotStructure: GeneratedPlotStructure | null;
  setPlotStructure: React.Dispatch<React.SetStateAction<GeneratedPlotStructure | null>>;
  activeHighlight: ActiveAuditHighlight | null;
  setActiveHighlight: React.Dispatch<React.SetStateAction<ActiveAuditHighlight | null>>;
  chapters: ChapterItem[];
  setChapters: React.Dispatch<React.SetStateAction<ChapterItem[]>>;
  currentEpNum: number;
  setCurrentEpNum: React.Dispatch<React.SetStateAction<number>>;
  contentLengthLimit: number;
  setContentLengthLimit: React.Dispatch<React.SetStateAction<number>>;
  targetEpisodes: number;
  setTargetEpisodes: React.Dispatch<React.SetStateAction<number>>;
  llmConfig: LLMConfigOverride;
  setLlmConfig: React.Dispatch<React.SetStateAction<LLMConfigOverride>>;
  applySuggestion: (suggestion: string) => void;
  applyDiff: (start: number, end: number, replacement: string) => void;
  syncGenerationToEditor: (output: string) => void;
  updateActiveChapterText: (text: string) => void;
  books: BookItem[];
  selectedBook: BookItem | null;
  isLoadingBooks: boolean;
  refreshBooks: () => Promise<void>;
  lineScores: LineScore[];
  setLineScores: React.Dispatch<React.SetStateAction<LineScore[]>>;
  hoveredNodeSummary: { summary: string; properties: Record<string, any> } | null;
  setHoveredNodeSummary: React.Dispatch<React.SetStateAction<{ summary: string; properties: Record<string, any> } | null>>;
}

const defaultCharacter: CharacterParams = {
  name: "アルト",
  personality: "熱血・正義感が強い",
  ability: "古代魔導剣術",
  genre: "ハイファンタジー (R15)",
};

const defaultGenerationState: GenerationState = {
  isGenerating: false,
  statusText: "",
  suggestions: [],
  currentTaskId: null,
  error: null,
};

const defaultInitialChapters: ChapterItem[] = [
  {
    ep_num: 1,
    title: "第1話 運命の覚醒",
    summary: "主人公アルトが古代の剣を手にし、冒険へ旅立つ。",
    content: "薄暗いダンジョンの中、15歳の青年アルトは古代の剣を手に取った。",
    is_catharsis: false,
    status: "writing",
  },
];

/**
 * サーバの章データを画面用の形へ変換する。
 *
 * サーバ側に状態を持たないため、`status` は本文の有無から決める
 * （本文が空ならまだ執筆前）。`StoredChapter` に `status` が無いまま
 * 描画すると、ステータス色の参照が `undefined` で落ちる。
 */
const toChapterItem = (stored: StoredChapter): ChapterItem => {
  const content = stored.content ?? "";
  return {
    ep_num: stored.ep_num,
    title: stored.title,
    summary: stored.summary,
    content,
    is_catharsis: false,
    status: content.trim().length > 0 ? "writing" : "draft",
  };
};

const NovelContext = createContext<NovelContextType | undefined>(undefined);

export const NovelProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [character, setCharacter] = useState<CharacterParams>(defaultCharacter);
  const [chapters, setChapters] = useState<ChapterItem[]>(defaultInitialChapters);
  const [currentEpNum, setCurrentEpNum] = useState<number>(1);
const [currentChapterText, setCurrentChapterText] = useState<string>(
     defaultInitialChapters[0]?.content ?? ""
   );
  const [generationState, setGenerationState] = useState<GenerationState>(defaultGenerationState);
  const [selectedBookId, setSelectedBookId] = useState<number>(1);
  const [plotStructure, setPlotStructure] = useState<GeneratedPlotStructure | null>(null);
  const [activeHighlight, setActiveHighlight] = useState<ActiveAuditHighlight | null>(null);

  const [contentLengthLimit, setContentLengthLimit] = useState<number>(2000);
  const [targetEpisodes, setTargetEpisodes] = useState<number>(10);
  const [llmConfig, setLlmConfig] = useState<LLMConfigOverride>(() => {
    try {
      const saved = localStorage.getItem("autonovel_llm_config");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const [books, setBooks] = useState<BookItem[]>([]);
  const [lineScores, setLineScores] = useState<LineScore[]>([]);
  const [hoveredNodeSummary, setHoveredNodeSummary] = useState<{ summary: string; properties: Record<string, any> } | null>(null);
  // 共有UI設定（selectedStyleId / customStyleProfile / showApiSettings / showApiKey）は
  // かつてはここで localStorage と同期していたが、**context value に含めていなかった**ため
  // 書き込むだけで読み出す主体が無く、デッドコードになっていた（R4）。
  // 実際の状態は GeneratePanel / SimpleModePanel がローカルに持つため、ここでは持たない。
  const [selectedBook, setSelectedBook] = useState<BookItem | null>(null);
  const [isLoadingBooks, setIsLoadingBooks] = useState<boolean>(false);

  const selectedBookIdRef = useRef(selectedBookId);
  useEffect(() => {
    selectedBookIdRef.current = selectedBookId;
  }, [selectedBookId]);

  const refreshBooks = useCallback(async () => {
    setIsLoadingBooks(true);
    try {
      const data = await fetchBooks();
      const safeData = Array.isArray(data) ? data : [];
      setBooks(safeData);
      const current = safeData.find((b) => b.id === selectedBookIdRef.current);
      setSelectedBook((current || safeData[0]) ?? null);
    } catch (err) {
      console.error("Failed to fetch books:", err);
    } finally {
      setIsLoadingBooks(false);
    }
  }, []);

  // 作品切り替え時にその作品の情報と保存済みの章一覧を取得
  useEffect(() => {
    let cancelled = false;
    const loadChapters = async () => {
      if (!selectedBookId) {
        setSelectedBook(null);
        return;
      }
      setIsLoadingBooks(true);
      try {
        const book = await fetchBookById(selectedBookId);
        if (!cancelled) {
          setSelectedBook(book);
        }
      } catch {
        if (!cancelled) {
          setSelectedBook(null);
        }
      }
      try {
        // サーバに保存済みの章を取り込む。これが無いとリロードで
        // 章の追加/削除/並び替えが全て初期値の 1 話へ戻ってしまう。
        const stored = await fetchChapters(selectedBookId);
        if (cancelled) return;
        setChapters(stored.map(toChapterItem));
      } catch (err) {
        // 読めなかったときは初期表示のままにする（通信不能で本文を消さない）
        console.error("Failed to fetch chapters:", err);
      } finally {
        if (!cancelled) setIsLoadingBooks(false);
      }
    };
    loadChapters();
    return () => { cancelled = true; };
  }, [selectedBookId]);

  // llmConfig 変更時に localStorage へ同期
  useEffect(() => {
    try {
      if (llmConfig && Object.keys(llmConfig).length > 0) {
        localStorage.setItem("autonovel_llm_config", JSON.stringify(llmConfig));
      } else {
        localStorage.removeItem("autonovel_llm_config");
      }
    } catch {
      // ignore storage error
    }
  }, [llmConfig]);

  const isSwitchingEpRef = useRef(false);

  /**
   * `setCurrentChapterText` の updater 内で「いまの本文」を読むためのミラー。
   *
   * updater 関数は純関数でなければならない（React は StrictMode で二重に呼ぶ）。
   * そのため updater の内側から `setChapters` を呼ぶのではなく、
   * 新しい本文を先に確定させてから 2 つの setter を順番に呼ぶ。
   */
  const currentChapterTextRef = useRef(currentChapterText);
  useEffect(() => {
    currentChapterTextRef.current = currentChapterText;
  }, [currentChapterText]);

  // 章切り替え時に該当章のテキストをロード
  useEffect(() => {
    isSwitchingEpRef.current = true;
    const target = chapters.find((c) => c.ep_num === currentEpNum);
    if (target) {
      setCurrentChapterText(target.content);
    }
    const timer = setTimeout(() => {
      isSwitchingEpRef.current = false;
    }, 50);
    return () => clearTimeout(timer);
  }, [currentEpNum]);

  // 本文編集時に chapters 配列の該当章 content も同期
  const updateActiveChapterText = useCallback((textOrUpdater: string | ((prev: string) => string)) => {
    const prev = currentChapterTextRef.current;
    const newText = typeof textOrUpdater === "function" ? textOrUpdater(prev) : textOrUpdater;
    currentChapterTextRef.current = newText;
    setCurrentChapterText(newText);
    setChapters((prevChapters) =>
      prevChapters.map((c) => (c.ep_num === currentEpNum ? { ...c, content: newText } : c))
    );
  }, [currentEpNum]);

  const applySuggestion = useCallback((suggestion: string) => {
    updateActiveChapterText((prev) =>
      prev.trim()
        ? `${prev.trim()}\n\n【展開】${suggestion}`
        : suggestion
    );
  }, [updateActiveChapterText]);

  const applyDiff = useCallback((start: number, end: number, replacement: string) => {
    updateActiveChapterText((prev) => {
      const before = prev.substring(0, start);
      const after = prev.substring(end);
      return `${before}${replacement}${after}`;
    });
  }, [updateActiveChapterText]);

  const syncGenerationToEditor = useCallback((output: string) => {
    if (output) {
      updateActiveChapterText(output);
    }
  }, [updateActiveChapterText]);

  return (
    <NovelContext.Provider
      value={{
        character,
        setCharacter,
        currentChapterText,
        setCurrentChapterText: updateActiveChapterText,
        generationState,
        setGenerationState,
        selectedBookId,
        setSelectedBookId,
        plotStructure,
        setPlotStructure,
        activeHighlight,
        setActiveHighlight,
        chapters,
        setChapters,
        currentEpNum,
        setCurrentEpNum,
        contentLengthLimit,
        setContentLengthLimit,
        targetEpisodes,
        setTargetEpisodes,
        llmConfig,
        setLlmConfig,
        applySuggestion,
        applyDiff,
        syncGenerationToEditor,
        updateActiveChapterText,
        books,
        selectedBook,
        isLoadingBooks,
        refreshBooks,
        lineScores,
        setLineScores,
        hoveredNodeSummary,
        setHoveredNodeSummary,
      }}
    >
      {children}
    </NovelContext.Provider>
  );
};

export function useNovelContext(): NovelContextType {
  const context = useContext(NovelContext);
  if (!context) {
    throw new Error("useNovelContext must be used within a NovelProvider");
  }
  return context;
}
