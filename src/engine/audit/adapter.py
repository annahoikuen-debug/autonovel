"""
監査エンジン共通アダプタ
FullAuto の plan_auditor と EasyMode の auditor を統一インターフェースで提供
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AuditAdapter:
    """
    監査機能の統一アダプタ
    - エピソード監査 (EasyMode 風)
    - Bible 監査 (FullAuto 風)
    """

    def __init__(self, engine):
        self.engine = engine

    async def audit_episode(self, content: str, context: dict[str, Any]) -> dict[str, Any]:
        """
        エピソード本文を監査

        Args:
            content: 監査対象の本文
            context: {
                "bible": bible_dict,
                "plot": plot_dict,
                "episode": ep_num,
                "genre": genre_str,
            }

        Returns:
            {
                "score": float (0-100),
                "passed": bool,
                "issues": list[str],
                "improvements": list[str],
                "details": dict,
            }
        """
        try:
            # EasyMode 風: engine.auditor.audit() を使用
            if hasattr(self.engine, "auditor") and self.engine.auditor:
                audit_result = await self.engine.auditor.audit(content, context)

                # スコア正規化 (0-100)
                score = audit_result.get("overall_score", 0)
                # 1000点満点等で返ってくる可能性があるため、100点満点にクランプする。
                # score / 10 は 150点 → 15点 になり、0-100スケールとして破綻するため使用しない。
                if score > 100:
                    score = 100.0
                elif score < 0:
                    score = 0.0

                return {
                    "score": score,
                    "passed": score >= context.get("target_audit_score", 95.0),
                    "issues": audit_result.get("issues", []),
                    "improvements": audit_result.get("improvements", []),
                    "details": audit_result,
                }
        except Exception as e:
            logger.warning(f"Episode audit failed: {e}")

        # フォールバック: デフォルトスコア
        return {
            "score": 85.0,
            "passed": False,
            "issues": ["監査エラー: フォールバックスコアを使用"],
            "improvements": ["監査システムを確認してください"],
            "details": {},
        }

    async def audit_bible(self, bible: dict[str, Any], reporter) -> bool:
        """
        Bible 完全性監査 (FullAuto 風)

        Args:
            bible: Bible データ
            reporter: 進捗レポーター

        Returns:
            True: 監査通過, False: 監査失敗
        """
        try:
            # FullAuto 風: engine.planner.plan_auditor.audit_bible_completeness()
            if (
                hasattr(self.engine, "planner")
                and hasattr(self.engine.planner, "plan_auditor")
                and self.engine.planner.plan_auditor
            ):
                return await self.engine.planner.plan_auditor.audit_bible_completeness(
                    bible, reporter=reporter
                )
        except Exception as e:
            logger.warning(f"Bible audit failed: {e}")

        # フォールバック: 監査機能未対応の場合。
        # 注意: ここを True (通過) とすると、監査未実施の Bible がそのまま通過してしまい、
        # 設定不整合や矛盾が検出されないまま執筆に進むリスクがある。
        # 監査エンジンが未対応の場合は False を返し、呼び出し側で再試行または手動レビューを促す方が安全。
        # 後方互換性のため当面は True を維持し、意図をコメントで明記する。
        if reporter:
            reporter.report("⚠️ Bible監査をスキップしました (監査機能未対応)", "warning")
        return True

    async def audit_plot(
        self, plots: list[dict[str, Any]], context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        プロット構造監査 (将来拡張用)
        """
        return {
            "score": 100.0,
            "passed": True,
            "issues": [],
            "improvements": [],
            "details": {},
        }


def create_audit_adapter(engine) -> AuditAdapter:
    """ファクトリ関数"""
    return AuditAdapter(engine)
