"""
formatters/erotic_censor.py
プラットフォーム別の伏字（shading）変換フォーマッター。
リファクタリング済み: 固定dict → config/platform_censorship_rules.py 参照
"""

from typing import Dict, List

from config.erotic_direct_mappings import DIRECT_TO_METAPHOR
from config.erotic_platform_presets import get_preset
from config.erotic_vocabulary import get_vocabulary_for_tier
from config.platform_censorship_rules import get_censorship_rules


def apply_censorship(text: str, preset_name: str = "kakuyomu_romance") -> str:
    """
    プリセットに基づいて伏字変換を適用する。

    変換ルールは config/platform_censorship_rules.py で管理される。
    """
    preset = get_preset(preset_name)
    mode = preset.get("censorship_mode", "heavy")

    if mode == "none":
        return text

    rules = get_censorship_rules(preset_name)
    result = text
    for rule in rules:
        src = rule["src"]
        dst = rule["dst"]
        result = result.replace(src, dst)

    return result


# ティア名を直接 preset_name として受け付けるためのマッピング
_PRESET_MAX_INTENSITY = {"mild": 1, "moderate": 2, "full": 3, "intense": 5}


def check_content_policy(text: str, preset_name: str = "kakuyomu_romance") -> None:
    """
    テキストに規制違反表現が含まれていないかチェックする。
    違反があれば ValueError を発生させて書き出しをブロックする。

    Args:
        text: チェック対象テキスト
        preset_name: プラットフォームプリセット名（デフォルト "kakuyomu_romance"）

    Raises:
        ValueError: 違反表現が検出された場合
    """
    if preset_name in _PRESET_MAX_INTENSITY:
        max_intensity = _PRESET_MAX_INTENSITY[preset_name]
        allowed_tier = preset_name
    else:
        preset = get_preset(preset_name)
        max_intensity = preset.get("max_intensity", 2)
        allowed_tier = preset.get("allowed_vocabulary_tier", "mild")

    # 各ティアの語彙を取得（ティアの有効性担保および許容範囲の確立）
    get_vocabulary_for_tier(allowed_tier)

    # 直接表現の検出: DIRECT_TO_METAPHOR のキーがテキストに含まれるか
    violations: List[str] = [expr for expr in DIRECT_TO_METAPHOR.keys() if expr in text]

    # セーフティ範囲（intensity 1-2 / mild）では直接表現を禁止する
    if max_intensity <= 2 and violations:
        joined = ", ".join(violations)
        raise ValueError(
            f"Content policy violation: preset '{preset_name}' "
            f"(max_intensity={max_intensity}, tier={allowed_tier}) "
            f"prohibits direct expressions: {joined}"
        )


def generate_censored_filename(original: str) -> str:
    """元ファイル名から伏字版ファイル名を生成する。"""
    if original.endswith(".txt"):
        return original.replace(".txt", "_censored.txt")
    return f"{original}_censored"


# 後方互換性: 旧 CENSORSHIP_TABLE は廃止済み
# 旧テーブルユーザーは get_censorship_rules("kakuyomu_romance") に移行すること
CENSORSHIP_TABLE: Dict[str, str] = {}
