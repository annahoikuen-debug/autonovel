"""Step 2 (C2): OpenAI 互換クライアントの usage フィールドアクセス修正。

C2: `response.choices[0].usage` は openai SDK 3.x の Choice に存在せず、
必ず AttributeError を発生する。usage はトップレベルの response.usage にある。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from src.llm.clients.openai import OpenAIApiClient
from src.backend.engine_utils import AdaptiveCooldown


def _make_cooldown() -> AdaptiveCooldown:
    return AdaptiveCooldown(base_sec=2.0, min_sec=1.0, max_sec=60.0)


class _FakeAsyncOpenAI:
    """openai.AsyncOpenAI のスタブ。chat.completions.create を模擬する。"""

    class chat:
        class completions:
            @staticmethod
            async def create(**kwargs):
                # top-level usage なし（None）でもクラッシュしないことを確認
                return ChatCompletion(
                    id="cmpl_test",
                    choices=[
                        Choice(
                            finish_reason="stop",
                            index=0,
                            message=ChatCompletionMessage(role="assistant", content="こんにちは"),
                        )
                    ],
                    created=1,
                    model="gpt-4o-mini",
                    object="chat.completion",
                    usage=None,  # top-level usage absent: C2 の修正対象
                )


@pytest.fixture
def fast_executor(monkeypatch):
    """executor_manager.run_io を直接呼び出しに置き換え、実スレッドプールを避ける。"""
    from src.core import executor_manager as em_module

    async def _run_io(func, *args, **kwargs):
        return func(*args, **kwargs)

    em = em_module.executor_manager
    monkeypatch.setattr(em, "run_io", _run_io)


def _patch_project_context(monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.config.project_context.ProjectContext.get_setting",
        lambda k, d=None: d,
    )


@pytest.mark.asyncio
async def test_no_attribute_error_when_usage_absent(fast_executor, monkeypatch):
    """C2: response.choices[0].usage に触れず、top-level usage なしでもクラッシュしない。"""
    monkeypatch.setattr(
        "src.infrastructure.config.project_context.ProjectContext.get_setting",
        lambda k, d=None: d,
    )
    client = OpenAIApiClient(cooldown=_make_cooldown())
    # _get_client をスタブに差し替え（実際の HTTP 通信を避ける）
    monkeypatch.setattr(client, "_get_client", lambda *a, **k: _FakeAsyncOpenAI())

    story, usage = await client.generate_text(
        model_name="gpt-4o-mini", prompt="こんにちは"
    )

    assert story == "こんにちは"
    # MockUsage が構築され、トークンカウントが 0 で安全に返される
    assert usage.prompt_token_count == 0
    assert usage.candidates_token_count == 0


@pytest.mark.asyncio
async def test_empty_choices_does_not_index_error(fast_executor, monkeypatch):
    """C2: choices が空の場合でも IndexError でクラッシュしない。"""
    monkeypatch.setattr(
        "src.infrastructure.config.project_context.ProjectContext.get_setting",
        lambda k, d=None: d,
    )
    client = OpenAIApiClient(cooldown=_make_cooldown())

    class _FakeEmptyChoices:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    return ChatCompletion(
                        id="cmpl_empty",
                        choices=[],  # 空
                        created=1,
                        model="gpt-4o-mini",
                        object="chat.completion",
                        usage=None,
                    )

    monkeypatch.setattr(client, "_get_client", lambda *a, **k: _FakeEmptyChoices())

    story, usage = await client.generate_text(
        model_name="gpt-4o-mini", prompt="こんにちは"
    )
    assert story == ""
    assert usage.prompt_token_count == 0
