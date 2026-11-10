"""PLAN_S1 N1（CLI import 修正）の回帰テスト。

壊れ方: src/cli/main.py が再び存在しないモジュール
（``src.narrative_balancer.dsp_balancer`` 等）を import する /
委譲先の引数名（dsp/grammar=--input、csp=--state）のマッピングを間違える → 赤。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.cli.main import build_parser, main as cli_main


def _make_beat(ep: int, tension: float = 5.0) -> dict:
    return {
        "episode": ep,
        "tension": tension,
        "beat_type": "SETUP",
        "title": f"Ep{ep}",
        "summary": "",
        "characters": ["Protagonist"],
        "is_defeat": False,
        "foreshadowing_setup": [],
        "foreshadowing_payoff": [],
    }


class TestDelegationTargetsExist:
    """委譲先の 3 パッケージ CLI と実在クラスの契約。"""

    def test_package_cli_imports_resolve(self):
        """N1 が委譲する 3 つの CLI モジュール main が import できること。"""
        from src.narrative_balancer.csp.cli import main as csp_main
        from src.narrative_balancer.dsp.cli import main as dsp_main
        from src.narrative_balancer.grammar.cli import main as grammar_main

        assert callable(dsp_main)
        assert callable(csp_main)
        assert callable(grammar_main)

    def test_no_ghost_module_imports_in_cli(self):
        """src/cli/main.py 内に実在しないモジュール名が残っていないこと。"""
        source = Path("src/cli/main.py").read_text(encoding="utf-8")
        assert "dsp_balancer" not in source
        assert "csp_balancer" not in source
        assert "grammar_balancer" not in source
        assert "DspBalancer" not in source
        assert "CspBalancer" not in source
        assert "GrammarBalancer" not in source


CFG_4 = (
    "n_episodes: 4\nmidpoint_episode: 2\nmidpoint_min_tension: 6\n"
    "all_is_lost_episode: 30\nall_is_lost_max_tension: 4\n"
    "climax_episode: 4\nclimax_min_tension: 6\n"
    "min_defeats: 0\nmax_defeats: 4\nmax_payoff_distance: 3\n"
    "weights:\n  smoothness: 1\n  char_balance: 1\n  quarter_target: 1\n"
    "solver:\n  max_time_seconds: 3.0\n  num_search_workers: 2\n"
)


class TestBalanceCommandWiring:
    """統一 CLI ``balance`` サブコマンドの動作。"""

    def test_balance_help_starts_without_import_error(self):
        """``balance --help`` が ImportError なしで起動すること（subprocess）。"""
        result = subprocess.run(
            [sys.executable, "-m", "src.cli.main", "balance", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert "dsp" in result.stdout

    def test_input_and_output_args_are_required(self, capsys):
        """--input/--output が required であること（N1 の契約）。"""
        with pytest.raises(SystemExit):
            build_parser().parse_args(["balance", "--type", "dsp"])
        capsys.readouterr()

    @pytest.mark.parametrize(
        ("balancer_type", "use_config"),
        [("dsp", False), ("csp", True), ("grammar", False)],
    )
    def test_cmd_balance_delegates_to_package_cli(
        self, balancer_type: str, use_config: bool, tmp_path: Path
    ):
        """3 種すべての balancer が beats JSON を入力として動作すること。

        壊れ方: csp への --state マッピング漏れ・dsp/grammar への
        --input マッピング漏れ・--config パススルー漏れがあると、このテストが赤になる。
        csp はデフォルト config（40 話前提）では 4 話が実行不可能なため、
        既存 CLI テスト（test_csp_cli.py CFG_4）と同じ 4 話用 config を渡す。
        """
        input_path = tmp_path / "beats.json"
        output_path = tmp_path / "balanced.json"
        input_path.write_text(
            json.dumps([_make_beat(ep, tension=5.0) for ep in range(1, 5)], ensure_ascii=False),
            encoding="utf-8",
        )

        argv = ["balance", "--type", balancer_type, "--input", str(input_path), "--output", str(output_path)]
        if use_config:
            config_path = tmp_path / "csp.yaml"
            config_path.write_text(CFG_4, encoding="utf-8")
            argv += ["--config", str(config_path)]

        rc = cli_main(argv)

        assert rc == 0, f"balance --type {balancer_type} failed"
        assert output_path.exists()

    def test_cmd_balance_unknown_type_returns_1(self, tmp_path: Path, capsys):
        """未知の --type で exit 1 すること。"""
        input_path = tmp_path / "beats.json"
        input_path.write_text("[]", encoding="utf-8")
        args = build_parser().parse_args(
            ["balance", "--input", str(input_path), "--output", str(tmp_path / "out.json")]
        )
        args.type = "unknown"  # choices は build_parser で検証済みのため直接代入して分岐を検証
        from src.cli.main import cmd_balance

        rc = cmd_balance(args)
        assert rc == 1
        capsys.readouterr()
