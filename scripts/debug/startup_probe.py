"""起動診断: ASGI アプリ直接在Process上で起動し、lifespan と主要エンドポイントを検証する。

ポートを掴まずにアプリ単体の起動整合性を確認できる。

使い方:
    python scripts/debug/startup_probe.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("HUEY_BACKEND", "sqlite")
os.environ.setdefault("DATABASE_URL", "sqlite:///./autonovel.db")
os.environ.setdefault("HUEY_IMMEDIATE", "false")

PROBE_PATHS = ["/health", "/healthz", "/api/health", "/api/v1/health", "/docs", "/openapi.json"]


async def main() -> int:  # noqa: C901, PLR0912
    t0 = time.perf_counter()
    try:
        from src.backend.server import app
    except BaseException:
        traceback.print_exc()
        print("RESULT: FAIL (import)")
        return 1
    print(f"[+] import ok in {time.perf_counter() - t0:.1f}s")

    import httpx

    transport = httpx.ASGITransport(app=app)

    # --- lifespan (startup/shutdown イベント) ---
    async with httpx.AsyncClient(
        transport=transport, base_url="http://probe", timeout=30.0
    ) as client:
        try:
            async with app.router.lifespan_context(app):
                print("[+] lifespan startup ok")
        except BaseException:
            traceback.print_exc()
            print("RESULT: FAIL (lifespan startup)")
            return 1

        for path in PROBE_PATHS:
            started = time.perf_counter()
            try:
                resp = await client.get(path)
            except BaseException as exc:  # noqa: BLE001
                print(f"[x] {path:<20} EXC {type(exc).__name__}: {exc}")
                continue
            ms = (time.perf_counter() - started) * 1000
            body = resp.text[:160].replace("\n", " ")
            print(f"[{resp.status_code}] {path:<20} {ms:7.1f}ms  {body}")

        try:
            async with app.router.lifespan_context(app):
                print("[+] lifespan startup ok (2nd time)")
        except BaseException:
            traceback.print_exc()
            print("RESULT: FAIL (lifespan startup 2nd)")
            return 1

    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
