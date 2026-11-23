"""
改善案8: カクヨムランキング上位を狙う初心者向けプリセットデータ。

フラグ ENABLE_ONBOARDING_KAKUYOMU_MODE が OFF の間は、
現行挙動とバイト同一を維持する。
"""

from __future__ import annotations

from pydantic import BaseModel


class KakuyomuRankingPreset(BaseModel):
    """カクヨム上位入りしやすいジャンル・タグ・タイトル構文・あらすじテンプレート。"""

    genre: str
    recommended_tags: list[str]
    title_patterns: list[str]
    synopsis_template: str
    target_word_count_per_ep: int
    update_frequency_recommendation: str


KAKUYOMU_RANKING_PRESETS: dict[str, KakuyomuRankingPreset] = {
    "cheat_tensei": KakuyomuRankingPreset(
        genre="異世界転生",
        recommended_tags=[
            "異世界転生",
            "チート",
            "成り上がり",
            "ざまぁ",
            "追放",
        ],
        title_patterns=[
            "【追放】〜されたので、〜",
            "実は世界最強の〜、勘違いされて無双",
            "転生したら最強チート持ちでした",
        ],
        synopsis_template=(
            "理不尽な追放にあった主人公が、隠されたチート能力を覚醒。\n"
            "元の仲間をざまぁしながら、新天地で無双する成り上がり物語。"
        ),
        target_word_count_per_ep=3000,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
    "villainess": KakuyomuRankingPreset(
        genre="悪役令嬢",
        recommended_tags=[
            "悪役令嬢",
            "婚約破棄",
            "溺愛",
            "ざまぁ",
            "逆転",
        ],
        title_patterns=[
            "婚約破棄された悪役令嬢は、〜で逆転する",
            "破滅フラグを回避して、隣国王子に溺愛される",
        ],
        synopsis_template=("乙女ゲームの悪役令嬢に転生した主人公が、\n破滅フラグを回避し、周囲の溺愛を勝ち取る物語。"),
        target_word_count_per_ep=2500,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
    "dungeon_stream": KakuyomuRankingPreset(
        genre="ダンジョン配信",
        recommended_tags=[
            "ダンジョン",
            "配信",
            "現代ダンジョン",
            "無自覚無双",
            "バズ",
        ],
        title_patterns=[
            "底辺配信者が隠し部屋で最強スキル覚醒",
            "同接1人から始めるダンジョン配信、気づけばトレンド1位",
        ],
        synopsis_template=(
            "ダンジョン配信で同接1人の絶望的な配信者が、\n"
            "隠し部屋でユニークスキルを覚醒。配信切り忘れでバズり、無双する。"
        ),
        target_word_count_per_ep=2800,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
    "modern_dungeon": KakuyomuRankingPreset(
        genre="現代ダンジョン",
        recommended_tags=[
            "現代ダンジョン",
            "ハンター",
            "成り上がり",
            "チート",
            "モンスターハンター",
        ],
        title_patterns=[
            "現代ダンジョンで覚醒したFランクハンターが無双する",
            "最弱スキルだと思っていたが、実は最強だった件",
        ],
        synopsis_template=(
            "現代に出現したダンジョンで、Fランクハンターの主人公が\n隠れた最強スキルを覚醒し、成り上がる物語。"
        ),
        target_word_count_per_ep=2800,
        update_frequency_recommendation="毎日1話（21:00頃）",
    ),
}


def list_presets() -> list[KakuyomuRankingPreset]:
    """全プリセットをリストで返す（フラグ制御は呼び出し側で行う）。"""
    return list(KAKUYOMU_RANKING_PRESETS.values())


def get_preset(key: str) -> KakuyomuRankingPreset | None:
    """キーでプリセットを取得する。"""
    return KAKUYOMU_RANKING_PRESETS.get(key)


__all__ = [
    "KakuyomuRankingPreset",
    "KAKUYOMU_RANKING_PRESETS",
    "list_presets",
    "get_preset",
]
