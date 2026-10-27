"""polish_span が検証付きで採用/不採用を返すことの回帰テスト。"""

import sys
import pathlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from src.generation.local_polish import LocalPolisher

LONG = "A" * 400


def _gw(text):
    gw = MagicMock()
    gw.agenerate = AsyncMock(return_value=text)
    gw.generate = AsyncMock(return_value=text)
    gw.generate_text = AsyncMock(return_value=text)
    return gw


@pytest.mark.asyncio
async def test_accepts_reasonable_replacement():
    out, ok = await LocalPolisher().polish_span(
        LONG, (0, 400), "指示", _gw("A" * 400 + "追記。")
    )
    assert ok is True and "追記。" in out


@pytest.mark.asyncio
async def test_rejects_catastrophic_shrink():
    out, ok = await LocalPolisher().polish_span(LONG, (0, 400), "指示", _gw("B"))
    assert ok is False and out == LONG


@pytest.mark.asyncio
async def test_rejects_paragraph_loss():
    text = "p1\n\np2\n\np3\n\np4"
    out, ok = await LocalPolisher().polish_span(
        text, (0, len(text)), "指示", _gw("全部まとめ")
    )
    assert ok is False and out == text


@pytest.mark.asyncio
async def test_unchanged_text_is_not_applied():
    out, ok = await LocalPolisher().polish_span(LONG, (0, 400), "指示", _gw(LONG))
    assert ok is False and out == LONG


def test_existing_methods_intact():
    for name in ("polish", "polish_with_llm", "_apply", "_build_prompt"):
        assert hasattr(LocalPolisher, name), name
    assert inspect.iscoroutinefunction(LocalPolisher.polish_with_llm)


def test_sync_polish_still_uses_module_level_call():
    with patch("src.generation.local_polish.call_llm_api", return_value="legacy"):
        assert "legacy" in LocalPolisher().polish("AAAABBBB", (4, 8), "指示")
