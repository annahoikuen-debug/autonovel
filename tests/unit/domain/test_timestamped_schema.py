"""ドメインスキーマの `created_at` / `updated_at` の回帰テスト。

このテストが固定する問題
----------------------
``TimestampedSchema`` はかつて

.. code-block:: python

    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()

と書かれていた。右辺は **モジュール import 時に 1 回だけ評価** されるため、
以降ずっと同一のインスタンスの全レコードが「プロセス起動時刻」を持つ結果になっていた。

* 複数レコードの `created_at` がすべて同じ → 順序や更新差分が一切取れない
* テストの再現性が崩れる（時計を巻き戻せない）
* デフォルト値が実質定数になるため「未指定」であることが追跡できない

``Field(default_factory=datetime.utcnow)`` に修正済み。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.domain.schemas.base import TimestampedSchema


def test_created_at_is_evaluated_per_instance():
    """2 つのインスタンスの ``created_at`` は互いに異なる。"""
    first = TimestampedSchema()
    time.sleep(0.01)
    second = TimestampedSchema()

    assert first.created_at != second.created_at, (
        "created_at が import 時に固定されている（default_factory になっていない）"
    )


def test_created_at_is_close_to_now():
    """デフォルト値は「そのインスタンスを生成した時刻」付近になる。"""
    before = time.time()
    schema = TimestampedSchema()
    after = time.time()

    # `datetime.utcnow()` は naive UTC。aware に直してから epoch 秒で比較する。
    # datetime はマイクロ秒単位に丸められるため `before` より僅かに古くなることも
    # ある。1 ミリ秒の余裕を許す。
    created = schema.created_at.replace(tzinfo=timezone.utc).timestamp()
    assert before - 0.001 <= created <= after + 0.001, (
        "created_at がインスタンス生成時刻から大きくずれている"
    )


def test_updated_at_also_defaults_per_instance():
    """``updated_at`` も同じ罠の影響を受けていない。"""
    first = TimestampedSchema()
    time.sleep(0.01)
    second = TimestampedSchema()

    assert first.updated_at != second.updated_at


def test_explicit_created_at_is_preserved():
    """明示値を渡した場合は default_factory に上書きされない。"""
    fixed = datetime(2020, 1, 2, 3, 4, 5)
    schema = TimestampedSchema(created_at=fixed)

    assert schema.created_at == fixed
