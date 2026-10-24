"""一時調査用: _run_illustration_batch 未アウェイト原因の特定。"""

import traceback


def test_repro_unawaited(caplog):
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import src.backend.tasks.illustration_tasks as it

    orig = it._run_illustration_batch
    orig_run_async = it._run_async
    created_stacks: list[str] = []
    awaited: list = []

    def wrapper(*a, **k):
        created_stacks.append("".join(traceback.format_stack()))
        return orig(*a, **k)

    def run_async_wrapper(coro):
        awaited.append(coro)
        try:
            return orig_run_async(coro)
        except BaseException:
            print("!!! _run_async raised:")
            traceback.print_exc()
            raise

    it._run_illustration_batch = wrapper
    it._run_async = run_async_wrapper

    huey_mod = sys.modules["src.backend.tasks.huey"]
    huey_instance = huey_mod.huey
    original_immediate = huey_instance.immediate
    huey_instance.immediate = True
    try:
        app = FastAPI()
        from src.backend.routers.illustrations import (
            get_illustration_workflow,
            router,
        )

        app.include_router(router, prefix="/api/illustrations")

        async def _override_workflow():
            class _FakeWorkflow:
                illustration_agent = MagicMock()

                async def execute(self, **kwargs):
                    return {"status": "success"}

            return _FakeWorkflow()

        app.dependency_overrides[get_illustration_workflow] = _override_workflow
        with patch(
            "src.backend.routers.illustrations.verify_book_ownership",
            new=AsyncMock(return_value=MagicMock()),
        ), patch.object(it, "_deduct_batch_credits", return_value=(0, 0)):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/illustrations/batch",
                    json={"book_id": 1, "settings": {"enableIllustration": True}},
                )
        print("resp:", resp.status_code, resp.json())
    finally:
        huey_instance.immediate = original_immediate
        it._run_illustration_batch = orig
        it._run_async = orig_run_async

    print("created:", len(created_stacks), "awaited:", len(awaited))
    for i, stack in enumerate(created_stacks):
        print(f"--- creation #{i} ---\n{stack}")

    import gc

    gc.collect()
    leftovers = [
        o
        for o in gc.get_objects()
        if type(o).__name__ == "coroutine" and getattr(o, "cr_code", None) is not None
    ]
    print("live coroutines:", len(leftovers))
    for c in leftovers:
        print("  ", c, getattr(c, "cr_origin", None))
    assert False, f"created={len(created_stacks)} awaited={len(awaited)}"
