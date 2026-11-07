"""LogicalAuditor — 非推奨ロジカル一貫性チェックエージェント。

src/agents/audit.py から機能分割（案A+B）により新設。
旧パス ``src/agents/audit.py`` は shim として残す。
"""

from __future__ import annotations

import warnings
from typing import Any

from src.models.audit import CriticFeedback, LogicalAuditIssueList
from src.models.db import PlotDbModel


class LogicalAuditor:
    """@deprecated ロジカル一貫性チェックエージェント。

    このクラスは非推奨です。新規コードでは `src.engine.audit.aggregator.AuditAggregator`
    または `src.agents.audit_agent.AuditAgent` を使用してください。(Phase 6: Step 65)
    """

    def __init__(
        self, repo: Any = None, llm: Any = None, ctx_mgr: Any = None, pm: Any = None, **kwargs
    ):
        warnings.warn(
            "LogicalAuditor is deprecated, use AuditAggregator or AuditAgent instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self.repo = repo
        self.ctx_mgr = ctx_mgr
        self.prompt_manager = pm

        # Priority 1: Explicit generate_json provided in kwargs (Common in tests)
        if "generate_json" in kwargs:
            self.llm = kwargs["generate_json"]
        # Priority 2: llm argument provided
        elif llm is not None:
            self.llm = llm
        else:
            self.llm = None

        self.wave_analyzer = None

    async def generate_critic_feedback(
        self, issue_list: LogicalAuditIssueList, draft_content: str, blueprint: str
    ) -> CriticFeedback:
        """
        Criticエージェントとして、具体的な修正案を含むフィードバックを生成する。
        """
        if not self.prompt_manager:
            from src.models.audit import CriticFeedback

            return CriticFeedback(rewrite_guidance="Prompt manager not configured.")

        prompt = await self.prompt_manager.build_critic_feedback_prompt(
            issue_list=issue_list, draft_content=draft_content, blueprint=blueprint
        )

        # Handle both LLMService and raw generate_json function
        if hasattr(self.llm, "generate_json"):
            # Use await directly; AsyncMock will return return_value when awaited
            result = await self.llm.generate_json(purpose="critic", prompt=prompt)
        elif callable(self.llm):
            result = await self.llm(purpose="critic", prompt=prompt)
        else:
            from src.models.audit import CriticFeedback

            return CriticFeedback(rewrite_guidance="LLM client not configured.")

        from src.models.audit import CriticFeedback

        # Debugging: print result type
        # print(f"DEBUG: result type: {type(result)}, result: {result}")
        if hasattr(result, "metadata"):
            data = result.metadata
        elif isinstance(result, dict):
            data = result.get("metadata", result)
        else:
            data = result

        if isinstance(data, dict):
            return CriticFeedback.model_validate(data)

        return (
            result
            if isinstance(result, CriticFeedback)
            else CriticFeedback(rewrite_guidance=str(result))
        )

    async def validate_alibi_and_timeline(
        self, blueprint: str, script: str
    ) -> tuple[bool, list[str]]:
        """
        アリバイとタイムラインの整合性を検証する（スタブ）
        """
        return True, []

    async def audit_logical_consistency(
        self, book_id: int, ep_num: int, blueprint: str, branch_id: int | None = None
    ) -> tuple[bool, str, float]:
        """作品のロジカル整合性をチェックします"""
        base_ok, base_feedback = await self._check_base_config(book_id, ep_num, branch_id)
        if not base_ok:
            return False, base_feedback, 0.0

        plot_ok, plot_feedback = await self._check_plot_integrity(book_id, ep_num, branch_id)
        if not plot_ok:
            return False, plot_feedback, 0.0

        char_ok, char_feedback = await self._check_character_actions(book_id)
        if not char_ok:
            return False, char_feedback, 0.0

        theme_ok, theme_feedback = await self._check_theme_continuity(blueprint)
        if not theme_ok:
            return False, theme_feedback, 0.0

        return True, "OK", 1.0

    async def _check_base_config(
        self, book_id: int, ep_num: int, branch_id: int | None = None
    ) -> tuple[bool, str]:
        """基本設定の一貫性"""
        if self.repo is None:
            return True, "OK"
        # branch_id は作品間で共有される（既定 1）ため、呼び出し側が渡した
        # branch_id を第一引数にし、book_id も併せて絞る（.plot.py / .chapter.py 参照）
        if branch_id is None:
            settings = await self.repo.bible.get_plot(book_id, ep_num)
        else:
            settings = await self.repo.bible.get_plot(
                branch_id, ep_num, branch_id=branch_id, book_id=book_id
            )
        if not settings:
            return False, "設定未設定"
        if not settings.get("scene_integrity", "false"):
            return False, "scene integrity violation"
        return True, "OK"

    async def _check_plot_integrity(
        self, book_id: int, ep_num: int, branch_id: int | None = None
    ) -> tuple[bool, str]:
        """プロット全体の一貫性"""
        if self.repo is None:
            return True, "OK"
        if branch_id is None:
            plot = await self.repo.plot.get_plot(book_id, ep_num)
        else:
            plot = await self.repo.plot.get_plot(
                branch_id, ep_num, branch_id=branch_id, book_id=book_id
            )
        if not plot:
            return False, "plot not found"
        if not await self._check_pacing(plot):
            return False, "inconsistent pacing"
        return True, "OK"

    async def _check_pacing(self, plot: PlotDbModel) -> bool:
        """テンションの一貫性チェック"""
        return True

    async def check_information_asymmetry(
        self, past_info: str, current_info: str
    ) -> tuple[bool, list[str]]:
        """
        情報の非対称性を検証する（スタブ）
        """
        return True, []

    async def _check_character_actions(self, book_id: int) -> tuple[bool, str]:
        """キャラクターの行動一貫性（スタブ）"""
        return True, "OK"

    async def _check_theme_continuity(self, blueprint: str) -> tuple[bool, str]:
        """テーマの連続性（スタブ）"""
        return True, "OK"

    async def analyze_tension_wave(self, book_id: int, ep_range: tuple = (1, 9999)) -> Any:
        """作品のtension履歴からNarrativeWavePatternを生成する"""
        try:
            from config.project_context import ProjectContext
            from src.models.audit import NarrativeWavePattern

            if self.repo is None:
                return NarrativeWavePattern()

            plots = await self.repo.plot.get_plots(book_id, ep_range[0], ep_range[1])
            if not plots:
                return NarrativeWavePattern()

            tension_history = [getattr(p, "tension", 50) for p in plots]

            if self.wave_analyzer is None:
                from src.backend.engine_narrative import WavePatternAnalyzer

                self.wave_analyzer = WavePatternAnalyzer(
                    threshold=ProjectContext.get_setting("catharsis_threshold", 65),
                    reset_value=ProjectContext.get_setting("catharsis_reset_value", 0),
                )

            return self.wave_analyzer.analyze(tension_history)
        except Exception as e:
            from src.models.audit import NarrativeWavePattern

            return NarrativeWavePattern(issues=[f"波パターン分析中にエラー: {str(e)}"])

    async def score_narrative_metrics(
        self,
        book_id: int,
        branch_id: int,
        ep_num: int,
        scene_num: int,
        scene_content: str,
        context: str = "",
        reporter: Any = None,
    ) -> list[dict[str, Any]]:
        """1シーン分の没入スコアと物語メトリクスをLLMで算出する"""
        default_scores = [
            {
                "metric_name": "immersion_score",
                "score": 0.0,
                "reasoning": "スコアリング失敗時デフォルト",
            },
            {"metric_name": "pov_stability", "score": 0.0, "reasoning": ""},
            {"metric_name": "empathy_gap", "score": 1.0, "reasoning": ""},
            {"metric_name": "curiosity_hook_rate", "score": 0.0, "reasoning": ""},
            {"metric_name": "sensory_density", "score": 0.0, "reasoning": ""},
            {"metric_name": "catharsis_density", "score": 0.0, "reasoning": ""},
        ]
        if not scene_content or not scene_content.strip():
            return default_scores

        try:
            from src.models.audit import ImmersionScore

            prompt = (
                "以下の小説本文を、以下の6観点で0.0-1.0で評価してください。"
                "評価結果は JSON で返してください。\n"
                "{\n"
                '  "pov_stability": 0.0-1.0,\n'
                '  "empathy_gap": 0.0-1.0,\n'
                '  "curiosity_hook_rate": 0.0-1.0,\n'
                '  "sensory_density": 0.0-1.0,\n'
                '  "catharsis_density": 0.0-1.0\n'
                "}\n\n"
                "【本文】\n" + scene_content[:12000] + "\n"
            )
            if context:
                prompt += "\n【参考コンテキスト】\n" + context[:4000] + "\n"

            raw = await self.llm(purpose="narrative_metrics", prompt=prompt)
            data = raw.get("metadata", raw) if isinstance(raw, dict) else {}
            immersion = ImmersionScore(
                pov_stability=float(data.get("pov_stability", 0.0) or 0.0),
                empathy_gap=float(data.get("empathy_gap", 1.0) or 1.0),
                curiosity_hook_rate=float(data.get("curiosity_hook_rate", 0.0) or 0.0),
                sensory_density=float(data.get("sensory_density", 0.0) or 0.0),
            )
            total_score = immersion.calculate_total()
            scores = [
                {"metric_name": "immersion_score", "score": total_score, "reasoning": "加重合計"},
                {"metric_name": "pov_stability", "score": immersion.pov_stability, "reasoning": ""},
                {"metric_name": "empathy_gap", "score": immersion.empathy_gap, "reasoning": ""},
                {
                    "metric_name": "curiosity_hook_rate",
                    "score": immersion.curiosity_hook_rate,
                    "reasoning": "",
                },
                {
                    "metric_name": "sensory_density",
                    "score": immersion.sensory_density,
                    "reasoning": "",
                },
                {
                    "metric_name": "catharsis_density",
                    "score": float(data.get("catharsis_density", 0.0) or 0.0),
                    "reasoning": "",
                },
            ]
            if reporter:
                reporter.report(
                    f"ℹ️ Ep.{ep_num} Scene.{scene_num}: 没入スコア {total_score:.1f}", "info"
                )
            return scores
        except Exception as e:
            if reporter:
                reporter.report(f"⚠️ スコアリング失敗: {type(e).__name__}: {e}", "warning")
            return default_scores
