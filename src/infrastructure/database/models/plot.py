from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from src.infrastructure.database.models.base_orm import Base
from src.infrastructure.database.types import CompatibleDateTime


"""Plot ORM モデル定義。

プロット情報（シナリオ設計）を永続化する。
"""


class Plot(Base):
    __tablename__ = "plots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_tension = Column(
        Float, nullable=True, comment="動的に計算された目標テンション値 (0.0-1.0)"
    )
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    # 複合一意制約 ``(book_id, branch_id, ep_num)`` の先頭列が ``book_id`` のため、
    # ``branch_id`` 単独の述語には使えない。branch_id のみによる絞り込み用に index を張る。
    branch_id = Column(Integer, default=1, nullable=False, index=True)
    ep_num = Column(Integer, nullable=False)
    thought_process = Column(Text, default="")
    title = Column(String(200))
    summary = Column(Text)
    one_line_summary = Column(Text, default="")
    detailed_blueprint = Column(Text, default="")
    tension = Column(Integer, default=50)
    tension_delta = Column(Integer, default=0)
    catharsis = Column(Integer, default=0)
    status = Column(String(50), default="planned")
    scenes = Column(Text, default="[]")
    is_catharsis = Column(Boolean, default=False)
    catharsis_type = Column(String(50), default="なし")
    love_meter = Column(Integer, default=0)
    next_hook = Column(Text, default="{}")
    misunderstanding_gap = Column(Text, default="")
    lite_model_director_notes = Column(Text, default="")
    script_content = Column(Text, default="")
    current_chain_phase = Column(String(50), default="Friction")
    resolution_style = Column(String(50), default="Cheat")
    burned_cost_or_loot = Column(String(100), default="なし")
    antagonist_status = Column(String(100), default="現状維持")
    thematic_milestone = Column(String(100), default="なし")
    state_integrity_score = Column(Integer, default=100)
    emotional_resonance_score = Column(Integer, default=0)
    thematic_depth_score = Column(Integer, default=0)
    literary_beauty_score = Column(Integer, default=0)
    erotic_intensity = Column(Integer, default=0)
    healed_fields = Column(Text, default="[]")
    is_micro_catharsis = Column(Boolean, default=False)
    information_asymmetry_level = Column(Float, default=0.0)
    cost_score = Column(Float, default=0.0)
    qol_delta = Column(Integer, default=0)
    discovery_item = Column(Text)
    sanctuary_event = Column(Text)
    is_locked = Column(Boolean, default=False)
    is_simulation = Column(Boolean, default=False)
    simulation_id = Column(String, server_default="", nullable=True)
    pov_character_id = Column(Integer, nullable=True)
    # 実使用: routers/plots.py:294 と plot.py:234 から必ず書き込まれるが、
    # モデルに存在しなかったため SQLAlchemy が黙って捨てていた（無言のデータ消失）。
    is_plot_twist = Column(Boolean, default=False, nullable=False)
    candidates = Column(Text, default="[]")
    created_at = Column(CompatibleDateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("book_id", "branch_id", "ep_num", name="uq_plots_book_branch_ep"),
    )
