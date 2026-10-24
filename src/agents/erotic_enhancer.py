"""
erotic_enhancer.py - 官能強化ユーティリティ (GraphRAG 心理・関係性パラメータ連動対応)
"""

from __future__ import annotations

from typing import Any

from src.agents.base import BaseAgent
from src.domain.value_objects.erotic_gate import EroticGate


class EroticEnhancer:
    """官能コンテンツを強化するユーティリティクラス (GraphRAG連携)"""

    def __init__(self, agent: BaseAgent):
        """
        Args:
            agent: 親エージェント（エロティック機能へのアクセスのために必要）
        """
        self.agent = agent

    def _resolve_graphrag_parameters(self, context: dict[str, Any]) -> dict[str, Any]:
        """GraphRAGパラメータを解決して返す"""
        rel = context.get("relationship_type")
        params: dict[str, Any] = {}
        if rel == "HATES":
            params = {
                "psychology_depth": 90,
                "default_consent": "implicit",
                "pace_ratios": {"intro": 0.3, "development": 0.4, "climax": 0.3},
            }
        elif rel == "MASTER_SERVANT":
            params = {
                "psychology_depth": 85,
                "metaphor_density": 65,
                "default_consent": "implicit",
                "pace_ratios": {"intro": 0.2, "development": 0.5, "climax": 0.3},
            }
        elif rel == "LOVES":
            params = {
                "psychology_depth": 75,
                "default_consent": "mutual",
                "sensory_weights": {"touch": 0.4, "sight": 0.3, "sound": 0.3},
                "pace_ratios": {"intro": 0.3, "development": 0.4, "climax": 0.3},
            }
        return params

    def enhance_erotic_content(self, prompt: str, result: str, context: dict[str, Any]) -> str:
        """
        官能コンテンツを強化する (GraphRAG 心理連携)。

        ゲートが有効な場合、直接表現の比喩フィルタリング (metaphor_filter)
        を適用して文学的な官能表現へ変換する。LLM再生成は上位パイプラインの
        責務であり、ここでは決定的な後処理のみを行う。

        Args:
            prompt: 元のプロンプト
            result: LLMによって生成された結果
            context: コンテキスト情報

        Returns:
            強化された結果文字列
        """
        # === Step 10 追加: ゲート判定を EroticGate に委譲 ===
        gate = EroticGate.from_context(context)
        if not gate.is_active():
            return result
        erotic_intensity = gate.intensity

        try:
            from src.engine.prompts.erotic_specialist import EroticSpecialist

            specialist = EroticSpecialist()
            # 強度3以上: 比喩フィルタによる直接表現の緩和を適用
            # （強度1-2の焦らし表現は原文の緊張感を優先し無変換）
            if erotic_intensity >= 3:
                result = specialist.metaphor_filter(result, erotic_intensity)
        except ImportError:
            # エロティック関連のモジュールが見つからない場合は元の結果を返す
            return result
        except Exception:
            # その他のエラーも元の結果を返す
            return result

        return result
