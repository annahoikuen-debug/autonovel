from typing import Any, List, Optional
import inspect
import logging
import os

from src.agents.base import BaseAgent
from src.agents.context_builder_agent import ContextBuilderAgent
from src.agents.erotic_enhancer import EroticEnhancer
from src.agents.orchestrator import AgentContext, AgentResult
from src.agents.prompt_composer import PromptComposer
from src.agents.writing.prose_refiner_agent import ProseRefinerAgent
from src.agents.writing.scene_writer import SceneWriter, SceneWriterOrchestrator
from src.domain.entities.scene import SceneRole
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository
from src.services.llm_service import LLMService
from src.services.rag.context_retriever import ForeshadowingEntity
from src.services.foreshadowing_service import ForeshadowingService
from src.services.prose.social_reaction_generator import SocialReactionGenerator
from src.models.writing_metadata import WritingMetadata
from src.services.prose.novel_output_splitter import NovelOutputSplitter
from prompts.manager import PromptManager
from src.pipeline.emotional_residue import EmotionalResidueExtractor
from src.pipeline.character_dict import load_character_dict

logger = logging.getLogger(__name__)


def _is_episode_digest_enabled() -> bool:
    """`ENABLE_EPISODE_DIGEST` フィーチャーフラグを読む（既定 on）。

    ダイジェスト生成は話ごとに1回のブロッキング LLM 呼出（約2500字入力）を伴う。
    コスト重視の運用では `ENABLE_EPISODE_DIGEST=0` により無効化できる
    （この場合 Layer2 は本文冒頭100字へフォールバックする）。
    """
    raw = os.getenv("ENABLE_EPISODE_DIGEST", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _resolve_digest_llm(llm: Any) -> Any:
    """ダイジェスト生成用に tier1（軽量）モデルを割り当てる。

    要約は構成系の軽量タスクなので、執筆用モデル（tier2/3）で回すと
    コストが無駄になる。`resolve_optimized_model` が
    使えない環境では渡された llm をそのまま使う。
    """
    if llm is None:
        return None
    try:
        from src.llm.model_router import resolve_optimized_model

        model_name = resolve_optimized_model("summary")
    except Exception as e:
        logger.debug("Falling back to the given LLM for digest generation: %s", e)
        return llm

    if not hasattr(llm, "generate"):
        return llm

    class _Tier1DigestLLM:
        """`generate(prompt=...)` だけを tier1 モデルへ差し替える薄いラッパー。"""

        def __init__(self, inner: Any, model_name: str):
            self._inner = inner
            self._model_name = model_name

        def generate(self, prompt: str, **kwargs: Any) -> Any:
            res = self._inner.generate(prompt=prompt, model_name=self._model_name, **kwargs)
            if inspect.isawaitable(res):
                return res
            return res

    return _Tier1DigestLLM(llm, model_name)


async def _resolve_total_episodes(
    session: Any, book_id: int, writing_context: dict[str, Any] | None = None
) -> int | None:
    """作品全体の予定話数（`Book.target_eps`）を解決する。

    v5.3 / Step 33: `check_and_resolve(total_episodes=...)` は Step 15 で
    追加されたが、本番の呼び出し元が一度も値を渡しておらず、実行時の
    `max_episode` は常に None だった（＝延期不能を検出できない）。
    コンテキストに明示値があればそれを優先し、無ければ DB を読む。
    """
    explicit = (writing_context or {}).get("total_episodes")
    if isinstance(explicit, int) and explicit > 0:
        return explicit
    if session is None or book_id is None:
        return None
    try:
        from sqlalchemy import select

        from src.backend.database.models import Book as BookModel

        res = await session.execute(
            select(BookModel.target_eps).where(BookModel.id == book_id)
        )
        row = res.first()
        value = row[0] if row is not None else None
        return int(value) if isinstance(value, int) and value > 0 else None
    except Exception as e:
        logger.debug("Failed to resolve Book.target_eps for book %s: %s", book_id, e)
        return None


def _resolve_session(repo: Any, session: Any) -> Any:
    """伏線・ダイジェスト・3層記憶で共通して使うセッション解決。

    v5.3 までは伏線側が `or repo.session`、ダイジェスト側が
    `artifacts.get("session")` のみで、`repo.session` しか持たない呼び出し元では
    ダイジェストだけ空振りしていた。ここに一本化する。
    """
    if session is not None:
        return session
    return getattr(repo, "session", None)


class EpisodeWriter(BaseAgent):
    def __init__(
        self,
        llm: LLMService,
        context_builder: ContextBuilderAgent,
        repo: Any = None,
        style_rag: Any = None,
        rag_prefetch: Any = None,
        context_retriever: Any = None,
        prompt_manager: PromptManager = None,
        compressor: Any = None,
        vector_store: Any = None,
        character_dict_path: str = None,
        plot_expander: Any = None,
    ):
        super().__init__(repo=repo, llm=llm, style_rag=style_rag, rag_prefetch=rag_prefetch)
        self.context_builder = context_builder
        self.context_retriever = context_retriever
        self.prompt_manager = prompt_manager
        self.compressor = compressor
        self.vector_store = vector_store
        self.plot_expander = plot_expander

        # 感情残基抽出器（遅延初期化）
        self._emotional_extractor: Optional[EmotionalResidueExtractor] = None
        self._character_dict_path = character_dict_path

        # Beat-to-Scene 分割執筆用のオーケストレーター（遅延初期化）
        self._scene_orchestrator: Optional[SceneWriterOrchestrator] = None
        self.last_metadata: Optional[WritingMetadata] = None
        # PLAN_W6 Step 9: 次話プロットの投機タスクの **ハンドル** を保持する。
        # 返り値を捨てると「最も並行度が高い処理」が管理不能になっていた。
        self._plot_prefetch_tasks: set = set()

    def _get_emotional_extractor(self) -> Optional[EmotionalResidueExtractor]:
        """感情残基抽出器を遅延初期化して取得"""
        if self._emotional_extractor is None and self.vector_store:
            try:
                char_dict = load_character_dict(self._character_dict_path)
                self._emotional_extractor = EmotionalResidueExtractor(
                    vector_store=self.vector_store,
                    character_dict=char_dict,
                )
            except Exception as e:
                logger.warning(f"感情残基抽出器初期化失敗: {e}")
                return None
        return self._emotional_extractor

    def _get_scene_orchestrator(self) -> SceneWriterOrchestrator:
        """SceneWriterOrchestratorを遅延初期化して取得する。"""
        if self._scene_orchestrator is None:
            scene_writer = SceneWriter(
                llm=self.llm,
                context_builder=self.context_builder,
                repo=self.repo,
                style_rag=self.style_rag,
                rag_prefetch=self.rag_prefetch,
                prompt_manager=self.prompt_manager,
                compressor=self.compressor,
            )
            self._scene_orchestrator = SceneWriterOrchestrator(scene_writer)
        return self._scene_orchestrator

    async def write_beat_to_scene(
        self,
        book_id: int,
        ep_num: int,
        context: dict[str, Any],
        target_word_count: int = 2400,
        custom_beats: Optional[dict[SceneRole, List[str]]] = None,
    ) -> str:
        """
        Beat-to-Scene 分割執筆でエピソード本文を生成する。
        1話を3シーン（導入・衝突・引き）に分割し、順次生成して結合する。

        Args:
            book_id: 書籍ID
            ep_num: エピソード番号
            context: 執筆コンテキスト
            target_word_count: 目標文字数（3シーンで均等配分）
            custom_beats: カスタムビート（シーン役割ごとのビートリスト）

        Returns:
            生成された本文（3シーン結合済み）
        """
        # JIT 詳細プロット展開フック (Plan J2)
        if self.plot_expander and hasattr(self.plot_expander, "ensure_detailed_plot"):
            try:
                detailed_plot = await self.plot_expander.ensure_detailed_plot(
                    book_id=book_id,
                    ep_num=ep_num,
                    branch_id=context.get("branch_id", 1),
                )
                if detailed_plot:
                    context["plot"] = detailed_plot
            except Exception as e:
                logger.warning(f"Ep.{ep_num}: JITプロット展開エラー (既存プロット継続): {e}")

        orchestrator = self._get_scene_orchestrator()

        # 3シーン順次生成
        scenes = await orchestrator.write_episode_scenes(
            book_id=book_id,
            branch_id=context.get("branch_id", 1),
            ep_num=ep_num,
            target_word_count=target_word_count,
            writing_context=context,
            custom_beats=custom_beats,
        )

        # シーンを結合して1話の本文として返す
        composed_text = orchestrator.compose_episode(scenes)

        # エロティックコンテンツを強化（結合後の全文に対して）
        erotic_enhancer = EroticEnhancer(self)
        composed_text = erotic_enhancer.enhance_erotic_content("", composed_text, context)

        # プロセ精練（オプション）
        try:
            genre = context.get("genre", "fantasy_action")
            style_intensity = context.get("style_intensity", "balanced")
            prose_refiner_enabled = context.get("prose_refiner_enabled", True)
            if prose_refiner_enabled:
                refiner = ProseRefinerAgent()
                refinement_result = await refiner.refine(
                    draft_text=composed_text,
                    genre=genre,
                    style_intensity=style_intensity,
                )
                composed_text = refinement_result.refined_text
        except Exception as e:
            logger.warning(f"Ep.{ep_num}: プロセ精練失敗: {e}")

        # ダンジョン配信ジャンルの場合、配信コメントブロックを追加
        if genre in ["dungeon_stream", "streaming_fantasy", "modern_fantasy"]:
            try:
                social_generator = SocialReactionGenerator(self.llm)

                # クライマックス部分を抽出（最後のシーン=引きシーンを使用）
                hook_scene = next((s for s in scenes if s.role == SceneRole.HOOK), None)
                climax_text = hook_scene.content if hook_scene else composed_text[-500:]

                comments = await social_generator.generate_stream_comments(
                    highlight_description=climax_text,
                    count=20,
                )

                if comments:
                    comment_block = "\n\n【配信コメント】\n"
                    for comment in comments[:10]:
                        comment_block += f"{comment.user}: {comment.text}\n"

                    composed_text = composed_text + comment_block

                    logger.info(f"Ep.{ep_num}: 配信コメントブロックを追加 ({len(comments)}件生成)")
            except Exception as e:
                logger.warning(f"Ep.{ep_num}: 配信コメント生成でエラー: {e}")

        clean_text, self.last_metadata = NovelOutputSplitter.split_novel_output(composed_text)

        # T6 Step 1: エピソード後処理（伏線自動回収 + ダイジェスト永続化）は
        # **`run()` のみ**が実行する。ここ（`write_beat_to_scene`）でも呼んでいたため、
        # `use_beat_to_scene=True`（既定経路）では 1話あたり **2回** 走っていた。
        # ダイジェスト生成は 1話1回のブロッキング LLM 呼出（約2500字入力）のため、
        # コストが2倍になっていた。`write()` は本文生成のみを責務とする。
        # メタデータはシーン単位では出力させない（`scene_hook.j2` が
        # 「メタ情報は不要」と指示しているため）、`run()` が統合後に1回だけ回収判定する。

        # 次話プロットの非同期投機的プリフェッチ (Plan J2)
        if self.plot_expander and hasattr(self.plot_expander, "prefetch_next_episode_plot"):
            try:
                task = self.plot_expander.prefetch_next_episode_plot(
                    book_id=book_id,
                    next_ep=ep_num + 1,
                    branch_id=context.get("branch_id", 1),
                )
                # PLAN_W6 Step 9: 返り値（asyncio.Task）を握り潰さない。
                self._track_plot_prefetch(task)
            except Exception as e:
                logger.debug(f"Ep.{ep_num}: 次話プリフェッチエラー (無視): {e}")

        return clean_text

    def _track_plot_prefetch(self, task: Any) -> None:
        """投機プロットタスクのハンドルを保持する（完了後は自動的に片付く）。"""
        if task is None:
            return
        holder = getattr(self, "_plot_prefetch_tasks", None)
        if holder is None:
            holder = set()
            self._plot_prefetch_tasks = holder
        holder.add(task)
        task.add_done_callback(holder.discard)

    async def _post_episode_finalize(
        self,
        book_id: int,
        branch_id: int,
        ep_num: int,
        written_text: str,
        writing_metadata: Any,
        repo: Any = None,
        session: Any = None,
        writing_context: dict[str, Any] | None = None,
    ) -> list[str]:
        """エピソード終了後の共通後処理（伏線回収 + ダイジェスト永続化）。

        **呼び出し点は `run()` の1箇所のみ**（T6 Step 1）。
        `write_beat_to_scene()` も `run()` を通るため、これで
        どちらの執筆経路でも長編耐性の機構が必ず1回だけ働く。

        Args:
            book_id: 作品ID
            branch_id: ブランチID
            ep_num: エピソード番号
            written_text: 生成された本文
            writing_metadata: LLM が返したメタデータ（無ければ None）
            repo: リポジトリ（無ければ伏線回収はスキップ）
            session: DB セッション（無ければ `repo.session` を使う）
            writing_context: 執筆コンテキスト（契約伏線IDの取得に使用）

        Returns:
            回収された伏線タイトルのリスト
        """
        if not written_text:
            return []

        resolved_titles: list[str] = []

        # 1) 伏線自動回収
        resolved_repo = repo if repo is not None else getattr(self, "repo", None)
        resolved_session = _resolve_session(resolved_repo, session)
        if resolved_repo is not None and resolved_session is not None:
            try:
                # v5.3: プロンプトに渡した契約伏線と同一の ID を渡す。
                # これにより EnsembleJudge の is_contracted が正しく判定され、
                # 「本話で回収必須の伏線」を高精度で判定できる。
                # 注意: ここに `or None` を付けると空リストが潰れ、
                # 「契約情報なし(None)」と「契約0件([])」が区別できなくなる。
                # そのまま渡すこと（Step 17）。
                contract_ids = [
                    f.get("id")
                    for f in ((writing_context or {}).get("contract_foreshadowings") or [])
                    if isinstance(f, dict) and f.get("id") is not None
                ]

                # v5.3 / Step 33: 作品全体の予定話数（`Book.target_eps`）を
                # 延期の上限として渡す。production の呼び出し元が
                # `total_episodes` を渡さないため `max_episode` が常に None に
                # なり、100話本でも延期不能が正しく判定されていなかった。
                total_episodes = await _resolve_total_episodes(
                    resolved_session, book_id, (writing_context or {})
                )

                foreshadowing_repo = DbForeshadowingRepository(resolved_session)
                foreshadowing_service = ForeshadowingService(foreshadowing_repo)
                resolved_titles = await foreshadowing_service.check_and_resolve(
                    book_id=book_id,
                    episode_num=ep_num,
                    draft_text=written_text,
                    writing_metadata=writing_metadata,
                    contract_ids=contract_ids,
                    total_episodes=total_episodes,
                )
                if resolved_titles:
                    logger.info(
                        f"Ep.{ep_num}: 伏線自動回収 - {', '.join(resolved_titles)}"
                    )
            except Exception as e:
                logger.warning(f"Ep.{ep_num}: 伏線自動回収でエラー: {e}")

        # 2) 事実ダイジェスト永続化
        # 伏線回収側と異なり、ここは例外が伝播すると**話全体が失敗**する。
        # ダイジェストは Layer2 の品質向上 (±100字要約) のための補助であり、
        # これを失ってまで1話-rollbackする理由がない。T6 Step 11:
        # 隔離 + 警告に揃え、握り潰しも無言化も避ける。
        try:
            await self._persist_episode_digest(
                resolved_session, book_id, ep_num, written_text
            )
        except Exception as e:
            logger.warning(
                f"Ep.{ep_num}: ダイジェスト永続化でエラー（本文と伏線回収は保持）: {e}"
            )

        return resolved_titles

    def detect_resolved_foreshadowings(
        self, content: str, pending_list: List[ForeshadowingEntity]
    ) -> List[str]:
        """生成された本文中から解決された伏線を簡易検知する。

        Args:
            content: 生成されたエピソード本文
            pending_list: 現在未回収の伏線リスト

        Returns:
            解決されたと判断された伏線のIDリスト
        """
        resolved_ids = []
        if not content or not pending_list:
            return resolved_ids

        content_lower = content.lower()
        for fs in pending_list:
            # キーワードのいずれかが本文に含まれているかをチェック
            for keyword in fs.keywords:
                if keyword.lower() in content_lower:
                    resolved_ids.append(fs.foreshadow_id)
                    break  # 1つでもキーワードが見つかったらその伏線は解決とみなす
            # 解決描写の簡易チェック（例: 「解決した」「明らかになった」等）
            # ここではキーワードチェックのみとする
        return resolved_ids

    async def build_context(
        self,
        book_id: int,
        branch_id: int,
        ep_num: int,
        target_word_count: int,
        style_tag: str | None = None,
    ) -> dict[str, Any]:
        """執筆に必要な完全なコンテキストを構築する。"""
        ctx = AgentContext(
            book_id=book_id,
            branch_id=branch_id,
            ep_num=ep_num,
            artifacts={
                "target_word_count": target_word_count,
                "style_tag": style_tag,
                "compressor": self.compressor,
            },
        )
        result = await self.context_builder.execute(ctx)
        return result.artifacts.get("writing_context", {})

    async def write(self, book_id: int, ep_num: int, context: dict[str, Any]) -> str:
        """
        エピソード本文を生成し、文字列で返す。
        :param book_id: 書籍ID
        :param ep_num: エピソード番号
        :param context: プロット情報、キャラ設定、世界設定などを含む辞書
        :return: 生成された本文（文字列）
        """
        # Beat-to-Scene 分割執筆が有効な場合はこちらを使用
        use_beat_to_scene = context.get("use_beat_to_scene", True)
        if use_beat_to_scene:
            target_word_count = context.get("target_word_count", 2400)
            custom_beats = context.get("custom_beats")
            return await self.write_beat_to_scene(
                book_id=book_id,
                ep_num=ep_num,
                context=context,
                target_word_count=target_word_count,
                custom_beats=custom_beats,
            )

        # 従来の一括生成（フォールバック/後方互換）
        # プロンプトを構築
        prompt_composer = PromptComposer(self)
        prompt = await prompt_composer.compose_writing_prompt(book_id, ep_num, context)

        # 初期結果を生成
        result = await self.llm.generate_text(
            purpose="writing",
            prompt=prompt,
            system_instruction=None,
            temperature=0.7,
        )
        if hasattr(result, "story_content"):
            result = result.story_content

        # エロティックコンテンツを強化
        erotic_enhancer = EroticEnhancer(self)
        result = erotic_enhancer.enhance_erotic_content(prompt, result, context)

        # プロセ精練（オプション）
        try:
            # 設定からジャンルとスタイル強度を取得（デフォルト値を設定）
            genre = context.get("genre", "fantasy_action")
            style_intensity = context.get("style_intensity", "balanced")
            prose_refiner_enabled = context.get("prose_refiner_enabled", True)
            if prose_refiner_enabled:
                refiner = ProseRefinerAgent()
                refinement_result = await refiner.refine(
                    draft_text=result,
                    genre=genre,
                    style_intensity=style_intensity
                )
                result = refinement_result.refined_text
        except Exception:
            # プロセ精練に失敗しても、元のテキストを返す（フォールバック）
            pass

        # Step 12: ダンジョン配信ジャンル等の場合、戦闘クライマックス後に自動で配信コメントブロックを本文へ結合する
        if genre in ["dungeon_stream", "streaming_fantasy", "modern_fantasy"]:
            try:
                # 社会反応ジェネレーターを初期化
                social_generator = SocialReactionGenerator(self.llm)

                # クライマックス部分を抽出（本文の最後の20%をクライマックスとみなす）
                climax_start_index = len(result) * 4 // 5  # 80%地点から開始
                if climax_start_index < len(result):
                    climax_text = result[climax_start_index:]
                else:
                    climax_text = result[-100:] if len(result) > 100 else result  # フォールバック

                # 配信コメントを生成
                comments = await social_generator.generate_stream_comments(
                    highlight_description=climax_text,
                    count=20
                )

                # コメントブロックをフォーマット
                if comments:
                    comment_block = "\n\n【配信コメント】\n"
                    for comment in comments[:10]:  # 最大10件まで表示
                        comment_block += f"{comment.user}: {comment.text}\n"

                    # 本文の終わりにコメントブロックを追加
                    result = result + comment_block

                    logger.info(f"Ep.{ep_num}: 配信コメントブロックを追加 ({len(comments)}件生成)")
            except Exception as e:
                logger.warning(f"Ep.{ep_num}: 配信コメント生成でエラー: {e}")

        clean_result, self.last_metadata = NovelOutputSplitter.split_novel_output(str(result))
        return clean_result

    async def run(self, ctx: AgentContext) -> AgentResult:
        """エージェント固有のメインロジック。サブクラスで実装する。"""
        book_id = ctx.book_id
        ep_num = ctx.ep_num
        # The writing context should be in the artifacts from the context_builder_agent
        writing_context = ctx.artifacts.get("writing_context", {})
        # Generate the written text
        written_text = await self.write(book_id, ep_num, writing_context)
        writing_metadata = getattr(self, "last_metadata", None)

        # T6 Step 1: エピソード後処理の**唯一の実行点**。
        # `write()` は `use_beat_to_scene=True`（既定）でも `False` でも
        # 必ずここを通るため、ここで1回だけ呼べば両経路をカバーできる。
        # （以前は `write_beat_to_scene()` 側でも呼んでいたため二重実行になっていた）
        await self._post_episode_finalize(
            book_id=book_id,
            branch_id=ctx.branch_id,
            ep_num=ep_num,
            written_text=written_text,
            writing_metadata=writing_metadata,
            repo=ctx.artifacts.get("repo"),
            session=ctx.artifacts.get("session"),
            writing_context=writing_context,
        )

        # エピソード終了後に感情残基を抽出・永続化
        try:
            extractor = self._get_emotional_extractor()
            if extractor and written_text:
                extractor.extract_and_persist(f"ep{ep_num}", written_text)
                logger.info(f"Ep.{ep_num}: 感情残基抽出完了")
        except Exception as e:
            logger.warning(f"Ep.{ep_num}: 感情残基抽出でエラー: {e}")

        return AgentResult(
            next_agent=None,
            artifacts={
                "written_text": written_text,
                "writing_metadata": writing_metadata,
            },
            should_retry=False,
            error=None,
        )

    async def _persist_episode_digest(
        self,
        session: Any,
        book_id: int,
        ep_num: int,
        written_text: str,
    ) -> None:
        """本話の事実ダイジェストを生成・保存する（失敗しても執筆は継続する）

        v5.3 / Step 32: ダイジェスト生成は話ごとに1回のブロッキング LLM 呼出
        （約2500字入力）を伴うため、1話あたりのコストに直結する。
        `ENABLE_EPISODE_DIGEST=0` で無効化できるようにし、モデルも
        tier1（構成・要約向けの軽量モデル）へ差し替える。
        """
        if session is None or not written_text:
            return
        if not _is_episode_digest_enabled():
            logger.info(
                f"Ep.{ep_num}: 事実ダイジェスト生成は ENABLE_EPISODE_DIGEST=0 で無効化されています"
            )
            return
        try:
            from src.services.context_compression.digest_service import (
                EpisodeDigestRepository,
                EpisodeDigestService,
            )

            service = EpisodeDigestService(
                repo=EpisodeDigestRepository(session),
                llm=_resolve_digest_llm(getattr(self, "llm", None)),
            )
            digest = await service.summarize_and_save(
                book_id=book_id,
                episode_num=ep_num,
                draft_text=written_text,
            )
            logger.info(f"Ep.{ep_num}: 事実ダイジェスト保存完了 ({len(digest)}字)")
        except Exception as e:
            logger.warning(f"Ep.{ep_num}: 事実ダイジェスト保存でエラー: {e}")
