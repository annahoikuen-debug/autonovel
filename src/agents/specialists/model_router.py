import logging
from typing import List, Dict, Any

import yaml

from src.llm.fallback_policy import DEFAULT_FALLBACK_CHAINS

logger = logging.getLogger(__name__)


class AuditorModelRouter:
    """モデルルーター - 8専門オーディター用の適切なLLMクライアント/プロバイダを解決する。"""

    def __init__(self, config_path: str = "config/audit_models.yaml", fallback_chains: Dict[str, List[str]] | None = None) -> None:
        """初期化。

        Args:
            config_path: 設定ファイルへのパス（auditor_models マッピング用）
            fallback_chains: 主プロバイダからフォールバック先プロバイダへのチェーンの辞書。
                None の場合はデフォルトチェーンを使用。
        """
        # フォールバックチェーンの読み込み（設定ファイルまたはデフォルト）
        self.fallback_chains = fallback_chains or DEFAULT_FALLBACK_CHAINS
        # モデル・マッピング: プロバイダ → モデル名
        self._model_mappings: Dict[str, str] = {
            "openai": "openai/gpt-4o",
            "claude": "anthropic/claude-3-5-sonnet-20241022",
            "gemini": "google/gemini-1.5-flash",
            "mock": "mock/model",
        }
        # プロバイダIDからクライアントインスタンスへのマッピング（実際のプロバイダで設定）
        self._client_registry: Dict[str, Any] = {}
        # 設定ファイルからオーディター→モデルマッピングを読み込み
        self._auditor_model_mapping: Dict[str, str] = self._load_auditor_model_config(config_path)
        # プロバイダ別のオーディター辞書（ホットリロード用）
        self._provider_auditors: Dict[str, list[str]] = {}
        self._rebuild_provider_auditors()

    def _load_auditor_model_config(self, config_path: str) -> Dict[str, str]:
        """config/audit_models.yaml から auditor→モデル名 マッピングを読み込む。"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            auditor_models = config.get("auditor_models", {})
            if isinstance(auditor_models, dict):
                return auditor_models
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load auditor model config from {config_path}: {e}")
        # フォールバック: 設計時のデフォルトマッピング
        return {
            "factual": "google/gemini-1.5-flash",
            "consistency": "google/gemini-1.5-flash",
            "style": "google/gemini-1.5-flash",
            "multimodal": "google/gemini-1.5-flash",
            "creativity": "anthropic/claude-3-5-sonnet-20241022",
            "reader_hook": "openai/gpt-4o",
            "emotion_curve": "anthropic/claude-3-5-sonnet-20241022",
            "structure": "openai/gpt-4o",
        }

    def _rebuild_provider_auditors(self) -> None:
        """プロバイダ別オーディター一覧を再構築（ホットリロード用）。"""
        self._provider_auditors = {}
        for auditor, model_name in self._auditor_model_mapping.items():
            provider = self._model_name_to_provider(model_name)
            if provider not in self._provider_auditors:
                self._provider_auditors[provider] = []
            if auditor not in self._provider_auditors[provider]:
                self._provider_auditors[provider].append(auditor)

    def register_client(self, provider: str, client: Any) -> None:
        """プロバイダへのLLMクライアントを登録する。

        Args:
            provider: プロバイダID（openai、claudeなど）
            client: LLMクライアントインスタンス
        """
        self._client_registry[provider] = client

    def get_llm_for_auditor(self, auditor_name: str) -> Any | None:
        """オーディター名を受け取り、割り当てられたクライアントを返す。"""
        primary_provider = self._resolve_primary_provider_for_auditor(auditor_name)
        if not primary_provider:
            return None

        # 2. プロバイダ解決（フォールバックチェーンを使用）
        candidates = [primary_provider] + self.fallback_chains.get(primary_provider, [])

        # 3. 各候補を検索し、クライアントを返す
        for candidate in candidates:
            if candidate in self._client_registry:
                return self._client_registry[candidate]

        # クライアントが 1 つも無い場合、時々黙って None を返して
        # 呼び出し側を score=50.0 のフォールバックに導いていた。
        # ここでは「クライアントが未登録」であることを明示する。
        if not self._client_registry:
            logger.error(
                "AuditorModelRouter has NO registered clients; auditor %r would "
                "always degrade to the neutral fallback. Call register_client() "
                "with the real LLM before running specialist auditors.",
                auditor_name,
            )
        return None

    def _resolve_primary_provider_for_auditor(self, auditor_name: str) -> str:
        """オーディター特性に基づいて優先プロバイダを返す。

        この方法はconfig/audit_models.yamlと同期する必要がある。
        """
        # 設定ファイルからモデル名を取得、プロバイダへマッピング
        model_name = self._auditor_model_mapping.get(auditor_name)
        if model_name:
            provider = self._model_name_to_provider(model_name)
            if provider:
                return provider

        # 設計マッピングに従う: 軽量タスク → gemini、高負荷タスク → claude/medium → openai
        if auditor_name in ("factual", "consistency", "style", "multimodal"):
            return "gemini"
        elif auditor_name in ("creativity", "emotion_curve"):
            return "claude"
        elif auditor_name == "reader_hook":
            return "openai"
        elif auditor_name == "structure":
            return "openai"
        else:
            # デフォルト: 実プロバイダへ退避する（mock は使わない）
            return "openai"

    def get_provider_for_auditor(self, auditor_name: str) -> str:
        """オーディターに割り当てられたプロバイダを取得する（クライアントのみの場合に便利）。"""
        primary = self._resolve_primary_provider_for_auditor(auditor_name)
        return primary

    def list_configured_auditors(self) -> list[str]:
        """設定で定義されたすべてのオーディターを返す。"""
        return list(self._auditor_model_mapping.keys())

    def refresh_from_config(self, config_path: str = "config/audit_models.yaml") -> None:
        """設定ファイルを再読み込み、チェーンを更新する（ホットリロード）。"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            # 明示的なフォールバックチェーンがあれば尊重する
            # ({provider: [provider_fallback, ...]} の形式)
            explicit = config.get("fallback_chains") or config.get("provider_chains")
            if explicit:
                self.fallback_chains = {
                    str(p): [str(c) for c in v] for p, v in explicit.items()
                }
                self._rebuild_provider_auditors()
                return

            chains = config.get("auditor_models", {})
            if not chains:
                return

            # 既知のプロバイダに対応する実クライアントのみをフォールバック対象にする。
            # 以前は「他のオーディター名」をチェーンに入れていたため
            # (``{"openai": ["openai", "creativity", ...]}``)、
            # get_llm_for_auditor が ``self._client_registry[candidate]`` を
            # 引いた時に必ず None になっていた。
            provider_order: List[str] = []
            for _auditor, model_name in chains.items():
                provider = self._model_name_to_provider(model_name)
                if provider and provider != "mock" and provider not in provider_order:
                    provider_order.append(provider)

            # 既知のクライアント登録済みプロバイダを末尾に足す
            for provider in self._client_registry:
                if provider not in provider_order and provider != "mock":
                    provider_order.append(provider)

            if not provider_order:
                logger.error(
                    "refresh_from_config: could not resolve any real provider from %s; "
                    "keeping the previous fallback chains.",
                    config_path,
                )
                return

            primary = provider_order[0]
            self.fallback_chains = {p: [c for c in provider_order if c != p] for p in provider_order}
            logger.info(
                "refresh_from_config: provider order=%s (primary=%s)", provider_order, primary
            )
            self._rebuild_provider_auditors()
        except Exception as e:
            logger.warning(f"Failed to refresh from config: {e}")

    def _model_name_to_provider(self, model_name: str) -> str:
        """モデル名からプロバイダを抽出する。

        以前は未知のモデル名に対して必ず "mock" を返していたため、
        ``auditor_models: {style: "gpt-4o"}`` のような設定が
        本番でも無言でモックへルーティングされ、8 specialists すべてが
        score=50.0 になっていた。未知のモデル名は「空の provider 名」を
        返し、呼び出し側で未解決として明示的に扱うようにする。
        """
        if not model_name:
            return ""
        lowered = model_name.lower()
        if "openai" in lowered or lowered.startswith("gpt-") or lowered.startswith(("o1", "o3", "o4")):
            return "openai"
        if "claude" in lowered or "anthropic" in lowered:
            return "claude"
        if "gemini" in lowered or "google" in lowered:
            return "gemini"
        if "mock" in lowered:
            return "mock"
        # 既知のプロバイダに解決できない。黙って mock にはしない。
        logger.warning(
            "Unknown model %r could not be mapped to a provider; "
            "auditor will fall back to the default provider instead of 'mock'.",
            model_name,
        )
        return ""

