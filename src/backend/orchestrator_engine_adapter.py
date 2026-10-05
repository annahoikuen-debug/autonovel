"""
OrchestratorEngineAdapter - Orchestrator を旧エンジン互換インターフェースでラップするアダプター。

これにより既存のパイプラインステップが変更なしで動作する。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.agents.orchestrator import Orchestrator, AgentContext, AgentName
from src.agents.planning import PlanningAgent
from src.agents.writing.agent import WritingAgent as SkillWritingAgent
from src.backend.database.pipeline_repo import session_factory_from

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """LLM 出力から JSON オブジェクトを取り出す。

    Markdown のコードフェンスで囲まれている場合と、回过神的后ろに
    説明文が付く場合の両方に対応する。
    """
    if not text:
        raise ValueError("LLM の応答が空です。")
    candidates: list[str] = []
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"LLM の応答から JSON を抽出できませんでした: {text[:200]!r}")


class _GenerateResultCompat:
    """``GenerateResult`` として、かつ dict としても扱える結果オブジェクト。

    ``src/models/base.py`` の ``GenerateResult`` は属性アクセス（``.success``）を
    要求する一方、``src/agents/planning.py`` は ``result.get("success")`` と
    dict アクセスで値を読む。両方の呼び出しを 1 つの生成結果で満たすために、
    ``get()`` を追加した ``GenerateResult`` を返す。
    """

    def __init__(self, **kwargs: Any) -> None:
        from src.models.base import GenerateResult

        self._result = GenerateResult(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_result"), name)

    def get(self, key: str, default: Any = None) -> Any:
        mapping = {
            "success": self._result.success,
            "metadata": self._result.metadata,
            "data": self._result.story_content,
            "story_content": self._result.story_content,
            "error_message": self._result.error_message,
        }
        return mapping.get(key, default)

    def __repr__(self) -> str:  # pragma: no cover - デバッグ表示のみ
        return f"_GenerateResultCompat({self._result!r})"


class LLMJsonBridge:
    """``BaseLLMAdapter`` を ``generate_json`` 契約へ橋渡しする。

    ``WorldBibleGenerator`` / ``PlanningAgent`` は
    ``await llm.generate_json(<model>, prompt, response_schema=..., reporter=...)``
    を呼び、``.success`` / ``.metadata`` を持つ結果を期待する。一方
    ``get_llm_adapter()`` が返す ``BaseLLMAdapter`` は ``generate_text`` しか
    持たない。このクラスがその差を吸収する。
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> Any:
        return self._adapter

    async def generate_json(
        self,
        *args: Any,
        prompt: str | None = None,
        response_schema: Any = None,
        reporter: Any = None,
        **kwargs: Any,
    ) -> _GenerateResultCompat:
        # ``purpose="planning"`` 形式（位置引数なし）にも対応する。
        if prompt is None:
            for arg in args:
                if isinstance(arg, str) and ("\n" in arg or len(arg) > 40):
                    prompt = arg
                    break
            if prompt is None:
                prompt = next((a for a in args if isinstance(a, str)), "")

        max_tokens = int(kwargs.get("max_tokens") or 8000)
        try:
            raw = await self._adapter.generate_text(
                prompt,
                system_prompt=kwargs.get("system_prompt"),
                max_tokens=max_tokens,
                temperature=float(kwargs.get("temperature", 0.7)),
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001 - 失敗を結果として伝える
            logger.warning("LLM JSON 生成に失敗しました: %s", exc)
            return _GenerateResultCompat(
                success=False, metadata={}, error_type=type(exc).__name__, error_message=str(exc)
            )

        try:
            data = _extract_json(raw)
        except ValueError as exc:
            logger.warning("LLM 応答の JSON 解析に失敗しました: %s", exc)
            return _GenerateResultCompat(success=False, metadata={}, error_type="json_decode", error_message=str(exc))

        # スキーマ検証は呼び出し側（``model_validate(metadata)``）が行う。
        # ここでは生の dict を返すだけにして、二重検証を避ける。
        return _GenerateResultCompat(success=True, metadata=data, story_content=raw)


class PlannerAdapter:
    """``WorldBibleGenerator`` を旧 planner インターフェースでラップ

    ``engine.planner`` は Orchestrator を必須にしない。DI コンテナから注入
    された ``repo`` / ``llm`` / ``db`` があれば、それだけで企画生成できる。
    Orchestrator があるときは、ノード実行を優先して委譲する。
    """

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        repo: Any = None,
        llm: Any = None,
        pm: Any = None,
        db: Any = None,
    ):
        self._orchestrator = orchestrator
        self._repo = repo
        self._llm = llm
        self._pm = pm
        self._db = db
        self._planning_agent = None
        self._bible_generator = None

    @property
    def planning_agent(self) -> PlanningAgent:
        if self._planning_agent is None:
            skills = self._orchestrator._skill_instances if self._orchestrator else {}
            self._planning_agent = PlanningAgent(
                repo=self._repo or skills.get("planning", {}).get("repo"),
                llm=self._llm or skills.get("planning", {}).get("llm"),
                prompt_manager=self._pm,
            )
        return self._planning_agent

    @property
    def bible_generator(self) -> Any:
        """``WorldBibleGenerator`` を遅延構築する。

        ``create_hegemony_plan`` の実体はここにある。``debate`` / ``marketing``
        / ``auditor`` は ``ultra_fast`` 経路では使われないため ``None`` のままにする。
        """
        if self._bible_generator is None:
            from src.services.bible_service import WorldBibleGenerator

            repo = self._repo
            if repo is None and self._db is not None:
                from src.backend.database.repository import DataRepositoryFacade

                repo = DataRepositoryFacade(self._db)

            llm = self._llm
            if llm is not None and not hasattr(llm, "generate_json"):
                llm = LLMJsonBridge(llm)

            pm = self._pm
            if pm is None:
                from prompts.manager import PromptManager

                pm = PromptManager()

            self._bible_generator = WorldBibleGenerator(repo, llm, pm, None, None, None)
        return self._bible_generator

    @property
    def plan_auditor(self) -> Any:
        """Bible 完全性監査。未注入なら ``None``（``PlanStep`` は監査をスキップする）。"""
        return getattr(self.bible_generator, "auditor", None)

    async def create_hegemony_plan(self, **kwargs: Any):
        """``WorldBibleGenerator.create_hegemony_plan`` と互換。

        戻り値は ``(book_id, bible)``。``PlanStep`` は ``bible.title`` を読む。
        """
        orchestrator = self._orchestrator
        if orchestrator is not None:
            planning_node = orchestrator.nodes.get("planning") or orchestrator.nodes.get(AgentName.PLANNING)
            if planning_node is not None:
                ctx = AgentContext(
                    book_id=kwargs.get("book_id", 0),
                    branch_id=1,
                    ep_num=1,
                    artifacts=kwargs,
                )
                result = await planning_node(ctx)
                book_id = result.artifacts.get("book_id")
                bible = result.artifacts.get("bible")
                if book_id is not None and bible is not None:
                    return book_id, bible

        return await self.bible_generator.create_hegemony_plan(**kwargs)

    async def infer_easy_mode_params(self, user_prompt: str, reporter: Any = None):
        """PlanningAgent.infer_easy_mode_params と互換"""
        agent = self.planning_agent
        if agent is not None and hasattr(agent, "infer_easy_mode_params"):
            return await agent.infer_easy_mode_params(user_prompt, reporter=reporter)
        raise NotImplementedError


class WriterAdapter:
    """WritingAgent (Skill版) を旧 writer インターフェースでラップ"""

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        repo: Any = None,
        llm: Any = None,
        style_rag: Any = None,
        rag_prefetch: Any = None,
        pm: Any = None,
        ctx_mgr: Any = None,
        session_factory: Any = None,
    ):
        self._orchestrator = orchestrator
        self._repo = repo
        self._llm = llm
        self._style_rag = style_rag
        self._rag_prefetch = rag_prefetch
        self._pm = pm
        self._ctx_mgr = ctx_mgr
        self._session_factory = session_factory
        self._writing_agent = None

    @property
    def writing_agent(self) -> SkillWritingAgent:
        if self._writing_agent is None:
            skills = self._orchestrator._skill_instances if self._orchestrator else {}
            pm = self._pm
            if pm is None:
                # SceneWriter / EpisodeWriter は prompt_manager を必須とする。
                # 未注入のままだと「PromptManager is not injected into WritingAgent」で
                # 全シーンが 0文字生成になり、4話目以降が空になる。
                from prompts.manager import PromptManager

                pm = PromptManager()
            self._writing_agent = SkillWritingAgent(
                repo=self._repo if self._repo is not None else skills.get("writing", {}).get("repo"),
                llm=self._llm if self._llm is not None else skills.get("writing", {}).get("llm"),
                style_rag=self._style_rag or skills.get("writing", {}).get("style_rag"),
                rag_prefetch=self._rag_prefetch or skills.get("writing", {}).get("rag_prefetch"),
                pm=pm,
                ctx_mgr=self._ctx_mgr,
                session_factory=self._session_factory,
            )
        return self._writing_agent

    async def generate_episodes_pipeline(self, **kwargs: Any):
        """WritingAgent.generate_episodes_pipeline と互換"""
        agent = self.writing_agent
        if agent is not None and hasattr(agent, "generate_episodes_pipeline"):
            return await agent.generate_episodes_pipeline(**kwargs)
        raise NotImplementedError("generate_episodes_pipeline が利用できません。WritingAgent を注入してください。")


class OrchestratorEngineAdapter:
    """
    Orchestrator を UltimateHegemonyEngine 互換インターフェースでラップするアダプター。

    既存のパイプラインステップ (pipeline_steps.py 等) が engine.planner, engine.writer 等を
    使用しているため、それらを Orchestrator 経由で提供する。
    """

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        repo: Any = None,
        db: Any = None,
        llm: Any = None,
        plot_service: Any = None,
        session_factory: Any = None,
        **extra: Any,
    ):
        """DI コンテナから注入された依存を保持する。

        以前は ``__init__(self, orchestrator)`` しか受け取っていなかったが、
        ``container/app.py`` の engine プロバイダは api_key / repo / db / llm /
        cooldown / plot_service / illustration_agent を渡しており、生成のたびに
        ``TypeError: unexpected keyword argument 'api_key'`` になっていた。
        その結果 ``container.engine()`` を触る全ワークフロー
        （plots / episodes / marketing 系）がワークフロー起動前に落ちていた。

        orchestrator は任意。未設定でも注入依存から各プロパティを解決できる。

        Args:
            session_factory: ``async with`` 可能なセッション工場。未指定かつ
                ``db`` がある場合はそこから組み立てる（伏線自動回収 /
                事実ダイジェスト保存が「1話1トランザクション」で動く）。
        """
        self._orchestrator = orchestrator
        self._injected: dict[str, Any] = {
            "repo": repo,
            "db": db,
            "llm": llm,
            "plot_service": plot_service,
            # 伏線自動回収 / 事実ダイジェスト保存用のセッション工場。
            # 明示指定が無ければ ``db`` から組み立てる（後処理だけ短いスコープ）。
            "session_factory": session_factory or (session_factory_from(db) if db is not None else None),
        }
        self._injected.update(extra)
        self._planner = None
        self._writer = None

    def _dep(self, name: str) -> Any:
        """注入済み依存を優先し、無ければ Orchestrator のスキルから探す。"""
        value = self._injected.get(name)
        if value is not None:
            return value
        orchestrator = self._orchestrator
        if orchestrator is None:
            return None
        for skill in getattr(orchestrator, "_skill_instances", {}).values():
            found = getattr(skill, name, None)
            if found:
                return found
        return None

    @property
    def orchestrator(self) -> Orchestrator | None:
        """注入されている Orchestrator（無ければ None）。"""
        return self._orchestrator

    @property
    def planner(self) -> PlannerAdapter:
        """旧 planner インターフェース。

        Orchestrator が無くても、注入された repo / llm / db から
        ``WorldBibleGenerator`` を組み立てる。以前は Orchestrator 未設定で
        必ず ``RuntimeError`` になり、pipeline_steps の PlanStep が到達不能だった。
        """
        if self._planner is None:
            self._planner = PlannerAdapter(
                self._orchestrator,
                repo=self.repo,
                llm=self.llm,
                db=self.db,
            )
        return self._planner

    @property
    def writer(self) -> WriterAdapter:
        if self._writer is None:
            self._writer = WriterAdapter(
                self._orchestrator,
                repo=self.repo,
                llm=self.llm,
                pm=self._dep("pm"),
                ctx_mgr=self.ctx_mgr,
                session_factory=self._dep("session_factory"),
            )
        return self._writer

    @property
    def repo(self) -> Any:
        """リポジトリへのアクセス"""
        return self._dep("repo")

    @property
    def llm(self) -> Any:
        return self._dep("llm")

    @property
    def pm(self) -> Any:
        return self._dep("pm")

    @property
    def ctx_mgr(self) -> Any:
        return self._dep("ctx_mgr")

    @property
    def plot_service(self) -> Any:
        return self._dep("plot_service")

    # その他必要なプロパティを追加
    @property
    def formatter(self) -> Any:
        return None

    @property
    def validator(self) -> Any:
        return None

    @property
    def auditor(self) -> Any:
        return None

    @property
    def narrative(self) -> Any:
        return None

    @property
    def critique(self) -> Any:
        return None

    @property
    def marketing(self) -> Any:
        return None

    @property
    def bible_agent(self) -> Any:
        return None

    @property
    def plot_agent(self) -> Any:
        return None

    @property
    def style_rag(self) -> Any:
        return None

    @property
    def db(self) -> Any:
        return self._dep("db")

    @property
    def logic_validator(self) -> Any:
        return None

    @property
    def generate_json(self) -> Any:
        if self.llm and hasattr(self.llm, "generate_json"):
            return self.llm.generate_json
        return None

    def dispose(self) -> None:
        pass

    async def sync_bible(self, book_id: int, reporter: Any | None = None) -> Any:
        raise NotImplementedError

    async def resolve_bible_setting(self, setting_id: int, status: str) -> None:
        raise NotImplementedError

    async def determine_target_tension(
        self,
        book_id: int,
        ep_num: int,
        genre: str,
        story_type: str | None = None,
    ) -> float:
        raise NotImplementedError

    async def validate_tension_deviation(
        self,
        ep_num: int,
        generated_tension: float,
        book_id: int,
        tolerance: float = 0.2,
    ) -> tuple[bool, float]:
        raise NotImplementedError
