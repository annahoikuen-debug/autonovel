"""Tier1 ratchet (`scripts/ci_tier_ratchet.py`) の動作保証テスト。

なぜテストが ratchet を起動しないのか
------------------------------------
2026-10-03 の初回実装では、本テストが Tier1 全体を `subprocess` で
起動する作りにしていた。しかし Tier1 には本テスト自身が含まれるため、
内側の pytest がさらに本テストを起動し、**プロセスが再帰的に
爆発した**（同一秒に 8 プロセス増加の実測）。

したがって設計を次のとおり変更した:

- ratchet は **pytest から呼ばず、CI から直接実行**する
  （既存の `scripts/ci_lint_ratchet.py` と同じ方式）
- 本テストは「Tier1 を実行する」のではなく、
  **ratchet の判定ロジックとベースライン構造を単体で検証する**だけに留める

これで「ゲートがゲートを再帰起動する」という構造 자체がnails をCoordination 消える。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RATCHET_PATH = Path("scripts/ci_tier_ratchet.py")
BASELINE_PATH = Path("reports/qa_tier_baseline.json")


def _load_ratchet():
    """`scripts/ci_tier_ratchet.py` をモジュールとして読み込む。"""
    spec = importlib.util.spec_from_file_location("ci_tier_ratchet", RATCHET_PATH)
    assert spec and spec.loader, f"{RATCHET_PATH} を読み込めなかった"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFailingFileParsing:
    """pytest 出力の FAILED/ERROR 行のパース。"""

    @pytest.fixture(scope="class")
    def ratchet(self):
        return _load_ratchet()

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("FAILED tests/unit/api/test_x.py::test_a - AssertionError: 1", "tests/unit/api/test_x.py"),
            ("ERROR tests/services/foo.py - TypeError: boom", "tests/services/foo.py"),
            ("ERROR tests/integration/bar.py::Fixture - TypeError", "tests/integration/bar.py"),
            ("FAILED tests/x.py - short form", "tests/x.py"),
            ("  FAILED tests/spaced.py::t - indented", "tests/spaced.py"),
            ("PASSED tests/ok.py::t - fine", None),
            ("tests/no_prefix.py::t - just output", None),
        ],
    )
    def test_parse_one_line(self, ratchet, line: str, expected: str | None) -> None:
        got = ratchet.parse_failing_files(line)
        assert got == ({expected} if expected else set()), f"{line!r} のパース結果: {got}"

    def test_error_message_is_not_part_of_the_key(self, ratchet) -> None:
        """collection エ러ーのメッセージ文言が変わってもキーは不変であること。

        メッセージ込みでキー化すると、ベースラインが
        「文言が変わっただけ」で stale 判定され、XFAIL ノイズになる。
        """
        a = ratchet.parse_failing_files("ERROR tests/a.py - TypeError: boom")
        b = ratchet.parse_failing_files("ERROR tests/a.py - ValueError: 別の原因")
        assert a == b == {"tests/a.py"}

    def test_backslash_paths_are_normalized(self, ratchet) -> None:
        out = "FAILED tests\\unit\\api\\test_x.py::t - e"
        assert ratchet.parse_failing_files(out) == {"tests/unit/api/test_x.py"}

    @pytest.mark.parametrize(
        ("stdout", "expected"),
        [
            # 正常終了
            ("....F..\n6 failed, 3 passed in 0.27s", True),
            (".....\n100 passed in 1.2s", True),
            ("no tests ran in 0.01s", True),
            # 途中中断（サマリ行なし）= 結果を得られていない
            ("", False),
            ("tests/unit/foo.py::test_a ....F", False),
            ("Interrupted: 1 error during collection", False),
        ],
    )
    def test_summary_line_detects_incomplete_run(
        self, ratchet, stdout: str, expected: bool
    ) -> None:
        """実行の中断と「失敗ゼロ」を区別できること。

        実行が中断されると pytest はサマリ行を出さないため、
        失敗ファイル集合が空になる。空を「全部 pass」と読むと
        ベースラインが誤って書き換えられ、ゲートが無意味になる。
        """
        assert ratchet._has_summary_line(stdout) is expected


class TestBaselineStructure:
    """ベースラインファイルの構造。"""

    def test_baseline_exists(self) -> None:
        assert BASELINE_PATH.exists(), (
            f"{BASELINE_PATH} が無い。先に `python scripts/ci_tier_ratchet.py --update` を実行すること"
        )

    def test_baseline_has_expected_schema(self) -> None:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        assert "tier1_failing_files" in data
        assert isinstance(data["tier1_failing_files"], list)
        for entry in data["tier1_failing_files"]:
            assert isinstance(entry, str), f"エントリが文字列でない: {entry!r}"
            assert entry.startswith("tests/"), f"Tier1 以外が混在: {entry}"
            assert " - " not in entry, f"メッセージが混入している: {entry}"

    def test_baseline_is_sorted_and_unique(self) -> None:
        files = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["tier1_failing_files"]
        assert files == sorted(files), "ベースラインがソートされていない"
        assert len(files) == len(set(files)), "ベースラインに重複がある"

    def test_no_tier3_paths_in_baseline(self) -> None:
        """Tier3（環境依存）が Tier1 ベースラインに混ざっていないこと。"""
        files = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["tier1_failing_files"]
        tier3 = ("tests/integration", "tests/perf", "tests/e2e", "tests/load")
        offenders = [f for f in files if f.startswith(tier3)]
        assert not offenders, f"Tier3 が Tier1 ベースラインに混在: {offenders}"


class TestTierDefinition:
    """Tier 定義自体の整合性。"""

    @pytest.fixture(scope="class")
    def ratchet(self):
        return _load_ratchet()

    def test_tier1_paths_exist(self, ratchet) -> None:
        missing = [p for p in ratchet.TIER1_PATHS if not Path(p).exists()]
        assert not missing, f"Tier1 に指定されたパスが存在しない: {missing}"

    def test_tier1_is_not_empty(self, ratchet) -> None:
        assert len(ratchet.TIER1_PATHS) >= 3

    def test_ratchet_does_not_exclude_itself(self, ratchet) -> None:
        """Tier1 に tests/regression が含まれること。

        ここが漏れると、回帰ゲート自身の失敗（collection 健全性、
        F821、静的ゲート）が捕捉されなくなる。ratchet が自己申告に見える状態を避ける。
        """
        assert "tests/regression" in ratchet.TIER1_PATHS, (
            "Tier1 から tests/regression が漏れていると、"
            "回帰ゲート自身の失敗が捕捉されなくなる"
        )
