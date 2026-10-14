"""テスト用のモック LLM アダプタ。

このモックは、テストごとにレスポンスをカスタマイズできるように設計されています。
ストリーミング応答とエラー注入をサポートします。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class LLMMocker:
    """LLM モックの振る舞いを設定するためのクラス。"""

    def __init__(self) -> None:
        self._responses: list[str] = []
        self._response_iter: int = 0
        self._exceptions: list[Exception] = []
        self._exception_iter: int = 0
        self._stream_chunks: list[list[str]] = []
        self._stream_chunk_iter: int = 0
        self._error_injection: dict[str, Any] = {}
        self._call_count: int = 0

    def set_responses(self, *responses: str) -> None:
        """生成するレスポンスのシーケンスを設定する。"""
        self._responses = list(responses)
        self._response_iter = 0

    def set_stream_chunks(self, *chunk_sequences: list[str]) -> None:
        """ストリーミング用のチャンクシーケンスを設定する。

        Args:
            *chunk_sequences: 各呼び出しで返すチャンクのリストのリスト。
                例: set_stream_chunks(["Hello", " world"], ["Foo", " bar"])
        """
        self._stream_chunks = list(chunk_sequences)
        self._stream_chunk_iter = 0

    def add_exception(self, *exceptions: Exception) -> None:
        """発生させる例外のシーケンスを設定する。"""
        self._exceptions = list(exceptions)
        self._exception_iter = 0

    def inject_error(self, exception_type: type[Exception], message: str, after_n_calls: int = 0) -> None:
        """指定回数呼び出し後にエラーを注入する。

        Args:
            exception_type: 発生させる例外の型 (例: ValueError, RuntimeError)
            message: 例外メッセージ
            after_n_calls: この回数呼び出された後にエラーを発生させる (0 なら即座に)
        """
        self._error_injection = {
            "exception_type": exception_type,
            "message": message,
            "after_n_calls": after_n_calls,
            "triggered": False,
        }

    def get_next_response(self) -> str:
        """次のレスポンスを取得する。"""
        self._call_count += 1

        # エラー注入チェック
        if self._error_injection and not self._error_injection["triggered"]:
            if self._call_count > self._error_injection["after_n_calls"]:
                self._error_injection["triggered"] = True
                raise self._error_injection["exception_type"](self._error_injection["message"])

        if self._exception_iter < len(self._exceptions):
            exc = self._exceptions[self._exception_iter]
            self._exception_iter += 1
            raise exc

        if self._response_iter < len(self._responses):
            response = self._responses[self._response_iter]
            self._response_iter += 1
            return response

        return "Mock response"

    def get_next_stream_chunks(self) -> list[str]:
        """次のストリームチャンクシーケンスを取得する。"""
        self._call_count += 1

        # エラー注入チェック
        if self._error_injection and not self._error_injection["triggered"]:
            if self._call_count > self._error_injection["after_n_calls"]:
                self._error_injection["triggered"] = True
                raise self._error_injection["exception_type"](self._error_injection["message"])

        if self._stream_chunk_iter < len(self._stream_chunks):
            chunks = self._stream_chunks[self._stream_chunk_iter]
            self._stream_chunk_iter += 1
            return chunks

        # デフォルト: 単語ごとに分割
        response = self.get_next_response()
        return response.split()

    def reset(self) -> None:
        """モックの状態をリセットする。"""
        self._responses = []
        self._response_iter = 0
        self._exceptions = []
        self._exception_iter = 0
        self._stream_chunks = []
        self._stream_chunk_iter = 0
        self._error_injection = {}
        self._call_count = 0


class MockLLMAdapter:
    """テスト用モック LLM アダプタ。"""

    def __init__(self, mocker: LLMMocker | None = None) -> None:
        """モックアダプターを初期化する。"""
        self._mocker = mocker or LLMMocker()

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """テキストを一括生成する（モック実装）。"""
        return self._mocker.get_next_response()

    async def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """テキストをストリーミング生成する（モック実装）。

        単語ごとにチャンクを分割して yield する。
        """
        response = self._mocker.get_next_response()
        for chunk in response.split():
            yield chunk + " "
            await asyncio.sleep(0)

    async def stream_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """ストリーミング応答をチャンク単位で返す (async for 対応)。

        LLMMocker.set_stream_chunks() で設定されたチャンクシーケンスを使用する。
        設定されていない場合は、単語ごとに分割して返す。

        Example:
            async for chunk in adapter.stream_response(prompt):
                print(chunk, end="", flush=True)
        """
        chunks = self._mocker.get_next_stream_chunks()
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0)

    def cancel(self) -> None:
        """進行中のストリームをキャンセルするフック。"""
        pass

    @property
    def mocker(self) -> LLMMocker:
        """内部の LLMMocker を取得する。"""
        return self._mocker
