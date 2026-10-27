"""静的解析ゲート: 未定義名 (ruff F821) が src/ に存在しないことを保証する。

なぜこのテストが必要か
----------------------
`src/backend/routers/episodes.py` の `upsert_chapter()` は
`_verify_branch_belongs_to_book(...)` という未定義名を参照していた
（import 実名は `verify_branch_belongs_to_book`、行10）。

このバグは **モジュールの import は成功する**（未定義名の参照が関数 본体内にあるため）
ため、既存のテストスイートも CI も検出できなかった。実行された場合に限り
`NameError` → HTTP 500 となる「本番で壊れる API」であった。

なお「`_` 接頭辞付きの呼び出し」を正規表現で機械的に弾く方針は採用しない。
`src/backend/routers/collab.py:35` の `_verify_book_access` のように
同一モジュール内で正当に定義されているPEP8 準拠のプライベート関数があり、
誤検出になる。
ruff F821 はモジュールスコープとローカルスコープを正しく解決するため、
本件のゲートとしてはこちらが適切。
"""
from __future__ import annotations

import subprocess
import sys

import pytest


def _run_ruff(select: str) -> tuple[int, str]:
    """ruff をサブプロセスで実行し、(終了コード, 出力) を返す。

    in-process で呼ぶと設定・キャッシュがホスト pytest と混ざるため、
    プロセス境界で隔離する。
    """
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "--select", select, "--quiet"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=".",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


@pytest.mark.integration
class TestNoUndefinedNames:
    """src/ に未定義名 (F821) が 0 件であること。"""

    def test_ruff_reports_no_f821(self) -> None:
        """F821 が 1 件でもあれば出ささない。"""
        code, out = _run_ruff("F821")
        assert code == 0, f"src/ に未定義名が検出されました:\n{out}"


@pytest.mark.integration
class TestChapterRouterGuardsResolve:
    """チャ保存系エンドポイントが参照するガード関数が実際に解決できること。

    `upsert_chapter` のバグは「import 時には検出できない」ため、
    関数本体の参照がモジュール名前空間で解決することを直接確認する。
    """

    def test_episodes_module_exposes_branch_guard(self) -> None:
        import src.backend.routers.episodes as m

        assert hasattr(m, "verify_branch_belongs_to_book"), (
            "episodes.py が参照する verify_branch_belongs_to_book が"
            "モジュール名前空間に存在しない"
        )

    def test_upsert_chapter_body_has_no_private_guard_alias(self) -> None:
        """`upsert_chapter` の本体に `_verify_*` 形式の呼び出しが残っていないこと。

        同名関数を `_` 付きで呼ぶ typo は import 成功をすり抜ける既知の障害なので、
        該当エンドポイントに限定して直接検査する。
        """
        import inspect

        from src.backend.routers.episodes import upsert_chapter

        body = inspect.getsource(upsert_chapter)
        assert "_verify_branch_belongs_to_book" not in body, (
            "upsert_chapter が未定義名 `_verify_branch_belongs_to_book` を"
            "参照しています（実行時に NameError）"
        )
        assert "verify_branch_belongs_to_book" in body, (
            "upsert_chapter がブランチ所有権ガードを呼んでいません"
        )
