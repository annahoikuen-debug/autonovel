/**
 * 日本語テキストの文体指標の推定.
 *
 * スタイル比較 UI で「実際の本文」を測定するために使う。
 * ここでの値はすべて**実測**であり、定数やダミーではない。
 *
 * なお日本語の文節解析（MeCab 等）はブラウザでは無いため、
 * 体言止め率の判定は語尾の動詞パターンによるヒューリスティックである。
 * 精度の追求が必要な場合はバックエンドの解析結果に差し替えること。
 */

/** 文末の句読点 */
const SENTENCE_ENDERS = "。．！？!?…";
/** 会話文の開始記号 */
const DIALOGUE_OPENERS = ["「", "『", "“", '"', "（", "("];

/**
 * 体言止めと判定するための語尾パターン。
 * 文末がここに含まれない（＝動詞で終わっていない）ものを体言止め候補とする。
 */
const VERBISH_ENDINGS = [
  "る", "た", "う", "い", "す", "だ", "て", "いる", "くる", "いく", "した",
  "です", "ます", "だっ", "ない", "れる", "せる", "とした", "している",
  "があった", "だった", "になる", "だった", "れない", "せる", "ば", "ね", "よ",
];

export interface StyleMetrics {
  /** 文数 */
  sentenceCount: number;
  /** 平均文長（文字/文、句読点と空白を除く） */
  averageSentenceLength: number;
  /** 会話文の比率（0-1） */
  dialogueRatio: number;
  /** 体言止め率の推定（0-1） */
  taigenStopRatio: number;
  /** 総文字数（空白と改行を除く） */
  charCount: number;
}

/** 1 つの文に分割する。句読点で切るが、会話の鉤括弧内の句読点は保持する。 */
export function splitSentences(text: string): string[] {
  const sentences: string[] = [];
  let buffer = "";
  let inQuote = 0;
  let quoteChar = "";

  for (const ch of text) {
    if (quoteChar) {
      if (ch === quoteChar) {
        inQuote -= 1;
        if (inQuote <= 0) {
          quoteChar = "";
          inQuote = 0;
        }
      }
    } else if (ch === "「" || ch === "『") {
      quoteChar = ch === "「" ? "」" : "』";
      inQuote = 1;
    } else if (ch === "“") {
      quoteChar = "”";
      inQuote = 1;
    }

    buffer += ch;

    if (!quoteChar && SENTENCE_ENDERS.includes(ch)) {
      const trimmed = buffer.trim();
      if (trimmed.length > 0) {
        sentences.push(trimmed);
      }
      buffer = "";
    }
  }

  const tail = buffer.trim();
  if (tail.length > 0) {
    sentences.push(tail);
  }
  return sentences;
}

/** 文から句読点・空白・鉤括弧を除いた本文の長さ。 */
function contentLength(sentence: string): number {
  return sentence.replace(/[\s。．、，,！？!?…「」『』“”"'（）()]/g, "").length;
}

/** その文が会話文かどうか（開始記号で始まる、または mostly quoted）。 */
function isDialogue(sentence: string): boolean {
  const stripped = sentence.trimStart();
  if (!stripped) return false;
  const opener = DIALOGUE_OPENERS.find((c) => stripped.startsWith(c));
  if (!opener) return false;
  // 会話文は短めに収まることが多いので、開始記号以外に文字が很少なら会話とみなす
  return contentLength(stripped) >= 2;
}

/** その文が体言止め候補かどうか（語尾が動詞パターンでない）。 */
export function looksLikeTaigenStop(sentence: string): boolean {
  const stripped = sentence
    .replace(/[。．、，,！!?…\s「」『』“”"'（）()]+$/u, "")
    .trim();
  if (contentLength(stripped) < 2) return false;
  if (VERBISH_ENDINGS.some((ending) => stripped.endsWith(ending))) return false;
  return true;
}

/** テキストの文体指標を実測する。 */
export function measureStyleMetrics(text: string): StyleMetrics {
  const clean = (text ?? "").toString();
  const sentences = splitSentences(clean);
  const charCount = clean.replace(/[\s\r\n]/g, "").length;

  if (sentences.length === 0) {
    return {
      sentenceCount: 0,
      averageSentenceLength: 0,
      dialogueRatio: 0,
      taigenStopRatio: 0,
      charCount,
    };
  }

  const totalContent = sentences.reduce((sum, s) => sum + contentLength(s), 0);
  const dialogueCount = sentences.filter(isDialogue).length;
  const taigenCount = sentences.filter(looksLikeTaigenStop).length;

  return {
    sentenceCount: sentences.length,
    averageSentenceLength: totalContent / sentences.length,
    dialogueRatio: dialogueCount / sentences.length,
    taigenStopRatio: taigenCount / sentences.length,
    charCount,
  };
}

/** 実測値を 0-100 のパーセント表示に整える。 */
export function toPercent(ratio: number): number {
  return Math.round(ratio * 100);
}
