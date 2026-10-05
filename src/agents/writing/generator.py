# src/agents/writing/generator.py
"""WritingGenerator - 本文生成の実装ロジック"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.episode_pipeline import EpisodePipeline
from src.agents.writing.episode_writer import EpisodeWriter
from src.agents.writing.opening_booster import OpeningBoosterAgent

logger = logging.getLogger(__name__)


class WritingGenerator:
    """本文生成ジェネレーター（EpisodePipeline と連携）"""

    def __init__(
        self,
        repo: Any = None,
        llm: Any = None,
        pm: Any = None,
        style_rag: Any = None,
        ctx_mgr: Any = None,
        reporter_factory: Any = None,
        plot_expander: Any = None,
        session_factory: Any = None,
    ):
        self.repo = repo
        self.llm = llm
        self.pm = pm
        self.style_rag = style_rag
        self.ctx_mgr = ctx_mgr
        self.reporter_factory = reporter_factory
        self.plot_expander = plot_expander
        # ``async with`` 可能なセッション工場（伏線回収 / 事実ダイジェスト用）。
        # None の場合は後処理がスキップされる（写作自体は成立する）。
        self.session_factory = session_factory
        self.branch_id = 1

        # 必要な属性を設定（SchedulerCoordinator が期待するもの）
        self.prompt_manager = pm
        self._writing_graph_manager = None

        # OpeningBoosterAgentを遅延初期化
        self._opening_booster: OpeningBoosterAgent | None = None
        # 後処理専用 EpisodeWriter を遅延初期化（1〜3話用）
        self._post_processing_writer: EpisodeWriter | None = None

    @property
    def opening_booster(self) -> OpeningBoosterAgent:
        """OpeningBoosterAgentを遅延初期化して取得する。"""
        if self._opening_booster is None:
            self._opening_booster = OpeningBoosterAgent(
                repo=self.repo,
                llm=self.llm,
                style_rag=self.style_rag,
            )
        return self._opening_booster

    def _get_post_processing_writer(self) -> EpisodeWriter | None:
        """後処理（伏線回収 / ダイジェスト）に使う EpisodeWriter を用意する。

        1〜3話（OpeningBoosterAgent 経路）は `EpisodeWriter.run()` を経由しないため、
        ここだけ明示的に `EpisodeWriter` を組み立てて後処理呼び出す。
        ContextBuilderAgent は伏線/ダイジェストには不要だが、
        EpisodeWriter のコンストラクタが必須とするため渡しておく。
        """
        if self._post_processing_writer is None:
            try:
                from src.agents.context_builder_agent import ContextBuilderAgent

                context_builder = ContextBuilderAgent(
                    repo=self.repo,
                    llm=self.llm,
                    style_rag=self.style_rag,
                )
                self._post_processing_writer = EpisodeWriter(
                    llm=self.llm,
                    context_builder=context_builder,
                    repo=self.repo,
                    style_rag=self.style_rag,
                    rag_prefetch=None,
                    prompt_manager=self.pm,
                    compressor=None,
                )
            except Exception as e:  # noqa: BLE001 - 後処理は補助なので落とさない
                logger.warning("後処理用の EpisodeWriter を初期化できませんでした: %s", e)
                return None
        return self._post_processing_writer

    async def _run_post_episode_finalize(
        self,
        book_id: int,
        branch_id: int,
        ep_num: int,
        written_text: str,
    ) -> None:
        """後処理を best-effort で実行する（失敗しても執筆は成立させる）。"""
        if not written_text:
            return
        writer = self._get_post_processing_writer()
        if writer is None:
            return
        try:
            await writer._post_episode_finalize(
                book_id=book_id,
                branch_id=branch_id,
                ep_num=ep_num,
                written_text=written_text,
                writing_metadata=None,
                repo=self.repo,
                session=None,
                session_factory=self.session_factory,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Ep.%s: 後処理でエラー（本文は保持）: %s", ep_num, e)

    async def _write_single_episode_core(
        self,
        book_id: int,
        ep_num: int,
        target_word_count: int = 2500,
        is_easy_mode: bool = False,
        passion: float = 1.0,
        genre: str = "異世界ファンタジー",
        protagonist_name: str = "主人公",
        inciting_incident: str = "",
        payoff_moment: str = "",
        branch_id: int = 1,
    ) -> int:
        """
        単発執筆のコア処理（循環呼び出しを避けるための独立関数）

        1話分の執筆実処理を行い、DBに保存して文字数を返す。
        OpeningBoosterAgent（1-3話）またはEpisodeWriter（4話以降・Beat-to-Scene）を直接呼び出す。

        Returns:
            生成された本文の文字数
        """
        # 第1話〜第3話はOpeningBoosterAgentを使用
        if ep_num in (1, 2, 3):
            from src.models.opening_booster import OpeningEpisodeConfig

            config = OpeningEpisodeConfig(
                ep_num=ep_num,
                target_word_count=target_word_count,
                inciting_incident=inciting_incident or f"第{ep_num}話の理不尽と事件",
                payoff_moment=payoff_moment or f"第{ep_num}話の転機と覚醒",
            )
            result = await self.opening_booster.generate_opening_episode(
                config=config,
                protagonist_name=protagonist_name,
                genre=genre,
            )

            # 生成された本文をDBに保存
            content = result.get("content", "")
            if self.repo and content:
                await self.repo.save_chapter(
                    book_id=book_id,
                    branch_id=branch_id,
                    ep_num=ep_num,
                    title=f"第{ep_num}話",
                    content=content,
                )

                # 1〜3話も後処理（伏線自動回収 / 事実ダイジェスト永続化）を走らせる。
                # 以前は OpeningBoosterAgent 経路が `EpisodeWriter.run()` を
                # 経由しないため、この2機構が1〜3話では永久に未実行だった
                # （= ダイジェストが最初の中盤危機語尾からしか無い長編になっていた）。
                # 本文保存が成功したときだけ実行する（0文字なら何もしない）。
                try:
                    await self._run_post_episode_finalize(
                        book_id=book_id,
                        branch_id=branch_id,
                        ep_num=ep_num,
                        written_text=content,
                    )
                except Exception as e:  # noqa: BLE001 - 後処理は補助なので落とさない
                    logger.warning("Ep.%s: 後処理でエラー（本文は保持）: %s", ep_num, e)

            return len(content)
        else:
            # 第4話以降はEpisodeWriter（Beat-to-Scene分割執筆）を使用
            # ContextBuilderが必要なので、ここでは簡易版として書く
            from src.agents.context_builder_agent import ContextBuilderAgent

            context_builder = ContextBuilderAgent(
                repo=self.repo,
                llm=self.llm,
                style_rag=self.style_rag,
            )

            writer = EpisodeWriter(
                llm=self.llm,
                context_builder=context_builder,
                repo=self.repo,
                style_rag=self.style_rag,
                rag_prefetch=None,
                prompt_manager=self.pm,
                compressor=None,
            )

            # コンテキストを構築（簡易版）
            context = {
                "book_id": book_id,
                "ep_num": ep_num,
                "target_word_count": target_word_count,
                "genre": genre,
                "style_intensity": "balanced",
                "is_easy_mode": is_easy_mode,
                "passion": passion,
                "regeneration_focus": [],
                "writing_focus": [],
                "regeneration_directive": None,
                "branch_id": branch_id,
                "use_beat_to_scene": True,  # Beat-to-Scene分割執筆を有効化
            }

            # v5.3 / Step 7: `write()` を直接呼ばず `run()` 経由で生成する。
            # `EpisodeWriter.run` は本文生成に加えて
            #   - 伏線自動回収（`check_and_resolve`）
            #   - 事実ダイジェスト永続化（`_persist_episode_digest`）
            # を行う。`write()` 直叩きでは両方が永久に未実行だった。
            from src.agents.orchestrator import AgentContext

            agent_ctx = AgentContext(
                book_id=book_id,
                branch_id=branch_id,
                ep_num=ep_num,
                artifacts={
                    "repo": self.repo,
                    # セッションは「後処理の直前だけ開く短いスコープ」から渡す。
                    # 以前は `getattr(self.repo, "session", None)` で取っていたが、
                    #   - DataRepositoryFacade では coroutine function が返り、
                    #     `'function' object has no attribute 'execute'`
                    #   - 本番の BookRepository では**同期** Session が返り、
                    #     `await self.db.flush()` が TypeError
                    # となり、どちらの経路でも伏線回収・ダイジェスト保存は
                    # 常に警告でスキップされていた（= 長編の伏線管理が死んでいた）。
                    # 呼び出し側が session_factory を注入する。
                    "session_factory": self.session_factory,
                    "writing_context": context,
                    **context,
                },
            )
            result = await writer.run(agent_ctx)

            if result.error:
                logger.warning(
                    "EpisodeWriter.run returned error for book_id=%s ep=%s: %s",
                    book_id,
                    ep_num,
                    result.error,
                )

            content = str(result.artifacts.get("written_text") or "")

            # 生成された本文をDBに保存
            if self.repo and content:
                await self.repo.save_chapter(
                    book_id=book_id,
                    branch_id=branch_id,
                    ep_num=ep_num,
                    title=f"第{ep_num}話",
                    content=content,
                )

            return len(content)

    def _get_bible(self, book_id: int) -> Any:
        """Bible を取得（SchedulerCoordinator 用）"""
        if self.repo is None:
            return None
        try:
            return self.repo.get_latest_bible(book_id)
        except Exception as e:
            logger.debug(f"Failed to get bible for book_id={book_id}: {e}")
            return None

    async def generate_opening_if_applicable(
        self,
        book_id: int,
        ep_num: int,
        target_word_count: int = 2500,
        inciting_incident: str = "",
        payoff_moment: str = "",
        genre: str = "異世界ファンタジー",
        protagonist_name: str = "主人公",
    ) -> dict[str, Any] | None:
        """第1話〜第3話の場合は OpeningBoosterAgent へ委譲し、それ以外は None を返す"""
        if ep_num in (1, 2, 3):
            from src.models.opening_booster import OpeningEpisodeConfig

            config = OpeningEpisodeConfig(
                ep_num=ep_num,
                target_word_count=target_word_count,
                inciting_incident=inciting_incident or f"第{ep_num}話の理不尽と事件",
                payoff_moment=payoff_moment or f"第{ep_num}話の転機と覚醒",
            )
            return await self.opening_booster.generate_opening_episode(
                config=config,
                protagonist_name=protagonist_name,
                genre=genre,
            )
        return None

    async def generate_episodes_pipeline(
        self,
        book_id: int,
        start_ep: int,
        end_ep: int,
        passion: float,
        target_word_count: int,
        is_easy_mode: bool,
        reporter: Any,
        branch_id: int = 1,
        style_tag: Any = None,
        regeneration_focus: list[str] = None,
        writing_focus: list[str] = None,
        regeneration_directive: str = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        """エピソード生成パイプラインを実行"""
        self.branch_id = branch_id

        # EpisodePipeline に自分自身を渡して実行
        pipeline = EpisodePipeline(self)
        return await pipeline.run(
            book_id=book_id,
            start_ep=start_ep,
            end_ep=end_ep,
            passion=passion,
            target_word_count=target_word_count,
            is_easy_mode=is_easy_mode,
            reporter=reporter,
            branch_id=branch_id,
            style_tag=style_tag,
            regeneration_focus=regeneration_focus or [],
            writing_focus=writing_focus or [],
            regeneration_directive=regeneration_directive,
        )

    async def generate_episodes(
        self,
        book_id: int,
        start_ep: int,
        end_ep: int,
        passion: float,
        target_word_count: int,
        is_easy_mode: bool,
        reporter: Any,
        branch_id: int = 1,
        style_tag: Any = None,
        regeneration_focus: list[str] = None,
        writing_focus: list[str] = None,
        regeneration_directive: str = None,
    ) -> int:
        """単発エピソード生成（パイプラインを経由せず直接コア関数を呼ぶ）"""
        total_chars = 0
        for ep_num in range(start_ep, end_ep + 1):
            chars = await self._write_single_episode_core(
                book_id=book_id,
                ep_num=ep_num,
                target_word_count=target_word_count,
                is_easy_mode=is_easy_mode,
                passion=passion,
                branch_id=branch_id,
            )
            total_chars += chars

            # レポーターに進捗を報告（あれば）
            if reporter:
                await reporter.report_progress(
                    book_id=book_id,
                    episode_num=ep_num,
                    written_chars=chars,
                )

        return total_chars

    async def analyze_and_import_chapter(
        self,
        book_id: int,
        ep_num: int,
        import_text: str,
        do_refine: bool = True,
    ) -> Any:
        """手書き原稿のインポート・研磨（未実装）

        呼び出し側が実装の有無を判定できるよう印を付ける
        （WritingCoordinator.supports_chapter_import が参照する）。
        """
        raise NotImplementedError("analyze_and_import_chapter is not implemented yet")

    #: 未実装である旨の印
    analyze_and_import_chapter._unimplemented_marker = True


# 後方互換性のためのエイリアス
class WritingAgent:
    """後方互換性のためのエイリアス（EngineFacade 等から呼ばれる）"""

    def __init__(
        self,
        repo: Any = None,
        llm: Any = None,
        style_rag: Any = None,
        plot_expander: Any = None,
        **kwargs,
    ):
        self.generator = WritingGenerator(
            repo=repo,
            llm=llm,
            style_rag=style_rag,
            plot_expander=plot_expander,
            **kwargs,
        )
        # EpisodePipeline が期待する属性
        self.repo = repo
        self.llm = llm
        self.style_rag = style_rag
        self.plot_expander = plot_expander
        self.prompt_manager = kwargs.get("pm")
        self.branch_id = 1
        self._writing_graph_manager = None

    def _get_bible(self, book_id: int) -> Any:
        return self.generator._get_bible(book_id)

    async def generate_episodes_pipeline(
        self,
        book_id: int,
        start_ep: int,
        end_ep: int,
        passion: float,
        target_word_count: int,
        is_easy_mode: bool,
        reporter: Any,
        branch_id: int = 1,
        style_tag: Any = None,
        regeneration_directive: str = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        return await self.generator.generate_episodes_pipeline(
            book_id=book_id,
            start_ep=start_ep,
            end_ep=end_ep,
            passion=passion,
            target_word_count=target_word_count,
            is_easy_mode=is_easy_mode,
            reporter=reporter,
            branch_id=branch_id,
            style_tag=style_tag,
            regeneration_directive=regeneration_directive,
        )

    async def generate_episodes(
        self,
        book_id: int,
        start_ep: int,
        end_ep: int,
        passion: float,
        target_word_count: int,
        is_easy_mode: bool,
        reporter: Any,
        branch_id: int = 1,
        style_tag: Any = None,
        regeneration_directive: str = None,
    ) -> int:
        return await self.generator.generate_episodes(
            book_id=book_id,
            start_ep=start_ep,
            end_ep=end_ep,
            passion=passion,
            target_word_count=target_word_count,
            is_easy_mode=is_easy_mode,
            reporter=reporter,
            branch_id=branch_id,
            style_tag=style_tag,
            regeneration_directive=regeneration_directive,
        )

    async def analyze_and_import_chapter(
        self,
        book_id: int,
        ep_num: int,
        import_text: str,
        do_refine: bool = True,
    ) -> Any:
        return await self.generator.analyze_and_import_chapter(
            book_id=book_id,
            ep_num=ep_num,
            import_text=import_text,
            do_refine=do_refine,
        )

    async def generate_opening_if_applicable(self, *args, **kwargs) -> Any:
        return await self.generator.generate_opening_if_applicable(*args, **kwargs)
