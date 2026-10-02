"""import しただけでスレッドが立ったり、プロセスのシングルトンが壊れたりしないことの archangel。

実測（2026-10-01, Python 3.14）:
- ``import src.core.executor_manager`` で新規スレッドは **0 本**。
  ``ThreadPoolExecutor`` は ``submit()`` されるまでスレッドを作らないため、
  「import 時に 40 スレッド生成」という指控は成り立たない。
  ただし「import 時に ExecutorManager インスタンスを作る」こと自体は残るため、
  本テストは **スレッド数** ではなく **import 時の副作用** を検出する。
- ``AppContainer`` は ``containers.DeclarativeContainer`` のクラスであり、
  ``AppContainer.db()`` はクラスレベルの ``providers.Singleton`` を解決する。
  よって既にプロセスシングルトンとして機能している（毎リクエスト生成されていない）。

本テストは M3 で追加。以降も追記のみ。
"""
from __future__ import annotations

import ast
import glob
import json
import subprocess
import sys
import textwrap

# import 時にスレッドを起こす呼び出し。これらがモジュールトップレベルに居たら違反。
IMPORT_TIME_THREAD_CALLS = (
    "threading.Thread",
    "Thread(",
    ".start()",
    ".submit(",
)

SCANNED_DIRS = ("src",)


def _files() -> list[str]:
    out: list[str] = []
    for root in SCANNED_DIRS:
        out.extend(p.replace("\\", "/") for p in glob.glob(f"{root}/**/*.py", recursive=True))
    return sorted(out)


def _top_level_nodes(tree: ast.Module) -> list[ast.stmt]:
    return list(tree.body)


def test_detector_flags_a_synthetic_import_time_thread():
    """archangel 自身が検出力を持つことの証明（P4: 検出器をMeta検証する）。

    悪化したモジュールをitiousに作って「検出できる」ことを確認する。
    検出器が常に空を返す実装になっていたら本テストが赤になる。
    """
    bad_source = textwrap.dedent(
        """
        import threading

        _t = threading.Thread(target=lambda: None)
        _t.start()
        """
    )
    offenders = _detect(textwrap.dedent("src/synthetic_bad.py"), bad_source)
    assert offenders, "検出器が import 時のスレッド生成を検出できていない"

    good_source = textwrap.dedent(
        """
        import threading


        def start_worker():
            t = threading.Thread(target=lambda: None)
            t.start()
            return t
        """
    )
    assert not _detect("src/synthetic_good.py", good_source), (
        "関数内でのスレッド起動まで禁止している（誤検出）"
    )


def _detect(rel: str, source: str) -> list[str]:
    """モジュールトップレベル（import 時）にスレッドを起こす呼び出しを列挙する。"""
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in _top_level_nodes(tree):
        if not isinstance(node, (ast.Assign, ast.Expr, ast.AnnAssign)):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            name = ast.unparse(call.func)
            if name.endswith(".start") or name.endswith(".submit") or name.endswith("Thread"):
                offenders.append(f"{rel}:{call.lineno} {name}")
    return offenders


def test_no_module_starts_threads_at_import():
    offenders: list[str] = []
    for rel in _files():
        src = open(rel, encoding="utf-8").read()
        offenders.extend(_detect(rel, src))
    assert not offenders, (
        f"import 時にスレッドを起動するモジュールがある: {offenders}\n"
        " 遅延生成（関数化 / lru_cache / get_xxx() ファクトリ）すること。"
    )


def test_importing_executor_manager_spawns_no_threads():
    """``import src.core.executor_manager`` で OS スレッドが増えないこと（実測）。"""
    probe = textwrap.dedent(
        """
        import json, threading
        before = {t.name for t in threading.enumerate()}
        import src.core.executor_manager as m
        after = {t.name for t in threading.enumerate()}
        print("RESULT" + json.dumps({
            "new": sorted(after - before),
            "io": len(m.executor_manager.io_executor._threads),
            "cpu": len(m.executor_manager.cpu_executor._threads),
        }))
        """
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT")), None)
    assert line, f"プローブが出力しない: {p.stdout[-2000:]}"
    data = json.loads(line[len("RESULT") :])
    assert data["new"] == [], f"import 時にスレッドが立った: {data['new']}"
    assert data["io"] == 0 and data["cpu"] == 0, (
        f"import 時に executor のスレッドが確保された: io={data['io']} cpu={data['cpu']}"
    )


def test_app_container_providers_are_process_singletons():
    """``AppContainer`` のプロバイダがプロセス内で同一インスタンスを返すこと。"""
    probe = textwrap.dedent(
        """
        from src.core.container.app import AppContainer
        print("SAME", AppContainer.db() is AppContainer.db())
        print("KIND", type(AppContainer.db).__name__)
        """
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    kv = dict(
        ln.split(" ", 1) for ln in p.stdout.splitlines() if ln.startswith(("SAME ", "KIND "))
    )
    assert kv.get("SAME") == "True", "AppContainer.db() が呼び出しごとに別インスタンスを返す"
    assert kv.get("KIND") == "Singleton", (
        f"AppContainer.db が Singleton プロバイダでない: {kv.get('KIND')}"
    )


def test_app_container_is_not_instantiated_per_call():
    """``AppContainer()`` の直接生成が増えないこと（ratchet: 実測 9 箇所）。

    クラスレベルの ``providers.Singleton`` を使うため、コンテナ実体を毎回作って
    リソースを分けたりしないこと。9 を超えたら红灯させる。
    """
    offenders: list[str] = []
    for rel in _files():
        tree = ast.parse(open(rel, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if ast.unparse(node.func).endswith("AppContainer"):
                offenders.append(f"{rel}:{node.lineno}")
    assert len(offenders) <= 9, (
        f"AppContainer() の直接生成が 9 箇所を超えた: {sorted(offenders)}"
    )
