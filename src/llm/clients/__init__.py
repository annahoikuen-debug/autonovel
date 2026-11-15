"""低レベル LLM 通信クライアント。

統合先: src/llm/clients/
実体は base.py にある（gemini.py/openai.py は PLAN_Q2 で削除済み）。
"""

from __future__ import annotations

from src.llm.clients.base import BaseLLMClient

__all__ = ["BaseLLMClient"]
