"""Coverage tests for src/backend/auth.py, checkpoint_saver.py and small engine helper modules."""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import src.backend.auth as auth_mod
from src.backend.auth import (
    require_admin_user,
    require_admin_user_or_key,
    require_api_key,
    require_valid_api_key,
    validate_api_key_or_raise,
    validate_api_key_sync,
)
from src.backend.checkpoint_saver import CheckpointManager, CheckpointSaver
from src.backend.database.models import User


def _user(role: str = "user", status: str = "active") -> User:
    return User(id=1, email="u@x.local", display_name="U", role=role, status=status)


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------

async def test_get_current_user_auth_disabled(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", True, raising=False)
    user = await auth_mod.get_current_user(token=None, db=AsyncMock())
    assert user.role == "admin"
    assert user.credits == 99999


async def test_get_current_user_requires_token(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    with pytest.raises(HTTPException) as ei:
        await auth_mod.get_current_user(token=None, db=AsyncMock())
    assert ei.value.status_code == 401
    assert ei.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_get_current_user_invalid_token(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    monkeypatch.setattr(auth_mod, "decode_token", lambda t, expected_type=None: None)
    with pytest.raises(HTTPException) as ei:
        await auth_mod.get_current_user(token="bad", db=AsyncMock())
    assert ei.value.detail == "無効なトークンです"


async def test_get_current_user_missing_sub(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    monkeypatch.setattr(auth_mod, "decode_token", lambda t, expected_type=None: {"foo": 1})
    with pytest.raises(HTTPException) as ei:
        await auth_mod.get_current_user(token="t", db=AsyncMock())
    assert ei.value.detail == "無効なトークンペイロードです"


@pytest.mark.parametrize("sub,expected", [("7", 7), (7, 7), (None, None)])
async def test_get_current_user_lookup(monkeypatch, sub, expected):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    monkeypatch.setattr(auth_mod, "decode_token", lambda t, expected_type=None: {"sub": sub} if sub else {})
    db = AsyncMock()
    db.get.return_value = _user() if sub is not None else None
    if sub is None:
        with pytest.raises(HTTPException) as ei:
            await auth_mod.get_current_user(token="t", db=db)
        assert ei.value.detail == "無効なトークンペイロードです"
        return
    user = await auth_mod.get_current_user(token="t", db=db)
    assert user.id == 1
    db.get.assert_awaited_once_with(User, expected)


async def test_get_current_user_inactive_user(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    monkeypatch.setattr(auth_mod, "decode_token", lambda t, expected_type=None: {"sub": "1"})
    db = AsyncMock()
    db.get.return_value = _user(status="disabled")
    with pytest.raises(HTTPException) as ei:
        await auth_mod.get_current_user(token="t", db=db)
    assert ei.value.status_code == 401

    db.get.return_value = None
    with pytest.raises(HTTPException):
        await auth_mod.get_current_user(token="t", db=db)


async def test_require_admin_user():
    assert (await require_admin_user(_user("admin"))).role == "admin"
    with pytest.raises(HTTPException) as ei:
        await require_admin_user(_user("user"))
    assert ei.value.status_code == 403


async def test_require_api_key_variants(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", True, raising=False)
    assert await require_api_key("Bearer x") == "dev-key"

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    monkeypatch.setattr(settings, "ALLOWED_API_KEYS", "k1, k2", raising=False)
    assert await require_api_key("Bearer  k1 ") == "k1"
    assert await require_api_key("k2") == "k2"

    monkeypatch.setattr(auth_mod, "validate_api_key_sync", lambda k: False)
    with pytest.raises(HTTPException) as ei:
        await require_api_key("nope")
    assert ei.value.detail == "Invalid or missing API Key"


async def test_require_admin_user_or_key(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", True, raising=False)
    dev = await require_admin_user_or_key(token=None, authorization="", db=AsyncMock())
    assert dev.role == "admin"

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)

    async def fake_current_user(token, db):
        return _user("admin")

    monkeypatch.setattr(auth_mod, "get_current_user", fake_current_user)
    admin = await require_admin_user_or_key(token="t", authorization="", db=AsyncMock())
    assert admin.role == "admin"

    async def fake_non_admin(token, db):
        return _user("user")

    monkeypatch.setattr(auth_mod, "get_current_user", fake_non_admin)
    with pytest.raises(HTTPException) as ei:
        await require_admin_user_or_key(token="t", authorization="", db=AsyncMock())
    assert ei.value.status_code == 403

    async def fake_key(authorization):
        return "api-key"

    monkeypatch.setattr(auth_mod, "require_api_key", fake_key)
    ro = await require_admin_user_or_key(token=None, authorization="key", db=AsyncMock())
    assert ro.role == "api_readonly"

    async def fake_key_empty(authorization):
        return ""

    monkeypatch.setattr(auth_mod, "require_api_key", fake_key_empty)
    with pytest.raises(HTTPException) as ei:
        await require_admin_user_or_key(token=None, authorization="", db=AsyncMock())
    assert ei.value.status_code == 401


def test_validate_api_key_sync(monkeypatch):
    from src.backend.config import settings

    monkeypatch.setattr(settings, "AUTH_DISABLED", True, raising=False)
    assert validate_api_key_sync("anything") == "dev-key"

    monkeypatch.setattr(settings, "AUTH_DISABLED", False, raising=False)
    assert validate_api_key_sync("") is False

    monkeypatch.setattr(settings, "ALLOWED_API_KEYS", "", raising=False)
    monkeypatch.delenv("ALLOWED_API_KEYS", raising=False)
    assert validate_api_key_sync("x") is False

    monkeypatch.setenv("ALLOWED_API_KEYS", " envkey , other ")
    assert validate_api_key_sync("envkey") == "envkey"
    assert validate_api_key_sync("bad") is False


def test_require_valid_api_key(monkeypatch):
    monkeypatch.setattr(auth_mod, "validate_api_key_sync", lambda k: False)
    assert require_valid_api_key("") == ""
    assert require_valid_api_key(None) is None
    with pytest.raises(HTTPException) as ei:
        require_valid_api_key("k")
    assert ei.value.status_code == 401

    monkeypatch.setattr(auth_mod, "validate_api_key_sync", lambda k: k)
    assert require_valid_api_key("k") == "k"


async def test_validate_api_key_or_raise(monkeypatch):
    monkeypatch.setattr(auth_mod, "require_api_key", lambda authorization: _ok(authorization))

    async def _ok(authorization):
        return authorization

    assert await validate_api_key_or_raise("hdr") == "hdr"


def test_get_prompt_manager_success_and_failure(monkeypatch):
    result = auth_mod.get_prompt_manager()
    assert result is None or result.__class__.__name__ == "PromptManager"

    import prompts.manager as pm_mod

    monkeypatch.setattr(pm_mod, "PromptManager", MagicMock(side_effect=RuntimeError("boom")))
    assert auth_mod.get_prompt_manager() is None


# --------------------------------------------------------------------------
# checkpoint_saver
# --------------------------------------------------------------------------

async def test_in_memory_saver_roundtrip(monkeypatch):
    monkeypatch.setattr("src.backend.checkpoint_saver.HAS_LANGGRAPH", False)
    monkeypatch.setattr("src.backend.checkpoint_saver.SqliteSaver", None)

    saver = CheckpointSaver(db_path=":memory:")
    assert saver.db_path == ":memory:"

    await saver.save_checkpoint({"id": "c1", "thread_id": "t1", "v": 1})
    assert (await saver.get_checkpoint("c1"))["v"] == 1
    assert (await saver.get_checkpoint("missing")) is None
    assert len(await saver.list_checkpoints("t1")) == 1
    assert await saver.list_checkpoints("other") == []
    await saver.delete_checkpoint("c1")
    assert await saver.get_checkpoint("c1") is None
    await saver.delete_checkpoint("c1")
    # saver instance is cached
    assert saver._get_saver() is saver._get_saver()


async def test_in_memory_saver_generates_id():
    from src.backend.checkpoint_saver import _InMemorySaver

    s = _InMemorySaver()
    cp = {"thread_id": "x"}
    await s.aput(cp)
    assert await s.aget(str(id(cp))) is cp
    assert s.from_conn_string("ignored") is s


async def test_checkpoint_saver_uses_sqlite_when_available(monkeypatch, tmp_path):
    import src.backend.checkpoint_saver as cs_mod

    created = {}

    class _FakeSqliteSaver:
        def __init__(self, path):
            created["path"] = path
            self.store = {}

        @classmethod
        def from_conn_string(cls, path):
            return cls(path)

        async def aput(self, checkpoint):
            self.store[checkpoint["id"]] = checkpoint

        async def aget(self, checkpoint_id):
            return self.store.get(checkpoint_id)

        async def alist(self, thread_id):
            return [c for c in self.store.values() if c.get("thread_id") == thread_id]

        async def adelete(self, checkpoint_id):
            self.store.pop(checkpoint_id, None)

    monkeypatch.setattr(cs_mod, "HAS_LANGGRAPH", True)
    monkeypatch.setattr(cs_mod, "SqliteSaver", _FakeSqliteSaver)

    saver = CheckpointSaver(db_path=str(tmp_path / "cp.db"))
    await saver.save_checkpoint({"id": "x1", "thread_id": "t"})
    assert created["path"].endswith("cp.db")
    assert (await saver.get_checkpoint("x1"))["id"] == "x1"
    assert len(await saver.list_checkpoints("t")) == 1
    await saver.delete_checkpoint("x1")
    assert await saver.get_checkpoint("x1") is None


def test_checkpoint_saver_default_path():
    saver = CheckpointSaver()
    assert saver.db_path.endswith("checkpoints.db")


class _FakeCheckpointRepo:
    saved = []

    def __init__(self, session):
        self.session = session

    def save(self, checkpoint):
        _FakeCheckpointRepo.saved.append(checkpoint)

    def get_latest_checkpoint(self, task_id):
        return getattr(self, "_cp", None)


def test_checkpoint_manager_record_and_load(monkeypatch):
    import src.backend.checkpoint_saver as cs_mod
    from src.domain.entities.checkpoint import CheckpointStatus

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cs_mod, "CheckpointRepository", _FakeCheckpointRepo)
    mgr = CheckpointManager(lambda: _Session())

    cp_id = mgr.record_step("task1", "plot", 1, {"a": 1}, status=CheckpointStatus.COMPLETED)
    assert cp_id == "task1_1_plot"
    assert _FakeCheckpointRepo.saved[-1].state_payload == {"a": 1}

    class _CompletedCheckpoint:
        status = CheckpointStatus.COMPLETED
        step_index = 1
        step_name = "plot"
        state_payload = {"a": 1}

    class _RepoWithCp(_FakeCheckpointRepo):
        def __init__(self, session):
            super().__init__(session)
            self._cp = _CompletedCheckpoint()

    monkeypatch.setattr(cs_mod, "CheckpointRepository", _RepoWithCp)
    assert mgr.load_last_state("task1") == (1, "plot", {"a": 1})

    class _RepoNoCp(_FakeCheckpointRepo):
        def __init__(self, session):
            super().__init__(session)
            self._cp = None

    monkeypatch.setattr(cs_mod, "CheckpointRepository", _RepoNoCp)
    assert mgr.load_last_state("task1") is None


# --------------------------------------------------------------------------
# small engine modules
# --------------------------------------------------------------------------

async def test_critique_service_delegates():
    from src.backend.critique_service import CritiqueService

    critique = MagicMock()
    critique.run_iterative_gap_analysis = AsyncMock(return_value="gaps")
    critique.audit_plot_as_issues = AsyncMock(return_value=["issue"])
    svc = CritiqueService(critique, MagicMock(), MagicMock())

    assert await svc.run_iterative_gap_analysis(3, "extra", flag=True) == "gaps"
    critique.run_iterative_gap_analysis.assert_awaited_once()
    assert await svc.audit_plot_as_issues("p") == ["issue"]


def test_engine_prompt_result_wrappers():
    from src.backend import engine_prompts

    assert engine_prompts.FastPlotScreenResult({"a": 1}).plot_data == {"a": 1}
    r = engine_prompts.AbilityAuditResult(["s"], ["w"])
    assert (r.strengths, r.weaknesses) == (["s"], ["w"])
    d = engine_prompts.DeAIAuditResult(["i"], ["r"])
    assert (d.issues, d.proposed_rules) == (["i"], ["r"])
    assert engine_prompts.DeAIProposedRules(["r"]).rules == ["r"]
    assert "Show, don't tell" in engine_prompts.get_rule_set("any")
    assert engine_prompts.PromptManager is not None


def test_engine_config_create_defaults_and_override():
    from src.backend.engine_config import EngineConfig
    from src.backend.engine_utils import AdaptiveCooldown

    cfg = EngineConfig.create("key")
    assert cfg.api_key == "key"
    assert isinstance(cfg.cooldown, AdaptiveCooldown)

    cd = AdaptiveCooldown(base_sec=1.0, min_sec=0.1, max_sec=2.0)
    assert EngineConfig.create("k2", cd).cooldown is cd


def test_engine_helpers_get_engine(monkeypatch):
    from src.backend import engine_helpers

    sentinel = object()
    seen = {}

    class _FakeContainer:
        def __init__(self, api_key=None):
            seen["api_key"] = api_key

        def engine_facade(self):
            return sentinel

    monkeypatch.setattr(engine_helpers, "AppContainer", _FakeContainer)
    assert engine_helpers.get_engine("abc") is sentinel
    assert seen["api_key"] == "abc"
