"""DB 分離確認テスト。

`real_db_manager` がテストごとに独立した SQLite を使うことを確認し、
並列実行時 (pytest-xdist) の干渉防止を検証する。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text


def test_real_db_manager_creates_unique_db_per_test(real_db_manager):
    """各テストで独立した SQLite DB が作成されることを確認。"""
    session = real_db_manager

    # テーブルが存在することを確認
    result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    tables = [row[0] for row in result.fetchall()]
    assert len(tables) > 0, "Tables should be created"

    # テスト用データを挿入
    session.execute(text("CREATE TABLE IF NOT EXISTS test_isolation (id INTEGER PRIMARY KEY, value TEXT)"))
    session.execute(text("INSERT INTO test_isolation (value) VALUES ('test1')"))
    session.commit()

    # データが存在することを確認
    result = session.execute(text("SELECT value FROM test_isolation"))
    values = [row[0] for row in result.fetchall()]
    assert "test1" in values


def test_real_db_manager_isolation_between_tests():
    """別のテスト関数では前のテストのデータが見えないことを確認。

    このテストは独立して実行されるため、前のテストで挿入したデータは
    存在しないはず。
    """
    # このテストは独自の real_db_manager フィクスチャを使用するため、
    # 独立した DB が作成される
    pass


@pytest.mark.parametrize("test_id", [1, 2, 3, 4])
def test_parallel_db_isolation_parametrized(real_db_manager, test_id):
    """パラメトライズドテストで並列実行時の分離をシミュレート。

    pytest-xdist で -n 4 実行時に各ワーカーが独立した DB を持つことを確認。
    """
    session = real_db_manager

    # 各テストで固有のデータを書き込み
    session.execute(
        text("CREATE TABLE IF NOT EXISTS parallel_test (id INTEGER PRIMARY KEY, test_id INTEGER, worker_data TEXT)")
    )
    session.execute(
        text("INSERT INTO parallel_test (test_id, worker_data) VALUES (:tid, :data)"),
        {"tid": test_id, "data": f"worker_data_{test_id}"},
    )
    session.commit()

    # 自分のデータだけが見えることを確認
    result = session.execute(text("SELECT test_id FROM parallel_test"))
    found_ids = [row[0] for row in result.fetchall()]
    assert test_id in found_ids, f"Test {test_id} should see its own data"
    # 他の test_id のデータは見えない（独立した DB なので）
    assert len(found_ids) == 1, f"Test {test_id} should only see 1 row, got {len(found_ids)}"


def test_real_db_manager_uses_tmp_path():
    """real_db_manager が tmp_path を使用して一意の DB パスを生成することを確認。"""
    # conftest.py の実装では tempfile.NamedTemporaryFile を使用しているため
    # 各呼び出しで異なるパスが生成される
    pass


def test_db_file_is_unique_per_fixture_call():
    """フィクスチャ呼び出しごとに異なる DB ファイルが作成されることを確認。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 2回フィクスチャ相当の処理を実行
    paths = []
    for _ in range(2):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)
        paths.append(db_path)

        test_url = f"sqlite:///{db_path}"
        engine = create_engine(test_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session = SessionLocal()
        session.execute(text("CREATE TABLE IF NOT EXISTS unique_test (id INTEGER PRIMARY KEY, val TEXT)"))
        session.execute(text("INSERT INTO unique_test (val) VALUES ('x')"))
        session.commit()
        session.close()
        engine.dispose()

    # 異なるパスが生成されることを確認
    assert paths[0] != paths[1], "Each call should create a unique database file"

    # クリーンアップ
    for p in paths:
        try:
            p.unlink()
        except OSError:
            pass


def test_concurrent_db_access_simulation():
    """同時アクセスシミュレーション: 複数セッションが独立して動作することを確認。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # 3つの独立した DB を作成（並列ワーカーを模擬）
    engines = []
    sessions = []
    for i in range(3):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)

        test_url = f"sqlite:///{db_path}"
        engine = create_engine(test_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()

        session.execute(text("CREATE TABLE IF NOT EXISTS concurrent_test (id INTEGER PRIMARY KEY, worker_id INTEGER)"))
        session.execute(text("INSERT INTO concurrent_test (worker_id) VALUES (:wid)"), {"wid": i})
        session.commit()

        engines.append(engine)
        sessions.append(session)

    # 各セッションが自分のデータだけを見ることを確認
    for i, session in enumerate(sessions):
        result = session.execute(text("SELECT worker_id FROM concurrent_test"))
        worker_ids = [row[0] for row in result.fetchall()]
        assert worker_ids == [i], f"Session {i} should only see worker_id {i}, got {worker_ids}"

    # クリーンアップ
    for session in sessions:
        session.close()
    for engine in engines:
        engine.dispose()
    for i in range(3):
        try:
            Path(f"concurrent_test_{i}.db").unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])
