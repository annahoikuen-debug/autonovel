"""伏線設置工作计划 (v5.3 長編耐性)。

伏線を設置するたびに「どの scope で」「何話目に回収するか」を
ビートシートから機械的に決定する。

v5.2 までは `promotion_service` が `ep_num <= 5 → short_term else long_term`
という経験則で scope を決め、`target_episode` は常に NULL のままだった。
NULL のままだと `ForeshadowingService.check_and_resolve` の
`is_contracted` が常に True となり、回収判定のアンサンブルスコアが
機能しなくなっていた（伏線の「契約」が実体化していない状態）。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config.commercial_beat_sheet import COMMERCIAL_40EP_BEATS
from src.models.foreshadowing_status import ForeshadowingScope

#: 短期伏線とみなす最大 Concrete 話数（この範囲内に回収スロットがあれば短期扱い）
SHORT_TERM_HORIZON = 3

#: 全体の既定話数（40話商業ビートシートの上限）
DEFAULT_TOTAL_EPISODES = 40

#: 長期伏線を吸着させる節目の順序（W5 Step 4）。
#: `_spread_target` の線形補間ではなく「物語の節目」を回収先にする。
LONG_TERM_ANCHOR_ORDER = ("midpoint", "climax")


def _use_short_horizon(use_short_term_horizon: bool | None) -> bool:
    """短期ホライズン丸めの有効判定（`None` = フラグ `FORESHADOW_SHORT_HORIZON`）。"""
    if use_short_term_horizon is None:
        from src.services.foreshadowing.flags import is_short_horizon_enabled

        return is_short_horizon_enabled()
    return bool(use_short_term_horizon)


def _use_anchor_snap(anchor_snap: bool | None) -> bool:
    """アンカー吸着の有効判定（`None` = フラグ `FORESHADOW_ANCHOR_SNAP`）。"""
    if anchor_snap is None:
        from src.services.foreshadowing.flags import is_anchor_snap_enabled

        return is_anchor_snap_enabled()
    return bool(anchor_snap)


@dataclass(frozen=True)
class ForeshadowingPlan:
    """伏線1本についての設置計画"""

    scope: ForeshadowingScope
    target_episode: int
    horizon: int  # target_episode - planted_episode

    @property
    def is_short_term(self) -> bool:
        return self.scope is ForeshadowingScope.SHORT_TERM


def _is_payoff_beat(beat: dict) -> bool:
    """そのビートが「回収を受け持つ」ビートかを判定する。

    `ForeshadowingRescheduler.find_next_suitable_episode` と同じ
    「foreshadowing_directive に『回収』を含むか」という基準を使うことで、
    設置計画と延期ロジックの判定基準を一致させる。
    """
    return "回収" in str(beat.get("foreshadowing_directive", ""))


def _payoff_slots(scope: ForeshadowingScope | None = None) -> list[dict]:
    """回収ビートを範囲順に返す。

    Args:
        scope: 指定時はその scope の回収を担当するビートのみ返す
    """
    beats = [b for b in COMMERCIAL_40EP_BEATS if _is_payoff_beat(b)]
    if scope is None:
        return sorted(beats, key=lambda b: b["range"][0])
    value = scope.value
    return sorted(
        (b for b in beats if value in (b.get("target_scopes") or [])),
        key=lambda b: b["range"][0],
    )


def _next_payoff_beat(planted_episode: int) -> tuple[dict, dict] | None:
    """設置話と対応する回収ビートと、その直前の回収ビートを返す。

    規則:
      - 設置話そのものを含む回収ビートがあれば、それを優先する
        （クライマックス中に撒いた伏線は同じクライマックスで回収されるべきで、
         クライマックス後に回収される/story_delay は構造的な破綻になる）
      - そうでなければ「設置話より後に始まる最初の回収ビート」を使う
      - 設置が回収区間幅を超える場合は巡回させ、同時回収数を分散する
    """
    beats = _payoff_slots()

    for idx, beat in enumerate(beats):
        start_ep, end_ep = beat["range"]
        # 設置話が区間末尾なら同ビート内では回収できない（horizon 0 は不可）
        if start_ep <= planted_episode < end_ep:
            prev = beats[idx - 1] if idx > 0 else {"range": (1, 3)}
            return beat, prev

    for idx, beat in enumerate(beats):
        if beat["range"][0] > planted_episode:
            prev = beats[idx - 1] if idx > 0 else {"range": (1, 3)}
            return beat, prev
    return None


def _spread_target(planted_episode: int, payoff: dict, prev: dict) -> int:
    """回収区間の中に回収先を一様分散させる。

    「設置が早い伏線 → 回収区間の前半」「設置が遅い伏線 → 後半」に
    線形マッピングすることで、同じビート内で回収が分散し、
    1話あたり複数本の回収Dumpによるプロンプト過負荷を防ぐ。

    設置話数が回収区間の幅を上回る場合（クライマックス区間に
    多数の伏線が集積するケース）は、巡回的に割り当てることで
    「1話あたり最大 ⌈設置話数 / 区間幅⌉ 本」に収める。
    """
    start_ep, end_ep = payoff["range"]
    width = end_ep - start_ep
    if width <= 0:
        return start_ep

    prev_start, prev_end = prev["range"]

    # 設置話そのものが回収区間内にある場合は、その直後を回収先にする
    # （設置话より前の回収は不可能 = ステートマシンの不変条件）
    if start_ep <= planted_episode < end_ep:
        return planted_episode + 1

    span = max(prev_end - prev_start, 1)
    if span > width:
        return start_ep + ((planted_episode - prev_start) % width)

    frac = (planted_episode - prev_start) / span
    frac = min(max(frac, 0.0), 1.0)
    return start_ep + round(frac * width)


def plan_foreshadowing(
    planted_episode: int,
    total_episodes: int | None = DEFAULT_TOTAL_EPISODES,
    use_short_term_horizon: bool | None = None,
    anchor: str | None = None,
    anchor_snap: bool | None = None,
) -> ForeshadowingPlan:
    """設置話から scope と回収予定話を決定する。

    決定ルール:
      1. 設置話より後に来る最初の「回収ビート」（directive に『回収』を含む
         ビート）を探す。`ForeshadowingRescheduler` と同じ判定基準を使う。
      2. そのビートが long_term を担当する場合は長期伏線、
         short_term を担当する場合は短期伏線とする。
      3.     回収先を回収区間の中に「設置位置に応じて線形分散」させ、
         全てが1話に集中しないようにする。
      4. 回収ビートが残っていない終盤は「設置 + 3話」をフォールバックとする。

    Args:
        planted_episode: 伏線を設置する話数（1-indexed）
        total_episodes: 作品全体の予定話数（None = 上限なしとして扱う）
        use_short_term_horizon: 短期ホライズンで丸めるか（`None` = フラグ既定OFF）
        anchor: アンカー名（明示指定用。既定 `None`。挙動は変えない）
        anchor_snap: 長期伏線を物語の節目へ吸着させるか（`None` = フラグ既定OFF）

    Returns:
        ForeshadowingPlan（scope / target_episode / horizon）

    Note:
        設置話が作品最終話を超える場合、回収先は作品内に存在しない。
        その場合は `planted_episode + 1`（= 作品外）を返し、
        `get_overdue` / KPI 側で「期限超過」として可視化される。

        ただし **horizon 0（回収先 == 設置話）は決して返さない**。
        `promotion_service` は最終プロット行で `total == planted` を渡すため、
        回収ビートによるクランプを Composites ると 39/39 件で horizon 0 になっていた。
    """
    # total_episodes が None（= 作品全体の話数が未知）のときは、
    # 作品枠によるクランプを実質無効にする。
    total = max(total_episodes, planted_episode) if total_episodes is not None else planted_episode

    located = _next_payoff_beat(planted_episode)
    if located is None:
        # 全回収スロットを使い切った＝長編の終盤。残りを有効活用する。
        scope = ForeshadowingScope.SHORT_TERM
        target = min(planted_episode + 3, total)
    else:
        payoff, prev = located
        is_long_term = any(
            b["range"] == payoff["range"] for b in _payoff_slots(ForeshadowingScope.LONG_TERM)
        )
        scope = ForeshadowingScope.LONG_TERM if is_long_term else ForeshadowingScope.SHORT_TERM
        target = min(_spread_target(planted_episode, payoff, prev), total)

    # 不変条件ガード: 回収先は必ず設置話より後（horizon >= 1）。
    # 作品最終話に撒いた場合など、クランプで horizon 0 になる経路を全て潰す。
    if target <= planted_episode:
        target = planted_episode + 1

    # ── W5 Step 3: 短期ホライズン（planted + SHORT_TERM_HORIZON 以内に丸める）──
    # 不変条件ガードの **後** に適用する（guard を壊さないため）。
    if _use_short_horizon(use_short_term_horizon):
        cap = min(planted_episode + SHORT_TERM_HORIZON, total)
        if target > cap:
            target = max(cap, planted_episode + 1)

    # ── W5 Step 4: アンカー吸着（長期伏線のみ）──
    # 線形補間の値より **前倒しはしない**（=`max`）。行き過ぎの回避が目的。
    if _use_anchor_snap(anchor_snap) and scope is ForeshadowingScope.LONG_TERM:
        from src.services.foreshadowing.anchors import anchor_episode

        snap = min(anchor_episode(a) for a in LONG_TERM_ANCHOR_ORDER)
        if snap > planted_episode:
            target = max(target, min(snap, total))
        if target <= planted_episode:
            target = planted_episode + 1

    return ForeshadowingPlan(
        scope=scope,
        target_episode=target,
        horizon=target - planted_episode,
    )


def plan_foreshadowings(
    planted_episodes: list[int],
    total_episodes: int | None = DEFAULT_TOTAL_EPISODES,
) -> list[ForeshadowingPlan]:
    """複数話分の設置計画をまとめて生成する。"""
    return [plan_foreshadowing(ep, total_episodes) for ep in planted_episodes]
