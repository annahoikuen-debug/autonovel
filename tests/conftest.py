"""pytest 共有フィクスチャ。テスト実行時の sys.path 設定と一時 DB を提供する。"""
from __future__ import annotations

import functools
import os
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# NOTE: 以前はここで `src.agent.*` → `src.agents.*` のエイリアスを
# sys.modules.setdefault で登録し、`except Exception: pass` で失敗を握り潰していた。
# その shim は削除済み: 全テストを `src.agents.*` へ統一し、エイリアスに依存しない形に
# した。`src/agent` は Part 5 (Step 16-18) で削除済みであり、存在しないモジュールを
# sys.modules で黙って置換する shim は、根本原因を隠して「No module named 'src.agent'」
# という無関係な collection error しか生まさないため使用しない。
# tests/regression/test_v5_repo_cleanliness.py が `src.agent` の再導入を禁止している。

from tests.mocks.llm_adapter import LLMMocker, MockLLMAdapter


def pytest_configure(config):
    """テスト収集前に環境変数を設定し、早期のDB初期化を防ぐ。"""
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("AUTONOVEL_RAG_MODE", "memory")
    os.environ.setdefault("RAG_FALLBACK_MODE", "memory")
    os.environ.setdefault("AUTH_DISABLED", "true")
    # 開発者のローカル .env に HUEY_BACKEND=memory が残っていても、
    # Settings.HUEY_BACKEND は Literal["sqlite","redis"] しか許可しないため
    # テスト収集時に ValidationError で全滅する。pydantic-settings は
    # 環境変数を .env より優先するので、ここで固定する。
    os.environ["HUEY_BACKEND"] = "sqlite"

    def dummy_init_db(*args, **kwargs):
        pass

    try:
        import src.backend.server

        src.backend.server.init_db = dummy_init_db
    except Exception:
        pass


import pytest

# NOTE: SQLAlchemy と `Base` はモジュール直下では import しない。
# これらを直下に置くと、pytest 本体だけが入った環境
# （CI の `release-consistency` ジョブなど）で `tests/` 配下のどのテストを
# 実行しても `tests/conftest.py` の import が失敗して collection error になる。
# 実際の生成物を扱うフィクスチャの中で遅延 import する。
if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.infrastructure.database.models.base_orm import Base


# 各種外部サービス利用可能性フラグ（軽量チェック）
CHROMADB_AVAILABLE = False
try:
    import importlib.util

    CHROMADB_AVAILABLE = importlib.util.find_spec("chromadb") is not None
except Exception:
    CHROMADB_AVAILABLE = False

RANK_BM25_AVAILABLE = False
try:
    import importlib.util

    RANK_BM25_AVAILABLE = importlib.util.find_spec("rank_bm25") is not None
except Exception:
    RANK_BM25_AVAILABLE = False

PGVECTOR_AVAILABLE = False
try:
    import importlib.util

    if importlib.util.find_spec("pgvector") is not None:
        PGVECTOR_AVAILABLE = True
    if os.environ.get("AUTONOVEL_FORCE_PGVECTOR", "1") != "1":
        PGVECTOR_AVAILABLE = False
except Exception:
    PGVECTOR_AVAILABLE = False


@functools.lru_cache(maxsize=1)
def check_redis_available() -> bool:
    """Redis の疎通確認を遅延評価で実行する（トップレベルブロック防止）。"""
    try:
        import redis

        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=0.5)
        return bool(client.ping())
    except Exception:
        return False


REDIS_AVAILABLE = False
if os.environ.get("TEST_WITH_REDIS", "0") == "1":
    REDIS_AVAILABLE = check_redis_available()

GEMINI_AVAILABLE = False
try:
    import importlib.util

    GEMINI_AVAILABLE = importlib.util.find_spec("google.generativeai") is not None
except Exception:
    GEMINI_AVAILABLE = False


@pytest.fixture
def real_db_manager(monkeypatch) -> Generator[Session, None, None]:
    """実際の SQLite 一時データベース管理器を提供する。

    統合テスト・ワークフローテストに使用される。
    ``DATABASE_URL`` を一時ファイル経由で差し替え、スキーマ生成後に
    有効な ``Session`` を ``yield`` する。終了時にファイルを削除する。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.backend.database as db_module
    import src.backend.database.core as db_core
    from src.backend.database import SessionLocal, engine

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    test_url = f"sqlite:///{db_path}"
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_url

    # core.py のグローバル変数も更新
    db_core.DATABASE_URL = test_url
    db_core._sync_engine = None
    db_core._sync_session_factory = None

    # 同一プロセス内で module の engine/SessionLocal を差し替える
    test_engine = create_engine(test_url, connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal  # type: ignore[assignment]

    # モデル定義から全テーブル作成（単一 Base による初期スキーマ反映）
    import src.backend.database.models  # noqa
    import src.backend.database.models_tenant  # noqa
    import src.infrastructure.database.models  # noqa
    from src.infrastructure.database.models.base_orm import Base

    Base.metadata.create_all(test_engine)

    # init_db をモンキーパッチして二重初期化を防ぐ
    def dummy_init_db(*args, **kwargs):
        pass

    monkeypatch.setattr(db_module, "init_db", dummy_init_db)
    monkeypatch.setattr(db_core, "init_db", dummy_init_db)

    session = TestSessionLocal()
    try:
        yield session
    finally:
        import gc

        try:
            session.rollback()
        except Exception:
            pass
        session.close()

        test_engine.dispose()
        gc.collect()

        # 元の状態に戻す
        db_module.engine = engine
        db_module.SessionLocal = SessionLocal  # type: ignore[assignment]
        db_core.DATABASE_URL = previous_url or (
            db_core.settings.DATABASE_URL
            if hasattr(db_core, "settings")
            else "sqlite:///storage/autonovel.db"
        )
        db_core._sync_engine = None
        db_core._sync_session_factory = None
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        try:
            if db_path.exists():
                db_path.unlink()
        except OSError:
            pass


@pytest.fixture
def db_session(real_db_manager: Generator[Session, None, None]) -> Generator[Session, None, None]:
    """テスト用 DB セッションフィクスチャ (real_db_manager のエイリアス)."""
    return real_db_manager


@pytest.fixture
def sqlite_db_url(tmp_path) -> str:
    """SQLite テスト用の一時データベース URL を返す。"""
    db_path = tmp_path / "test_migrations.db"
    return f"sqlite:///{db_path}"


@pytest.fixture
def postgres_db_url() -> str | None:
    """PostgreSQL テスト用のデータベース URL を返す（環境変数未設定なら None）。"""
    return os.environ.get("POSTGRES_TEST_URL")


@pytest.fixture
def tmp_chroma_path(tmp_path):
    """Chromadb 用の一時ディレクトリパスを返す."""
    p = tmp_path / "chroma"
    p.mkdir()
    return str(p)


@pytest.fixture(autouse=True)
def reset_metrics():
    """各テスト後に health.py のプロセスメトリクスをゼロリセットする。

    pytest-xdist 並列実行時にメトリクスがリークするのを防止する。
    """
    from src.backend.observability.health import metrics

    yield
    metrics.reset_for_testing()


@pytest.fixture
def client(db_session: Session):
    """FastAPI TestClient フィクスチャ."""
    from fastapi.testclient import TestClient

    from src.backend import database
    from src.backend.server import app

    app.dependency_overrides[database.get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def llm_mocker() -> LLMMocker:
    """LLM モックの振る舞いを設定するための LLMMocker フィクスチャ。"""
    return LLMMocker()


@pytest.fixture(autouse=True)
def mock_llm_adapter(llm_mocker: LLMMocker, monkeypatch) -> MockLLMAdapter:
    """get_llm_adapter を自動的にモックアダプターにパッチするフィクスチャ。"""
    mock_adapter = MockLLMAdapter(llm_mocker)

    def mock_get_llm_adapter(*args, **kwargs):
        return mock_adapter

    monkeypatch.setattr("src.services.llm.factory.get_llm_adapter", mock_get_llm_adapter)
    return mock_adapter


# ============================================================================
# 環境依存テストの collection error 回避 (Step 36)
# ============================================================================
# ortools 等のオプショナル依存が未インストールの環境では、該当テストファイルを
# collection error ではなく「収集しない」扱いにして、全体スイートが
# failed=0, errors=0 を維持できるようにする。
REDIS_AVAILABLE = False
GEMINI_AVAILABLE = False


def _optional_module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


_ORTOOLS_AVAILABLE = _optional_module_available("ortools")

# ortools が無い環境で収集を見送るテストは、**実際に ortools を import するものだけ**。
# 以前はパス名に "dsp" / "detector" / "balancer" などのキーワードが含まれるだけで
# まとめて収集を飛ばしていたが、サブ文字列一致のため
# `tests/unit/anti_ai/test_*_detector.py` や `tests/unit/fusion/test_conflict_detector.py`
# （これらは AI 検知のテストで narrative_balancer とは無関係）を含め
# 35 ファイルが無言で未収集になっていた。エラーも出ないため、
# 中身のテストが壊れていても CI は緑のままだった。
_ORTOOLS_REQUIRED_TESTS = frozenset(
    {
        "tests/unit/narrative_balancer/test_earley_incremental.py",
        "tests/unit/test_csp_models.py",
        "tests/unit/test_csp_config.py",
    }
)


def _rel_path(collection_path) -> str:
    """リポジトリルートからの相対パスを POSIX 区切りで返す。"""
    try:
        return Path(str(collection_path)).resolve().relative_to(Path(ROOT)).as_posix()
    except (ValueError, OSError):
        return Path(str(collection_path)).as_posix()


def pytest_ignore_collect(collection_path, config):  # noqa: ANN001, ARG001
    """環境依存および非推奨テストの収集回避。"""
    lowered = str(collection_path).lower()

    # 非推奨スタブ化された age_client のレガシーテスト
    if "age_client" in lowered:
        return True

    # ortools 依存テストの収集回避（実際に ortools を import するものだけ）
    if not _ORTOOLS_AVAILABLE and _rel_path(collection_path) in _ORTOOLS_REQUIRED_TESTS:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    """非推奨または環境未対応のテストをスキップ。"""
    for item in items:
        lowered = str(item.fspath).lower()
        if "age_client" in lowered:
            item.add_marker(
                pytest.mark.skip(
                    reason="Legacy age_client tests are deprecated (replaced by Relational Memory)"
                )
            )
        if not _ORTOOLS_AVAILABLE and _rel_path(item.fspath) in _ORTOOLS_REQUIRED_TESTS:
            item.add_marker(pytest.mark.skip(reason="ortools is not installed in environment"))
