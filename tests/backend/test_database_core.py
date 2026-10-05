import pytest
from unittest.mock import ANY, Mock, AsyncMock, patch
import asyncio
from pathlib import Path

from src.backend.database.core import (
    retry_with_logging,
    WorkspaceManager,
    DatabaseManager,
    init_db,
    get_db_manager,
    set_db_manager,
    SessionLocal,
    engine
)


class TestRetryWithLogging:
    """retry_with_logging デコレータのテスト"""

    @pytest.mark.asyncio
    async def test_retry_with_logging_success_on_first_try(self):
        """最初の試行で成功する場合のテスト"""
        call_count = 0

        @retry_with_logging(retries=3, base_delay=0.01)
        async def func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_with_logging_success_after_retries(self):
        """リトライ後に成功する場合のテスト"""
        call_count = 0

        @retry_with_logging(retries=3, base_delay=0.01)
        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise asyncio.TimeoutError("temporary error")
            return "success"

        result = await func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_logging_final_failure(self):
        """最終的に失敗する場合のテスト"""
        call_count = 0

        @retry_with_logging(retries=2, base_delay=0.01)
        async def func():
            nonlocal call_count
            call_count += 1
            raise asyncio.TimeoutError("persistent error")

        with pytest.raises(asyncio.TimeoutError, match="persistent error"):
            await func()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_with_logging_non_retryable_exception(self):
        """リトライ対象外の例外のテスト"""
        call_count = 0

        @retry_with_logging(retries=3, base_delay=0.01)
        async def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("non-retryable error")

        with pytest.raises(ValueError, match="non-retryable error"):
            await func()

        assert call_count == 1


class TestWorkspaceManager:
    """WorkspaceManager クラスのテスト"""

    def test_get_path_returns_correct_path(self):
        """get_path が正しいパスを返すことを確認（OS 非依存）"""
        with patch('src.backend.database.core.BASE_DIR', Path('/tmp/test')):
            result = WorkspaceManager.get_path("test.txt")
            expected = Path('/tmp/test') / "test.txt"
            assert result == str(expected)

    def test_list_backups_returns_sorted_list(self):
        """list_backups がソートされたリストを返すことを確認"""
        with patch('src.backend.database.core.BASE_DIR') as mock_base_dir:
            # Mock Path.glob to return specific backup files
            mock_path1 = Mock()
            mock_path1.stat().st_mtime = 1000
            mock_path2 = Mock()
            mock_path2.stat().st_mtime = 2000
            mock_path3 = Mock()
            mock_path3.stat().st_mtime = 1500

            mock_base_dir.glob.return_value = [mock_path1, mock_path2, mock_path3]

            result = WorkspaceManager.list_backups()
            assert len(result) == 3
            # Should be sorted by mtime descending (newest first)
            assert result[0] == mock_path2  # mtime=2000
            assert result[1] == mock_path3  # mtime=1500
            assert result[2] == mock_path1  # mtime=1000

    def test_create_snapshot_creates_backup(self):
            """create_snapshot がバックアップを作成することを確認

            2026-10-04: 旧テストは `patch('pathlib.Path')` を使っていたが、
            `core.py` は `from pathlib import Path` で**名前を束縛**している
            ため、この patch は効いていなかった（実体の Path が使われ、
            POSIX リテラルの比較が Windows で失敗していた）。
            patch 先は束縛名（`src.backend.database.core.Path`）でなければならない。
            """
            with patch('src.backend.database.core.BASE_DIR', Path('/tmp')):
                with patch('src.backend.database.core.Path.exists', return_value=True):
                    with patch('src.backend.database.core.shutil.copy2') as mock_copy:
                        with patch('src.backend.database.core.logger') as mock_logger:
                            with patch('time.time', return_value=1234567890):
                                result = WorkspaceManager.create_snapshot(str(Path('/tmp/test.db')))

                                # 実 Path で計算された結果を比較する（プラットフォーム非依存）
                                expected = str(
                                    Path('/tmp/test.db').with_suffix('.bak_1234567890.db')
                                )
                                assert result == expected, (result, expected)
                                mock_copy.assert_called_once()
                                mock_logger.info.assert_called_once_with(
                                    f"Snapshot created: {Path(expected).name}"
                                )

    def test_create_snapshot_returns_empty_if_source_not_exists(self):
        """Test that create_snapshot returns empty string when source does not exist"""
        with patch('pathlib.Path.exists', return_value=False):
            result = WorkspaceManager.create_snapshot("/nonexistent.db")
            assert result == ""


class TestDatabaseManager:
    """DatabaseManager クラスのテスト"""

    def test_init_sets_attributes_correctly(self):
        """初期化時に属性が正しく設定されることを確認"""
        db_manager = DatabaseManager("sqlite:///test.db", pool_size=5)

        assert db_manager.db_path == "sqlite:///test.db"
        assert db_manager._pool_size == 5
        assert hasattr(db_manager, 'engine')
        assert hasattr(db_manager, 'session_factory')

    def test_init_does_not_carry_warning_flag(self):
        """`_warned_about_str_sql` が残っていないことを確認。

        2026-10-04: 当初は「警告を 1 回だけ出す」フラグとして存在したが、
        現在の実装は警告ではなく **hard reject**（`TypeError`）に変更され、
        フラグ自体は削除された。テストが private 属性に依存していたため陳腐化していた。
        「存在しない」ことを確認する形に変更する。
        """
        db_manager = DatabaseManager("sqlite:///test.db")
        assert not hasattr(db_manager, "_warned_about_str_sql")

    def test_get_session_returns_async_session(self):
        """get_session メソッドが AsyncSession を返すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")
        mock_session = Mock()

        with patch.object(db_manager, 'session_factory', return_value=mock_session):
            result = db_manager.get_session()
            assert result == mock_session

    @pytest.mark.asyncio
    async def test_get_conn_creates_connection_wrapper(self):
        """get_conn が互換ラッパーを返すことを確認。

        2026-10-04: 削除された `DatabaseConnectionWrapper`（`pass` だけのシム、
        `src/` 内に呼び出し元ゼロ）の代わりに、`get_conn()` が実際に返すのは
        内部の `_CompatWrapper` である。（旧テストはシムの型を前提にしていたため
        11 件が `takes no arguments` で落ちていた）
        """
        db_manager = DatabaseManager("sqlite:///test.db")

        mock_sql_conn = Mock()
        mock_raw_conn = Mock()
        mock_dbapi_conn = Mock()

        mock_sql_conn.get_raw_connection = AsyncMock(return_value=mock_raw_conn)
        mock_raw_conn._connection = mock_dbapi_conn

        with patch.object(db_manager, 'engine') as mock_engine:
            mock_engine.connect = AsyncMock(return_value=mock_sql_conn)

            result = await db_manager.get_conn()

            # `_CompatWrapper` は get_conn の局所クラスなので、
            # 「ラッパーの公開面」を確認する（名前で束縛しない）
            assert result is not None
            assert result.sql_conn is mock_sql_conn
            assert result.dbapi_conn is mock_dbapi_conn
            # ラッパーの最小の委譲面が生きていること
            result.cursor()
            mock_dbapi_conn.cursor.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_read_conn_returns_same_as_get_conn(self):
        """get_read_conn メソッドが get_conn と同じ結果を返すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")

        with patch.object(db_manager, 'get_conn') as mock_get_conn:
            mock_result = Mock()
            mock_get_conn.return_value = mock_result

            result = await db_manager.get_read_conn()

            assert result == mock_result
            mock_get_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_read_conn_calls_close_on_connection(self):
        """release_read_conn メソッドが接続の close を呼び出すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")
        mock_conn = Mock()
        mock_conn.close = AsyncMock()

        await db_manager.release_read_conn(mock_conn)

        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_enque_write_calls_execute(self):
        """enqueue_write メソッドが execute メソッドを呼び出すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")
        mock_execute = AsyncMock()

        with patch.object(db_manager, 'execute', mock_execute):
            await db_manager.enqueue_write("SELECT * FROM test", (1, 2))

            mock_execute.assert_called_once_with("SELECT * FROM test", (1, 2))

    @pytest.mark.asyncio
    async def test_flush_writes_does_nothing(self):
        """flush_writes メソッドが何もしないことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")
        # 例外が発生しないことを確認
        await db_manager.flush_writes()

    @pytest.mark.asyncio
    async def test_execute_rejects_raw_string(self):
        """execute が生の文字列 SQL を拒否することを確認。

        2026-10-04: 当初は「警告を出し text() に変換する」仕様だったが、
        現在の実装は **hard reject**（TypeError）に変更されている。
        「呼び出し規約の強制」としての意図であり、変換ではない。
        このため拒否されることの固定が正しい（かつ旧テストが Conversion を
        前提にしていたため陳腐化していた）。
        """
        db_manager = DatabaseManager("sqlite:///test.db")

        with pytest.raises(TypeError) as exc:
            await db_manager.execute("SELECT * FROM test WHERE id = :id", {"id": 1})
        assert "no longer accepts raw strings" in str(exc.value)

    @pytest.mark.asyncio
    async def test_execute_accepts_text_clause(self):
        """text() を渡した場合は通ること（拒否が正常系を壊していないことの確認）。"""
        from sqlalchemy import text

        db_manager = DatabaseManager("sqlite:///test.db")

        mock_conn = Mock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()

        with patch.object(db_manager, 'engine') as mock_engine:
            mock_engine.begin = Mock(return_value=mock_conn)

            await db_manager.execute(text("SELECT * FROM test WHERE id = :id"), {"id": 1})
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_one_returns_mapped_result(self):
        """fetch_one メソッドがマッピングされた結果を返すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")

        mock_result = Mock()
        mock_mappings = Mock()
        mock_mappings.fetchone.return_value = {"col1": "val1", "col2": "val2"}
        mock_result.mappings.return_value = mock_mappings

        mock_conn = Mock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch.object(db_manager, 'engine') as mock_engine:
            mock_engine.connect = Mock(return_value=mock_conn)

            from sqlalchemy import text
            result = await db_manager.fetch_one(text("SELECT * FROM test"), {"1": 1})

            assert result == {"col1": "val1", "col2": "val2"}
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_all_returns_list_of_mapped_results(self):
        """fetch_all メソッドがマッピングされた結果のリストを返すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")

        mock_result1 = {"col1": "val1", "col2": "val2"}
        mock_result2 = {"col1": "val3", "col2": "val4"}
        mock_mappings = Mock()
        mock_mappings.fetchall.return_value = [mock_result1, mock_result2]

        mock_result = Mock()
        mock_result.mappings.return_value = mock_mappings

        mock_conn = Mock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch.object(db_manager, 'engine') as mock_engine:
            mock_engine.connect = Mock(return_value=mock_conn)

            from sqlalchemy import text
            result = await db_manager.fetch_all(text("SELECT * FROM test"), {"1": 1})

            assert result == [mock_result1, mock_result2]
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_lastrowid_returns_lastrowid(self):
        """fetch_lastrowid メソッドが lastrowid を返すことを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")

        mock_result = Mock()
        mock_result.lastrowid = 42

        mock_conn = Mock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        # 実装は exec_driver_sql ではなく conn.execute() を使う（バインド済みパラメータ）
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch.object(db_manager, 'engine') as mock_engine:
            mock_engine.begin = Mock(return_value=mock_conn)

            from sqlalchemy import text
            result = await db_manager.fetch_lastrowid(text("INSERT INTO test VALUES (1)"))

            assert result == 42
            mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_internal_state_upserts_record(self):
        """save_internal_state メソッドが UPSERT を正しく実行することを確認"""
        db_manager = DatabaseManager("sqlite:///test.db")

        mock_session = Mock()
        # `async with self.get_session()` / `async with session.begin()` なので
        # モックは非同期 CM プロトコルに対応する
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_begin = Mock()
        mock_begin.__aenter__ = AsyncMock(return_value=mock_begin)
        mock_begin.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin = Mock(return_value=mock_begin)

        mock_stmt = Mock()
        mock_result = Mock()
        mock_scalar_result = Mock()

        # `save_internal_state` は `from sqlalchemy import select` を**関数内**で
        # 行うため、モジュール属性 `src.backend.database.core.select` は存在せず、
        # 旧テストの patch は AttributeError になっていた。patch 先は
        # 実際の import 元（`sqlalchemy`）でなければならない。
        with patch('sqlalchemy.select', return_value=mock_stmt):
            with patch.object(db_manager, 'get_session', return_value=mock_session):
                # `await session.execute(...)` なので AsyncMock。
                # 実装は `result.scalar_one_or_none()` を使う。
                with patch.object(mock_session, 'execute', new_callable=AsyncMock) as mock_execute:
                    mock_execute.return_value = mock_result
                    with patch.object(
                        mock_result, 'scalar_one_or_none', return_value=mock_scalar_result
                    ):

                        # Test UPDATE case (record exists)
                        mock_scalar_result.value = "old_value"
                        await db_manager.save_internal_state("test_key", "new_value")

                        assert mock_scalar_result.value == "new_value"

                        # Test INSERT case (record doesn't exist)
                        mock_scalar_result = None
                        mock_result.scalar_one_or_none.return_value = None
                        mock_new_state = Mock()

                        with patch('src.backend.database.models.InternalState', return_value=mock_new_state):
                            await db_manager.save_internal_state("test_key", "new_value")

                            mock_session.add.assert_called_once_with(mock_new_state)

    def test_init_db_uses_alembic_as_schema_source_of_truth(self):
        """init_db は Alembic migration を適用する（create_all では作らない）"""
        with patch('os.environ.get', return_value=""):
            with patch('src.backend.database.core.DATABASE_URL', "sqlite:///test.db"):
                with patch('src.backend.database.core._run_alembic_upgrade') as mock_alembic:
                    with patch('src.backend.database.core.create_engine') as mock_create_engine:
                        with patch('src.infrastructure.database.models.Base') as mock_infra_base:
                            with patch('src.backend.database.models.Base') as mock_backend_base:
                                init_db()

                                # 正常系は Alembic upgrade のみ。
                                # create_all によるスキーマ生成は行わない。
                                mock_alembic.assert_called_once()
                                mock_infra_base.metadata.create_all.assert_not_called()
                                mock_backend_base.metadata.create_all.assert_not_called()

    def test_init_db_falls_back_to_create_all_only_outside_production(self):
        """Alembic が失敗しても、非本番では create_all へフォールバックする。"""
        from src.backend.config import settings

        with patch('os.environ.get', return_value=""):
            with patch('src.backend.database.core.DATABASE_URL', "sqlite:///test.db"):
                with patch.object(settings, "APP_ENV", "development"):
                    with patch('src.backend.database.core._run_alembic_upgrade', side_effect=RuntimeError("boom")):
                        with patch('src.backend.database.core.create_engine') as mock_create_engine:
                            with patch('src.infrastructure.database.models.Base') as mock_infra_base:
                                mock_engine = Mock()
                                mock_create_engine.return_value = mock_engine

                                init_db()

                                mock_infra_base.metadata.create_all.assert_called_once_with(mock_engine)

    def test_init_db_refuses_create_all_fallback_in_production(self):
        """本番では Alembic 失敗時に create_all へ落とさず、起動を失敗させる。"""
        from src.backend.config import settings

        with patch('os.environ.get', return_value=""):
            with patch('src.backend.database.core.DATABASE_URL', "postgresql+psycopg2://u:p@db/x"):
                with patch.object(settings, "APP_ENV", "production"):
                    with patch('src.backend.database.core._run_alembic_upgrade', side_effect=RuntimeError("boom")):
                        with patch('src.backend.database.core.create_engine') as mock_create_engine:
                            with patch('src.infrastructure.database.models.Base') as mock_infra_base:
                                with pytest.raises(RuntimeError, match="Alembic"):
                                    init_db()

                                mock_infra_base.metadata.create_all.assert_not_called()

    def test_get_db_manager_returns_database_manager_instance(self):
        """get_db_manager 関数が DatabaseManager のインスタンスを返すことを確認"""
        with patch('src.backend.database.core.DATABASE_URL', "sqlite:///test.db"):
            result = get_db_manager()

            assert isinstance(result, DatabaseManager)
            assert result.db_path == "sqlite:///test.db"

    def test_set_db_manager_issues_warning_and_tries_override(self):
        """set_db_manager が非推奨警告を出し、AppContainer の override を試みることを確認"""
        mock_manager = Mock()

        with patch('src.backend.database.core.logger') as mock_logger:
            with patch('src.core.container.AppContainer') as mock_app_container:
                mock_app_container.db.override = Mock()

                set_db_manager(mock_manager)

                mock_logger.warning.assert_any_call(
                    "set_db_manager is deprecated. Use DI container instead."
                )
                # 正常系では "override に失敗" は出ない
                # （その警告は override が例外を投げた場合のみ）
                mock_app_container.db.override.assert_called_once_with(mock_manager)

    def test_set_db_manager_warns_when_override_fails(self):
        """override が例外を投げた場合に警告を出すことを確認。

        旧テストは正常系で「override に失敗」の警告を期待していたが、
        実装上その警告は `override()` が例外を投げた場合のみ出る。
        正常系と異常系を分離して固定する。
        """
        mock_manager = Mock()

        with patch('src.backend.database.core.logger') as mock_logger:
            with patch('src.core.container.AppContainer') as mock_app_container:
                mock_app_container.db.override = Mock(side_effect=RuntimeError("boom"))

                set_db_manager(mock_manager)

                mock_logger.warning.assert_any_call(
                    "AppContainer.db.override に失敗: %s", ANY, exc_info=True
                )


class TestProxies:
    """Proxy クラスのテスト"""

    def test_sessionlocal_proxy_calls_factory(self):
        """SessionLocal プロキシがファクトリを呼び出すことを確認"""
        mock_factory = Mock()
        mock_factory.return_value = "session_instance"

        with patch('src.backend.database.core._get_sync_engine_and_factory') as mock_getter:
            mock_getter.return_value = (None, mock_factory)

            result = SessionLocal()

            assert result == "session_instance"
            mock_factory.assert_called_once()

    def test_engine_proxy_delegates_to_engine(self):
        """engine プロキシが実際の engine に委譲することを確認"""
        mock_engine = Mock()
        mock_engine.some_attribute = "test_value"

        with patch('src.backend.database.core._get_sync_engine_and_factory') as mock_getter:
            mock_getter.return_value = (mock_engine, None)

            result = engine.some_attribute

            assert result == "test_value"


if __name__ == "__main__":
    pytest.main([__file__])
