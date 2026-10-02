"""
prompt_composer.py - プロンプト構�築ユーティリティ
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.scene import Scene



class PromptComposer:
    """プロンプトを構築するユーティリティクラス"""

    def __init__(self, agent: Any | None = None):
        """
        Args:
            agent: 親エージェント（プロンプトマネージャへのアクセスのために必要）
        """
        self.agent = agent
        self.sections: dict[str, str] = {}

    def add_section(self, name: str, content: str) -> None:
        """セクションを追加する"""
        self.sections[name] = content

    @staticmethod
    def _format_three_layer_context(three_layer: Any) -> str:
        """3層ローリング記憶をプロンプト注入用のテキストへ整形する。

        `EpisodeContextBuilder.build_context` の戻り値は
        `{"layer1_bible": {...}, "layer2_summary": {...}, "layer3_previous": {...}}`
        形式の辞書。v5.2 までは組み立てられるだけでプロンプトへ届いていなかった。

        Args:
            three_layer: 3層コンテキスト辞書（None / 空なら空文字）

        Returns:
            プロンプトに挿入可能なテキスト
        """
        if not three_layer or not isinstance(three_layer, dict):
            return ""

        def _text_of(layer: Any) -> str:
            if isinstance(layer, dict):
                return str(layer.get("text") or "")
            return str(layer or "")

        parts: list[str] = []
        layer1 = _text_of(three_layer.get("layer1_bible"))
        if layer1:
            parts.append(f"【Layer1: 世界観・キャラクター設定（不変）】\n{layer1}")
        layer2 = _text_of(three_layer.get("layer2_summary"))
        if layer2:
            parts.append(f"【Layer2: 過去の確定事実タイムライン】\n{layer2}")
        layer3 = _text_of(three_layer.get("layer3_previous")) or _text_of(
            three_layer.get("layer3_raw")
        )
        if layer3:
            parts.append(f"【Layer3: 直前エピソードの原文】\n{layer3}")
        return "\n\n".join(parts)

    def build(self) -> str:
        """セクションを結合してプロンプトを構築する"""
        return "\n\n".join(self.sections.values())

    async def compose_writing_prompt(
        self,
        book_id: int,
        ep_num: int,
        context: dict[str, Any],
    ) -> str:
        """�執�筆用プロンプトを構�築する。

        Args:
            book_id: 書籍ID
            ep_num: エピソード番号
            context: プロット情報、キャラ設定、世界設定などを含む�辞書

        Returns:
            �� 構�築されたプロンプト文字列
        """
        if getattr(self.agent, "prompt_manager", None) is None:
            raise ValueError("PromptManager is not injected into WritingAgent")

        plot_data = context.get("plot", {})
        if not plot_data.get("detailed_blueprint"):
            if hasattr(self.agent, "logger"):
                self.agent.logger.warning(
                    f"Ep.{ep_num}: detailed_blueprint is empty. Writing may be low quality."
                )

        script_text = context.get("script", "")
        # v5.3 / Step 30: `foreshadowing_ctx`（伏線ID付き一覧）を第一優先で使う。
        # 従来は空文字で初期化し RAG のみに依存しており、
        # ContextBuilderAgent が組み立てた伏線ID付きテキストが dead-letter になっていた。
        # RAG へのフォールバックは、この値が空のときだけ行う。
        foreshadowing_context = context.get("foreshadowing_ctx", "") or ""
        context_retriever = getattr(self.agent, "context_retriever", None)
        if not foreshadowing_context and context_retriever and book_id is not None:
            plot_data = context.get("plot", {})
            plot_outline = plot_data.get("detailed_blueprint", "")
            if not plot_outline:
                plot_outline = plot_data.get("summary", "")
            character_names = []  # We don't have character names easily, so pass empty list
            try:
                context_dict = context_retriever.retrieve_writing_context(
                    book_id=book_id,
                    current_ep=ep_num,
                    plot_outline=plot_outline,
                    character_names=character_names,
                )
                foreshadowing_context = context_retriever.format_context_for_prompt(context_dict)
            except Exception as e:
                if hasattr(self.agent, "logger"):
                    self.agent.logger.warning(
                        f"Ep.{ep_num}: Failed to get foreshadowing context: {e}"
                    )
                foreshadowing_context = ""
        prompt = await getattr(self.agent, "prompt_manager").build_final_writing_prompt(
            ep_num=ep_num,
            plot_data=plot_data,
            script_text=script_text,
            target_word_count=context.get("target_word_count", 2000),
            book_id=book_id,
            char_static_ctx=context.get("char_static_ctx", ""),
            char_dynamic_ctx=context.get("char_dynamic_ctx", ""),
            prev_ctx=context.get("prev_ctx", ""),
            pov_character_name=context.get("pov_character_name", ""),
            dialogue_profiles=context.get("dialogue_profiles", {}),
            density_level=context.get("density_level", "Standard"),
            style_tag=context.get("style_tag"),
            foreshadowing_context=foreshadowing_context,
            # v5.3: 契約伏線（伏線ステートマシンの target_episode == 本話）
            contract_foreshadowings=context.get("contract_foreshadowings") or [],
            # v5.3: 3層ローリング記憶（Layer1 バイブル / Layer2 過去ダイジェスト / Layer3 直前本文）
            three_layer_ctx=self._format_three_layer_context(context.get("three_layer_context")),
            # v5.3 / Step 29: 背景（継続中）の未回収伏線。契約伏線と重複排除して
            # PromptManager 側で上限・省略サマリを行う。
            unresolved_foreshadowings=await self._load_unresolved_foreshadowings(
                book_id, ep_num, context
            ),
        )

        regeneration_directive = context.get("regeneration_directive")
        if regeneration_directive:
            prompt = (
                f"==================================================\n"
                f"【最優先・再生成修正ディレクティブ】\n"
                f"前回の審査で指摘された以下の問題点・Actionable Diffsを最優先で反映して執筆してください:\n\n"
                f"{regeneration_directive}\n"
                f"==================================================\n\n"
                + prompt
            )

        # PLAN 03: 生々しいエゴ・打算・身体反応の強制指示（AI優等生病の外科的切除）
        try:
            from pathlib import Path
            import jinja2
            from src.agents.context_builder_agent import resolve_character_flaw

            char_flaw = context.get("character_flaw")
            if not char_flaw:
                char_data = context.get("character") or {"name": context.get("pov_character_name", "主人公")}
                char_flaw = resolve_character_flaw(char_data)

            tmpl_path = Path(__file__).resolve().parents[2] / "prompts" / "templates"
            jenv = jinja2.Environment(loader=jinja2.FileSystemLoader(str(tmpl_path)))
            tmpl = jenv.get_template("narrative/raw_emotion_instruction.j2")
            emotion_instruction = tmpl.render(character_flaw=char_flaw)
            prompt = emotion_instruction + "\n\n" + prompt
        except Exception as e:
            if hasattr(self.agent, "logger"):
                self.agent.logger.warning("Failed to render raw_emotion_instruction: %s", e)

        return prompt

    @staticmethod
    def _format_contract_foreshadowings(contract_foreshadowings: Any) -> str:
        """契約伏線（このシーンで触る/回収する伏線）をシーンプロンプト用に整形する。

        Args:
            contract_foreshadowings: 契約伏線辞書リスト（空なら空文字）

        Returns:
            シーンプロンプトへ挿入可能なテキスト
        """
        if not contract_foreshadowings:
            return ""
        lines = ["【本話の回収ミッション（契約伏線）】"]
        for f in contract_foreshadowings:
            if not isinstance(f, dict):
                continue
            target = f.get("target_episode")
            lines.append(
                f"- [伏線ID: {f.get('id')}] 『{f.get('title', '')}』: "
                f"{f.get('description', '')}"
                f"（第{f.get('planted_episode', '?')}話設置"
                f"{f'・第{target}話回収予定' if target else ''}）"
            )
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    async def _load_unresolved_foreshadowings(
        self,
        book_id: int | None,
        ep_num: int,
        context: dict[str, Any],
        rows: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """未回収伏線（背景ブロック用）を DB から取得する。

        v5.3 / Step 29: 従来 `background_foreshadowings` は空リスト固定で、
        契約伏線があると継続中の未回収伏線が丸ごとプロンプトから消えていた。

        コンテキストに既に `_foreshadowing_source` があればそれを使い、
        無ければセッション（`context["session"]` → `agent.repo.session`）経由で
        取得する。DB が使えない場合は空リスト（従来挙動）にフォールバックする。

        W5 Step 10: フラグ `FORESHADOW_RELEVANCE_INJECTION` が ON のときだけ、
        シーンとの関連度上位 `FORESHADOW_RELEVANCE_TOP_K` 件に絞る。
        **既定 OFF なので現挙動は完全に維持される**。契約鉤子には触らない。
        """
        from src.services.foreshadowing import flags as _fs_flags

        normalized = await self._collect_unresolved(book_id, ep_num, context, rows)
        if not _fs_flags.is_relevance_injection_enabled():
            return normalized
        if not normalized:
            return normalized

        from src.services.foreshadowing.relevance import score_and_select

        scene_text = f"{context.get('phase', '')} {context.get('scene_summary', '')}"
        selected = score_and_select(
            scene_text,
            normalized,
            top_k=_fs_flags.get_relevance_top_k(),
            current_episode=ep_num,
        )
        # 何も渡すとプロンプトが壊れるため、最低 1 件は残す
        return selected or normalized[:1]

    async def _collect_unresolved(
        self,
        book_id: int | None,
        ep_num: int,
        context: dict[str, Any],
        rows: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """未回収伏線（背景ブロック用）を機械的に正規化して返す。"""
        if rows is not None:
            return [dict(r) for r in rows]

        provided = context.get("unresolved_foreshadowings")
        if provided is not None:
            return list(provided)

        if book_id is None:
            return []
        session = context.get("session") or getattr(getattr(self.agent, "repo", None), "session", None)
        if session is None:
            return []
        try:
            from src.infrastructure.repositories.foreshadowing_repo import (
                DbForeshadowingRepository,
            )

            records = await DbForeshadowingRepository(session).get_unresolved(book_id)
        except Exception as e:
            if hasattr(self.agent, "logger"):
                self.agent.logger.warning(
                    f"Ep.{ep_num}: 未回収伏線（背景）の取得に失敗: {e}"
                )
            return []
        return [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "planted_episode": r.planted_episode,
                "target_episode": r.target_episode,
                "status": r.status,
                "scope": getattr(r, "scope", "short_term"),
            }
            for r in records
        ]

    async def compose_scene_prompt(
        self,
        book_id: int,
        ep_num: int,
        scene: "Scene",
        context: dict[str, Any],
    ) -> str:
        """シーン生成用プロンプトを構築する。

        Args:
            book_id: 書籍ID
            ep_num: エピソード番号
            scene: シーンオブジェクト
            context: 執筆コンテキスト

        Returns:
            構築されたプロンプト文字列
        """
        if getattr(self.agent, "prompt_manager", None) is None:
            raise ValueError("PromptManager is not injected into WritingAgent")

        # シーン用テンプレートを取得
        from src.domain.entities.scene import SceneRole
        from pathlib import Path
        import jinja2

        template_map = {
            SceneRole.INTRODUCTION: "scene_introduction.j2",
            SceneRole.CONFLICT: "scene_conflict.j2",
            SceneRole.HOOK: "scene_hook.j2",
        }
        template_name = template_map.get(scene.role, "scene_introduction.j2")

        tmpl_path = Path(__file__).resolve().parents[2] / "prompts" / "templates"
        jenv = jinja2.Environment(loader=jinja2.FileSystemLoader(str(tmpl_path)))
        tmpl = jenv.get_template(f"narrative/{template_name}")

        # コンテキストサマリーを構築
        plot_data = context.get("plot", {})
        writing_context_summary = self._build_writing_context_summary(context, plot_data)

        # 前シーンの内容
        previous_scene_content = context.get("previous_scene_content", "")

        # キャラクターの欠点情報
        char_flaw = context.get("character_flaw")
        if not char_flaw:
            char_data = context.get("character") or {"name": context.get("pov_character_name", "主人公")}
            try:
                from src.agents.context_builder_agent import resolve_character_flaw
                char_flaw = resolve_character_flaw(char_data)
            except Exception:
                char_flaw = "完璧を求めすぎて動けなくなる"

        # v5.3 / Step 30: シーン単位のプロンプトにも契約伏線と3層記憶を渡す。
        # 従来はシーン分岐に伏線IDも3層記憶も一切届かず、
        # エピソード単位のプロンプトだけが伏線回収の契約を受けていた
        # （Step 8 項目2 が未実装のまま残っていた分）。
        foreshadowing_hints = (
            context.get("foreshadowing_hints")
            or context.get("foreshadowing_ctx")
            or ""
        )

        # プロンプトレンダリング
        prompt = tmpl.render(
            scene_data=scene,
            episode_number=ep_num,
            previous_scene_content=previous_scene_content,
            writing_context_summary=writing_context_summary,
            story_arc_summary=context.get("story_arc_summary", ""),
            character_states=context.get("character_states", ""),
            foreshadowing_hints=foreshadowing_hints,
            contract_foreshadowing_ctx=self._format_contract_foreshadowings(
                context.get("contract_foreshadowings")
            ),
            three_layer_ctx=self._format_three_layer_context(
                context.get("three_layer_context")
            ),
            active_conflicts=context.get("active_conflicts", ""),
            cliffhanger_requirements=context.get("cliffhanger_requirements", ""),
            pov_character=context.get("pov_character_name", "主人公"),
            style_instruction=context.get("style_instruction", ""),
            char_flaw=char_flaw,
        )

        # 再生成ディレクティブがある場合は先頭に追加
        regeneration_directive = context.get("regeneration_directive")
        if regeneration_directive:
            prompt = (
                f"==================================================\n"
                f"【最優先・再生成修正ディレクティブ】\n"
                f"前回の審査で指摘された以下の問題点・Actionable Diffsを最優先で反映して執筆してください:\n\n"
                f"{regeneration_directive}\n"
                f"==================================================\n\n"
                + prompt
            )

        return prompt

    def _build_writing_context_summary(
        self,
        context: dict[str, Any],
        plot_data: dict[str, Any],
    ) -> str:
        """執筆コンテキストのサマリーを構築する。"""
        parts = []

        if plot_data.get("one_line_summary"):
            parts.append(f"【話の核】{plot_data['one_line_summary']}")

        if plot_data.get("detailed_blueprint"):
            bp = plot_data["detailed_blueprint"]
            if len(bp) > 500:
                bp = bp[:500] + "..."
            parts.append(f"【詳細プロット】{bp}")

        if context.get("world_setting"):
            ws = context["world_setting"]
            if len(ws) > 300:
                ws = ws[:300] + "..."
            parts.append(f"【世界設定】{ws}")

        if context.get("genre"):
            parts.append(f"【ジャンル】{context['genre']}")

        return "\n\n".join(parts) if parts else "（コンテキスト情報なし）"
