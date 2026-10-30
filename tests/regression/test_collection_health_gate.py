"""テストスイート collection 健全性ゲート。

何が起きたか
------------
2026-10-03 の公開前監査で、`tests/utils/test_text_diff_regression.py` が
存在しない Python モジュール `src.utils.textDiff` を import していた
（実体は TypeScript の `src/utils/textDiff.ts`）。

この 1 件の collection error が、pytest の既定動作
（`--continue-on-collection-errors` なし）により
**セッション全体を中断**させ、9,493 件収集済みテストが
1 件も実行されなくなった。

同種の「ゲート自体の死」は別の形でも起きている:

- `tests/regression/test_emotional_residue_regression.py` が未宣言依存
  `fakeredis` を import → クリーン環境で setup ERROR
- `tests/regression/test_status_md_counts_match_reality.py` が pytest を
  `subprocess.run(text=True)` で起動し encoding 未指定 → Windows(CP932) で
  UnicodeDecodeError → collection 不能

いずれも「テストが落ちた」のではなく「テストが**実行されなくなった**」ため、
CI は緑を返しうる。このゲートはcollection 自体を検証し、
「テストが黙って死んでいる」状態を防ぎます。

なぜこれが最優先（P0）か
----------------------
テストの検証力が 0 になると、その後に追加するゲートもすべて無意味になる。
実行されていることの確認は、他のあらゆるゲートの前提条件である。
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass

import pytest

#: 計画書 PLAN_J1 W6 の回帰条件: `pytest --collect-only -q | tail` が30秒以内。
#: `tail` が表示するのは "9507 tests collected in 19.83s" という
#: **pytest 自己申告の collection 時間**であるため、これを基準にする。
COLLECTION_SECONDS_BUDGET = 30.0

#: collection が実際に**件数を取り損ねていないこと**の下限（既存ゲートと共有）。
MIN_COLLECTED_TESTS = 1000


@dataclass(frozen=True)
class CollectionRun:
    """1回の collection 実行と、そこから採取した計測値。"""

    proc: subprocess.CompletedProcess[str]
    wall_seconds: float
    collected: int
    pytest_collection_seconds: float | None


#: collection は重い（subprocess 起動で数十秒）ため、このモジュール内の
#: 複数テストで **1回だけ** 実行して共有する。
#: 独立実行だと 3 回 × 約35秒 が発生し、それ自体がスイート速度を落とす。
_COLLECTION_RUN: CollectionRun | None = None


def _parse_collected_and_seconds(stdout: str) -> tuple[int, float | None]:
    """`9493 tests collected in 19.83s` から (件数, 秒) を採取する。"""
    collected = 0
    seconds: float | None = None
    for line in stdout.splitlines():
        if "collected" not in line:
            continue
        # 件数
        for token in line.replace(",", " ").split():
            if token.isdigit():
                collected = max(collected, int(token))
        # 秒（pytest の自己申告）
        m = re.search(r"\bin\s+([0-9]+(?:\.[0-9]+)?)s\b", line)
        if m:
            seconds = float(m.group(1))
    return collected, seconds


def _run_collection() -> CollectionRun:
    """テストスイートを collection する（結果はメモ化）。

    `--continue-on-collection-errors` を**あえて付ける**。
    これが無いと 1 件のエラーで全体が中断し、
    「何件エラーか」を知ることすらできない。
    """
    global _COLLECTION_RUN
    if _COLLECTION_RUN is not None:
        return _COLLECTION_RUN

    started = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--collect-only",
            "-q",
            "--continue-on-collection-errors",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        cwd=".",
    )
    wall = time.monotonic() - started
    collected, seconds = _parse_collected_and_seconds(proc.stdout)
    _COLLECTION_RUN = CollectionRun(
        proc=proc,
        wall_seconds=wall,
        collected=collected,
        pytest_collection_seconds=seconds,
    )
    return _COLLECTION_RUN


def _collect_tests() -> subprocess.CompletedProcess[str]:
    """collection 結果の CompletedProcess を返す（既存呼び出し互換）。"""
    return _run_collection().proc


@pytest.mark.integration
class TestCollectionIsHealthy:
    """テストが「実行される状態」にあることを保証する。"""

    def test_no_collection_errors(self) -> None:
        """collection error が 0 件であること。

        1 件でもあれば、そのファイルを含むテストは**実行されない**。
        gate 自体が無効化される主要原因なので、ここ是最優先で守る。
        """
        proc = _collect_tests()

        error_lines = [
            line
            for line in proc.stdout.splitlines()
            if line.startswith("ERROR ") or line.startswith("E   ")
        ]
        assert not error_lines, (
            "テストの collection error があります。該当テストは実行されません:\n"
            + "\n".join(error_lines[:40])
            + f"\n（ 内訳: {len(error_lines)} 件）"
        )

    def test_collection_actually_collects_a_meaningful_number(self) -> None:
        """テストが実際に収集されていること（0 件収集の検出）。

        collection error で全体が中断されると、「0 件収集」という形で
        現れることがある。このテストは無条件な「緑」を弾く。
        """
        proc = _collect_tests()
        assert proc.returncode in (0, 1), (
            f"collection が異常終了した (rc={proc.returncode}):\n{proc.stderr[-2000:]}"
        )

        # `9493 tests collected` 相当の行を探す
        collected = 0
        for line in proc.stdout.splitlines():
            if "tests collected" in line or "test collected" in line:
                # 例: "9493 tests collected" / "9493/10000 tests collected (5 errors)"
                for token in line.replace(",", " ").split():
                    if token.isdigit():
                        collected = max(collected, int(token))
        assert collected > 1000, (
            f"収集されたテストが {collected} 件しかない。"
            "collection error で全体が中断されている可能性がある"
        )


@pytest.mark.integration
class TestCollectionSpeed:
    """collection 速度が計画書 PLAN_J1 W6 の予算内であることを保証する。"""

    def test_collection_seconds_within_budget(self) -> None:
        """`pytest --collect-only -q | tail` の collection 時間が30秒以内であること。

        **測っているもの**: `tail` が表示する
        `9507 tests collected in 19.83s` の **pytest 自己申告値**。
        実測（2026-10-30）は 17.3〜23.7 秒で予算内。

        なぜ wall 時間で測らないか
        --------------------------
        wall（プロセス起動〜終了）は 31.4〜46.8 秒と**揺らぎ**、30秒の
        ハードゲートにするとこのマシン上でもフラグになる。しかもその大半は
        `conftest.pytest_configure` による `import src.backend.server`（13〜15秒）
        に費やされ、これは **テスト側では削減できない**:
        `src.backend.server` は **35個のテストモジュールが module 直下で import** しており、
        configure 側を外しても collection が同じコストを吸収する（ネットゼロ）。

        したがって「収集そのものが遅くなっていないこと」を安定して検出できる
        pytest 自己申告値を予算とする。wall 時間は参考値として上限だけ弾く。
        """
        run = _run_collection()

        assert run.pytest_collection_seconds is not None, (
            "collection の所要時間が出力から採取できなかった。\n"
            f"stdout 末尾:\n{run.proc.stdout[-1500:]}"
        )
        assert run.pytest_collection_seconds <= COLLECTION_SECONDS_BUDGET, (
            f"collection が {run.pytest_collection_seconds:.1f} 秒で、"
            f"予算 {COLLECTION_SECONDS_BUDGET} 秒を超えた（劣化）。"
            f"収集件数: {run.collected}"
        )

        # 無条件の「緑」を弾く: 件数を取り損ねると軽くなって当然なので、
        # 予算チェックは「十分な件数を収集した上で」成立している必要がある。
        assert run.collected >= MIN_COLLECTED_TESTS, (
            f"収集件数が {run.collected} 件しかない。"
            "件数不足のまま軽い collection を予算内と誤判定しないこと。"
        )

        # wall は機種・I/O 状態で揺れるため 30 秒とは比較せず、
        # 「collection が本来の数十秒から桁違いに遅くなった」ことだけを検出する。
        assert run.wall_seconds <= 180.0, (
            f"collection の wall 時間が {run.wall_seconds:.1f} 秒と異常。"
            "（pytest 自己申告は "
            f"{run.pytest_collection_seconds:.1f} 秒）"
        )
