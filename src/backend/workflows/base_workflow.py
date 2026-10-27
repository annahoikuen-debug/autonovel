from abc import ABC, abstractmethod
import inspect
import logging
from typing import Any

from src.backend.database import DataRepository
from src.backend.orchestrator_engine_adapter import OrchestratorEngineAdapter
from src.backend.planning_service import PlanningService
from src.backend.protocols import BiblePort, CritiquePort, TensionPort, WritingPort
from src.backend.writing_service import WritingService
from src.shared.utils import StatusReporter

logger = logging.getLogger(__name__)


def _is_usable_tension_port(candidate: Any) -> bool:
    """TensionPort の 2 メソッドが「呼ばれても例外を投げない」実装かを判定する.

    OrchestratorEngineAdapter は両メソッドを定義しているが中身が
    ``raise NotImplementedError`` であり、属性の有無 (``hasattr``) では
    使えると誤判定されてしまう。adapter 自身を信用せずに、
    ソース上で未実装かを静的に確認する。
    """
    for name in ("determine_target_tension", "validate_tension_deviation"):
        method = getattr(candidate, name, None)
        if method is None or not callable(method):
            return False
        try:
            source = inspect.getsource(method)
        except (OSError, TypeError):
            # ソースが取れない場合は判定を諦めて「使える」とみなす
            return True
        body = source.split("\n", 1)[1] if "\n" in source else ""
        if "NotImplementedError" in body:
            return False
    return True


class BaseWorkflow(ABC):
    """
    Abstract base class for all domain workflows.
    Each workflow encapsulates a single use case of the application.

    Phase 4 (ADR-0004) より、engine に加えてドメインサービス
    (WritingService, PlanningService 等) を受け取れるよう拡張した。
    engine は任意（後方互換のため Optional）とし、services は
    注入されなければ engine から委譲する。
    """

    def __init__(
        self,
        engine: OrchestratorEngineAdapter | None = None,
        writing: WritingPort | None = None,
        planner: PlanningService | None = None,
        writing_service: WritingService | None = None,
        repo: DataRepository | None = None,
        critique: CritiquePort | None = None,
        narrative: Any | None = None,
        marketing: Any | None = None,
        bible_agent: BiblePort | None = None,
        plot_agent: Any | None = None,
        formatter: Any | None = None,
        vector_store: Any | None = None,
        llm_client: Any | None = None,
        tension: TensionPort | None = None,
        image_service: Any | None = None,
        illustration_agent: Any | None = None,
        illustration_workflow: Any | None = None,
    ):
        self.engine = engine
        # WritingPort: 注入されなければ engine.writer で代用（後方互換）
        self.writing: WritingPort = (
            writing
            if writing is not None
            else (getattr(engine, "writer", None) if engine else None)  # type: ignore[assignment]
        )
        # PlanningService: 注入されなければ engine.planner で代用
        self.planner: PlanningService | None = (
            planner
            if planner is not None
            else (getattr(engine, "planner", None) if engine else None)
        )
        # WritingService: 注入されなければ engine.writer で代用（プロトコル互換）
        self.writing_service: WritingService | None = (
            writing_service
            if writing_service is not None
            else (getattr(engine, "writer", None) if engine else None)
        )
        # DataRepository: 注入されなければ engine.repo で代用
        self.repo: DataRepository | None = (
            repo if repo is not None else (getattr(engine, "repo", None) if engine else None)
        )
        # その他のサービスポート
        self.critique: CritiquePort | None = (
            critique
            if critique is not None
            else (getattr(engine, "critique", None) if engine else None)
        )
        self.narrative: Any | None = (
            narrative
            if narrative is not None
            else (getattr(engine, "narrative", None) if engine else None)
        )
        self.marketing: Any | None = (
            marketing
            if marketing is not None
            else (getattr(engine, "marketing", None) if engine else None)
        )
        self.bible_agent: BiblePort | None = (
            bible_agent
            if bible_agent is not None
            else (getattr(engine, "bible_agent", None) if engine else None)
        )
        self.plot_agent: Any | None = (
            plot_agent
            if plot_agent is not None
            else (getattr(engine, "plot_agent", None) if engine else None)
        )
        self.formatter: Any | None = (
            formatter
            if formatter is not None
            else (getattr(engine, "formatter", None) if engine else None)
        )
        # Prefetch 用
        self.vector_store: Any | None = (
            vector_store if vector_store is not None else getattr(engine, "vector_store", None)
        )
        self.llm_client: Any | None = (
            llm_client
            if llm_client is not None
            else (getattr(engine, "llm", None) or getattr(engine, "client", None))
        )
        # TensionService: 注入されなければ engine の tension_agent で代用、
        # なければ engine のメソッドで代用（engine が TensionPort 相当のメソッドを持つため）
        self.tension: TensionPort | None = (
            tension
            if tension is not None
            else (getattr(engine, "tension_agent", None) if engine else None)
        )
        if self.tension is None and engine is not None:
            # engine が直接 determine_target_tension / validate_tension_deviation を持つ場合は
            # engine 自身を tension として利用（後方互換）
            if hasattr(engine, "determine_target_tension") and hasattr(
                engine, "validate_tension_deviation"
            ):
                self.tension = engine

        # 両メソッドを未実装のまま advertise している（NotImplementedError を投げる）
        # エンジン适配器は、呼び出された時点で必ず 500 になるため、属性の有無では
        # 「使える」と判定できない。実際に呼べる実装があるかをここで確定させる。
        if self.tension is not None and not _is_usable_tension_port(self.tension):
            logger.warning(
                "Tension 功能が未実装のエンジン (%s) が注入されたため、テンション目標の"
                "算出・逸脱検証を無効化する。プロット展開自体は続行する。",
                type(self.tension).__name__,
            )
            self.tension = None

        self.image_service = image_service
        self.illustration_agent = illustration_agent
        self.illustration_workflow = illustration_workflow

    @abstractmethod
    async def execute(self, reporter: StatusReporter, **kwargs) -> dict[str, Any]:
        """
        Execute the workflow logic.
        """
        pass
