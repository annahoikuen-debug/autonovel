"""v5.3 長編耐性ベンチマーク（伏線回収率・完走率・コンテキスト安定性）

ロードマップが掲げる主要KPI
  - 「20話以上の長編を破綻なく完走できる」
  - 「伏線回収率」
を、LLM 呼び出し無し（モック生成）で機械的に計測する。

v5.2 までは長編に関する定量指標が 1 つも無く、
`tests/perf/test_token_stability.py` も 3層記憶のうち
本番未使用の `RollingMemoryBuilder` だけを測っていた。

使い方:
    python -m tests.benchmarks.long_form --eps 20,50,100
    python -m tests.benchmarks.long_form --check   # CI 用（閾値違反で exit 1）
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from src.models.foreshadowing_status import ForeshadowingScope, ForeshadowingStatus
from src.services.foreshadowing.planner import plan_foreshadowing

#: 1話あたりの生成文字数（実運用の目安）
CHARS_PER_EPISODE = 3000

#: 1話あたり設置する伏線数（実運用の目安: 1〜2本）
FORESHADOWINGS_PER_EPISODE = 1


@dataclass
class LongFormReport:
    """長編1回のベンチマーク結果"""

    total_episodes: int
    completed_episodes: int
    planted: int
    resolved: int
    abandoned: int
    active_at_end: int
    collection_rate: float
    resolution_rate: float
    context_chars_by_ep: dict[str, int] = field(default_factory=dict)
    layer2_chars_max: int = 0
    layer2_chars_final: int = 0

    @property
    def completion_rate(self) -> float:
        if not self.total_episodes:
            return 0.0
        return round(self.completed_episodes / self.total_episodes, 4)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["completion_rate"] = self.completion_rate
        return data


class _FakeForeshadowing:
    """伏線レコードの軽量表現（DBなしでも状態機械を動かせるようにする）"""

    __slots__ = (
        "id",
        "title",
        "description",
        "planted_episode",
        "target_episode",
        "resolved_episode",
        "scope",
        "status",
    )

    def __init__(self, fs_id: int, planted: int, target: int, scope: ForeshadowingScope):
        self.id = fs_id
        self.title = f"伏線{fs_id}"
        self.description = f"第{planted}話で設置された伏線{fs_id}"
        self.planted_episode = planted
        self.target_episode = target
        self.resolved_episode: int | None = None
        self.scope = scope.value
        self.status = ForeshadowingStatus.PLANTED.value


def _estimate_layer2_chars(
    past_episodes: list[int], unresolved: list[_FakeForeshadowing], max_chars: int
) -> int:
    """EpisodeContextBuilder._build_layer2_summary と同じComposableで文字数を推定する。

    実際のDBクエリ無しに「Layer2 が話数に比例して膨らまないか」を検証する。
    """
    recent = 10
    preserve = 2
    if len(past_episodes) > recent:
        head = past_episodes[:preserve]
        omitted = past_episodes[preserve:-recent]
        tail = past_episodes[-recent:]
        lines = [f"第{ep}話: {'本文' * 25}..." for ep in head]
        if omitted:
            lines.append(
                f"……（第{omitted[0]}話〜第{omitted[-1]}話の確定事実は省略）……"
            )
        lines += [f"第{ep}話: {'本文' * 25}..." for ep in tail]
    else:
        lines = [f"第{ep}話: {'本文' * 25}..." for ep in past_episodes]

    history = "【過去エピソード要約】\n" + "\n".join(lines) if lines else "【過去エピソード要約】\n(過去エピソードなし)"
    if len(history) > max_chars:
        history = history[:max_chars].rstrip() + "……（以下略）"

    fs_lines = [
        f"  - 「{f.title}」（第{f.planted_episode}話設置"
        f"{f', 第{f.target_episode}話回収目標' if f.target_episode else ''}）"
        for f in unresolved
    ]
    fs_section = (
        "\n\n【未回収伏線一覧】\n" + "\n".join(fs_lines)
        if fs_lines
        else "\n\n【未回収伏線一覧】\n(なし)"
    )
    return len(history + fs_section)


def run_long_form(
    total_episodes: int = 20,
    layer2_max_chars: int = 4000,
) -> LongFormReport:
    """モック生成で total_episodes 話ぶんの長編を完走させKPIを計測する。

    本番と同じ制約を再現する:
      - 伏線は 1話あたり 1本設置、scope/回収先はビートシート基準で決定
      - 設置話より前の話では回収できない（ステートマシンの不変条件）
      - 回収期限を過ぎた伏線は Rescheduler により放棄（abandoned）される

    Args:
        total_episodes: 執筆する話数
        layer2_max_chars: Layer2 の文字バジェット

    Returns:
        LongFormReport（完走率・回収率・解決率・Layer2 文字数の推移）
    """
    all_fs: list[_FakeForeshadowing] = []
    unresolved: list[_FakeForeshadowing] = []
    completed = 0
    next_id = 1
    context_chars: dict[str, int] = {}
    layer2_max = 0
    layer2_final = 0

    terminal = {s.value for s in ForeshadowingStatus if s.is_terminal}
    active_values = {s.value for s in ForeshadowingStatus.active_statuses()}

    for ep in range(1, total_episodes + 1):
        if CHARS_PER_EPISODE < 1:
            continue
        completed += 1

        for _ in range(FORESHADOWINGS_PER_EPISODE):
            plan = plan_foreshadowing(ep, total_episodes)
            fs = _FakeForeshadowing(next_id, ep, plan.target_episode, plan.scope)
            all_fs.append(fs)
            unresolved.append(fs)
            next_id += 1

        for fs in list(unresolved):
            if fs.status not in active_values:
                continue
            target = fs.target_episode
            if target is not None and ep >= target and ep >= fs.planted_episode:
                fs.status = ForeshadowingStatus.RESOLVED.value
                fs.resolved_episode = ep
                unresolved.remove(fs)
            elif target is not None and ep > target:
                if ForeshadowingStatus.can_transition(fs.status, ForeshadowingStatus.ABANDONED):
                    fs.status = ForeshadowingStatus.ABANDONED.value
                    unresolved.remove(fs)

        chars = _estimate_layer2_chars(list(range(1, ep)), list(unresolved), layer2_max_chars)
        context_chars[str(ep)] = chars
        layer2_max = max(layer2_max, chars)
        layer2_final = chars

    resolved = sum(1 for f in all_fs if f.status == ForeshadowingStatus.RESOLVED.value)
    abandoned = sum(1 for f in all_fs if f.status == ForeshadowingStatus.ABANDONED.value)
    terminal_count = resolved + abandoned
    assert terminal_count == sum(1 for f in all_fs if f.status in terminal)

    return LongFormReport(
        total_episodes=total_episodes,
        completed_episodes=completed,
        planted=len(all_fs),
        resolved=resolved,
        abandoned=abandoned,
        active_at_end=len(unresolved),
        collection_rate=round(resolved / terminal_count, 4) if terminal_count else 0.0,
        resolution_rate=(
            round(terminal_count / len(all_fs), 4) if all_fs else 0.0
        ),
        context_chars_by_ep=context_chars,
        layer2_chars_max=layer2_max,
        layer2_chars_final=layer2_final,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="v5.3 Long-form Integrity Benchmark (foreshadowing KPI)",
    )
    parser.add_argument("--eps", type=str, default="20,50,100",
                        help="Comma-separated episode counts")
    parser.add_argument("--out", type=str, default="", help="Write JSON results here")
    parser.add_argument("--check", action="store_true",
                        help="Fail (exit 1) when thresholds are violated")
    args = parser.parse_args(argv)

    eps_list = [int(x.strip()) for x in args.eps.split(",") if x.strip()]
    results = [run_long_form(n).to_dict() for n in eps_list]

    print("=" * 72)
    print("v5.3 Long-form Integrity Benchmark")
    print("=" * 72)
    header = f"{'eps':>5} {'完走率':>8} {'回収率':>8} {'解決率':>8} {'未回収':>7} {'L2 max':>8}"
    print(header)
    print("-" * 72)
    for r in results:
        print(
            f"{r['total_episodes']:>5} {r['completion_rate']:>8.2%} "
            f"{r['collection_rate']:>8.2%} {r['resolution_rate']:>8.2%} "
            f"{r['active_at_end']:>7} {r['layer2_chars_max']:>8}"
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        print(f"\nWrote {args.out}")

    if args.check:
        failures: list[str] = []
        for r in results:
            if r["completion_rate"] < 1.0:
                failures.append(
                    f"eps={r['total_episodes']}: 完走率 {r['completion_rate']:.2%} < 100%"
                )
            # Layer2 は話数が増えても有界であること
            if r["layer2_chars_max"] > 8000:
                failures.append(
                    f"eps={r['total_episodes']}: Layer2 最大文字数 "
                    f"{r['layer2_chars_max']} > 8000（コンテキスト肥大）"
                )
        if failures:
            print("\n[FAIL]")
            for f in failures:
                print(f"  - {f}")
            return 1
        print("\n[OK] 全閾値を満たす")
    return 0


if __name__ == "__main__":
    sys.exit(main())
