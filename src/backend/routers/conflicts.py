"""API endpoints for conflict review and manual resolution."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.backend.auth import get_current_user
from src.backend.database.models import User
from src.stores.conflict_store import ConflictStore

router = APIRouter(
    prefix="/api/conflicts",
    tags=["conflicts"],
    dependencies=[Depends(get_current_user)],
)

_conflict_store_instance: Optional[ConflictStore] = None


def get_conflict_store(user_id: int) -> ConflictStore:
    global _conflict_store_instance
    if _conflict_store_instance is None:
        _conflict_store_instance = ConflictStore()
    # ユーザー別スコープを記録（簡易版）
    _conflict_store_instance.user_id = user_id  # type: ignore[attr-defined]
    return _conflict_store_instance


def set_conflict_store(store: ConflictStore) -> None:
    global _conflict_store_instance
    _conflict_store_instance = store


class ResolveConflictRequest(BaseModel):
    resolution: str  # "annotation" | "rule_engine" | "pipeline" | "manual"
    manual_value: Optional[float] = None


@router.get("")
def list_conflicts(
    episode: Optional[int] = Query(None, description="エピソード番号"),
    current_user: User = Depends(get_current_user),
):
    """矛盾一覧取得（ユーザー別スコープ）"""
    store = get_conflict_store(current_user.id)
    if episode is not None:
        conflicts = store.get_conflicts_by_episode(episode)
    else:
        conflicts = store.get_all_conflicts()
    return [c.to_dict() for c in conflicts]


@router.get("/{conflict_id}")
def get_conflict(
    conflict_id: str,
    current_user: User = Depends(get_current_user),
):
    """矛盾詳細取得（ユーザー別スコープ）"""
    store = get_conflict_store(current_user.id)
    c = store.get_conflict(conflict_id)
    if not c:
        raise HTTPException(status_code=404, detail="Conflict not found")
    res = store.get_resolution(conflict_id)
    c_dict = c.to_dict()
    c_dict["resolution"] = res
    return c_dict


@router.post("/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    body: ResolveConflictRequest,
    current_user: User = Depends(get_current_user),
):
    """矛盾の手動解決を保存（ユーザー別スコープ）"""
    store = get_conflict_store(current_user.id)
    valid_resolutions = {"annotation", "rule_engine", "pipeline", "manual"}
    if body.resolution not in valid_resolutions:
        raise HTTPException(status_code=400, detail=f"Invalid resolution. Must be one of {valid_resolutions}")

    if body.resolution == "manual" and body.manual_value is None:
        raise HTTPException(status_code=400, detail="manual_value is required when resolution is 'manual'")

    store.resolve_conflict(
        conflict_id=conflict_id,
        resolution=body.resolution,
        manual_value=body.manual_value,
    )
    return {
        "status": "resolved",
        "conflict_id": conflict_id,
        "resolution": body.resolution,
        "manual_value": body.manual_value,
    }
