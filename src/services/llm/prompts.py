"""小説執筆・設定生成用のプロンプトテンプレート。"""

from __future__ import annotations

NOVEL_SYSTEM_PROMPT = """あなたはプロのWeb小説家および編集者です。
読者を惹きつける魅力的な描写、テンポの良い会話、感情を揺さぶるストーリーテリングを得意としています。
指定されたジャンル・キャラクター設定・前話の文脈を踏まえ、高品質なWeb小説本文を執筆してください。

【執筆ルール】
1. 視点と文体を統一し、臨場感あふれる情景描写と心理描写を行ってください。
2. キャラクターの性格・能力・口調の設定を忠実に守ってください。
3. 指定されたレーティング・ジャンルの作風を遵守してください。
4. 出力は本文のみとし、「承知しました」「以下が本文です」等の挨拶・メタ発言は一切含めないでください。
"""

NOVEL_USER_PROMPT_TEMPLATE = """【ジャンル】: {genre}
【主人公設定】:
- 名前: {char_name}
- 性格・特徴: {char_personality}
- 特殊能力・スキル: {char_ability}

【前話までのあらすじ / 文脈】:
{history_context}

【今回の執筆シーン / 前話の末尾】:
{current_chapter}

上記の情報を元に、続く魅力的な本文を執筆してください。
"""

SUGGESTIONS_PROMPT_TEMPLATE = """以下の小説本文の展開を踏まえ、次の話（エピソード）で起こりうる魅力的な展開の提案（Chips用）を3つ、箇条書きで短く提示してください。

【本文】:
{chapter_text}

【出力形式】
- 提案1
- 提案2
- 提案3
"""

GRAPH_EXTRACTION_SYSTEM_PROMPT = """あなたは高度な物語解析・ナレッジグラフ抽出システムです。
入力された小説の章本文を分析し、登場するエンティティ（人物、場所、アイテム、出来事）と、それらの間の関係性を正確に抽出してJSON形式で出力してください。

【抽出ルール】
1. 人物(Character)の生死状態、現在の居場所、所持アイテム、他者への感情/関係性を漏れなく抽出してください。
2. 重要な伏線や出来事(Event)、特殊な能力・アイテム(Item)の獲得や移動を逃さないでください。
3. 出力は必ず指定されたJSONスキーマに従ってください。
"""

GRAPH_EXTRACTION_USER_PROMPT = """以下の小説の章テキストから、エンティティと関係性を抽出してください。

【本文】:
{text}
"""

NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE = """【ジャンル】: {genre}
【主人公設定】:
- 名前: {char_name}
- 性格・特徴: {char_personality}
- 特殊能力・スキル: {char_ability}

{style_bias_section}

【GraphRAG: 確定している世界観・人物相関・アイテム状態】:
{graph_context}

【GraphRAG: 過去の関連シーン・伏線】:
{vector_context}

【前話までのダイジェスト】:
{history_context}

【直前のシーン】:
{current_chapter}

上記の確定事実と過去の文脈を決して矛盾させず、指定された【作家性DNA・文体】を忠実に再現して、続く魅力的な本文を執筆してください。
"""

# ---------------------------------------------------------------------------
# STORY_SPINE: 構造指示の段階適用（B8）
#
# `SPINE_QUALITY` で切り替える。**既定は "off"** で、既存書籍の再生成結果を
# 一文字も変えない。段階:
#   off  : 何も注入しない（既存プロンプトとバイト単位で同一）
#   soft : 参考情報として duty を1行足す（既存プロンプトは壊さない）
#   hard : この話で必ず果たすことを義務として指定する
# ---------------------------------------------------------------------------

SPINE_QUALITY_ENV = "SPINE_QUALITY"
SPINE_QUALITY_LEVELS = ("off", "soft", "hard")


def get_spine_quality() -> str:
    """適用レベルを取得する。未知の値・未設定は安全側の "off" に倒す。"""
    import os

    raw = (os.getenv(SPINE_QUALITY_ENV, "off") or "off").strip().lower()
    return raw if raw in SPINE_QUALITY_LEVELS else "off"


def build_spine_section(spine=None, quality: str | None = None, ep_num: int = 1) -> str:
    """プロンプトに注入する構造指示を組み立てる。

    quality が "off" のときは **常に空文字** を返す。空文字を埋めれば
    `NOVEL_USER_PROMPT_WITH_GRAPHRAG_TEMPLATE` の出力は従来と完全に一致する。
    """
    level = (quality or get_spine_quality()).strip().lower()
    if level not in SPINE_QUALITY_LEVELS or level == "off" or spine is None:
        return ""
    try:
        beat = spine.at(ep_num)
    except Exception:
        return ""
    if beat is None:
        return ""

    if level == "soft":
        return f"【構造の参考】{beat.label}: {beat.duty}"
    return (
        f"【この話で必ず果たすこと】{beat.label}（目標テンション {beat.tension:.2f} / "
        f"種別 {beat.artifact}）: {beat.duty}"
    )


def build_spine_summary(spine, max_items: int = 12) -> str:
    """作品全体の構造を1行に圧縮する（プロンプトの構造確定フェーズ用）。"""
    if spine is None or not getattr(spine, "beats", None):
        return ""
    parts = []
    for b in spine.beats[:max_items]:
        span = f"{b.ep_start}" if b.ep_start == b.ep_end else f"{b.ep_start}-{b.ep_end}"
        parts.append(f"{span}話:{b.label}")
    return " / ".join(parts)
