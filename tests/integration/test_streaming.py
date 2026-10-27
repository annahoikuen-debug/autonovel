"""SSE ストリーミング生成エンドポイントの統合テスト (Step 15-17)。

検証対象: GET /easy_mode/generate/stream
- 正常系: start / chunk / done イベントが順序通りに返る
- 切断検知: クライアント切断時に adapter.cancel() が呼ばれる
- レート制限: 同一 IP から短時間に大量リクエストが来ると 429 を返す
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient


def _b64(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _parse_sse_events(text: str) -> list[dict]:
    events: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            events.append(json.loads(line[len("data:") :].strip()))
        except json.JSONDecodeError:
            continue
    return events


def test_stream_query_fields_emits_start_chunks_done(client: TestClient) -> None:
    """GET /easy_mode/generate/stream 正常系（個別のクエリフィールド経由）: start → chunk* → done.

    base64 `payload` クエリパラメータは、LLM API キーを含みうる入力を
    アクセスログとブラウザ履歴へ漏らすため、明示的に 400 で拒否される。
    サポートされた経路（個別のクエリフィールド）で検証する。
    """
    resp = client.get(
        "/easy_mode/generate/stream",
        params={
            "current_chapter": "森の奥で主人公は剣を抜いた。",
            "content_length_limit": 2000,
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("x-accel-buffering") == "no"

    events = _parse_sse_events(resp.text)
    types = [e.get("type") for e in events]
    assert types[0] == "start"
    assert "chunk" in types
    assert types[-1] == "done"
    chunks = [e for e in events if e.get("type") == "chunk"]
    assert len(chunks) >= 1


def test_stream_get_rejects_base64_payload_query_param(client: TestClient) -> None:
    """base64 `payload` クエリパラメータは 400 で拒否される（セキュリティ修正の回帰テスト）。

    クエリ文字列はアクセスログ・ブラウザ履歴・プロキシログに平文で残るため、
    `llm_config.api_key` / `base_url` を埋め込める base64 payload は受け付けない。
    """
    payload = _b64(
        {
            "current_chapter": "森の奥で主人公は剣を抜いた。",
            "llm_config": {"api_key": "sk-leaked-into-access-logs", "base_url": "http://evil/"},
        }
    )
    resp = client.get(f"/easy_mode/generate/stream?payload={payload}")
    assert resp.status_code == 400
    assert "payload" in resp.text


def test_stream_post_emits_start_chunks_done(client: TestClient) -> None:
    """POST /easy_mode/generate/stream 正常系: start → chunk* → done."""
    payload = {
        "current_chapter": "森の奥で主人公は剣を抜いた。",
        "chapter_history": [],
        "character_params": {},
        "content_length_limit": 2000,
    }
    resp = client.post("/easy_mode/generate/stream", json=payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("x-accel-buffering") == "no"

    events = _parse_sse_events(resp.text)
    types = [e.get("type") for e in events]
    assert types[0] == "start"
    assert "chunk" in types
    assert types[-1] == "done"
    chunks = [e for e in events if e.get("type") == "chunk"]
    assert len(chunks) >= 1


def test_stream_post_validation_error(client: TestClient) -> None:
    """POST /easy_mode/generate/stream バリデーションエラー: content_length_limit: -1 → 422"""
    payload = {
        "current_chapter": "テスト",
        "chapter_history": [],
        "character_params": {},
        "content_length_limit": -1,  # 不正な値
    }
    resp = client.post("/easy_mode/generate/stream", json=payload)
    assert resp.status_code == 422


def test_stream_post_invokes_cancel_on_disconnect(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST ストリーミング中にクライアント切断時に adapter.cancel() が呼ばれる。
    GET 版と同様に、generator 内の disconnect_check をモンキーパッチする。
    """
    import src.backend.routers.streaming as streaming_module

    async def _always_disconnected(_request: object) -> bool:
        return True

    monkeypatch.setattr(streaming_module, "_check_disconnect", _always_disconnected)

    from src.services.llm.mock_adapter import MockLLMAdapter

    cancel_called = {"n": 0}

    class _SpyAdapter(MockLLMAdapter):
        def cancel(self) -> None:
            cancel_called["n"] += 1
            super().cancel()

    monkeypatch.setattr(streaming_module, "get_llm_adapter", lambda *args, **kwargs: _SpyAdapter())

    from src.backend.rate_limit import stream_limiter

    stream_limiter.reset()

    payload = {
        "current_chapter": "切断テスト",
        "chapter_history": [],
        "character_params": {},
        "content_length_limit": 2000,
    }

    resp = client.post("/easy_mode/generate/stream", json=payload)
    assert resp.status_code == 200

    assert cancel_called["n"] >= 1


def test_stream_invokes_cancel_on_disconnect(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """クライアント切断時に adapter.cancel() が呼ばれる。

    ``request.is_disconnected`` は starlette の内部 ``receive`` チャネルを
    消費するため TestClient 上では再現が難しいため、ここでは generator 内
    のロジックで ``disconnect_check`` を強制的に True 返すモンキーパッチを
    あてる経路 (``src.backend.routers.streaming`` 名前空間) で検証する。

    入力は base64 `payload` クエリパラメータではなく、個別のクエリフィールドで渡す
    （``payload`` はアクセスログ漏えい防止のため 400 で拒否される）。
    """
    import src.backend.routers.streaming as streaming_module

    async def _always_disconnected(_request: object) -> bool:
        return True

    monkeypatch.setattr(streaming_module, "_check_disconnect", _always_disconnected)

    from src.services.llm.mock_adapter import MockLLMAdapter

    cancel_called = {"n": 0}

    class _SpyAdapter(MockLLMAdapter):
        def cancel(self) -> None:
            cancel_called["n"] += 1
            super().cancel()

    monkeypatch.setattr(streaming_module, "get_llm_adapter", lambda *args, **kwargs: _SpyAdapter())

    from src.backend.rate_limit import stream_limiter

    stream_limiter.reset()

    resp = client.get(
        "/easy_mode/generate/stream",
        params={"current_chapter": "切断テスト", "content_length_limit": 2000},
    )
    assert resp.status_code == 200

    assert cancel_called["n"] >= 1


def test_stream_rate_limit(client: TestClient) -> None:
    """同一 IP から 4 回以上リクエストすると 429 が返る。"""
    from src.backend.rate_limit import stream_limiter

    stream_limiter.reset()
    params = {"current_chapter": "RL", "content_length_limit": 2000}

    statuses: list[int] = []
    for _ in range(4):
        r = client.get("/easy_mode/generate/stream", params=params)
        statuses.append(r.status_code)

    assert statuses[0] == 200
    assert 429 in statuses
