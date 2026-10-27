from __future__ import annotations

import logging
import os
from copy import deepcopy

logger = logging.getLogger(__name__)

# 本番のフォールバックチェーンに mock を含めない。
# 以前は全チェーンの終端に "mock" が入っていたため、実プロバイダが
# すべて失敗すると MockAdapter の出力が本物と区別できないまま
# 生成結果としてパイプラインを流していた。
#
# テスト/CI で mock を有効にしたい場合は環境変数 AUTONOVEL_ALLOW_MOCK_LLM=1
# を設定する（既定は無効）。
ALLOW_MOCK_ENV = "AUTONOVEL_ALLOW_MOCK_LLM"


def _mock_allowed() -> bool:
    raw = os.environ.get(ALLOW_MOCK_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _base_chains() -> dict[str, list[str]]:
    chains: dict[str, list[str]] = {
        "claude": ["openai", "gemini"],
        "openai": ["gemini", "claude"],
        "gemini": ["openai", "claude"],
        "ollama": [],
        "vllm": ["ollama"],
        "mock": [],
    }
    if _mock_allowed():
        for key in ("claude", "openai", "gemini", "ollama", "vllm"):
            chains[key].append("mock")
        logger.warning(
            "%s is enabled: the 'mock' provider will be used as a last-resort "
            "fallback and its output is NOT real LLM output.",
            ALLOW_MOCK_ENV,
        )
    return chains


DEFAULT_FALLBACK_CHAINS: dict[str, list[str]] = _base_chains()


class FallbackPolicy:
    def __init__(
        self,
        fallback_chains: dict[str, list[str]] | None = None,
    ) -> None:
        # 明示的に渡されたチェーンには手を加えない（呼び出し側の意図を優先）。
        # 未指定時のみ mock 除外の既定チェーンを使う。
        self.fallback_chains = deepcopy(fallback_chains or _base_chains())

    def get_fallback_sequence(self, primary_provider: str) -> list[str]:
        provider = primary_provider.strip().lower()
        seen = {provider}
        sequence: list[str] = []
        pending = list(self.fallback_chains.get(provider, []))
        while pending:
            candidate = pending.pop(0).strip().lower()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            sequence.append(candidate)
            pending.extend(self.fallback_chains.get(candidate, []))
        return sequence

    def get_next_provider(self, primary_provider: str) -> str | None:
        sequence = self.get_fallback_sequence(primary_provider)
        return sequence[0] if sequence else None
