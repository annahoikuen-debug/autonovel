"""AutoNovel ローカル起動スクリプト (Python 版クロスプラットフォームランチャー)。

`scripts/start_local.ps1` と同じ構成を起動するが、Linux / macOS でも使える。

  - Backend  : uvicorn src.backend.server:app        (http://localhost:8200)
  - Worker   : huey.bin.huey_consumer                (Huey タスクキュー)
  - Frontend : npm run dev                            (http://localhost:5173)

特徴:
  - 起動に使う Python を「バックエンド依存が揃っているか」で自動選択する
  - 各サービスの出力を logs/ へ保存する（失敗が黒箱にならない）
  - ヘルスチェックが通るまで待ってから「起動完了」と報告する
  - Ctrl+C で 3 プロセスとその子プロセスをまとめて停止する

使い方:
    python scripts/start_local.py                 # 全部起動
    python scripts/start_local.py --no-browser    # ブラウザを開かない
    python scripts/start_local.py --no-worker     # ワーカーなし（バックエンドのみ）
    python scripts/start_local.py --ready-timeout 300
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
LOG_DIR = ROOT_DIR / "logs"

BACKEND_PORT = 8200
FRONTEND_PORT = 5173

#: バックエンドを起動するために必要なモジュール。
REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "huey",
    "sqlalchemy",
    "alembic",
    "pydantic",
)


def _python_candidates() -> list[tuple[str, Path]]:
    """(ラベル, 実行ファイル) の候補を「使える順」で返す。"""
    candidates: list[tuple[str, Path]] = []
    venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        candidates.append((".venv", venv_python))
    venv_python_posix = ROOT_DIR / ".venv" / "bin" / "python"
    if venv_python_posix.exists():
        candidates.append((".venv", venv_python_posix))
    for exe in ("python", "python3"):
        found = shutil.which(exe)
        if found:
            candidates.append((f"PATH {exe}", Path(found)))
    return candidates


def _can_run_backend(python: Path) -> bool:
    probe = "; ".join(f"import {m}" for m in REQUIRED_MODULES)
    try:
        result = subprocess.run(
            [str(python), "-c", probe],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_python() -> Path | None:
    """バックエンドを起動できる Python インタプリタを返す。"""
    for label, exe in _python_candidates():
        if _can_run_backend(exe):
            print(f"[python] {exe}  ({label})")
            return exe
    return None


def _probe(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _log_files(name: str) -> tuple[Path, Path]:
    out = LOG_DIR / f"{name}.log"
    err = LOG_DIR / f"{name}.err.log"
    for path in (out, err):
        path.unlink(missing_ok=True)
    return out, err


def _show_log_tail(name: str, lines: int = 30) -> None:
    for path in _log_files_existing(name):
        if path.stat().st_size == 0:
            continue
        print(f"--- {path.name} (last {lines} lines) ---", file=sys.stderr)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]:
            print(f"    {line}", file=sys.stderr)


def _log_files_existing(name: str) -> list[Path]:
    return [p for p in (LOG_DIR / f"{name}.log", LOG_DIR / f"{name}.err.log") if p.exists()]


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoNovel local launcher")
    parser.add_argument("--no-browser", action="store_true", help="起動後にブラウザを開かない")
    parser.add_argument("--no-worker", action="store_true", help="Huey ワーカーを起動しない")
    parser.add_argument("--ready-timeout", type=int, default=180, help="準備完了を待つ秒数")
    args = parser.parse_args()

    print("=" * 60)
    print("  AutoNovel Local Launcher")
    print("=" * 60)
    print(f"  Frontend UI : http://localhost:{FRONTEND_PORT}")
    print(f"  Backend API : http://localhost:{BACKEND_PORT}")
    print(f"  API Docs    : http://localhost:{BACKEND_PORT}/docs")
    print("=" * 60)

    python = resolve_python()
    if python is None:
        print("", file=sys.stderr)
        print(
            f"[ERROR] バックエンドを起動できる Python がありません "
            f"(要: {', '.join(REQUIRED_MODULES)})",
            file=sys.stderr,
        )
        print("   remedies:", file=sys.stderr)
        print('    py -m pip install -e ".[dev]"', file=sys.stderr)
        print("    (または scripts/doctor.ps1 で詳細な診断)", file=sys.stderr)
        return 1

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HUEY_BACKEND"] = "sqlite"
    env["DATABASE_URL"] = "sqlite:///./autonovel.db"
    env["HUEY_IMMEDIATE"] = "false"
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONUNBUFFERED"] = "1"

    # DB を先に初期化する（immature な状態でサーバを起動しない）
    init_db = ROOT_DIR / "scripts" / "init_db.py"
    if init_db.exists():
        print("\n[1/3] Initializing database ...")
        subprocess.run([str(python), str(init_db)], cwd=str(ROOT_DIR), env=env, check=False)

    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        print("[ERROR] npm が見つかりません (PATH を確認してください)", file=sys.stderr)
        return 1
    if not (FRONTEND_DIR / "node_modules" / ".bin").exists():
        print(
            "[ERROR] frontend/node_modules/.bin がありません。`cd frontend && npm install` を実行してください。",
            file=sys.stderr,
        )
        return 1

    commands: list[tuple[str, list[str], Path]] = [
        (
            "backend",
            [
                str(python),
                "-m",
                "uvicorn",
                "src.backend.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
            ],
            ROOT_DIR,
        ),
    ]
    if not args.no_worker:
        commands.append(
            (
                "worker",
                [str(python), "-m", "huey.bin.huey_consumer", "src.backend.tasks.huey.huey"],
                ROOT_DIR,
            )
        )
    commands.append(
        (
            "frontend",
            [npm, "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"],
            FRONTEND_DIR,
        )
    )

    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        for index, (name, cmd, cwd) in enumerate(commands, start=2):
            out_path, err_path = _log_files(name)
            print(f"[{index}/3] Starting {name} ...")
            handle_out = out_path.open("wb")
            handle_err = err_path.open("wb")
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=handle_out,
                stderr=handle_err,
            )
            processes.append((name, proc))
            print(f"        pid={proc.pid}  logs -> {out_path}")

        # --- 準備完了待ち ------------------------------------------------- #
        deadline = time.monotonic() + args.ready_timeout
        backend_ready = False
        frontend_ready = False
        while time.monotonic() < deadline:
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n[ERROR] {name} が終了しました (code={proc.returncode})", file=sys.stderr)
                    _show_log_tail(name)
                    raise KeyboardInterrupt
            if not backend_ready and _probe(f"http://127.0.0.1:{BACKEND_PORT}/health"):
                backend_ready = True
                print("  [OK] Backend ready")
            if not frontend_ready and _probe(f"http://127.0.0.1:{FRONTEND_PORT}/"):
                frontend_ready = True
                print("  [OK] Frontend ready")
            if backend_ready and frontend_ready:
                break
            time.sleep(2)

        print("")
        if backend_ready:
            print(f"  Backend  : http://localhost:{BACKEND_PORT}  (docs: /docs)")
        else:
            print(f"  [WARN] Backend が {args.ready_timeout} 秒以内に応答しませんでした", file=sys.stderr)
        if frontend_ready:
            print(f"  Frontend : http://localhost:{FRONTEND_PORT}")
        else:
            print(f"  [WARN] Frontend が {args.ready_timeout} 秒以内に応答しませんでした", file=sys.stderr)
        print(f"  Logs     : {LOG_DIR}")
        print("  Ctrl+C で停止")
        print("")

        if backend_ready and frontend_ready and not args.no_browser:
            webbrowser.open(f"http://localhost:{FRONTEND_PORT}")

        while True:
            time.sleep(2)
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n[WARN] {name} が終了しました:", file=sys.stderr)
                    _show_log_tail(name)
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\n[stop] サービスを停止しています ...")
    finally:
        for name, proc in processes:
            if proc.poll() is not None:
                continue
            if os.name == "nt":
                subprocess.call(  # noqa: S603, S607
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                proc.terminate()
        for _, proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("[stop] すべて停止しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
