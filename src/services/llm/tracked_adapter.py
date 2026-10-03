"""LLM 呼び出しの計測ラッパー (v5.3 / Step 2-3).

本番スキル経路（`generation_tasks.py` の `dependencies`）に
:class:`TokenTracker` を注入し、**タスク種別ごとの LLM 呼び出し回数・
トークン・推定コスト**を計測できるようにする。

v5.2 までは `TokenTracker` が `novel_producer.py` / `report_generator.py`
でのみ使われ、本番のスキルパイプラインでは 1 話あたりの LLM 回数も
コストも算出できなかった。そのため v6 の最適化（WS-A: 監査並列化、
WS-B: モデルルーティング）の効果検証ができなかった。

本モジュールは既存の LLM アダプタをラップし、
すべての呼び出しを素通ししつつ計測だけを追加する（挙動は変えない）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.services.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

#: 用途 → タスク種別の対応（コスト最適化の判断単位）
TASK_TYPE_FOR_PURPOSE: dict[str, str] = {
    "writing": "writing",
    "planning": "planning",
    "audit": "audit",
    "enrichment": "enrichment",
    "illustration": "illustration",
    "context": "context",
}


class TrackedLLMAdapter:
    """LLM アダプタをラップし、呼び出し回数とトークン使用量を記録する。

    未知の属性は内側のアダプタへ素通しする（``__getattr__``）ため、
    既存のスキルがアダプタ固有のメソッドを呼んでも壊れない。
    """

    def __init__(
        self,
        inner: Any,
        tracker: TokenTracker,
        task_type: str,
        model_name: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        self._inner = inner
        self._tracker = tracker
        self._task_type = task_type
        self._model_name = model_name
        self._agent_name = agent_name

    def __getattr__(self, name: str) -> Any:
        """未知の属性は内側アダプタへ委譲する。"""
        return getattr(self._inner, name)

    @property
    def model_name(self) -> str | None:
        return self._model_name or getattr(self._inner, "model_name", None)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """トークン数の粗い推定。

        日本語は概ね 1 文字 ≒ 1 トークン、ASCII は 4 文字 ≒ 1 トークン
        とする。実トークナイザはプロバイダごとに異なるため、
        本値は「相対比較用の指標」であり、課金金額の根拠にしないこと。
        """
        if not text:
            return 0
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        other_chars = len(text) - ascii_chars
        return (ascii_chars // 4) + other_chars

    def _record(self, prompt: str, output: str) -> None:
        self._tracker.add_usage(
            input_tokens=self._estimate_tokens(prompt),
            output_tokens=self._estimate_tokens(output),
            model_name=self.model_name,
            agent_name=self._agent_name,
            task_type=self._task_type,
        )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        result = await self._inner.generate_text(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            **kwargs,
        )
        self._record(f"{system_prompt or ''}{prompt}", str(result))
        return result

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        result = self._inner.generate(
            prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            **kwargs,
        )
        if hasattr(result, "__await__"):
            result = await result
        self._record(f"{system_prompt or ''}{prompt}", str(result))
        return result

    async def stream_text(self, *args: Any, **kwargs: Any):
        """ストリーミング生成。逐次チャンクを素通ししつつ出力を集計する。

        計測は ``try/finally`` で行う: コンシューマーが途中で ``break`` した
        り上流が例外を投げたりすると、``async for`` の後に置いたままだと
        コストは課金されているがローカルには記録されないまま飛んでいた。
        """
        chunks: list[str] = []
        try:
            async for chunk in self._inner.stream_text(*args, **kwargs):
                chunks.append(chunk)
                yield chunk
        finally:
            prompt = ""
            if args:
                prompt = str(args[0])
            elif "prompt" in kwargs:
                prompt = str(kwargs["prompt"])
            # generate_text / generate と同じ形（system_prompt を含めて推定する）
            system_prompt = ""
            if len(args) > 1:
                system_prompt = str(args[1])
            elif "system_prompt" in kwargs:
                system_prompt = str(kwargs["system_prompt"] or "")
            self._record(f"{system_prompt}{prompt}", "".join(chunks))

    def cancel(self) -> None:
        cancel = getattr(self._inner, "cancel", None)
        if callable(cancel):
            cancel()


def build_tracked_adapters(
    llm_adapter: Any,
    planning_adapter: Any | None = None,
    audit_adapter: Any | None = None,
    tracker: TokenTracker | None = None,
    models: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """用途別アダプタを計測付きに包んで返す。

    Args:
        llm_adapter: 執筆用アダプタ
        planning_adapter: 構成用アダプタ（無ければ ``llm_adapter`` を使用）
        audit_adapter: 監査用アダプタ（無ければ ``llm_adapter`` を使用）
        tracker: 計測先（無ければ新規生成）
        models: 用途ごとのモデル名（コスト計算に使用）

    Returns:
        ``llm`` / ``planning_llm`` / ``audit_llm`` / ``token_tracker`` を含む辞書。
    """
    tracker = tracker or TokenTracker()
    models = models or {}

    planning_adapter = planning_adapter if planning_adapter is not None else llm_adapter
    audit_adapter = audit_adapter if audit_adapter is not None else llm_adapter

    return {
        "llm": TrackedLLMAdapter(
            llm_adapter, tracker, TASK_TYPE_FOR_PURPOSE["writing"], models.get("writing")
        ),
        "planning_llm": TrackedLLMAdapter(
            planning_adapter,
            tracker,
            TASK_TYPE_FOR_PURPOSE["planning"],
            models.get("planning"),
        ),
        "audit_llm": TrackedLLMAdapter(
            audit_adapter, tracker, TASK_TYPE_FOR_PURPOSE["audit"], models.get("audit")
        ),
        "token_tracker": tracker,
    }
