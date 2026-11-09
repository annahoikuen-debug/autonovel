from __future__ import annotations

"""監査実行記録モデル定義。

UnifiedAuditor の定量・定性スコア、合否、LLM/プロンプト/温度などの
メタ情報、および監査時点の本文スナップショットを保持する。

このモデルは M0 (計測基盤) で導入し、AI 判定器キャリブレーションの
計測データソースとする。書き込みは fail-open で行い、監査の本処理
に影響を与えない。
"""

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


class AuditRun(Base):
    """単一の監査実行レコード。"""

    __tablename__ = "audit_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    ep_num = Column(Integer, nullable=False, index=True)

    # 定量内訳 (rule_based_metrics 由来)
    q_rhythm = Column(Float, nullable=False)
    q_dialogue = Column(Float, nullable=False)
    q_cliffhanger = Column(Float, nullable=False)
    q_cliche_count = Column(Integer, nullable=False)

    # 定性内訳 (unified_audit_prompt の 4 軸)
    qual_hook = Column(Float, nullable=False)
    qual_emotional = Column(Float, nullable=False)
    qual_character = Column(Float, nullable=False)
    qual_overall = Column(Float, nullable=False)

    # 合否
    final_score = Column(Float, nullable=False, index=True)
    is_passed = Column(Boolean, nullable=False)

    # 再現性のためのメタ
    gate_version = Column(String(50), nullable=False, default="1.0")
    model_name = Column(String(100), nullable=False)
    prompt_version = Column(String(50), nullable=False)
    temperature = Column(Float, nullable=False)
    judge_mode = Column(String(20), nullable=False)

    # 本文スナップショット (リテイクで上書きされるため監査時点の本文を保持)
    text_hash = Column(String(64), nullable=False, index=True)
    text_snapshot = Column(Text, nullable=False)

    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_audit_runs_book_ep", "book_id", "ep_num"),
    )
