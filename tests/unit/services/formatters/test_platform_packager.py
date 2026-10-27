"""services/formatters: プラットフォーム整形・ルビ/傍点トランスパイル・パッケージ生成。"""

from __future__ import annotations

import io
import zipfile

from src.services.formatters.platform_formatter import PlatformFormatter
from src.services.formatters.ruby_transpiler import PublishPlatform, RubyTranspiler

RUBY = "彼は｜魔法《マジック》を唱えた。"
BOUTEN = "これは《《重要》》だ。"


def test_publish_platform_values():
    assert PublishPlatform.NAROU.value == "narou"
    assert PublishPlatform("kakuyomu") is PublishPlatform.KAKUYOMU


def test_transpile_ruby_targets():
    assert RubyTranspiler.transpile_ruby(RUBY, PublishPlatform.ALPHAPOLIS) == "彼は#魔法(マジック)#を唱えた。"
    assert RubyTranspiler.transpile_ruby(RUBY, PublishPlatform.NAROU) == "彼は|魔法《マジック》を唱えた。"
    assert RubyTranspiler.transpile_ruby(RUBY, "kakuyomu") == "彼は|魔法《マジック》を唱えた。"
    assert RubyTranspiler.transpile_ruby(RUBY, PublishPlatform.AOZORA) == RUBY
    assert RubyTranspiler.transpile_ruby(RUBY, PublishPlatform.KDP_EPUB) == RUBY
    assert RubyTranspiler.transpile_ruby("ルビなし", "narou") == "ルビなし"


def test_transpile_bouten_targets():
    assert RubyTranspiler.transpile_bouten(BOUTEN, "kakuyomu") == BOUTEN
    assert RubyTranspiler.transpile_bouten(BOUTEN, "narou") == "これは|重《・》|要《・》だ。"
    assert RubyTranspiler.transpile_bouten(BOUTEN, "alphapolis") == "これは#重(・)##要(・)#だ。"
    assert RubyTranspiler.transpile_bouten(BOUTEN, "aozora") == "これは［＃傍点］重要［＃傍点終わり］だ。"
    assert RubyTranspiler.transpile_bouten(BOUTEN, "kdp_epub") == BOUTEN


def test_transpile_all_combines():
    out = RubyTranspiler.transpile_all("《《AB》》と｜漢字《ルビ》", "narou")
    assert "|A《・》" in out
    assert "|漢字《ルビ》" in out


def test_normalize_typography_basics():
    out = PlatformFormatter.normalize_typography("  地の文。\r\n\r「セリフ」\n\n\n\n\n次。", "narou")
    assert "　地の文。" in out
    assert "「セリフ」" in out
    assert "\n\n\n" not in out
    assert "\r" not in out


def test_normalize_typography_ellipsis_odd_even():
    assert PlatformFormatter.normalize_typography("待った…", "narou").endswith("……")
    assert PlatformFormatter.normalize_typography("待った……", "narou").endswith("……")
    assert PlatformFormatter.normalize_typography("待った………", "narou").endswith("……")


def test_normalize_typography_all_dialogue_starters():
    for starter in ("「", "『", "（", "(", "【", "［", "[", "〈", "《", "“", '"'):
        out = PlatformFormatter.normalize_typography(f"{starter}台詞", "narou")
        assert out == f"{starter}台詞"


def test_validate_limits_all_platforms():
    long_title = "あ" * 101
    assert PlatformFormatter.validate_limits(long_title, "", "narou")
    assert PlatformFormatter.validate_limits("題", "あ" * 1001, "narou")
    assert PlatformFormatter.validate_limits(long_title, "あ" * 10001, "kakuyomu")
    assert PlatformFormatter.validate_limits(long_title, "", "alphapolis")
    assert PlatformFormatter.validate_limits("題", "あ" * 5000, "kakuyomu") == []
    assert PlatformFormatter.validate_limits("題", "あ", PublishPlatform.KDP_EPUB) == []


def test_format_episode_with_author_notes_variants():
    plain = PlatformFormatter.format_episode_with_author_notes("T", "本文", "narou")
    assert plain["foreword"] == ""
    assert plain["afterword"] == ""
    assert plain["full_text"] == "　本文"
    assert plain["title"] == "T"

    both = PlatformFormatter.format_episode_with_author_notes(
        "T", "本文", "narou", foreword="前", afterword="後"
    )
    assert "【前書き】" in both["full_text"]
    assert "【後書き】" in both["full_text"]
    assert "―" * 20 in both["full_text"]

    after_only = PlatformFormatter.format_episode_with_author_notes(
        "T", "本文", "narou", afterword="後"
    )
    assert "【前書き】" not in after_only["full_text"]
    assert "【後書き】" in after_only["full_text"]


def test_package_for_platform_variants():
    episodes = [
        {"title": "第一話/壱", "content": "本文1", "foreword": "前", "afterword": "後"},
        {"content": "本文2"},
    ]
    data = PlatformFormatter.package_for_platform("作品名", "", episodes, PublishPlatform.NAROU)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "00_作品情報・あらすじ.txt" in names
        assert any(n.startswith("本文/001_") for n in names)
        assert any(n.endswith("002_第2話.txt") for n in names)
        overview = zf.read("00_作品情報・あらすじ.txt").decode("utf-8")
        assert "（あらすじ未設定）" in overview
        assert "投稿先プラットフォーム: narou" in overview
        assert "第1話: 第一話/壱" in overview
        body = zf.read([n for n in names if n.startswith("本文/001_")][0]).decode("utf-8")
        assert "【前書き】" in body

    data2 = PlatformFormatter.package_for_platform("W", "あらすじ", [], "kakuyomu")
    with zipfile.ZipFile(io.BytesIO(data2)) as zf:
        assert zf.namelist() == ["00_作品情報・あらすじ.txt"]


def test_platform_formatter_module_exports():
    from src.services.formatters import platform_formatter as mod

    assert "PlatformFormatter" in mod.__all__
    assert mod.PublishPlatform is PublishPlatform
    assert mod.RubyTranspiler is RubyTranspiler
