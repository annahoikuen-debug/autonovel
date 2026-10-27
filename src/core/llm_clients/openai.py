from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from src.backend.engine_utils import AdaptiveCooldown, safe_model_validate
from src.backend.sanitizer import OutputSanitizer
from src.core.exceptions import LLMUnrecoverableError
from src.core.llm_clients.base import BaseLLMClient
from src.core.observability import StructuredLogger
from src.services.retry_decorator import RetryState, with_llm_retry

logger = StructuredLogger(__name__)


class OpenAIApiClient(BaseLLMClient):
    """OpenAI互換APIエンドポイントとの通信を担当。

    (vLLM, Ollama, OpenRouter, Together AI等に対応)
    """

    def __init__(self, cooldown: AdaptiveCooldown):
        self.cooldown = cooldown
        self._active_requests = 0
        # (base_url, api_key) -> AsyncOpenAI。呼び出しごとに新規生成していた際は
        # httpx コネクションプール/TLS セッションが 1 呼び出し 1 個のまま
        # 解放されず（リトライ 5 回 x プロバイダ 3 種 x エージェント数十>),
        # ソケットと FD をリークしていた。
        self._clients: dict[tuple[str, str], Any] = {}

    def _get_client(self, base_url: str, api_key: str) -> Any:
        import openai

        key = (base_url, api_key)
        client = self._clients.get(key)
        if client is None:
            client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
            self._clients[key] = client
        return client

    async def aclose(self) -> None:
        """保持している全 AsyncOpenAI クライアントをクローズする（シャットダウン時）。"""
        clients, self._clients = self._clients, {}
        for client in clients.values():
            try:
                await client.close()
            except Exception as e:  # pragma: no cover - best effort
                logger.warning(f"Failed to close OpenAI client: {e}")

    @with_llm_retry()
    async def generate_json(
        self,
        model_name: str,
        prompt: str,
        system_instruction: str | None = None,
        response_schema: Any = None,
        temp: float = 1.0,
        max_retries: int = 5,
        stream_callback: Callable[[str], None] | None = None,
        retry_state: RetryState | None = None,
        nsfw_mode: bool = False,
    ) -> tuple[dict[str, Any], str, Any]:
        try:
            import openai  # noqa: F401  # 依存存在の早期チェック（_get_client でも使用）
        except ImportError:
            raise ImportError(
                "OpenAI / Gemma integration requires the 'openai' python package. Please install it with 'pip install openai'."
            )

        from config.project_context import ProjectContext

        base_url = ProjectContext.get_setting("openai_base_url") or "https://api.openai.com/v1"
        api_key = ProjectContext.get_setting("openai_api_key") or "dummy"
        client = self._get_client(base_url, api_key)

        if stream_callback is not None:
            # 以前は引数を受け取るだけで一切使っておらず、OpenAI の「ストリーミング」は
            # 実際には非ストリーミングの 1 Shot 応答を丸ごと返していた（部分出力が
            # 一度も UI に出ない）。黙って無視せず、明示的に拒否する。
            raise NotImplementedError(
                "OpenAIApiClient does not support streaming (stream_callback). "
                "Remove the stream_callback argument or use GeminiProvider."
            )

        current_temp = retry_state.temp if retry_state else temp
        current_model = retry_state.model_name if retry_state else model_name
        error_feedback = retry_state.error_feedback if retry_state else ""
        top_p = ProjectContext.get_setting("inference_top_p", 0.95)
        top_k = ProjectContext.get_setting("inference_top_k", 64)

        system_sandbox = ProjectContext.get_setting("system_sandbox", "")

        system_content = ""
        if system_sandbox:
            system_content += system_sandbox + "\n\n"
        if system_instruction:
            system_content += system_instruction

        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": prompt})

        if error_feedback:
            messages[-1]["content"] = (
                f"【🚨出力形式エラー報告🚨】\n前回の出力に以下の不備がありました: {error_feedback}\n\n{prompt}"
            )

        if response_schema and hasattr(response_schema, "model_fields"):
            fields = list(response_schema.model_fields.keys())
            if "※重要:" not in messages[-1]["content"]:
                messages[-1]["content"] += (
                    f"\n\n※重要: JSONには以下のキーを必ず含めてください: {', '.join(fields)}"
                )
                messages[-1]["content"] += (
                    "\n\nCRITICAL: Output MUST be valid JSON ONLY. Start with '{' and end with '}'."
                )

        response_format = None
        if response_schema:
            response_format = {"type": "json_object"}

        extra_body = {}
        if top_k:
            extra_body["top_k"] = top_k

        start_time = time.time()
        try:
            from src.core.async_utils import safe_timeout

            async with safe_timeout(120.0):
                response = await client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    temperature=current_temp,
                    top_p=top_p,
                    response_format=response_format,
                    extra_body=extra_body if extra_body else None,
                )
        except TimeoutError as e:
            raise TimeoutError(f"OpenAI API timed out after 120s: {e}")
        except Exception as e:
            err_msg = str(e).lower()
            if any(
                x in err_msg
                for x in [
                    "401",
                    "403",
                    "unauthorized",
                    "invalid key",
                    "api key",
                    "404",
                    "not found",
                    "400",
                    "bad request",
                ]
            ):
                logger.error(f"❌ Unrecoverable OpenAI API error: {e}")
                raise LLMUnrecoverableError(f"Unrecoverable OpenAI API error: {e}") from e
            if any(x in err_msg for x in ["429", "quota", "too many requests"]):
                from src.core.exceptions import LLMTemporaryError

                raise LLMTemporaryError(f"OpenAI Rate Limit: {e}") from e
            raise e

        full_text = response.choices[0].message.content or ""
        duration = time.time() - start_time

        usage_metadata = response.choices[0].usage
        prompt_tokens = usage_metadata.prompt_tokens if usage_metadata else 0
        completion_tokens = usage_metadata.completion_tokens if usage_metadata else 0
        # SDK が total_tokens を返す場合はそれを優先する。無い場合のみ導出する。
        total_tokens = (
            getattr(usage_metadata, "total_tokens", 0)
            if usage_metadata
            else 0
        ) or (prompt_tokens + completion_tokens)

        class MockUsage:
            def __init__(self, p, c, t):
                self.prompt_token_count = p
                self.candidates_token_count = c
                # 以前は未定義のため OpenAIProvider._parse_usage の
                # total_tokens が常に 0 になり、コスト/トークン集計が
                # 過小報告になっていた。
                self.total_token_count = t

        usage = MockUsage(prompt_tokens, completion_tokens, total_tokens)

        metadata, story = OutputSanitizer.extract_content_and_metadata(full_text)

        if response_schema and hasattr(response_schema, "model_validate"):
            safe_model_validate(response_schema, metadata)

        # with_llm_retry() が成功時に cooldown.on_success() を呼ぶためここでは
        # 呼ばない（二重計上は AdaptiveCooldown のランプを 2 倍速にして
        # レートリミッタを実質無効化していた）。
        logger.info(
            f"✅ OpenAI Success: model={current_model}, len={len(prompt)}, dur={duration:.2f}s"
        )
        return metadata, story, usage

    @with_llm_retry()
    async def generate_text(
        self,
        model_name: str,
        prompt: str,
        system_instruction: str | None = None,
        temp: float = 0.7,
        max_retries: int = 5,
        stream_callback: Callable[[str], None] | None = None,
        retry_state: Any | None = None,
        nsfw_mode: bool = False,
    ) -> tuple[str, Any]:
        """
        OpenAI 互換エンドポイントでテキストだけを取得するラッパー。
        generate_json の実装を流用し、response_schema を None にして
        テキスト（story）と usage オブジェクトを返す。
        """
        metadata, story, usage = await self.generate_json(
            model_name=model_name,
            prompt=prompt,
            system_instruction=system_instruction,
            response_schema=None,
            temp=temp,
            max_retries=max_retries,
            stream_callback=stream_callback,
            retry_state=retry_state,
            nsfw_mode=nsfw_mode,
        )
        return story, usage
