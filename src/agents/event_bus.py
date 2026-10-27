# src/agents/event_bus.py
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from redis.asyncio import Redis


@dataclass
class AgentEvent:
    agent: str
    payload: dict[str, Any]
    correlation_id: str
    round_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Phase 2: Specialist audit event types
AUDIT_SPECIALIST_STARTED = "audit.specialist.started"
AUDIT_SPECIALIST_COMPLETED = "audit.specialist.completed"

# Phase 4: Enrichment event types
ENRICHMENT_STARTED = "enrichment.started"
ENRICHMENT_STEP_COMPLETED = "enrichment.step_completed"
ENRICHMENT_COMPLETED = "enrichment.completed"
ENRICHMENT_ERROR = "enrichment.error"

# Phase 7: Blind Peer Review event types
BLIND_REVIEW_ROUND_COMPLETED = "blind_review.round_completed"
BLIND_REVIEW_SESSION_COMPLETED = "blind_review.session_completed"

# Orchestrator backtrack event
AGENT_BACKTRACKED = "agent.backtracked"


class EventBus:
    def __init__(self, use_redis: bool = False, redis_url: str | None = None):
        self._subs: dict[str, list[Callable[[AgentEvent], Awaitable[None]]]] = {}
        self._redis: Redis | None = None
        self._use_redis = use_redis
        self._redis_url = redis_url or "redis://localhost:6379/0"
        self._consumer_task: asyncio.Task | None = None
        # fire-and-forget タスクへの強参照。イベントループは弱参照しか保持しないため、
        # ここを保持しないと GC に回収され実行中に消失する。
        self._background_tasks: set[asyncio.Task] = set()

    def subscribe(self, agent: str, handler: Callable[[AgentEvent], Awaitable[None]]) -> None:
        self._subs.setdefault(agent, []).append(handler)

    def subscribe_async(self, agent: str, handler: Callable[[AgentEvent], Awaitable[None]]) -> None:
        """非同期ハンドラ登録（subscribe のエイリアス）"""
        self.subscribe(agent, handler)

    @staticmethod
    def _coerce_event(event: Any, payload: dict[str, Any] | None = None) -> AgentEvent:
        """``AgentEvent`` または ``(name, payload)`` のどちらでも受理して正規化する。

        後方互換のための shim。``src/backend/tasks/dag_scheduler`` /
        ``worker_recovery`` は ``publish_async(event_type, payload)`` という
        2 引数leases で 1 引数メソッドを呼ぶため TypeError になり、
        呼び出し側の ``except Exception: logger.debug(...)`` で黙殺されていた。
        """
        if isinstance(event, AgentEvent):
            return event
        if isinstance(event, str):
            return AgentEvent(
                agent=event,
                payload=payload or {},
                correlation_id=(payload or {}).get("correlation_id")
                or (payload or {}).get("task_id")
                or event,
            )
        raise TypeError(
            f"EventBus.publish expects an AgentEvent or (name, payload); got {type(event)!r}"
        )

    async def publish(self, event: AgentEvent, payload: dict[str, Any] | None = None) -> list[asyncio.Task]:
        """ハンドラを fire-and-forget で起動し、タスクを返す（呼び出し側が wait する前提）。"""
        ev = self._coerce_event(event, payload)
        tasks = []
        for handler in self._subs.get(ev.agent, []):
            tasks.append(asyncio.create_task(self._invoke_handler(handler, ev)))

        if self._use_redis and self._redis is not None:
            tasks.append(self._create_redis_task(ev))

        return tasks

    @staticmethod
    async def _invoke_handler(
        handler: Callable[[AgentEvent], Awaitable[None]], ev: AgentEvent
    ) -> None:
        """ハンドラ例外を握り潰さないラッパー。同期ハンドラも許容する。"""
        result = handler(ev)
        if inspect.isawaitable(result):
            await result

    def _create_redis_task(self, ev: AgentEvent) -> asyncio.Task:
        stream_name = f"agent_events:{ev.correlation_id}"
        return asyncio.create_task(
            self._redis.xadd(
                stream_name,
                {
                    "agent": ev.agent,
                    "payload": json.dumps(ev.payload, ensure_ascii=False),
                    "correlation_id": ev.correlation_id,
                },
            )
        )

    async def publish_async(self, event: Any, payload: dict[str, Any] | None = None) -> None:
        """非同期イベント発行。全ハンドラ完了を待ち、例外はログに記録する。

        以前は ``await self.publish(event)`` とするだけでタスク一覧を捨てていたため、
        await してもハンドラ完了の保証にならず、参照を 잃ったタスクは GC 対象となり、
        ハンドラ例外は「Task exception was never retrieved」として不可視になっていた。
        """
        tasks = await self.publish(event, payload)
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.warning(
                    "EventBus handler failed for agent=%r correlation_id=%r: %r",
                    self._coerce_event(event, payload).agent,
                    self._coerce_event(event, payload).correlation_id,
                    result,
                    exc_info=result,
                )

    def emit(self, event: Any, payload: dict[str, Any] | None = None) -> asyncio.Task | None:
        """同期コンテキストから使える非同期発行。実行中ループがあればバックグラウンドで走らせる。

        ``SkillAgent.emit_event`` は同期・非同期両方のコンテキストから 36 箇所で呼ばれる
        ため、``async def`` 化すると呼び出し側 36 箇所の変更が必要になる。
        そのため这里では「ループがあれば安全に登録、なければ警告して落とす」設計にする。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "EventBus.emit called with no running event loop; event %r dropped. "
                "Use 'await event_bus.publish_async(...)' from async code.",
                self._coerce_event(event, payload).agent,
            )
            return None
        task = loop.create_task(
            self.publish_async(event, payload), name="event_bus_emit"
        )
        # GC 対策 AND 例外可視化（fire_and_forget 相当.done コールバック）
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._log_task_exception)
        return task

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("EventBus.emit background publish failed: %r", exc, exc_info=exc)

    async def publish_sync(self, event: Any, payload: dict[str, Any] | None = None) -> None:
        """同期的にイベント発行（全ハンドラ完了を待つ）"""
        await self.publish_async(event, payload)

    async def publish_blind(
        self,
        event: AgentEvent,
        gate: Any,
        round_id: str | None = None,
    ) -> list[asyncio.Task]:
        """Blind peer review 対応発行。

        gate.scrub_payload() で参照禁止エージェントの出力をマスクしてから発行する。

        Args:
            event: 発行するイベント
            gate: BlindReviewGate インスタンス
            round_id: 現在のレビューラウンドID（クロスラウンド汚染防止用）
        """
        from src.services.blind_review import BlindReviewGate
        if isinstance(gate, BlindReviewGate):
            scrubbed_payload = gate.scrub_payload(event.payload)

            # メタデータにラウンド情報を埋め込み（クロスラウンド汚染検知用）
            blind_payload = {
                **scrubbed_payload,
                "_blind_meta": {
                    "round_id": round_id or event.round_id,
                    "gate_config_hash": getattr(gate, "config_hash", None),
                    "scrubbed_at": __import__("datetime").datetime.now().isoformat(),
                }
            }

            blind_event = AgentEvent(
                agent=event.agent,
                payload=blind_payload,
                correlation_id=event.correlation_id,
                round_id=round_id or event.round_id,
                metadata={"blind_review": True, **(event.metadata or {})},
            )
            return await self.publish(blind_event)
        return await self.publish(event)

    async def start_redis(self) -> None:
        """Redis 接続を初期化し、コンシューマータスクを開始。"""
        if not self._use_redis:
            return
        try:
            import redis.asyncio as redis

            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            # コンシューマータスクは必要に応じて別途実装
        except ImportError:
            # redis-py 不在時は無視
            self._use_redis = False

    async def stop_redis(self) -> None:
        """Redis 接続をクローズ。"""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        if self._consumer_task is not None:
            await self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass


_global_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """システム共通のグローバル EventBus シングルトンを取得."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


__all__ = [
    "AUDIT_SPECIALIST_COMPLETED",
    "AUDIT_SPECIALIST_STARTED",
    "BLIND_REVIEW_ROUND_COMPLETED",
    "BLIND_REVIEW_SESSION_COMPLETED",
    "ENRICHMENT_COMPLETED",
    "ENRICHMENT_ERROR",
    "ENRICHMENT_STARTED",
    "ENRICHMENT_STEP_COMPLETED",
    "AGENT_BACKTRACKED",
    "AgentEvent",
    "EventBus",
    "get_event_bus",
]
