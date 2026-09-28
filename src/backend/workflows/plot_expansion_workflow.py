import json
import logging
from typing import Any

from src.shared.utils import StatusReporter

from .base_workflow import BaseWorkflow

logger = logging.getLogger(__name__)


class PlotExpansionWorkflow(BaseWorkflow):
    """プロットの追加・再生成フロー"""

    def _resolve_expander(self):
        """実際に expand_plots を持つサービスを返す。

        優先順位:
          1. plot_agent（container.plot_expander() = PlotAgent）
          2. planner に expand_plots がある場合のみ planner
        属性の有無 (``hasattr``) ではなく実際に呼べるかを基準にする。
        """
        candidates = (self.plot_agent, self.planner)
        for candidate in candidates:
            if candidate is not None and callable(getattr(candidate, "expand_plots", None)):
                return candidate

        raise RuntimeError(
            "expand_plots を提供するサービスが見つかりません。"
            f"plot_agent={type(self.plot_agent).__name__}, "
            f"planner={type(self.planner).__name__}。"
            "container の plot_expander 設定を確認してください。"
        )

    async def execute(self, reporter: StatusReporter, **kwargs) -> dict[str, Any]:
        book_id = kwargs["book_id"]
        gen_from = kwargs["gen_from"]
        gen_to = kwargs["gen_to"]
        mode = kwargs.get("mode", "final")

        bible = await self.repo.get_latest_bible(book_id)
        logger.debug(
            "plot_expansion bible=%r settings=%r",
            bible,
            getattr(bible, "settings", None) if bible else None,
        )
        settings = (
            bible.settings
            if isinstance(bible.settings, dict)
            else json.loads(bible.settings or "{}")
            if bible
            else {}
        )
        arcs = settings.get("arcs", [])
        # 候補生成モードの場合、planner側に候補生成を指示する
        # 現在の expand_plots が candidates をサポートしていない場合は、
        # planner 内部の LLM 呼び出しで divergence_instruction が注入されるため、
        # その結果をそのまま保存する。
        # 1. 生成前に目標Tension値を計算してDBに保存
        # - ジャンルと物語タイプをBibleから取得（簡易的に'general'と想定）
        genre = "general"
        story_type = None
        # 1. 生成前に目標Tension値を計算してDBに保存
        #    ※ tension が利用不可（未実装エンジン）ならこの工程はスキップする。
        #      従来はここで NotImplementedError が送出され、プロット展開ごと
        #      500 になっていた。展開自体は tension と独立して実行できる。
        if self.tension is None:
            logger.warning(
                "Tension 功能が利用不可のため、目標Tensionの算出と逸脱検証をスキップします。"
            )
            if reporter:
                reporter.report(
                    "テンション目標の算出は未対応のため，本次プロット展開では検証しません。",
                    "warn",
                )
        else:
            for ep_num in range(gen_from, gen_to + 1):
                await self.tension.determine_target_tension(book_id, ep_num, genre, story_type)

        # 2. プロット展開を実行
        #
        # 展開は planner ではなく plot_agent が実装している。
        # ``_build_service_dict`` は planner=container.planner()（= PlanningAgent）と
        # plot_agent=container.plot_expander()（= PlotAgent）の両方を渡すため、
        # 従来は PlanningAgent に対して expand_plots を呼び、属性不在で落ちていた。
        # PlotAgent.expand_plots は DefaultPlotExpander へ委譲する実装。
        expander = self._resolve_expander()
        results = await expander.expand_plots(
            book_id,
            list(range(gen_from, gen_to + 1)),
            arcs,
            reporter=reporter,
            force=True if mode == "candidates" else False,
        )

        # 3. 生成されたTension値のバリデーション
        if results and mode != "candidates" and self.tension is not None:
            for res in results:
                ep_num = res.ep_num
                gen_tension = res.tension / 100.0  # 0-100 scale to 0.0-1.0
                is_valid, dev = await self.tension.validate_tension_deviation(
                    ep_num, gen_tension, book_id
                )
                if not is_valid:
                    if reporter:
                        reporter.report(
                            f"第{ep_num}話のTensionが目標から逸脱しています (偏差: {dev:.2f})。次回の調整を推奨します。",
                            "warn",
                        )
        return {"count": len(results), "mode": mode}
