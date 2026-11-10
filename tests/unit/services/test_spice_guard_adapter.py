"""Unit tests for src/services/spice_guard_adapter.py."""

from src.services.spice_guard_adapter import SpiceGuardAdapter, SpiceElement, create_spice_guard_adapter


def test_spice_guard_adapter_creation():
    """SpiceGuardAdapter のインスタンス生成テスト。"""
    adapter = create_spice_guard_adapter("fantasy")
    assert adapter is not None
    assert adapter.genre == "fantasy"


def test_spice_guard_adapter_extract_spice():
    """抽出スパイス要素の確認テスト。"""
    adapter = create_spice_guard_adapter("fantasy")
    text = "主人公が酒場で飲みすぎた。暴力的な描写がある。"
    elements = adapter.extract_spice(text)
    assert isinstance(elements, list)


def test_spice_guard_adapter_inject_markers():
    """マーカー注入の確認テスト。"""
    adapter = create_spice_guard_adapter("fantasy")
    text = "テキスト本文"
    elements = [SpiceElement(type="alcohol", text="酒", position=1, priority="high")]
    result = adapter.inject_markers(text, elements)
    assert isinstance(result, str)


def test_spice_guard_adapter_clean_markers():
    """マーカークリーンの確認テスト。"""
    adapter = create_spice_guard_adapter("fantasy")
    text = "テキスト[[スパイク]]本文"
    result = adapter.clean_markers(text)
    assert isinstance(result, str)


def test_spice_guard_adapter_build_rewrite_prompt():
    """リライトプロンプト生成の確認テスト。"""
    adapter = create_spice_guard_adapter("fantasy")
    content = "元の内容"
    improvements = ["改善案1"]
    elements = [SpiceElement(type="alcohol", text="酒", position=1, priority="high")]
    prompt = adapter.build_rewrite_prompt(content, improvements, elements)
    assert isinstance(prompt, str)


def test_spice_guard_adapter_default_genre():
    """デフォルトジャンルでの適切なテーブル読み込みテスト。"""
    adapter = create_spice_guard_adapter("")
    assert adapter is not None


def test_spice_element_creation():
    """SpiceElement の正常系コンストラクタ確認テスト。"""
    element = SpiceElement(type="alcohol", text="酒", position=1, priority="high")
    assert element.type == "alcohol"
    assert element.text == "酒"
    assert element.position == 1
    assert element.priority == "high"


def test_spice_element_default_priority():
    """SpiceElement デフォルトpriority確認テスト。"""
    element = SpiceElement(type="violence", text="暴力", position=1)
    assert element.priority == "medium"


