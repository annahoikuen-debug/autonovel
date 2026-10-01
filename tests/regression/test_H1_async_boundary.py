"""同期関数から無防備に ``asyncio.run`` / ``run_until_complete`` を呼ばないことの archangel。

``asyncio.run`` は「実行中のイベントループがある環境」では RuntimeError になる。
イベントループ内から呼ばれる前提のコード（FastAPI のハンドラ内から呼ばれる
同期ヘルパー等）で無防備に呼ぶと、テストは緑・本番で落ちる。

本テストは M1 で共有し、以降は追記のみ。
"""
from __future__ import annotations

import ast
import glob

# 正当な箇所のみを列挙する。理由が無い allowlist エントリは本計画の失敗。
# sync entry point（Huey ワーカー / CLI / 同期ファサード）は ループ外で動くため許可。
ALLOWLIST: dict[str, str] = {
    "src/backend/tasks/__init__.py": (
        "全て `@huey.task` / `@huey.periodic_task` 修飾のワーカースレッド用 entry point。"
        "呼び出し側（routers/*.py）はhuey に投入するだけで本体は走らない。"
        "TODO(H1-5): Huey immediate モード時にリクエストループ内でも走る経路を別途確認"
    ),
    "src/backend/tasks/commercial_tasks.py": (
        "@huey.task 修飾のワーカー entry point。`run_now` からの直接呼び出しも"
        "ワーカースレッド内で完結する。TODO(H1-5): immediate モード時の経路を確認"
    ),
    "src/backend/tasks/generation_tasks.py": (
        "@huey.task 修飾のワーカー用 _run_async ヘルパー。"
        "TODO(H1-5): immediate モード時の経路を確認"
    ),
    "src/backend/tasks/huey.py": (
        "@huey.task 修飾のワーカー entry point。"
        "TODO(H1-5): immediate モード時の経路を確認"
    ),
    "src/backend/tasks/illustration_tasks.py": (
        "@huey.task 修飾のワーカー用 _run_async ヘルパー。"
        "TODO(H1-5): immediate モード時の経路を確認"
    ),
    "src/cli/illustration_cli.py": (
        "argparse の main()。プロセス起動時に 1 回だけ呼ばれる同期 entry point。"
        "TODO(H1-6): なし（構造的に安全）"
    ),
    "src/infrastructure/api/api_client.py": (
        "close_client() はアプリケーション終了時の同期ファサード。"
        "docstring が「実行中のイベントループがないコンテキスト」を前提と明記し、"
        "asyncio.run は except RuntimeError で保護されている。"
        "TODO(H1-5): 前提が崩れた場合の起動時ログ監視"
    ),
}

# 「ループ内に居るなら task 化して待つ」ガード。あれば asyncio.run には到達しない。
# `asyncio.get_event_loop()` はガードにならない（実行中ループを返すだけで、
# その上で run_until_complete すると RuntimeError になる）ため意図的に除外。
GUARD_NAMES = ("get_running_loop", "run_coroutine_threadsafe", "from_thread")
GUARD_OBJECTS = ("ThreadPoolExecutor", "Thread")


def _files() -> list[str]:
    return sorted(
        p.replace("\\", "/")
        for p in glob.glob("src/**/*.py", recursive=True)
        if not p.replace("\\", "/").startswith("tests/")
    )


def _call_name(call: ast.Call) -> str:
    try:
        return ast.unparse(call.func)
    except Exception:  # noqa: BLE001 - unparse は exotic な式では失敗しうる
        return ""


def _is_suspect(name: str) -> bool:
    return name == "asyncio.run" or name.endswith(".run_until_complete")


def _is_guard(name: str) -> bool:
    return any(g in name for g in GUARD_NAMES) or name.split(".")[-1] in GUARD_OBJECTS


def _offenders() -> list[str]:
    """最外層の関数単位で判定する。

    入れ子のワーカー（``def _worker()``）は親のガードを継承するため、
    関数ごとに独立して見ると誤検出になる。
    """
    offenders: list[str] = []
    for rel in _files():
        tree = ast.parse(open(rel, encoding="utf-8").read())
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            if not any(_is_suspect(_call_name(c)) for c in calls):
                continue
            if any(_is_guard(_call_name(c)) for c in calls):
                continue
            offenders.append(f"{rel}:{node.lineno} {node.name}()")
    return sorted(offenders)


def _file_of(offender: str) -> str:
    return offender.split(":", 1)[0]


def test_no_unguarded_asyncio_run_in_sync_functions():
    unlisted = [o for o in _offenders() if _file_of(o) not in ALLOWLIST]
    assert not unlisted, (
        f"ガード無しの asyncio.run / run_until_complete が {len(unlisted)} 件ある:\n  "
        + "\n  ".join(unlisted)
        + "\n\n ループ外で動く entry point なら ALLOWLIST にファイルパスと "
        "「理由 + TODO(H1-N)」を書いて許可すること。"
    )


def test_allowlist_entries_still_exist():
    """allowlist に残したファイルが削除済みだと archangel が空振りになるので検出する。"""
    existing = set(_files())
    stale = sorted(p for p in ALLOWLIST if p not in existing)
    assert not stale, f"ALLOWLIST に載ったファイルが存在しない（archangel が空振りする）: {stale}"


def test_allowlist_entries_have_reasons():
    for path, reason in ALLOWLIST.items():
        assert reason.strip(), f"{path} の allowlist に理由が無い"
        assert "TODO(H1-" in reason, (
            f"{path} の allowlist に TODO(H1-N) の番号が無い（§9: 数値外れ禁止）"
        )