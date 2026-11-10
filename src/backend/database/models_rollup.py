"""DigestRollupModel - 階層的逐次要約メモリのロールアップ ORM モデル (PLAN_M1 Step 5).

`digest_rollups` テーブルは「巻>章>話」のツリー状逐次要約を保存する。
- level='block': 章（ブロック）の確定事実要約（デフォルト10話/章）
- level='volume': 巻の確定事実要約（デフォルト5章/巻=50話/巻）

`stale_at` はメンバ digests 更新で失効フラグとして設定され、
次回の digest 保存時に該当 rollup の再生成トリガとなる。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint

from src.infrastructure.database.models.base_orm import Base


class DigestRollupModel(Base):
    """階層的ダイジェストロールアップモデル。

    Attributes:
        id: ロールアップの一意識別子
        book_id: 所属作品ID（booksテーブル外部キー）
        level: ロールアップの粒度（'block'=章, 'volume'=巻）
        start_ep: 対象範囲の開始話数
        end_ep: 対象範囲の終了話数
        digest_text: その範囲の確定事実要約テキスト
        stale_at: メンバ digest 更新により失効した日時（None=有効）
        created_at: レコード作成日時
        updated_at: レコード更新日時
    """

    __tablename__ = "digest_rollups"
    __table_args__ = (
        UniqueConstraint(
            "book_id", "level", "start_ep", "end_ep",
            name="uq_digest_rollups_book_level_range",
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level = Column(Text, nullable=False)
    start_ep = Column(Integer, nullable=False)
    end_ep = Column(Integer, nullable=False)
    digest_text = Column(Text, nullable=False)
    stale_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<DigestRollup(id={self.id}, book_id={self.book_id}, "
            f"level={self.level}, ep={self.start_ep}-{self.end_ep}, "
            f"stale={self.stale_at is not None})>"
        )
