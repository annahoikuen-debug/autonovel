from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""監査実行記録モデル定義。

UnifiedAuditor の定量・定性スコア、合否、LLM/プロンプト/温度などの
メタ情報、および監査時点の本文スナップショットを保持する。

このモデルは M0 (計測基盤) で導入し、AI 判定器キャリブレーションの
計測データソースとする。書き込みは fail-open で行い、監査の本処理
に影響を与えない。
"""


class AuditRun(Base):
    """単一の監査実行レコード。"""

    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ep_num: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # 定量内訳 (rule_based_metrics 由来)
    q_rhythm: Mapped[float] = mapped_column(Float, nullable=False)
    q_dialogue: Mapped[float] = mapped_column(Float, nullable=False)
    q_cliffhanger: Mapped[float] = mapped_column(Float, nullable=False)
    q_cliche_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # 定性内訳 (unified_audit_prompt の 4 軸)
    qual_hook: Mapped[float] = mapped_column(Float, nullable=False)
    qual_emotional: Mapped[float] = mapped_column(Float, nullable=False)
    qual_character: Mapped[float] = mapped_column(Float, nullable=False)
    qual_overall: Mapped[float] = mapped_column(Float, nullable=False)

    # 合否
    final_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # 再現性のためのメタ
    gate_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    judge_mode: Mapped[str] = mapped_column(String(20), nullable=False)

    # 本文スナップショット (リテイクで上書きされるため監査時点の本文を保持)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (  # type: ignore[assignment]
        Index("ix_audit_runs_book_ep", "book_id", "ep_num"),
    )
