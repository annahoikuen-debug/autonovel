"""逆算プロット生成ワークフロー"""

from __future__ import annotations
import logging
from typing import Any, List

from .base_workflow import BaseWorkflow
from config.story_spine.loader import get_length
from src.services.spine_resolver import resolve_spine
from src.shared.utils import StatusReporter
from src.models.plot import ArcBlueprint, CatharsisPattern
from pydantic import BaseModel

if False:  # TYPE_CHECKING
    from config.story_spine.beat import Spine

logger = logging.getLogger(__name__)


class PlotEpisodeInit(BaseModel):
    """初期プロット構造（逆算ビルダー出力用）"""

    ep_num: int
    title: str
    one_line_summary: str
    tension: int
    catharsis: int
    is_catharsis: bool
    thematic_milestone: str
    burned_cost_or_loot: str
    antagonist_status: str
    resolution_style: str


CONFLICT_TO_ARC_TEMPLATE = {
    "ideal_vs_reality": {"arcs": 3, "pattern": "thesis_antithesis_synthesis"},
    "past_vs_future": {"arcs": 4, "pattern": "confrontation_resolution"},
    "individual_vs_org": {"arcs": 3, "pattern": "escalation_breakthrough"},
    "love_vs_duty": {"arcs": 4, "pattern": "dilemma_sacrifice"},
}

EMOTIONAL_GOAL_TO_CATHARSIS = {
    "triumph": {"type": "大カタルシス", "tensionPeak": 95, "pattern": "explosion"},
    "bittersweet": {"type": "中カタルシス", "tensionPeak": 80, "pattern": "wave"},
    "twist": {"type": "スパイク型", "tensionPeak": 90, "pattern": "spike"},
    "heartwarming": {"type": "小カタルシス連鎖", "tensionPeak": 70, "pattern": "gradual"},
}

HOOK_TO_EP1_TEMPLATE = {
    "isekai_awakening": {"tension": 40, "beats": ["awakening", "discovery", "first_use"]},
    "daily_break": {"tension": 60, "beats": ["peace", "incident", "decision"]},
    "mystery_hook": {"tension": 50, "beats": ["discovery", "investigation", "clue"]},
    "fated_meeting": {"tension": 55, "beats": ["encounter", "conflict", "realization"]},
}

ARC_SUMMARIES = {
    "ideal_vs_reality": ["理想を掲げ旅立つ", "現実の壁に打ち砕かれる", "理想と現実の統合"],
    "past_vs_future": ["過去の亡霊と対峙", "真実を知り苦悩する", "未来を選び取る", "新たな道へ"],
    "individual_vs_org": ["組織の歯車となる", "内部から崩壊を目論む", "組織を打ち破る"],
    "love_vs_duty": ["出会いと使命の板挟み", "愛を選ぶか義務を選ぶか", "犠牲を払う", "新たな均衡"],
}


class ReversePlotGenerationWorkflow(BaseWorkflow):
    """4ステップ回答からプロット構造を生成"""

    async def extract_plot(self, text: str) -> dict[str, Any]:
        """
        テキストからプロット構造を抽出する（簡易インターフェース）。

        Args:
            text: 入力テキスト（小説の全文など）

        Returns:
            プロット情報の辞書。少なくとも"acts"キーを含む
        """
        # 実際の実装では、テキストを解析してストーリー構造を決定する
        # ここではテスト目的で簡易的な実装を提供

        # 簡易ロジック: テキストの長さや特定のキーワードに基づいて幕数を決定
        if not text or len(text.strip()) == 0:
            return {"acts": []}

        # 非常に簡易的なヒューリスティック:
        # - 短いテキスト: 1幕
        # - 中程度のテキスト: 2幕
        # - 長いテキスト: 3幕
        text_length = len(text)
        if text_length < 500:
            act_count = 1
        elif text_length < 2000:
            act_count = 2
        else:
            act_count = 3

        # ダミーの幕名を生成
        acts = [f"第{i+1}幕" for i in range(act_count)]

        return {"acts": acts}

    async def execute(self, reporter: StatusReporter | None = None, **kwargs) -> dict[str, Any]:
        answers = kwargs["answers"]
        target_episodes = kwargs.get("target_episodes") or kwargs.get("targetEpisodes", 10)
        genre = kwargs.get("genre", "ハイファンタジー (R15)")

        if reporter:
            reporter.report("回答を解析し、プロット構造を設計中...", "info")

        # 1. 回答からアーク構成を決定
        arcs = self._design_arcs(answers, target_episodes)
        if reporter:
            reporter.update_progress(1, 3, "アーク構成完了", f"{len(arcs)}アークに分割")

        # 2. 各話の初期プロット設計
        episodes = self._design_episodes(answers, arcs, target_episodes, genre)
        if reporter:
            reporter.update_progress(2, 3, "エピソード設計完了", f"{len(episodes)}話分生成")

        # 3. カタルシスパターン生成
        catharsis = self._design_catharsis(answers, target_episodes)
        if reporter:
            reporter.update_progress(3, 3, "感情曲線設計完了")

        catharsis_dict = catharsis.model_dump()
        return {
            "arcs": [arc.model_dump() for arc in arcs],
            "episodes": [ep.model_dump() for ep in episodes],
            "catharsis_pattern": catharsis_dict,
            "catharsisPattern": catharsis_dict,
        }

    def _spine_for(self, target_episodes: int) -> "Spine":
        """逆プロット用の Spine を解決する（LLM を呼ばない）。"""
        return resolve_spine("exile_rise", "web_volume", "web", target_episodes)

    def _design_arcs(self, answers: dict, target_episodes: int) -> List[ArcBlueprint]:
        conflict = answers.get("coreConflict", "ideal_vs_reality")
        arc_template = CONFLICT_TO_ARC_TEMPLATE.get(conflict, {"arcs": 3, "pattern": "standard"})

        num_arcs = arc_template["arcs"]
        # 部(arc)の区切りは LENGTH_PROFILE が持つ（自前の割り算をやめる）
        try:
            arc_range = get_length("web_volume").get("arc_count", [num_arcs, num_arcs])
        except Exception:
            arc_range = [num_arcs, num_arcs]
        num_arcs = max(1, min(num_arcs, int(arc_range[1])))
        eps_per_arc = max(1, target_episodes // num_arcs)

        arcs = []
        summaries = ARC_SUMMARIES.get(conflict, ["序盤", "中盤", "終盤"])
        for i in range(num_arcs):
            start = i * eps_per_arc + 1
            end = (i + 1) * eps_per_arc if i < num_arcs - 1 else target_episodes
            arcs.append(
                ArcBlueprint(
                    arc_num=i + 1,
                    start_ep=start,
                    end_ep=end,
                    title=f"第{i + 1}部",
                    summary=summaries[min(i, len(summaries) - 1)],
                )
            )
        return arcs

    def _design_episodes(
        self, answers: dict, arcs: List[ArcBlueprint], target_episodes: int, genre: str = ""
    ) -> List[PlotEpisodeInit]:
        emotional_goal = answers.get("emotionalGoal", "triumph")
        sacrifice = answers.get("sacrifice", "peace")
        opening_hook = answers.get("openingHook", "isekai_awakening")

        catharsis_map = EMOTIONAL_GOAL_TO_CATHARSIS[emotional_goal]

        # テンションと各話の役割は STORY_SPINE が単一のソースになる。
        # （旧実装は `_calc_tension` で自前計算しており、構造テンプレと二重実装になっていた）
        spine = self._spine_for(target_episodes)
        # 逆プロットで選ばれた「つかみ」を第1話の指示に必ず反映する
        # （旧実装は `_ = answers.get("openingHook")` で捨てていた）
        first_duty = spine.at(1).duty if spine.at(1) else "つかみを提示する。"
        hook_duty = f"[つかみ:{opening_hook}] {first_duty}"

        episodes = []
        for ep in range(1, target_episodes + 1):
            beat = spine.at(ep)
            # Spine の tension は 0.0-1.0。既存フィールドは 0-100 の int なので換算する。
            tension = round((beat.tension if beat else 0.5) * 100)
            is_catharsis = self._is_catharsis_ep(ep, target_episodes, catharsis_map["pattern"])

            if ep == 1:
                summary = hook_duty
            elif beat is not None:
                summary = f"[{beat.label}] {beat.duty}"
            else:
                summary = self._ep_summary(ep, target_episodes, answers)

            episodes.append(
                PlotEpisodeInit(
                    ep_num=ep,
                    title=f"第{ep}話",
                    one_line_summary=summary,
                    tension=tension,
                    catharsis=int(tension * 0.8) if is_catharsis else 0,
                    is_catharsis=is_catharsis,
                    thematic_milestone=self._milestone(ep, target_episodes, answers),
                    burned_cost_or_loot="なし" if ep < target_episodes else sacrifice,
                    antagonist_status="強化" if ep < target_episodes * 0.7 else "弱体化",
                    resolution_style="Cheat" if "ファンタジー" in genre else "Logic",
                )
            )
        return episodes

    def _is_catharsis_ep(self, ep: int, total: int, pattern: str) -> bool:
        if pattern == "explosion":
            return ep == total
        elif pattern == "wave":
            return ep in [total // 3, 2 * total // 3, total]
        elif pattern == "spike":
            return ep in [total // 2, total]
        else:
            return ep == total

    def _design_catharsis(self, answers: dict, target_episodes: int) -> CatharsisPattern:
        emotional_goal = answers.get("emotionalGoal", "triumph")
        catharsis_map = EMOTIONAL_GOAL_TO_CATHARSIS[emotional_goal]

        if catharsis_map["pattern"] == "explosion":
            catharsis_points = [target_episodes]
        elif catharsis_map["pattern"] == "wave":
            catharsis_points = [target_episodes // 3, 2 * target_episodes // 3, target_episodes]
        elif catharsis_map["pattern"] == "spike":
            catharsis_points = [target_episodes // 2, target_episodes]
        else:
            catharsis_points = [target_episodes]

        # テンション波も Spine の値を単一のソースとする
        spine = self._spine_for(target_episodes)
        tension_wave = [
            int(round((spine.at(ep).tension if spine.at(ep) else 0.5) * 100))
            for ep in range(1, target_episodes + 1)
        ]

        return CatharsisPattern(
            pattern_type=catharsis_map["pattern"],
            catharsis_points=catharsis_points,
            tension_wave=tension_wave,
        )

    def _ep_summary(self, ep: int, total: int, answers: dict) -> str:
        phase = "導入" if ep <= total * 0.25 else "展開" if ep <= total * 0.75 else "結末"
        conflict = answers.get("coreConflict", "ideal_vs_reality")
        return f"[{phase}] {conflict}の局面で、主人公が選択を迫られる"

    def _milestone(self, ep: int, total: int, answers: dict) -> str:
        if ep == 1:
            return "冒険の始まり"
        elif ep == total // 3:
            return "最初の試練"
        elif ep == 2 * total // 3:
            return "最大の危機"
        elif ep == total:
            return "決着"
        return "物語の進行"
