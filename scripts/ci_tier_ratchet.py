"""Tier1 テスト失敗の「悪化のみ検出」ratchet。

なぜ ratchet なのか
------------------
2026-10-03 の公開前監査で、このプロジェクトに残る失敗 142 行のうち
**43% (61 行) が環境不在 (Docker/Redis/ChromaDB/Postgres)** だった。
これらを全て 0 にするのは労力が実バ::$from 逸脱する一方で、
放置すると「新しい回帰」が既存赤に紛れて検出されなくなる。

そこで方針を次のように固定する:

- **Tier1**（PR 必須）: `tests/unit`, `tests/backend`, `tests/services`,
  `tests/regression`, `tests/security`, `tests/shared`。
  ここに**新たな失敗ファイル**が 1 件でも生じた時点で fail する。
- **Tier3**（週次・環境依存）: `tests/integration`, `tests/perf`,
  `tests/e2e`, `tests/load`。現状 CI では実行されず、記録のみ。

目的は「赤を 0 にすること」ではなく **「赤が増えることを許さないこと」** である。

既存の `scripts/ci_lint_ratchet.py` と同じ「悪化のみ検出」方式に倣う。
このスクリプトは **pytest から呼び出されない**（pytest 内のテストから
Tier1 全体を起動すると自身を含めて再帰する。2026-10-03 に実際に
プロセスを爆発させた実例がある）。CI から直接実行する。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASELINE = Path("reports/qa_tier_baseline.json")

TIER1_PATHS = (
    "tests/unit",
    "tests/backend",
    "tests/services",
    "tests/regression",
    "tests/security",
    "tests/shared",
)


def run_tier1_isolated() -> tuple[set[str], list[str]]:
    """`tests/regression` の各ファイルを**単独で**実行して失敗を列挙する。

    なぜこれが要るのか
    ----------------
    2026-10-04 の調査で、本 ratchet の blind spot が判明した。
    `tests/regression/test_v53_concurrent_transition.py` は:

    - 単独実行 → **7 件失敗**
    - Tier1 の固定順序（`tests/unit` → ... → `tests/regression`） → **通過**

    原因は他テストの import 副作用（`models_tenant` が
    `Base.metadata` に登録される）。ratchet は固定順序で 1 回だけ実行するため、
    この種の「順序依存」は**原理的に検出できない**。

    ゲート自身は緑なのに、そのファイルに回帰が入っても誰も気づかない。
    そこで回帰ゲートは「ファイル単独実行」を必須にし、
    順序依存そのものを検出可能にする。

    Returns:
        (単独実行で失敗したファイル集合, 実行できなかったファイル一覧)
    """
    failed: set[str] = set()
    skipped: list[str] = []

    files = sorted(Path("tests/regression").glob("test_*.py"))
    if not files:
        return failed, ["tests/regression にテストファイルが無い"]

    for path in files:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(path).replace("\\", "/"),
                "-q", "--tb=no",
                "--continue-on-collection-errors",
                "-p", "no:cacheprovider",
                "--timeout=300",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
        )
        rel = str(path).replace("\\", "/")
        if not _has_summary_line(proc.stdout):
            # 取得できなかったものは「失敗」として扱わず、実行不能として報告する
            skipped.append(rel)
            continue
        if proc.returncode != 0:
            failed.add(rel)

    return failed, skipped


def run_tier1() -> tuple[int, set[str]]:
    """Tier1 を実行し、(終了コード, 失敗ファイル集合, 完了したか) を返す。

    **途中中断された結果を「失敗ゼロ」と誤読してはならない。**
    実行が中断されると pytest は short summary を出力しないため、
    失敗ファイル集合が空になる。空 = 「全て pass」ではなく
    「結果を得られなかった」可能性がある。
    そこで summary 行（`N passed` / `N failed`）の有無で実行の完否を判定し、
    取得できていない場合は fail する。
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            *TIER1_PATHS,
            "-q", "--tb=no",
            "--continue-on-collection-errors",
            "-p", "no:cacheprovider",
            "--timeout=300",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
    )
    files = parse_failing_files(proc.stdout)
    completed = _has_summary_line(proc.stdout)
    return proc.returncode, files, completed


def _has_summary_line(stdout: str) -> bool:
    """pytest の最終サマリ行（"N passed" / "N failed" 等）があるか。

    `Interrupted:` は collection error でセッションが打ち切られたことを
    意味し、これは「結果を得られていない」状態なので先に除外する。
    （" error " を含むためサマリ判定が誤って true になる）
    """
    tail = stdout.strip().splitlines()[-20:]
    for line in tail:
        if "Interrupted:" in line:
            return False
    for line in tail:
        if any(
            token in line
            for token in (
                " passed",
                " failed",
                " error",
                " skipped",
                "xfailed",
                "xpassed",
                "no tests ran",
            )
        ):
            return True
    return False


def parse_failing_files(stdout: str) -> set[str]:
    """pytest の FAILED/ERROR 行から失敗ファイルのパス集合を抽出する。

    pytest の出力には 2 形式ある:

        FAILED tests/x.py::test_name - AssertionError: ...
        ERROR tests/y.py - TypeError: ...

    前者は `::` でテスト名が付くが、後者 (collection/setup エラー) は
    ファイルのみで後ろに説明が続く。`split(" ", 1)` すると
    `tests/y.py - TypeError...` がキーになり、メッセージ文言が変わるだけで
    baseline が stale 判定される。したがって空白区切りの**最初のトークンのみ**を取る。
    """
    files: set[str] = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("FAILED ") or stripped.startswith("ERROR ")):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        path = parts[1].split("::")[0].replace("\\", "/")
        if path:
            files.add(path)
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="ベースラインを書き換える")
    ap.add_argument(
        "--skip-isolation",
        action="store_true",
        help="回帰ゲートの単独実行検査を省く（高速化・検出力低下）",
    )
    args = ap.parse_args()

    _, actual, completed = run_tier1()
    actual_sorted = sorted(actual)

    if not completed:
        print(
            "FAIL: Tier1 の実行が完了しなかった（pytest のサマリ行が得られない）。\n"
            "実行が中断・タイムアウトした可能性があり、"
            "『失敗ゼロ』として扱ってはならない。",
            file=sys.stderr,
        )
        return 1

    # 順序依存検出（別項で検査する）
    isolated_failures: set[str] = set()
    isolation_skipped: list[str] = []
    if not args.skip_isolation:
        isolated_failures, isolation_skipped = run_tier1_isolated()

    if args.update:
        combined = sorted(set(actual_sorted) | isolated_failures)
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "tier1_failing_files": combined,
                    "tier1_failing_files_bulk_run": actual_sorted,
                    "tier1_failing_files_isolated": sorted(isolated_failures),
                    "note": (
                        "Tier1 の既知の失敗ファイル。新たな失敗が 1 件でも出たら fail する。"
                        "ファイルを直したら必ずこのリストからも削除すること。"
                        "既存ファイルをリストに足すのは自己申告であり防御にならない。"
                        "bulk_run = 一括実行での失敗、isolated = 単独実行での失敗。"
                        "差分があるファイルは順序依存を持つ（他テストの import 副作用）。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"baseline updated: {len(combined)} files (bulk {len(actual_sorted)}, isolated {len(isolated_failures)})")
        for f in combined:
            marks = []
            if f in isolated_failures and f not in actual_sorted:
                marks.append("ISOLATED-ONLY(順序依存)")
            elif f in isolated_failures:
                marks.append("bulk+isolated")
            else:
                marks.append("bulk")
            print(f"  - {f}  [{', '.join(marks)}]")
        if isolation_skipped:
            print(f"  (実行できなかった回帰ファイル: {len(isolation_skipped)})")
            for f in isolation_skipped:
                print(f"    ? {f}")
        return 0

    if not BASELINE.exists():
        print(
            f"FAIL: ベースライン {BASELINE} が存在しない。"
            "先に `--update` で作成すること",
            file=sys.stderr,
        )
        return 1

    recorded = set(json.loads(BASELINE.read_text(encoding="utf-8"))["tier1_failing_files"])
    # sorted() は list を返すため、引き算の外側に置くと
    # `list - set` で TypeError になる（ゲート自体が死ぬ）。
    new_failures = sorted((set(actual) | isolated_failures) - recorded)
    fixed = sorted(recorded - actual)

    print(f"Tier1 failing files: actual={len(actual)} baseline={len(recorded)}")

    if new_failures:
        print(
            "FAIL: Tier1 に新たな失敗ファイルが "
            f"{len(new_failures)} 件発生しました（= 新しい回帰）:",
            file=sys.stderr,
        )
        for f in new_failures:
            print(f"  + {f}", file=sys.stderr)
        print(
            "\n既存失敗を baseラインに足すのは自己申告であり防御ではありません。"
            "該当ファイルを直してから `--update` してください。",
            file=sys.stderr,
        )
        return 1

    if fixed:
        # 改善を検出したら自動でベースラインを下げる（ratchet の本旨）
        BASELINE.write_text(
            json.dumps(
                {
                    "tier1_failing_files": actual_sorted,
                    "note": json.loads(BASELINE.read_text(encoding="utf-8")).get("note", ""),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"GOOD: {len(fixed)} 件減少。ベースラインを下げた。")
        for f in fixed:
            print(f"  - {f}")

    print("OK: Tier1 に新たな失敗はありません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
