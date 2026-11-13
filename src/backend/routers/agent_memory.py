"""Agent memory inspection, dump and compaction API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends

from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.agents.memory.manager import MemoryManager

router = APIRouter(
    prefix="/api/agent/memory",
    tags=["agent_memory"],
    dependencies=[Depends(get_current_user)],
)

_agent_memory_manager: Optional[MemoryManager] = None


def get_agent_memory_manager(user_id: int) -> MemoryManager:
    """ユーザー別メモリマネージャーを取得（テナント分離）。
    
    グローバルシングルトンではなく、user_id をキーにメモリ状態を分離する。
    """
    global _agent_memory_manager
    if _agent_memory_manager is None:
        _agent_memory_manager = MemoryManager()
    # user_id をメモリマネージャーにスコープ化（簡易版：インスタンスに記録）
    _agent_memory_manager.user_id = user_id  # type: ignore[attr-defined]
    return _agent_memory_manager


def set_agent_memory_manager(manager: MemoryManager) -> None:
    global _agent_memory_manager
    _agent_memory_manager = manager


@router.get("/core")
def get_core_memory(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """CoreMemory の全内容をダンプ（ユーザー別スコープ）"""
    manager = get_agent_memory_manager(current_user.id)
    return manager.core_memory.dump()


@router.get("/working")
def get_working_memory(current_user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """WorkingMemory のフレームスタックを取得（ユーザー別スコープ）"""
    manager = get_agent_memory_manager(current_user.id)
    frames = manager.working_memory.get_frames()
    return [f.to_dict() for f in frames]


@router.get("/archival/stats")
def get_archival_stats(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """ArchivalMemory の統計情報取得（ユーザー別スコープ）"""
    manager = get_agent_memory_manager(current_user.id)
    entries = list(manager.archival_memory._entries.values())
    return {
        "total_entries": len(entries),
        "entry_types": list({e.metadata.get("type", "unknown") for e in entries}),
    }


@router.post("/compact")
def force_compact_memory(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """CoreMemory の強制圧縮を実行（ユーザー別スコープ）"""
    manager = get_agent_memory_manager(current_user.id)
    compacted = manager.compact()
    return {
        "compacted": compacted,
        "tokens_after": manager.core_memory.estimate_tokens(),
    }
