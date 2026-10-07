"""非同期 API クライアントの単体テスト（HTTP は全てモック）."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.exceptions import APIError as APIException
from src.infrastructure.api import api_client as ac
import src.infrastructure.api.api_client as api_client


@pytest.fixture(autouse=True)
def _restore_clients():
    sync = ac._resilient_client
    async_client = ac._async_client
    yield
    ac._resilient_client = sync
    ac._async_client = async_client


def make_response(status_code: int = 200, payload=None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TestSyncClient:
    def test_get_client_reuses_resilient(self):
        client = MagicMock()
        ac._resilient_client = client
        assert ac.get_client() is client

    def test_get_client_creates(self, monkeypatch):
        ac._resilient_client = None
        created = MagicMock()
        monkeypatch.setattr(ac.httpx, "Client", lambda **kw: created)
        assert ac.get_client() is created
        assert ac._resilient_client is created

    def test_request_get_uses_params(self):
        client = MagicMock()
        client.request.return_value = "RESP"
        ac._resilient_client = client
        assert ac._request("GET", "/x", a=1) == "RESP"
        _, kwargs = client.request.call_args
        assert kwargs["params"] == {"a": 1}
        assert kwargs["json"] is None

    def test_request_post_uses_json(self):
        client = MagicMock()
        client.request.return_value = "RESP"
        ac._resilient_client = client
        ac._request("POST", "/x", a=1)
        _, kwargs = client.request.call_args
        assert kwargs["json"] == {"a": 1}
        assert kwargs["params"] is None

    def test_request_post_no_kwargs(self):
        client = MagicMock()
        ac._resilient_client = client
        ac._request("PUT", "/x")
        _, kwargs = client.request.call_args
        assert kwargs["json"] is None

    def test_request_head_and_delete(self):
        client = MagicMock()
        ac._resilient_client = client
        for method in ("DELETE", "HEAD", "OPTIONS"):
            ac._request(method, "/x", q=2)
            _, kwargs = client.request.call_args
            assert kwargs["params"] == {"q": 2}, method

    def test_resolve_if_coroutine_passthrough(self):
        assert ac._resolve_if_coroutine(123) == 123

    def test_resolve_if_coroutine_no_loop(self):
        async def coro():
            return "done"

        assert ac._resolve_if_coroutine(coro()) == "done"

    def test_resolve_if_coroutine_in_running_loop(self):
        async def coro():
            return "threaded"

        async def outer():
            return ac._resolve_if_coroutine(coro())

        assert asyncio.run(outer()) == "threaded"

    def test_resolve_if_coroutine_error_in_thread(self):
        async def coro():
            raise ValueError("bad")

        async def outer():
            return ac._resolve_if_coroutine(coro())

        with pytest.raises(ValueError):
            asyncio.run(outer())

    def test_close_client(self):
        client = MagicMock()
        ac._resilient_client = client
        ac.close_client()
        client.close.assert_called_once()
        assert ac._resilient_client is None

    def test_close_client_without_client(self):
        ac._resilient_client = None
        ac.close_client()

    def test_close_client_runtime_error(self, caplog):
        # 実行中のループがあるため close_async_client の asyncio.run が RuntimeError になる
        ac._resilient_client = None
        # asyncio.run に到達するには _async_client が非 None でなければならない
        # （close_client のガード `if _async_client is not None` の内側が
        # 検証対象）。None だと分岐ごとスキップされ RuntimeError が起きない。
        ac._async_client = MagicMock()
        real_run = ac.asyncio.run

        def boom(coro):
            coro.close()
            raise RuntimeError("loop running")

        ac.asyncio.run = boom
        try:
            with caplog.at_level("WARNING"):
                ac.close_client()
        finally:
            ac.asyncio.run = real_run
        assert any("イベントループ" in r.message for r in caplog.records)


class TestAsyncClient:
    def test_get_async_client_creates(self, monkeypatch):
        ac._async_client = None
        created = MagicMock()
        created.is_closed = False
        monkeypatch.setattr(ac.httpx, "AsyncClient", lambda **kw: created)
        assert ac._get_async_client() is created

    def test_get_async_client_recreates_when_closed(self, monkeypatch):
        closed = MagicMock()
        closed.is_closed = True
        ac._async_client = closed
        created = MagicMock()
        created.is_closed = False
        monkeypatch.setattr(ac.httpx, "AsyncClient", lambda **kw: created)
        assert ac._get_async_client() is created

    async def test_close_async_client(self):
        client = MagicMock()
        client.is_closed = False
        client.aclose = AsyncMock()
        ac._async_client = client
        await ac.close_async_client()
        client.aclose.assert_awaited_once()
        assert ac._async_client is None

    async def test_close_async_client_already_closed(self):
        client = MagicMock()
        client.is_closed = True
        ac._async_client = client
        await ac.close_async_client()
        assert ac._async_client is None

    async def test_async_request_success(self, monkeypatch):
        client = MagicMock()

        async def request(method, url, **kwargs):
            return make_response(200, {"ok": True})

        client.request = request
        monkeypatch.setattr(ac, "_get_async_client", lambda: client)
        resp = await ac._async_request("GET", "http://x/y", params={"a": 1})
        assert resp.json() == {"ok": True}

    async def test_async_request_logs_with_audit(self, monkeypatch):
        client = MagicMock()
        response = make_response(200, {})

        async def request(method, url, **kwargs):
            return response

        client.request = request
        monkeypatch.setattr(ac, "_get_async_client", lambda: client)
        audit = MagicMock()
        container = MagicMock()
        container.audit_logger.return_value = audit
        proxy = MagicMock()
        proxy.get_di_container.return_value = container
        monkeypatch.setitem(
            __import__("sys").modules, "src.infrastructure.proxy", proxy
        )
        await ac._async_request("POST", "http://x/books", json={"k": 1})
        assert audit.log.called

    async def test_async_request_connect_error(self, monkeypatch):
        client = MagicMock()

        async def request(method, url, **kwargs):
            raise httpx.ConnectError("down")

        client.request = request
        monkeypatch.setattr(ac, "_get_async_client", lambda: client)
        with pytest.raises(APIException):
            await ac._async_request("GET", "http://x")

    async def test_async_request_timeout(self, monkeypatch):
        client = MagicMock()

        async def request(method, url, **kwargs):
            raise httpx.TimeoutException("slow")

        client.request = request
        monkeypatch.setattr(ac, "_get_async_client", lambda: client)
        with pytest.raises(APIException):
            await ac._async_request("GET", "http://x")

    async def test_async_request_status_error_with_audit(self, monkeypatch):
        client = MagicMock()
        response = make_response(404)
        err = httpx.HTTPStatusError("404", request=MagicMock(), response=response)
        response.raise_for_status.side_effect = err

        async def request(method, url, **kwargs):
            return response

        client.request = request
        monkeypatch.setattr(ac, "_get_async_client", lambda: client)
        audit = MagicMock()
        container = MagicMock()
        container.audit_logger.return_value = audit
        proxy = MagicMock()
        proxy.get_di_container.return_value = container
        monkeypatch.setitem(__import__("sys").modules, "src.infrastructure.proxy", proxy)
        with pytest.raises(APIException):
            await ac._async_request("GET", "http://x")
        assert audit.log.called

    async def test_async_request_unexpected_error(self, monkeypatch):
        client = MagicMock()

        async def request(method, url, **kwargs):
            raise ValueError("weird")

        client.request = request
        monkeypatch.setattr(ac, "_get_async_client", lambda: client)
        proxy = MagicMock()
        container = MagicMock()
        audit = MagicMock()
        container.audit_logger.return_value = audit
        proxy.get_di_container.return_value = container
        monkeypatch.setitem(__import__("sys").modules, "src.infrastructure.proxy", proxy)
        with pytest.raises(APIException):
            await ac._async_request("GET", "http://x")
        assert audit.log.called


class TestApiMethods:
    @pytest.fixture
    def responder(self, monkeypatch):
        calls = []

        def install(payload, response=True):
            async def fake(method, url, **kwargs):
                calls.append((method, url, kwargs))
                if not response:
                    return None
                return make_response(200, payload)

            monkeypatch.setattr(ac, "_async_request", fake)
            return calls

        return install

    async def test_list_books(self, responder):
        calls = responder([{"id": 1}])
        assert await ac.list_books() == [{"id": 1}]
        assert calls[0][0] == "GET"

    async def test_list_books_empty(self, responder):
        responder(None, response=False)
        assert await ac.list_books() == []

    async def test_get_book(self, responder):
        responder({"id": 1})
        assert await ac.get_book(1) == {"id": 1}

    async def test_get_book_none(self, responder):
        responder(None, response=False)
        assert await ac.get_book(1) is None

    async def test_delete_book(self, responder):
        responder({})
        assert await ac.delete_book(1) is True
        responder(None, response=False)
        assert await ac.delete_book(1) is False

    async def test_get_plots(self, responder):
        responder([1])
        assert await ac.get_plots(1) == [1]

    async def test_get_chapters(self, responder):
        responder([1])
        assert await ac.get_chapters(1) == [1]

    async def test_get_bible(self, responder):
        responder({"b": 1})
        assert await ac.get_bible(1) == {"b": 1}

    async def test_get_opt_history(self, responder):
        responder([1])
        assert await ac.get_opt_history(1) == [1]

    async def test_get_task_status(self, responder):
        responder({"state": "done"})
        assert await ac.get_task_status("t1") == {"state": "done"}

    async def test_get_task_status_no_response(self, responder):
        responder(None, response=False)
        res = await ac.get_task_status("t1")
        assert res["is_running"] is False
        assert res["error"] == "バックエンドとの通信エラー"

    async def test_get_task_status_error(self, monkeypatch, caplog):
        async def boom(method, url, **kwargs):
            raise RuntimeError("dead")

        monkeypatch.setattr(ac, "_async_request", boom)
        res = await ac.get_task_status("t1")
        assert "詳細: dead" in res["error"]

    async def test_stop_task(self, responder):
        responder({})
        assert await ac.stop_task("t1") is True
        responder(None, response=False)
        assert await ac.stop_task("t1") is False

    async def test_generate_easy(self, responder):
        calls = responder({"task_id": "tid"})
        res = await ac.generate_easy("k", {}, "g", "kw", "a", 10, 1, 2000, "c", 0.5)
        assert res == "tid"
        assert calls[0][2]["json"]["api_key"] == "k"

    async def test_generate_easy_none(self, responder):
        responder(None, response=False)
        assert await ac.generate_easy("k", {}, "g", "kw", "a", 1, 1, 1, "c", 0.5) is None

    async def test_generate_episodes(self, responder):
        responder({"task_id": "t"})
        res = await ac.generate_episodes("k", {}, 1, 1, 2, 1.0, 2000, True, {}, False)
        assert res == "t"

    async def test_plan_generation(self, responder):
        responder({"task_id": "t"})
        assert await ac.plan_generation("k", {}, {}) == "t"

    async def test_retry_failed_episodes(self, responder):
        responder({"task_id": "t"})
        assert await ac.retry_failed_episodes("k", {}, 1, 1.0, 2000) == "t"

    async def test_expand_plots(self, responder):
        responder({"task_id": "t"})
        assert await ac.expand_plots("k", {}, 1, 1, 3) == "t"

    async def test_rebuild_plots(self, responder):
        responder({"task_id": "t"})
        assert await ac.rebuild_plots("k", {}, {}) == "t"

    async def test_critique_optimize(self, responder):
        responder({"task_id": "t"})
        assert await ac.critique_optimize("k", {}, 1) == "t"

    async def test_import_chapter(self, responder):
        responder({"task_id": "t"})
        assert await ac.import_chapter("k", 1, 1, "text", True) == "t"

    async def test_generate_marketing(self, responder):
        responder({"task_id": "t"})
        assert await ac.generate_marketing("k", 1, 3) == "t"

    async def test_analyze_style_dna(self, responder):
        responder({"dna": []})
        assert await ac.analyze_style_dna("k", "sample") == {"dna": []}
        responder(None, response=False)
        assert await ac.analyze_style_dna("k", "s") == {}

    async def test_create_chapter(self, responder):
        responder({})
        assert await ac.create_chapter(1, 1, "t", "c", "s", "k", "i", {}, {}, "now") is True
        responder(None, response=False)
        assert await ac.create_chapter(1, 1, "t", "c", "s", "k", "i", {}, {}, "now") is False

    async def test_delete_chapter(self, responder):
        responder({})
        assert await ac.delete_chapter(1, 1) is True
        responder(None, response=False)
        assert await ac.delete_chapter(1, 1) is False

    async def test_get_issues(self, responder):
        responder([{"id": 1}])
        assert await ac.get_issues(1) == [{"id": 1}]

    async def test_resolve_issue(self, responder):
        responder({"ok": True})
        assert await ac.resolve_issue(1, "fix", "k") == {"ok": True}
        responder(None, response=False)
        assert (await ac.resolve_issue(1, "fix", "k"))["status"] == "error"

    async def test_save_pending_patch(self, responder):
        responder({"success": True})
        assert await ac.save_pending_patch(1, "t", "c", {}) == {"success": True}
        responder(None, response=False)
        assert (await ac.save_pending_patch(1, "t", "c", {}))["success"] is False

    async def test_get_pending_patches(self, responder):
        responder([{"id": 1}])
        assert await ac.get_pending_patches(1) == [{"id": 1}]

    async def test_approve_patch(self, responder):
        responder({})
        assert await ac.approve_patch(1) == {"success": True}
        responder(None, response=False)
        assert (await ac.approve_patch(1))["success"] is False

    async def test_reject_patch(self, responder):
        responder({})
        assert await ac.reject_patch(1) == {"success": True}
        responder(None, response=False)
        assert (await ac.reject_patch(1))["success"] is False

    async def test_get_prompt_versions(self, responder):
        responder([1])
        assert await ac.get_prompt_versions(1) == [1]

    async def test_rollback_prompt_version(self, responder):
        responder({"ok": 1})
        assert await ac.rollback_prompt_version(1, 2) == {"ok": 1}
        responder(None, response=False)
        assert (await ac.rollback_prompt_version(1, 2))["success"] is False

    async def test_audit_producer_plan(self, responder):
        responder({"score": 80})
        assert await ac.audit_producer_plan("k", "g", "kw", "memo") == {"score": 80}
        responder(None, response=False)
        assert await ac.audit_producer_plan("k", "g", "kw", "memo") == {}

    async def test_export_package(self, responder):
        calls = responder({"file": "x"})
        resp = await ac.export_package("k", 1)
        assert resp.json() == {"file": "x"}
        assert calls[0][2]["params"] == {"api_key": "k"}


def test_module_exposes_thread_for_coroutine_resolution():
    assert api_client.threading is threading
