"""services/marketing: 構文抽出・CTR/キャッチフレーズ採点・エクスポートの補助カバレッジ。"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock

import pytest

from src.services.marketing.catchphrase_scorer import score_catchphrase_ctr
from src.services.marketing.ctr_scorer import score_title_ctr
from src.services.marketing.export_package import MarketingService
from src.services.marketing.trend_syntax_extractor import extract_syntax_features


def test_extract_syntax_features_exile_reversal():
    f = extract_syntax_features("追放されたが世界唯一最強になった")
    assert f["syntax_type"] == "追放ざまぁ"
    assert f["has_contrast"] is True
    assert f["is_optimal_length"] is False
    assert "追放" in f["keywords"]
    assert f["char_count"] == 16


def test_extract_syntax_features_exile_tilde_only():
    assert extract_syntax_features("追放〜")["syntax_type"] == "追放ざまぁ"
    assert extract_syntax_features("追放ざまぁ")["syntax_type"] == "追放ざまぁ"
    assert extract_syntax_features("追放神級")["syntax_type"] == "追放ざまぁ"


def test_extract_syntax_features_misunderstanding_and_reversal():
    f = extract_syntax_features("彼女は黒幕だ")
    assert f["syntax_type"] == "勘違い無双"
    assert f["has_contrast"] is True
    assert extract_syntax_features("実は覚醒")["syntax_type"] == "無自覚無双"
    assert extract_syntax_features("何もない本")["syntax_type"] == "一般"


def test_extract_syntax_features_contrast_tilde_branch():
    f = extract_syntax_features("今更〜実は〜")
    assert f["has_contrast"] is True
    f2 = extract_syntax_features("〜単なる〜")
    assert f2["has_contrast"] is False


def test_extract_syntax_features_optimal_length():
    f = extract_syntax_features("あ" * 40)
    assert f["is_optimal_length"] is True


def test_score_title_ctr_bands():
    long_title = "あ" * 40
    res = score_title_ctr(long_title)
    assert res["char_count"] == 40
    assert res["is_optimal_length"] is True
    assert res["title"] == long_title

    short = score_title_ctr("短")
    assert short["char_count"] == 1

    mid = score_title_ctr("あ" * 25)
    assert 0.0 <= mid["score"] <= 100.0

    over = score_title_ctr("あ" * 100)
    assert over["score"] >= 0.0

    huge = score_title_ctr("あ" * 500)
    assert huge["score"] >= 0.0


def test_score_title_ctr_symbols_and_keywords():
    res = score_title_ctr("【最強】実は〜覚醒【神】")
    assert res["has_contrast"] is True
    assert res["hooks"]
    assert res["score"] > 20.0
    assert score_title_ctr("  spaced  ")["title"] == "spaced"


def test_score_catchphrase_ctr_bands():
    assert score_catchphrase_ctr("あ" * 36) == 0
    assert score_catchphrase_ctr("あ" * 20) >= 40
    assert score_catchphrase_ctr("あ" * 5) < 40
    assert 0 <= score_catchphrase_ctr("あ" * 35) <= 100


def test_score_catchphrase_ctr_power_and_hooks():
    res = score_catchphrase_ctr("「実は」そう言った――！？もう遅い？無双？")
    assert res == 100
    assert score_catchphrase_ctr("") == 20


async def test_export_package_book_data_only():
    svc = MarketingService(repo=None)
    data, name = await svc.create_export_package(
        7,
        {
            "title": "T",
            "genre": "G",
            "chapters": [{"ep_num": 2, "content": "c"}],
            "characters": [{"name": "n"}],
            "plots": [{"ep_num": 1}],
            "bible_settings": "not-a-dict",
        },
    )
    assert name == "export_7.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dump = json.loads(z.read("04_データダンプ.json"))
        assert dump["bible_settings"] == "not-a-dict"
        assert "title" not in dump["chapters"][0]
        assert z.read("01_本文.txt").startswith(b"\xef\xbb\xbf")
        assert "設定なし" in z.read("02_キャラクター・世界観設定集.txt").decode("utf-8")


async def test_export_package_repo_exception_fallback():
    repo = MagicMock()
    repo.get_book.side_effect = RuntimeError("boom")
    svc = MarketingService(repo=repo)
    data, name = await svc.create_export_package(3)
    assert name == "export_3.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dump = json.loads(z.read("04_データダンプ.json"))
        assert dump["title"] == "R15ファンタジー作品"


async def test_export_package_partial_repo_objects():
    repo = MagicMock()
    book = MagicMock()
    book.title = ""
    book.genre = ""
    book.current_branch_id = None
    repo.get_book.return_value = book
    repo.get_all_non_anchor_chapters.return_value = [object()]
    repo.get_all_characters.return_value = [object()]
    repo.get_latest_bible.return_value = "not-bible"
    repo.get_all_plots.return_value = [object()]
    svc = MarketingService(repo=repo)
    data, _ = await svc.create_export_package(11)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dump = json.loads(z.read("04_データダンプ.json"))
        assert dump["book_id"] == 11
        assert dump["chapters"][0]["ep_num"] == 1
        assert dump["characters"][0]["name"] == "不明"
        assert dump["plots"][0]["title"] == ""


async def test_export_package_zip_failure_raises(monkeypatch):
    def boom(self, *a, **k):
        raise OSError("disk")

    monkeypatch.setattr(zipfile.ZipFile, "__init__", boom)
    svc = MarketingService(repo=None)
    with pytest.raises(RuntimeError, match="Export package creation failed"):
        await svc.create_export_package(1)


async def test_export_package_book_data_empty_title_falls_back():
    svc = MarketingService(repo=None)
    data, _ = await svc.create_export_package(2, {"title": "", "genre": ""})
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dump = json.loads(z.read("04_データダンプ.json"))
        assert dump["title"] == "R15ファンタジー作品"
        assert dump["genre"] == "ファンタジー (R15)"
