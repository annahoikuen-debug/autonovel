from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Plot ORM モデル定義。

プロット情報（シナリオ設計）を永続化する。
"""


class Plot(Base):
    __tablename__ = "plots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_tension: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="動的に計算された目標テンション値 (0.0-1.0)"
    )
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    # 複合一意制約 ``(book_id, branch_id, ep_num)`` の先頭列が ``book_id`` のため、
    # ``branch_id`` 単独の述語には使えない。branch_id のみによる絞り込み用に index を張る。
    branch_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    ep_num: Mapped[int] = mapped_column(Integer, nullable=False)
    thought_process: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    one_line_summary: Mapped[str] = mapped_column(Text, default="")
    detailed_blueprint: Mapped[str] = mapped_column(Text, default="")
    tension: Mapped[int] = mapped_column(Integer, default=50)
    tension_delta: Mapped[int] = mapped_column(Integer, default=0)
    catharsis: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="planned")
    scenes: Mapped[str] = mapped_column(Text, default="[]")
    is_catharsis: Mapped[bool] = mapped_column(Boolean, default=False)
    catharsis_type: Mapped[str] = mapped_column(String(50), default="なし")
    love_meter: Mapped[int] = mapped_column(Integer, default=0)
    next_hook: Mapped[str] = mapped_column(Text, default="{}")
    misunderstanding_gap: Mapped[str] = mapped_column(Text, default="")
    lite_model_director_notes: Mapped[str] = mapped_column(Text, default="")
    script_content: Mapped[str] = mapped_column(Text, default="")
    current_chain_phase: Mapped[str] = mapped_column(String(50), default="Friction")
    resolution_style: Mapped[str] = mapped_column(String(50), default="Cheat")
    burned_cost_or_loot: Mapped[str] = mapped_column(String(100), default="なし")
    antagonist_status: Mapped[str] = mapped_column(String(100), default="現状維持")
    thematic_milestone: Mapped[str] = mapped_column(String(100), default="なし")
    state_integrity_score: Mapped[int] = mapped_column(Integer, default=100)
    emotional_resonance_score: Mapped[int] = mapped_column(Integer, default=0)
    thematic_depth_score: Mapped[int] = mapped_column(Integer, default=0)
    literary_beauty_score: Mapped[int] = mapped_column(Integer, default=0)
    erotic_intensity: Mapped[int] = mapped_column(Integer, default=0)
    healed_fields: Mapped[str] = mapped_column(Text, default="[]")
    is_micro_catharsis: Mapped[bool] = mapped_column(Boolean, default=False)
    information_asymmetry_level: Mapped[float] = mapped_column(Float, default=0.0)
    cost_score: Mapped[float] = mapped_column(Float, default=0.0)
    qol_delta: Mapped[int] = mapped_column(Integer, default=0)
    discovery_item: Mapped[str | None] = mapped_column(Text)
    sanctuary_event: Mapped[str | None] = mapped_column(Text)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_simulation: Mapped[bool] = mapped_column(Boolean, default=False)
    simulation_id: Mapped[str | None] = mapped_column(String, server_default="", nullable=True)
    pov_character_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 実使用: routers/plots.py:294 と plot.py:234 から必ず書き込まれるが、
    # モデルに存在しなかったため SQLAlchemy が黙って捨てていた（無言のデータ消失）。
    is_plot_twist: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    candidates: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("book_id", "branch_id", "ep_num", name="uq_plots_book_branch_ep"),)
