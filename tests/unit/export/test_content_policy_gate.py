"""
tests/unit/export/test_content_policy_gate.py

コンテンツポリシーチェック (formatters.erotic_censor.check_content_policy) のユニットテスト。

P4 原則（赤→緑）に従い作成。
- 赤: formatters/erotic_censor に check_content_policy が未実装のため ImportError で失敗
- 緑: N4-1 で check_content_policy が実装された後、ValueError の送出/非送出が期待通りになる

テスト契約 (N4-1 実装が満たすべきインターフェース):
  from formatters.erotic_censor import check_content_policy
  check_content_policy(text: str, preset_name: str = "mild") -> None
    違反時: ValueError を送出
    非違反時: 何も返さず正常終了
  preset_name: "mild" / "moderate" / "full" / "intense"
"""

from __future__ import annotations

import pytest

from formatters.erotic_censor import check_content_policy

# --- テスト対象テキスト ---

DIRECT_TEXT = "二人はベッドでセックスをし、絶頂を迎えた。"
MILD_DIRECT_TEXT = "二人はキスをした。"  # 強度 1 の直接表現
STRICT_TRIGGER_TEXT = "二人はキスをし、セックスをした。"  # 強度 1 と 3 の直接表現
SAFE_TEXT = "二人は手を繋いで公園を散歩した。"


def test_content_policy_blocks_direct_expression():
    """直接表現（"セックス" など）を含むテキストで ValueError が発生する。"""
    with pytest.raises(ValueError):
        check_content_policy(DIRECT_TEXT, preset_name="mild")


def test_content_policy_blocks_direct_expression_default_preset():
    """デフォルト preset (mild) でも直接表現はブロックされる。"""
    with pytest.raises(ValueError):
        check_content_policy(DIRECT_TEXT)


def test_content_policy_allows_safe_text():
    """官能的な直接表現を含まないテキストは ValueError なしで通過する。"""
    check_content_policy(SAFE_TEXT, preset_name="mild")
    check_content_policy(SAFE_TEXT, preset_name="moderate")
    check_content_policy(SAFE_TEXT, preset_name="full")
    check_content_policy(SAFE_TEXT, preset_name="intense")


@pytest.mark.parametrize("preset_name", ["mild", "moderate", "full", "intense"])
def test_content_policy_all_preset_names_accept_safe_text(preset_name: str):
    """全 preset で安全なテキストは通過する。"""
    check_content_policy(SAFE_TEXT, preset_name=preset_name)


def test_content_policy_strict_preset():
    """厳しい preset (max_intensity が低い) ほど多くの表現が違反となる。"""
    # mild (max 1): "キス"(1) は通過、"セックス"(3) は違反 -> ValueError
    with pytest.raises(ValueError):
        check_content_policy(STRICT_TRIGGER_TEXT, preset_name="mild")
    # moderate (max 2): "セックス"(3) は依然違反 -> ValueError
    with pytest.raises(ValueError):
        check_content_policy(STRICT_TRIGGER_TEXT, preset_name="moderate")
    # full (max 3): "セックス"(3) も通過 -> ValueError なし
    check_content_policy(STRICT_TRIGGER_TEXT, preset_name="full")


def test_content_policy_lenient_preset():
    """緩い preset (max_intensity が高い) では通過する。"""
    check_content_policy(DIRECT_TEXT, preset_name="full")   # max 3 >= "セックス"(3)
    check_content_policy(DIRECT_TEXT, preset_name="intense")  # max 5


def test_content_policy_value_error_message():
    """ValueError のメッセージに違反表現が含まれる。"""
    with pytest.raises(ValueError, match="セックス"):
        check_content_policy(DIRECT_TEXT, preset_name="mild")


def test_content_policy_unknown_preset_falls_back_to_mild():
    """未知の preset は安全側 (mild) にフォールバックする。"""
    with pytest.raises(ValueError):
        check_content_policy(DIRECT_TEXT, preset_name="nonexistent_preset")
