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

import subprocess
import sys

import pytest


def _collect_tests() -> subprocess.CompletedProcess[str]:
    """テストスイートを collection する。

    `--continue-on-collection-errors` を**あえて付ける**。
    これが無いと 1 件のエラーで全体が中断し、
    「何件エラーか」を知ることすらできない。
    """
    return subprocess.run(
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
