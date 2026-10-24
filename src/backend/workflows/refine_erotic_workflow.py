"""
src/backend/workflows/refine_erotic_workflow.py
官能シーン研磨用ワークフロー
"""

import logging
from typing import Any

from config.erotic_pacing import EroticCurve
from src.shared.utils import StatusReporter

from .base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)


class RefineEroticWorkflow(BaseWorkflow):
    """官能シーンの研磨・整合性チェックを行うワークフロー"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # エロティック専門家とチェッカーを初期化（失敗しても継続）
        try:
            from src.engine.prompts.erotic_specialist import EroticSpecialist
            from src.agents.erotic_integrity import EroticIntegrityChecker
            from src.services.erotic_afterglow_evaluator import AfterglowEvaluator

            self._erotic_specialist = EroticSpecialist()
            self._integrity_checker = EroticIntegrityChecker()
            self._afterglow_evaluator = AfterglowEvaluator()
        except Exception:
            # 初期化に失敗した場合はNoneに設定し、後で処理
            self._erotic_specialist = None
            self._integrity_checker = None
            self._afterglow_evaluator = None

    async def refine_scene(self, scene_text: str, intensity: int = 2) -> str:
        """
        官能シーンのテキストを洗練する。

        Args:
            scene_text: 元のシーンテキスト
            intensity: 強度レベル（デフォルト: 2）

        Returns:
            洗練されたシーンテキスト
        """
        if not scene_text:
            return scene_text

        # エージェントが利用できない場合は基本的な処理のみを行う
        if self._erotic_specialist is None:
            return scene_text

        # 1. 比喩表現への文学変換
        refined_content = self._erotic_specialist.metaphor_filter(scene_text, intensity)

        # 他のエージェントも利用できない場合はここで返す
        if self._integrity_checker is None or self._afterglow_evaluator is None:
            return refined_content

        # 2. 整合性チェック (EroticIntegrityChecker)
        is_ok = True
        try:
            curve = EroticCurve.create_default(intensity)
            peak_beat = curve.get_peak_beat()
            consent_state = peak_beat.consent_state if peak_beat else "implicit"
            is_ok, issues, _, _ = self._integrity_checker.check_all(refined_content, consent_state=consent_state)
            if not is_ok:
                logger.warning("官能整合性チェックで問題検出: %s", issues)
        except Exception as exc:
            logger.warning("EroticIntegrityChecker check failed: %s", exc)

        # 3. afterglow 評価
        afterglow_ok = True
        try:
            afterglow_start = len(refined_content) * 3 // 4
            afterglow_candidate = refined_content[afterglow_start:]
            afterglow_ok, afterglow_issues = self._afterglow_evaluator.evaluate(afterglow_candidate)
            if not afterglow_ok:
                logger.warning("afterglow品質問題: %s", afterglow_issues)
        except Exception as exc:
            logger.warning("AfterglowEvaluator evaluation failed: %s", exc)

        # 整合性またはafterglow品質に問題がある場合はログを残し、
        # 上位層（execute / LLM再生成パイプライン）がフラグを参照できるようにする。
        # ここでは検出のみを行い、テキスト自体は比喩変換済みの内容を返す。
        return refined_content

    async def execute(self, reporter: StatusReporter | None = None, **kwargs) -> dict[str, Any]:
        book_id = kwargs["book_id"]
        # branch_id は作品間で共有される（既定 1）ため、照合には book_id も必須
        branch_id = kwargs.get("branch_id", 1)
        ep_num = kwargs["ep_num"]
        intensity = kwargs.get("intensity", 2)
        _ = kwargs.get("platform_preset", "kakuyomu_romance")

        if reporter:
            reporter.set_message("官能シーン研磨を開始中...")
            reporter.add_log(f"対象作品: {book_id}, 話数: {ep_num}, 強度: {intensity}")

        all_issues: list[str] = []
        is_ok = True
        afterglow_ok = True

        # 1. 章本文の取得
        async with self.repo as uow:
            chapter = await uow.chapters.get_chapter(branch_id, ep_num, book_id=book_id)
            if not chapter:
                raise ValueError(f"Chapter not found for book_id {book_id}, ep_num {ep_num}")

            original_content = chapter.content or ""

            # 2. 比喩表現への文学的変換
            from src.engine.prompts.erotic_specialist import EroticSpecialist

            specialist = EroticSpecialist()
            refined_content = specialist.metaphor_filter(original_content, intensity)

            # 3. 整合性チェック (EroticIntegrityChecker)
            from src.agents.erotic_integrity import EroticIntegrityChecker

            checker = EroticIntegrityChecker()
            # 強度から同意状態を取得
            curve = EroticCurve.create_default(intensity)
            peak_beat = curve.get_peak_beat()
            consent_state = peak_beat.consent_state if peak_beat else "implicit"
            is_ok, issues, _, _ = checker.check_all(refined_content, consent_state=consent_state)

            # 3.5. afterglow 品質評価（peak の後に afterglow がある場合）
            from src.services.erotic_afterglow_evaluator import AfterglowEvaluator

            evaluator = AfterglowEvaluator()
            # afterglow 部分を便宜的抽出（本文末尾の1/4をafterglow候補として評価）
            afterglow_start = len(refined_content) * 3 // 4
            afterglow_candidate = refined_content[afterglow_start:]
            afterglow_ok, afterglow_issues = evaluator.evaluate(afterglow_candidate)

            if not is_ok:
                all_issues.extend(issues)
                for issue in issues:
                    if reporter:
                        reporter.add_log(f"⚠️ 整合性警告: {issue}")
            if not afterglow_ok:
                all_issues.extend(afterglow_issues)
                for issue in afterglow_issues:
                    if reporter:
                        reporter.add_log(f"⚠️ afterglow品質警告: {issue}")

            # 4. 本文を更新
            chapter.content = refined_content
            # プロット側の erotic_intensity を更新
            plot = await uow.plots.get_plot(branch_id, ep_num, branch_id=branch_id, book_id=book_id)
            if plot:
                plot.erotic_intensity = intensity

            await uow.session.commit()

        if reporter:
            reporter.add_log("比喩表現への文学的変換が完了しました")
            if not (is_ok and afterglow_ok):
                if not is_ok:
                    reporter.add_log("整合性チェックに失敗しました")
                if not afterglow_ok:
                    reporter.add_log("afterglow品質評価に失敗しました")
            reporter.set_message("官能シーン研磨が完了しました")

        return {
            "success": True,
            "issues": all_issues,
            "is_ok": is_ok and afterglow_ok,
            "intensity_applied": intensity,
        }


__all__ = ["RefineEroticWorkflow"]
