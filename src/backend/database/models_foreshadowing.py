"""ForeshadowingModel - 伏線ステートマシン SQLAlchemy ORMモデル。

伏線の設置・進展・回収・放棄をリレーショナルテーブルで管理する。
Apache AGE / NetworkX を完全に置換するv5.0の中核テーブル。

`keywords`（設置時に付ける手がかり語）:
    - 設置側（planting）のみ書き込まれ、回収判定や既存クエリの入力には
      一切影響しないため `nullable=True`。
    - 格納形式は **Text 列に入る JSON 文字列**。JSON 配列カラム（JSONB / ARRAY）
      は使わないので、既存 SQLite DB への追加でも互換性が壊れない。
    - 区切り文字に `,` を使うと「`,` を含むキーワード」が往復で壊れるため、
      `encode_keywords` / `decode_keywords` を通じて
      区切り文字・引用符・制御文字を含む合格率を無損失で往復させる。
    - `decode_keywords` は **例外を投げない**。手動編集で壊れた行は
      「キーワードなし」に劣化し、呼び出し側で落ちない。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from src.infrastructure.database.models.base_orm import Base

logger = logging.getLogger(__name__)


def encode_keywords(keywords: Optional[Iterable[Any]]) -> Optional[str]:
    """キーワード列を Text 表現（JSON 文字列）へ変換する。

    `None`（未指定）と空列はどちらも `None` を返す。空リストは
    どの消費側から見ても「未設定」と等価で、情報量を持たないため。

    非文字列要素は `str()` で強制変換する（話数などの int もそのまま渡せる）。
    """
    if keywords is None:
        return None
    items = [str(k) for k in keywords]
    if not items:
        return None
    return json.dumps(items, ensure_ascii=False)


def decode_keywords(raw: Optional[Any]) -> Optional[list]:
    """Text 表現（JSON 文字列）をキーワード列へ戻す。

    NULL / 解析不能 / リストでない payload は `None` を返す。手で編集された
    行で例外が漏れて呼び出し側を落とさないことを優先する（**決して投げない**）。
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:  # pragma: no cover - 防御的
            return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        logger.warning("foreshadowing.keywords is not valid JSON; ignoring: %r", raw)
        return None
    if not isinstance(parsed, list):
        logger.warning("foreshadowing.keywords is not a JSON list; ignoring: %r", raw)
        return None
    return parsed


class ForeshadowingModel(Base):
    """伏線ステートマシンモデル。

    Attributes:
        id: 伏線の一意識別子
        book_id: 所属作品ID（booksテーブル外部キー）
        title: 伏線タイトル（例: 「謎の剣」「消えた手紙」）
        description: 伏線の内容説明
        planted_episode: 伏線を設置した話数
        target_episode: 回収目標話数（NULL許容：作者に委ねる場合）
        resolved_episode: 実際に回収された話数（NULL = 未回収）
        scope: 伏線のスコープ (short_term / long_term)
        status: 伏線の現在ステータス (planted / progressed / resolved / abandoned)
        keywords: 手がかり語リスト（JSON 文字列 / NULL = 未設定）
        created_at: レコード作成日時
        updated_at: レコード更新日時
    """

    __tablename__ = "foreshadowings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    planted_episode = Column(Integer, nullable=False)
    target_episode = Column(Integer, nullable=True)
    resolved_episode = Column(Integer, nullable=True)
    scope = Column(String(32), nullable=False, server_default='short_term')
    status = Column(String(20), default="planted", nullable=False, index=True)
    keywords = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # ── keywords ヘルパ（往復の検証点） ───────────────

    @property
    def keyword_list(self) -> list:
        """`keywords` 列をリストとして読む（未設定なら空リスト）"""
        return decode_keywords(self.keywords) or []

    def set_keywords(self, keywords: Optional[Iterable[Any]]) -> None:
        """`keywords` 列へリストを書き込む（JSON 文字列に変換）"""
        self.keywords = encode_keywords(keywords)

    def __repr__(self) -> str:
        return (
            f"<Foreshadowing(id={self.id}, title='{self.title}', "
            f"status='{self.status}', planted_ep={self.planted_episode})>"
        )
