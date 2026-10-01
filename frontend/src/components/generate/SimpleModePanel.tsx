import React, { useEffect, useState } from "react";
import { Modal } from "../common/Modal";
import { Button } from "../common/Button";
import type { CharacterParams as Character } from "../../types";
import type { GenerationState } from "../../types";
import { GENRE_OPTIONS, FALLBACK_GENRE_OPTIONS, GenreOption } from "../../constants/genres";
import { fetchStylePresets } from "../../api/styleApi";
import type { StylePresetSummary } from "../../types/style";

/** 文体プリセットのフォールバック（API 未起動・失敗時の選択肢） */
const FALLBACK_STYLE_PRESETS: Array<{ id: string; label: string }> = [
  { id: "auto", label: "AIにおまかせ（標準）" },
  { id: "style_web_standard", label: "Web小説（読みやすい文体）" },
  { id: "style_light_novel", label: "ライトノベル（会話中心）" },
  { id: "style_dark_fantasy", label: "ダークファンタジー" },
];

export interface SpineTemplateCard {
  card_id?: string;
  id?: string;
  label: string;
  pattern: string;
  length: string;
  market: string;
  style_key?: string;
  description?: string;
}

export interface SimpleModePanelProps {
  character?: Character;
  setCharacter?: React.Dispatch<React.SetStateAction<Character>>;
  llmConfig?: any;
  setLlmConfig?: React.Dispatch<React.SetStateAction<any>>;
  yonkomaEnabled?: boolean;
  setYonkomaEnabled?: React.Dispatch<React.SetStateAction<boolean>>;
  generationState?: GenerationState;
  /**
   * 執筆を開始する。`styleKey` は画面で選んだ文体プリセット ID。
   *
   * 以前は引数なしだったため、文体選択が生成処理まで届かない状態だった。
   * 「選んだ設定が反映される」ことを型で保証するため引数として受け取る。
   */
  startGeneration?: (styleKey?: string) => void;
  cancelGeneration?: (taskId: string | null) => void;
  isStreaming?: boolean;
  startStreaming?: (styleKey?: string) => void;
  cancelStreaming?: () => void;
  isPaused?: boolean;
  resumeStreaming?: () => void;
  pauseStreaming?: () => void;
  streamOutput?: string;
  isBusy?: boolean;
  targetEpisodes?: number;
  setTargetEpisodes?: React.Dispatch<React.SetStateAction<number>>;
  contentLengthLimit?: number;
  setContentLengthLimit?: React.Dispatch<React.SetStateAction<number>>;
  currentChapterText?: string;
  setCurrentChapterText?: React.Dispatch<React.SetStateAction<string>>;
  onMessage?: (msg: string) => void;
  onRunGacha?: () => void;
  onRunDigest?: () => void;
  isGachaLoading?: boolean;
  isDigestLoading?: boolean;
}

export function SimpleModePanel(props: SimpleModePanelProps = {}) {
  const [showStudioPeek, setShowStudioPeek] = useState(false);
  const [showCustomConfig, setShowCustomConfig] = useState(false);

  // 内部状態フォールバック（propsが未指定でも動作保証）
  const [localChar, setLocalChar] = useState<Character>({
    name: "アルト",
    personality: "熱血・正義感が強い",
    ability: "古代魔導剣術",
    genre: "HighFantasy",
  });
  const [localEpisodes, setLocalEpisodes] = useState<number>(20);
  const [localContentLength, setLocalContentLength] = useState<number>(2000);
  const [localChapterText, setLocalChapterText] = useState<string>("");

  const character = props.character ?? localChar;
  const setCharacter = props.setCharacter ?? setLocalChar;
  const targetEpisodes = props.targetEpisodes ?? localEpisodes;
  const setTargetEpisodes = props.setTargetEpisodes ?? setLocalEpisodes;
  const contentLengthLimit = props.contentLengthLimit ?? localContentLength;
  const setContentLengthLimit = props.setContentLengthLimit ?? setLocalContentLength;
  const currentChapterText = props.currentChapterText ?? localChapterText;
  const setCurrentChapterText = props.setCurrentChapterText ?? setLocalChapterText;

  const generationState = props.generationState ?? { isGenerating: false, statusText: "", error: null };
  const isStreaming = props.isStreaming ?? false;
  const isBusy = props.isBusy ?? false;
  const streamOutput = props.streamOutput ?? "";

  // STORY_SPINE 構造テンプレートカード・ジャンル・長さ定義
  const [cards, setCards] = useState<SpineTemplateCard[]>([]);
  const [lengths, setLengths] = useState<any[]>([]);
  const [genreOptions, setGenreOptions] = useState<GenreOption[]>(GENRE_OPTIONS);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  /**
   * 文体プリセット。
   *
   * 以前は内部キー（`style_web_standard` など）を直接打つテキストボックスで、
   * 初見の利用者には理解できず、しかも値を API へ渡していないため変更しても
   * 生成結果に影響しなかった。ここでは読みやすい選択式に変更している。
   */
  const [styleKey, setStyleKey] = useState<string>("auto");
  const [stylePresets, setStylePresets] = useState<Array<{ id: string; label: string }>>(
    FALLBACK_STYLE_PRESETS,
  );

  // 文体プリセットをバックエンドから取得する（失敗時は静的フォールバックを維持）
  useEffect(() => {
    let isMounted = true;
    void fetchStylePresets()
      .then((presets: StylePresetSummary[]) => {
        if (!isMounted || presets.length === 0) return;
        setStylePresets(
          presets.map((p) => ({ id: p.id, label: p.name })),
        );
      })
      .catch(() => {
        // API 未起動時はフォールバックの選択肢をそのまま使う
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    fetch("/api/config/planning_options")
      .then((res) => res.json())
      .then((data) => {
        if (!isMounted) return;
        if (data.cards) {
          const rawCards = Array.isArray(data.cards) ? data.cards : Object.values(data.cards);
          setCards(rawCards);
        }
        if (data.lengths) {
          const rawLengths = Array.isArray(data.lengths) ? data.lengths : Object.values(data.lengths);
          setLengths(rawLengths);
        }
        if (data.genres) {
          const rawGenres = Array.isArray(data.genres) ? data.genres : Object.values(data.genres);
          const mapped = rawGenres.map((g: any) => ({
            value: g.key || g.value,
            label: g.label || g.name || g.key,
            presetKey: g.preset_key ?? null,
            pattern: g.pattern ?? null,
          }));
          if (mapped.length > 0) setGenreOptions(mapped);
        }
      })
      .catch(() => {
        // API未起動時はローカルフォールバックを維持
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectCard = (card: SpineTemplateCard) => {
    setSelectedCardId(card.card_id ?? null);

    // 話数の自動入力 (length.eps_range の中央または既定値)
    let eps = 40;
    const lenObj = lengths.find((l) => (l.key || l.id) === card.length);
    if (lenObj?.eps_range && Array.isArray(lenObj.eps_range)) {
      eps = Math.round((lenObj.eps_range[0] + lenObj.eps_range[1]) / 2);
    } else if (card.length === "web_volume") {
      eps = 40;
    } else if (card.length === "short") {
      eps = 2;
    }
    setTargetEpisodes(eps);

    // 1話文字数の自動入力
    if (lenObj?.chars_per_ep && Array.isArray(lenObj.chars_per_ep)) {
      setContentLengthLimit(Math.round((lenObj.chars_per_ep[0] + lenObj.chars_per_ep[1]) / 2));
    } else if (card.length === "web_volume") {
      setContentLengthLimit(2500);
    } else if (card.length === "short") {
      setContentLengthLimit(4000);
    }

    // 文体スタイルの自動入力
    if (card.style_key) {
      setStyleKey(card.style_key);
    }

    // GENRE_REGISTRY に基づくジャンル解決
    const matchedGenre =
      genreOptions.find((g) => g.pattern === card.pattern) ||
      FALLBACK_GENRE_OPTIONS.find((g) => g.pattern === card.pattern);
    if (matchedGenre) {
      setCharacter((prev: Character) => ({ ...prev, genre: matchedGenre.value }));
    }
  };

  return (
    <div>
      {/* Tier 1: 構造テンプレートカード一覧 */}
      {cards.length > 0 && (
        <div className="form-group" style={{ marginBottom: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <label className="label" style={{ fontWeight: 700, margin: 0 }}>
              🎯 構造テンプレートカード（選ぶだけで即執筆）
            </label>
            <button
              type="button"
              className="btn btn-link"
              style={{ fontSize: "0.8rem", padding: 0 }}
              onClick={() => setShowCustomConfig(!showCustomConfig)}
            >
              {showCustomConfig ? "▲ かんたん表示に戻す" : "⚙️ 詳細設定をカスタマイズ"}
            </button>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
              gap: "8px",
              maxHeight: "220px",
              overflowY: "auto",
              padding: "4px",
            }}
          >
            {cards.map((card) => {
              const cid = card.card_id;
              const isSelected = selectedCardId === cid;
              return (
                <div
                  key={cid}
                  onClick={() => handleSelectCard(card)}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "8px",
                    border: isSelected ? "2px solid var(--accent-cyan, #06b6d4)" : "1px solid rgba(255,255,255,0.1)",
                    backgroundColor: isSelected ? "rgba(6, 182, 212, 0.15)" : "rgba(255,255,255,0.03)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  <span className="card-title" style={{ display: "block", fontWeight: 600, fontSize: "0.9rem" }}>{card.label}</span>
                  <span className="card-meta" style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted, #888)", marginTop: "2px" }}>
                    {card.length} / {card.market}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 目標話数入力 */}
      <div className="form-group">
        <label className="label" htmlFor="target-episodes">目標話数</label>
        <input
          id="target-episodes"
          type="number"
          className="input"
          value={targetEpisodes}
          onChange={(e) => setTargetEpisodes(parseInt(e.target.value, 10) || 1)}
          min={1}
          max={300}
        />
      </div>

      {/* 1話あたりの目標文字数 */}
      <div className="form-group">
        <label className="label">1話あたりの目標文字数</label>
        <input
          type="number"
          className="input"
          value={contentLengthLimit}
          onChange={(e) => setContentLengthLimit(parseInt(e.target.value, 10) || 2000)}
          step={100}
          min={500}
          max={10000}
        />
      </div>

      {/*
        文体スタイルは内部キーを叩く実装だったため、選択式に変更。
        label は htmlFor で入力に紐付け、select には説明を添えて理解しやすくしている。
      */}
      <div className="form-group">
        <label className="label" htmlFor="style-preset-select">文体の雰囲気</label>
        <select
          id="style-preset-select"
          className="select"
          value={styleKey}
          onChange={(e) => setStyleKey(e.target.value)}
          data-testid="style-preset-select"
          title="AIが使う文章の特徴（語尾・長短・テンポ）を決めます"
        >
          {stylePresets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.label}
            </option>
          ))}
        </select>
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
          文章の語尾や文章の長さの偏りを決めます。迷ったら「AIにおまかせ」で大丈夫です。
        </p>
      </div>

      {/* 作品ジャンル選択 */}
      <div className="form-group">
        <label className="label">作品ジャンル・レーティング</label>
        <select
          className="select"
          value={character.genre}
          onChange={(e) => setCharacter((prev: Character) => ({ ...prev, genre: e.target.value }))}
          title="GENRE_REGISTRY に基づく標準化ジャンル"
        >
          {genreOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label className="label">主人公の名前</label>
        <input
          className="input"
          value={character.name}
          onChange={(e) => setCharacter((prev: Character) => ({ ...prev, name: e.target.value }))}
          title="Studioモードではキャラクターの詳細プロファイルと関係性マッピングが可能です"
        />
      </div>

      <div className="form-group">
        <label className="label">性格・特徴</label>
        <input
          className="input"
          value={character.personality}
          onChange={(e) => setCharacter((prev: Character) => ({ ...prev, personality: e.target.value }))}
          title="StudioモードではAIによる性格分析と一貫性チェックが行われます"
        />
      </div>

      <div className="form-group">
        <label className="label">特殊能力・スキル</label>
        <input
          className="input"
          value={character.ability}
          onChange={(e) => setCharacter((prev: Character) => ({ ...prev, ability: e.target.value }))}
          title="Studioモードでは能力バランス分析とプロットへの組み込み提案が行われます"
        />
      </div>

      {/* カスタマイズ詳細（話数・目標文字数） */}
      {showCustomConfig && (
        <div
          style={{
            padding: "12px",
            backgroundColor: "rgba(255,255,255,0.02)",
            borderRadius: "8px",
            border: "1px dashed rgba(255,255,255,0.15)",
            marginBottom: "16px",
          }}
        >
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="label">1話あたりの目標文字数</label>
            <input
              type="number"
              className="input"
              value={contentLengthLimit}
              onChange={(e) => setContentLengthLimit(parseInt(e.target.value, 10) || 2000)}
              step={100}
              min={500}
              max={10000}
            />
          </div>
        </div>
      )}

      <div className="form-group">
        <label className="label">執筆対象の冒頭 / 前話プロンプト</label>
        <textarea
          className="textarea"
          rows={4}
          value={currentChapterText}
          onChange={(e) => setCurrentChapterText(e.target.value)}
          title="Studioモードではリアルタイム品質スコア表示、シーン別プレビュー、AIによる詳細な推敲サポートが利用できます"
        />
      </div>

      {/*
        生成の進捗をテキストで常時見せる。
        以前は `generationState.statusText` を描画する箇所が無く、
        ボタンが「執筆中...」に変わるだけだったため、
        「いま何が起きているのか」が分からないまま待つしかなかった。
      */}
      <div
        role="status"
        aria-live="polite"
        data-testid="generation-status"
        style={{
          minHeight: "20px",
          marginBottom: "8px",
          fontSize: "0.85rem",
          color: "var(--accent-cyan)",
          fontWeight: 600,
        }}
      >
        {generationState.isGenerating
          ? (generationState.statusText || "🪄 執筆しています。そのままお待ちください…")
          : ""}
      </div>

      {generationState.error && (
        <div
          role="alert"
          data-testid="generation-error"
          style={{
            marginBottom: "12px",
            padding: "8px 12px",
            borderRadius: "8px",
            border: "1px solid rgba(239,68,68,0.4)",
            background: "rgba(239,68,68,0.12)",
            color: "var(--accent-danger, #ef4444)",
            fontSize: "0.85rem",
          }}
        >
          ❌ {generationState.error}
        </div>
      )}

      {/*
        主CTAを 1 つに絞り、残りのサブ操作は視覚的に控えめにする。
        以前は 5 つのボタンが同列・同サイズで「どれを押すべきか」判断できなかった。
      */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        <button
          className="btn btn-primary"
          style={{
            flex: 2,
            backgroundColor: "var(--accent-cyan)",
            borderColor: "var(--accent-cyan)",
            color: "#000",
            fontWeight: 700,
            minWidth: "200px",
            minHeight: "48px",
            fontSize: "1.05rem",
          }}
          onClick={() => props.startGeneration?.(styleKey)}
          disabled={isBusy}
          data-testid="btn-easy-generate"
          title="選んだ設定でそのまま本文をつくります。まずこれを押してください"
        >
          {generationState.isGenerating ? "🪄 執筆中..." : "🪄 かんたん執筆開始"}
        </button>

        <button
          className="btn btn-secondary"
          style={{ flex: 1, minWidth: "120px" }}
          onClick={() => props.startStreaming?.(styleKey)}
          disabled={isBusy}
          data-testid="btn-streaming-generate"
          title="一文字ずつ書き進めながら表示します。書き始めの感覚を確かめたいときに"
        >
          {isStreaming ? "⚡ 執筆中..." : "⚡ 逐次執筆"}
        </button>

        {generationState.isGenerating && !isStreaming && (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => props.cancelGeneration?.(generationState.currentTaskId)}
            title="Studioモードでは、生成の一時停止と詳細なログ確認が利用できます"
          >
            ⏹ 中止
          </button>
        )}

        <button
          type="button"
          className="btn btn-outline-secondary"
          style={{ flex: 1, minWidth: "120px", fontSize: "0.9rem" }}
          onClick={() => setShowStudioPeek(true)}
          disabled={isBusy}
          data-testid="btn-studio-peek"
        >
          👀 Studio機能チラ見せ
        </button>

        <Modal
          isOpen={showStudioPeek}
          onClose={() => setShowStudioPeek(false)}
          title="👀 Studio でできること"
          testId="studio-peek-modal"
          closeBtnTestId="btn-close-studio-peek"
          maxWidth={520}
        >
          <ul style={{ paddingLeft: "20px", lineHeight: 1.9, color: "var(--text-main)" }}>
            <li>🖼️ 場面ごとのマルチメディアプレビューと画像生成</li>
            <li>🔍 AI 診断・品質スコアの詳細表示</li>
            <li>📖 プロットビジュアライザーと Beat シート編集</li>
            <li>🎭 キャラクター設定の詳細編集</li>
          </ul>
          <p
            style={{
              marginTop: "16px",
              fontSize: "0.9rem",
              color: "var(--text-muted)",
              lineHeight: 1.7,
            }}
          >
            ここまで書いた内容はそのまま残ります。実際に使うときは「Studio」タブから移動できます。
          </p>
          <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end", marginTop: "20px" }}>
            <Button variant="secondary" onClick={() => setShowStudioPeek(false)}>
              閉じる
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setShowStudioPeek(false);
                window.location.assign("/studio");
              }}
              data-testid="btn-studio-peek-goto"
            >
              Studio を開く →
            </Button>
          </div>
        </Modal>

        <button
          className="btn btn-outline-primary"
          style={{ flex: 1, minWidth: "120px", borderColor: "var(--accent-cyan)", color: "var(--accent-cyan)" }}
          onClick={props.onRunGacha}
          disabled={isBusy || props.isGachaLoading}
          title="3つの物語案をランダムに生成します"
        >
          {props.isGachaLoading ? "🎲 生成中..." : "🎲 企画ガチャ"}
        </button>
        <button
          className="btn btn-outline-secondary"
          style={{ flex: 1, minWidth: "120px" }}
          onClick={props.onRunDigest}
          disabled={isBusy || props.isDigestLoading}
          title="選択したプランからダイジェストを生成します"
        >
          {props.isDigestLoading ? "📖 解析中..." : "📖 ダイジェスト"}
        </button>
      </div>

      {isStreaming && (
        <div style={{ marginTop: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
            <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--accent-cyan)" }}>
              ⚡ リアルタイム執筆プレビュー
            </span>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #888)" }}>
              {streamOutput.length.toLocaleString()} 文字
            </span>
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono, 'Consolas', 'Menlo', monospace)",
              fontSize: "0.8rem",
              lineHeight: 1.6,
              backgroundColor: "rgba(0, 0, 0, 0.4)",
              border: "1px solid var(--accent-cyan, #0ff)",
              borderRadius: "8px",
              padding: "12px",
              maxHeight: "200px",
              overflowY: "auto",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              boxShadow: "inset 0 2px 6px rgba(0,0,0,0.4)",
            }}
          >
            {streamOutput || (
              <span style={{ color: "var(--text-muted, #888)", fontStyle: "italic" }}>生成中...</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default SimpleModePanel;