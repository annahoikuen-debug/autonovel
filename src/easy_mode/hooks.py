"""
改善案1・2 用フック制御モジュール。

- 序盤フックエンジン (OpeningBooster / score_cliffhanger) を EasyModePipeline に配線
- タイトル・キャッチコピーCTR採点 (score_title_ctr / score_catchphrase_ctr) を配線

フラグ ENABLE_SEQ_HOOK_WIRING / ENABLE_CTR_WIRING が False の間は no-op であり、
現行挙動とバイト同一を維持する。
"""

from __future__ import annotations


from src.config.kakuyomu_ranking_presets import KAKUYOMU_RANKING_PRESETS
from src.config.kakuyomu_syntax_patterns import OPTIMAL_LENGTH_MAX
from src.engine.narrative.opening_booster_service import OpeningBoosterService
from src.infrastructure.config.settings import settings
from src.integrations.marketing.catchphrase_scorer import score_catchphrase_ctr
from src.integrations.marketing.ctr_scorer import score_title_ctr
from src.models.seq_hook import CTRMetrics, HookMetrics


def should_apply_hook(ep_num: int) -> bool:
    """エピソード番号が1〜3話かつフラグONの場合にフックエンジンを適用する。"""
    if not settings.ENABLE_SEQ_HOOK_WIRING:
        return False
    return 1 <= ep_num <= 3


def evaluate_and_maybe_rewrite(text: str, ep_num: int) -> tuple[str, HookMetrics | None]:
    """
    テキストの章末引きを採点し、平穏（peaceful）ならリライト指令を付与して返す。

    Returns:
        (テキスト, HookMetrics | None) — フラグOFFまたは非対象エピソードなら (text, None)
    """
    if not should_apply_hook(ep_num):
        return text, None

    service = OpeningBoosterService(target_eps=[1, 2, 3])
    evaluation = service.evaluate_tail(ep_num, text)

    metrics = HookMetrics(
        ep_num=ep_num,
        hook_type=evaluation.hook_type.value,
        score=evaluation.score,
        requires_rewrite=evaluation.requires_rewrite,
        reason=evaluation.reason,
        tail_sentence=evaluation.tail_sentence,
    )

    if evaluation.requires_rewrite:
        directive = service.generate_rewrite_directive(evaluation)
        text = text + directive

    return text, metrics


def build_hook_directive(metrics: HookMetrics) -> str:
    """HookMetrics からリライト指令文字列を生成する。"""
    if not metrics.requires_rewrite:
        return ""
    return (
        f"\n\n【🚨序盤クリフハンガー強制リライト指令】\n"
        f"現在の結末判定: {metrics.hook_type} (スコア: {metrics.score})\n"
        f"理由: {metrics.reason}\n"
        f"指示: エピソード末尾を即座に「危機 (crisis)」「衝撃の真実 (shocking_truth)」「反撃の狼煙 (triumph_trigger)」のいずれかで締めくくってください。"
    )


def evaluate_ctr(
    title: str,
    catchphrase: str | None = None,
) -> CTRMetrics | None:
    """
    タイトル・キャッチコピーのCTR採点を実行する。

    Returns:
        CTRMetrics | None — フラグOFFなら None
    """
    if not settings.ENABLE_CTR_WIRING:
        return None

    title_info = score_title_ctr(title)
    title_score = float(title_info.get("score", 0.0)) if isinstance(title_info, dict) else 0.0
    syntax_type = str(title_info.get("syntax_type", "一般")) if isinstance(title_info, dict) else "一般"

    catchphrase_score = 0.0
    catchphrase_needs_improvement = False
    if catchphrase:
        catchphrase_score = float(score_catchphrase_ctr(catchphrase))
        catchphrase_needs_improvement = catchphrase_score < 60.0

    title_needs_improvement = title_score < 60.0

    return CTRMetrics(
        title_score=title_score,
        catchphrase_score=catchphrase_score,
        title_needs_improvement=title_needs_improvement,
        catchphrase_needs_improvement=catchphrase_needs_improvement,
        syntax_type=syntax_type,
    )


def generate_ctr_suggestions(
    title: str,
    genre: str,
    syntax_type: str,
) -> list[str]:
    """
    トレンド構文に基づくタイトル改善案を3案生成する。

    現在はテンプレートベースで生成。LLMは呼ばない（コスト・レイテンシ回避）。
    """
    suggestions: list[str] = []

    if syntax_type == "追放ざまぁ":
        suggestions = [
            f"【追放】{genre}の最強{title}、勘違いされてざまぁ返し",
            f"実は最強の{genre}主人公、追放されて無双する",
            f"追放された{genre}チート、元の仲間をざまぁして成り上がる",
        ]
    elif syntax_type == "勘違い無双":
        suggestions = [
            f"【勘違い】{genre}の主人公、周囲が勝手に神格化して無双",
            f"{genre}で勘違い無双、実は最強だった件について",
            f"勘違いされる{genre}チート、気づけば最強",
        ]
    elif syntax_type == "無自覚無双":
        suggestions = [
            f"【無自覚】{genre}の主人公、最強なのに気づかないまま無双",
            f"{genre}で無自覚無双、周囲が騒然とする",
            f"無自覚な{genre}チート、気づけば最強",
        ]
    else:
        # 一般：パワーワード＋対比構造を付与した3案
        suggestions = [
            f"【{genre}】{title} 〜最強の逆転〜",
            f"{title} 〜実は〜",
            f"{genre}の{title} 〜成り上がり〜",
        ]

    # 最適文字数範囲（35〜55字）を意識して短縮・調整
    adjusted: list[str] = []
    for s in suggestions:
        if len(s) > OPTIMAL_LENGTH_MAX:
            s = s[: OPTIMAL_LENGTH_MAX - 1] + "…"
        adjusted.append(s)

    return adjusted[:3]


# 改善案4: GENRE_REGISTRY の preset_key → KAKUYOMU_RANKING_PRESETS のキー対応。
# 「確実に同義と言える対応」のみマップする。未対応キーはタグ提案なし（空リスト）。
# 誤ったジャンルのタグを提示しないため、推測ベースの近似マップは意図的に避けている。
_TAG_PRESET_ALIASES: dict[str, str] = {
    "cheat_tensei": "cheat_tensei",
    "aku_reijo": "villainess",
    "dungeon_admin": "dungeon_stream",
    "modern_cheat": "modern_dungeon",
    "zarma": "cheat_tensei",
}


def generate_tag_suggestions(genre: str, keywords: list[str] | None = None) -> list[str]:
    """
    UI ジャンルからカクヨム推奨タグ候補を生成する（改善案4）。

    第1候補は KAKUYOMU_RANKING_PRESETS の recommended_tags。
    keywords があれば追加候補として統合する（重複除去・最大10件）。

    Returns:
        list[str] — フラグOFFまたはプリセット未解決ジャンルなら空リスト
    """
    if not settings.ENABLE_TAG_WIRING:
        return []

    from config.story_spine.genre_registry import resolve_preset_key

    preset_key = resolve_preset_key(genre)
    if preset_key is None:
        return []

    alias = _TAG_PRESET_ALIASES.get(preset_key)
    if alias is None:
        return []

    preset = KAKUYOMU_RANKING_PRESETS.get(alias)
    if preset is None:
        return []

    tags = list(preset.recommended_tags)
    for kw in keywords or []:
        kw = kw.strip()
        if kw and kw not in tags:
            tags.append(kw)

    return tags[:10]


__all__ = [
    "should_apply_hook",
    "evaluate_and_maybe_rewrite",
    "build_hook_directive",
    "evaluate_ctr",
    "generate_ctr_suggestions",
    "generate_tag_suggestions",
]
