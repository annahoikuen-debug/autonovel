"""src/domain/entities/checkpoint.py (CheckpointStatus / WorkflowCheckpoint) の単体テスト."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.domain.entities.checkpoint import CheckpointStatus, WorkflowCheckpoint


class TestCheckpointStatus:
    """CheckpointStatus 列挙体のテスト."""

    def test_values(self):
        """各ステータスが期待される文字列値を持つ."""
        assert CheckpointStatus.PENDING == "pending"
        assert CheckpointStatus.IN_PROGRESS == "in_progress"
        assert CheckpointStatus.COMPLETED == "completed"
        assert CheckpointStatus.FAILED == "failed"


class TestWorkflowCheckpoint:
    """WorkflowCheckpoint のテスト."""

    def test_create_minimal(self):
        """必須フィールドのみでチェックポイントを作成できる."""
        checkpoint = WorkflowCheckpoint(
            checkpoint_id="cp-1",
            task_id="task-1",
            step_name="step_a",
        )
        assert checkpoint.checkpoint_id == "cp-1"
        assert checkpoint.task_id == "task-1"
        assert checkpoint.step_name == "step_a"
        assert checkpoint.step_index == 0
        assert checkpoint.status == CheckpointStatus.PENDING
        assert checkpoint.state_payload == {}
        assert checkpoint.error_message is None
        assert isinstance(checkpoint.created_at, datetime)
        assert isinstance(checkpoint.updated_at, datetime)

    def test_create_full(self):
        """全フィールド指定でチェックポイントを作成できる."""
        checkpoint = WorkflowCheckpoint(
            checkpoint_id="cp-2",
            task_id="task-2",
            step_name="step_b",
            step_index=3,
            status=CheckpointStatus.IN_PROGRESS,
            state_payload={"key": "value"},
            error_message="エラー発生",
        )
        assert checkpoint.step_index == 3
        assert checkpoint.status == CheckpointStatus.IN_PROGRESS
        assert checkpoint.state_payload == {"key": "value"}
        assert checkpoint.error_message == "エラー発生"

    def test_status_transition(self):
        """ステータスを PENDING → IN_PROGRESS → COMPLETED と遷移できる."""
        checkpoint = WorkflowCheckpoint(checkpoint_id="cp-3", task_id="task-3", step_name="step_c")
        assert checkpoint.status == CheckpointStatus.PENDING
        checkpoint.status = CheckpointStatus.IN_PROGRESS
        assert checkpoint.status == CheckpointStatus.IN_PROGRESS
        checkpoint.status = CheckpointStatus.COMPLETED
        assert checkpoint.status == CheckpointStatus.COMPLETED

    def test_invalid_status(self):
        """未定義のステータス文字列は ValidationError."""
        with pytest.raises(ValidationError):
            WorkflowCheckpoint(
                checkpoint_id="cp-4",
                task_id="task-4",
                step_name="step_d",
                status="unknown_status",
            )
