"""静的解析の「劣化のみ検出」ratchet + 期限付きバーンダウン。

ベースライン JSON に記録された件数を超えたら fail する。
加えて `policy == "burn-down"` の場合、`targets` に定義した
期限付きマイルストーン（例: mypy 半減を 2026-11-30 まで）を強制する:

* 現在値 > baseline 　　　　　　 → fail（悪化検出）
* 期限切れ milestone があり、
  現在値 > target 　　　　　　　 → fail（バーンダウン未達）
* 現在値 < baseline 　　　　　　 → baseline を自動的に下げる（ratchet）
* baseline < 期限切れ target の値 → baseline を target まで下げる（強制改善）

「全エラー 0 化」を目的とはしない (PLAN_H1 §9 で対象外と明記)。

対象:
  ruff   : `ruff check src tests config scripts` のエラー数
  mypy   : `mypy src` のエラー数（invalid-ignore も同一プロセス出力から解析。
            pyproject [tool.mypy] ignore_missing_imports = true により
            --ignore-missing-imports は冗長）
  format : `ruff format --check src` の「整形が必要なファイル数」

使い方:
  python scripts/ci_lint_ratchet.py                 # ruff（後方互換）
  python scripts/ci_lint_ratchet.py --tool mypy
  python scripts/ci_lint_ratchet.py --tool format
  python scripts/ci_lint_ratchet.py --tool invalid-ignore
  python scripts/ci_lint_ratchet.py --tool all
  python scripts/ci_lint_ratchet.py --tool ruff --update
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

BASELINE = Path("config/ci_lint_baseline.json")
RUFF_COUNT_RE = re.compile(r"Found\s+(\d+)\s+error")
MYPY_COUNT_RE = re.compile(r"Found\s+(\d+)\s+error")
FORMAT_COUNT_RE = re.compile(r"(\d+)\s+files?\s+would be reformatted")
INVALID_IGNORE_RE = re.compile(r'Invalid "type: ignore" comment')

TOOLS = ("ruff", "mypy", "format", "invalid-ignore")
BASELINE_KEYS = {
    "ruff": "ruff_errors",
    "mypy": "mypy_errors",
    "format": "format_files",
    "invalid-ignore": "invalid_ignore_errors",
}


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def run_ruff() -> int:
    p = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "config",
            "scripts",
            "--output-format=concise",
        ]
    )
    output = p.stdout + p.stderr
    m = RUFF_COUNT_RE.search(output)
    if m:
        return int(m.group(1))
    # 0 件のとき ruff は "All checks passed!" を返す
    if "All checks passed" in output:
        return 0
    raise RuntimeError(f"ruff の出力からエラー数を取得できませんでした:\n{output[-2000:]}")


# mypy と invalid-ignore は 1 プロセスで共用する。
# pyproject.toml の [tool.mypy] ignore_missing_imports = true により、
# `mypy src` と `mypy src --ignore-missing-imports` の出力は同一であり、
# 2 回 mypy を起動する必要はない（実測: 8.1s + 7.7s -> 8.1s）。
# この前提（ignore_missing_imports = true）が崩れた場合は、invalid-ignore の
# 走査で --ignore-missing-imports を付けた別プロセスが必要になる。
_mypy_cache: dict[str, int] | None = None


def _run_mypy_once() -> tuple[int, int]:
    """mypy src を 1 回実行し、(エラー件数, invalid-ignore 件数) を返す。"""
    global _mypy_cache
    if _mypy_cache is not None:
        return _mypy_cache["errors"], _mypy_cache["invalid_ignore"]

    p = _run([sys.executable, "-m", "mypy", "src"])
    output = p.stdout + p.stderr
    if "Success: no issues found" in output:
        result = {"errors": 0, "invalid_ignore": 0}
    else:
        m = MYPY_COUNT_RE.search(output)
        if not m:
            raise RuntimeError(
                "mypy の出力からエラー数を取得できませんでした"
                f"（終了コード {p.returncode}）:\n{output[-2000:]}"
            )
        result = {
            "errors": int(m.group(1)),
            "invalid_ignore": len(INVALID_IGNORE_RE.findall(output)),
        }
    _mypy_cache = result
    return result["errors"], result["invalid_ignore"]


def run_mypy() -> int:
    return _run_mypy_once()[0]


def run_format() -> int:
    p = _run([sys.executable, "-m", "ruff", "format", "--check", "src"])
    output = p.stdout + p.stderr
    m = FORMAT_COUNT_RE.search(output)
    if m:
        return int(m.group(1))
    if "already formatted" in output or p.returncode == 0:
        return 0
    raise RuntimeError(f"ruff format の出力から件数を取得できませんでした:\n{output[-2000:]}")


def run_invalid_ignore() -> int:
    return _run_mypy_once()[1]


RUNNERS = {"ruff": run_ruff, "mypy": run_mypy, "format": run_format, "invalid-ignore": run_invalid_ignore}


def _load_baseline() -> dict[str, object]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _save_baseline(data: dict[str, object]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


README = Path("README.md")
README_BASELINE_RE = re.compile(r"ruff=\d+ / mypy=\d+ / format=\d+")


def _sync_readme_baseline(data: dict[str, object]) -> None:
    """--update 時に README.md のベースライン値行を JSON と同期する。

    README に「ruff=N / mypy=N / format=N」形式の行が 1 箇所のみ存在する前提。
    """
    text = README.read_text(encoding="utf-8")
    expected = f'ruff={data["ruff_errors"]} / mypy={data["mypy_errors"]} / format={data["format_files"]}'
    new_text, count = README_BASELINE_RE.subn(expected, text)
    if count != 1:
        raise RuntimeError(
            f"README.md のベースライン値行が 1 箇所に見つかりませんでした（{count} 箇所）"
        )
    README.write_text(new_text, encoding="utf-8")


def _expired_targets(data: dict[str, object], tool: str) -> list[dict[str, object]]:
    """当該 tool のメトリクスに対し、期限が過ぎたバーンダウン target を返す。"""
    if data.get("policy") != "burn-down":
        return []
    key = BASELINE_KEYS[tool]
    today = date.today()
    expired: list[dict[str, object]] = []
    for t in data.get("targets", []) or []:
        if not isinstance(t, dict):
            continue
        if t.get("metric") != key:
            continue
        try:
            due = date.fromisoformat(str(t["by"]))
        except (KeyError, ValueError):
            continue
        if due < today:
            expired.append(t)
    return expired


def _check_single_metric(
    data: dict[str, object], tool: str, key: str, actual: int, *, update: bool
) -> tuple[int, bool]:
    """1 メトリクスをベースラインと比較し、(失敗数0/1, data変更有無) を返す。

    data は直接変異する（ベースラインの記録・引き下げ）。ファイル書き出しは
    呼び出し側 (check_tool) で一度だけ行う。
    """
    base = data.get(key)
    if update:
        data[key] = actual
        print(f"{tool}: baseline updated: {actual} ({key})")
        return 0, True
    if base is None:
        # 初回導入時はベースラインを記録して通す（次回以降から ratchet が効く）
        data[key] = actual
        print(f"{tool}: baseline was missing; recorded {actual} ({key})")
        return 0, True
    base = int(base)  # type: ignore[arg-type]
    status = f"{tool}: actual={actual} baseline={base} ({key})"

    # --- バーンダウン target 強制 ---
    forced_floor = 0
    for t in _expired_targets(data, tool):
        target = int(t["target"])
        forced_floor = max(forced_floor, target)
        if actual > target:
            print(
                f"FAIL: {status} / 期限切れマイルストーン '{t['milestone']}' 未達 "
                f"(target={target}, by={t['by']})。"
                " 改善するか、期日の延長を baseline の targets で行うこと。",
                file=sys.stderr,
            )
            return 1, False
        status += f" target'{t['milestone']}'=達成({target})"

    # baseline が期限切れ target より緩い場合、target まで強制的に下げる
    if forced_floor > base:
        data[key] = forced_floor
        print(
            f"{status} / baseline を期限切れ target まで強制引き下げ: {base} -> {forced_floor}"
        )
        return 0, True

    print(status)
    if actual > base:
        print(
            f"FAIL: {tool} の{key} がベースラインより {actual - base} 件増加した。"
            " 意図した増加なら `--update` でベースラインを更新すること。",
            file=sys.stderr,
        )
        return 1, False
    if actual < base:
        print(
            f"GOOD: {base - actual} 件減少。ベースラインは変更せず（--update で明示的に下げる）。({key})"
        )
        return 0, False
    return 0, False


def check_tool(tool: str, *, update: bool) -> int:
    data = _load_baseline()
    failures = 0
    dirty = False

    if tool == "mypy":
        # mypy と invalid-ignore は同一プロセス出力から両方を検証する。
        # pyproject [tool.mypy] ignore_missing_imports = true により、
        # `mypy src` 1 回の実行で両メトリクスを取得できる。
        errors, invalid_ignore = _run_mypy_once()
        for key, actual in (
            ("mypy_errors", errors),
            ("invalid_ignore_errors", invalid_ignore),
        ):
            f, d = _check_single_metric(data, "mypy", key, actual, update=update)
            failures += f
            dirty = dirty or d
    else:
        actual = RUNNERS[tool]()
        key = BASELINE_KEYS[tool]
        f, d = _check_single_metric(data, tool, key, actual, update=update)
        failures += f
        dirty = dirty or d

    if update or dirty:
        _save_baseline(data)
        if update:
            _sync_readme_baseline(data)

    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tool",
        choices=(*TOOLS, "all"),
        default="ruff",
        help="ratchet 対象（既定: ruff）",
    )
    ap.add_argument("--update", action="store_true", help="ベースラインを書き換える")
    args = ap.parse_args()

    tools = TOOLS if args.tool == "all" else (args.tool,)
    failures = 0
    for tool in tools:
        failures += check_tool(tool, update=args.update)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
