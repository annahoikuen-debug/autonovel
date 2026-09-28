"""Foreshadowing rescheduler for postponing unfulfilled foreshadowing resolution."""

import logging
from typing import Optional

from src.config.commercial_beat_sheet import get_beat_for_episode
from src.infrastructure.repositories.foreshadowing_repo import DbForeshadowingRepository

logger = logging.getLogger(__name__)


class ForeshadowingRescheduler:
    """Automatically reschedules unresolved foreshadowings to subsequent suitable beats."""

    #: `max_episode` 未指定時の走査上限（40话固定は長編で延期を殺すため廃止）。
    #: ビートシートは 40话超でも最後のビートを返すので、この幅なら十分。
    UNBOUNDED_SCAN_LIMIT = 200

    @classmethod
    def find_next_suitable_episode(
        cls, current_episode: int, max_episode: int | None = None
    ) -> Optional[int]:
        """回収に適した次の話数を探索する。

        Args:
            current_episode: 現在の話数
            max_episode: 作品全体の予定話数（None = 上限なし）

        Returns:
            次の回収予定話数。延期が不可能な場合は None（＝回収期限切れ確定）。
        """
        scan_end = (
            current_episode + cls.UNBOUNDED_SCAN_LIMIT
            if max_episode is None
            else max_episode
        )
        for ep in range(current_episode + 1, scan_end + 1):
            beat = get_beat_for_episode(ep)
            if beat:
                # Check if beat directive mentions resolution/recovery
                fs_dir = beat.get("foreshadowing_directive", "") if isinstance(beat, dict) else getattr(beat, "foreshadowing_directive", "")
                if "回収" in str(fs_dir):
                    return ep

        # 回収ビートが残っていない場合のフォールバック: 2話先へ延ばす。
        # 旧実装は min(current+2, max) を返しており、max が近いと
        # 「現在話以下（＝延期ではない）」を返して成功を偽装していた。
        candidate = current_episode + 2
        if max_episode is not None and candidate > max_episode:
            logger.info(
                "Foreshadowing postponement impossible: cur_ep=%s max_ep=%s",
                current_episode,
                max_episode,
            )
            return None
        return candidate

    @classmethod
    async def reschedule_foreshadowing(
        cls,
        foreshadowing_id: int,
        current_episode: int,
        repo: DbForeshadowingRepository,
        max_episode: int | None = None,
    ) -> Optional[int]:
        """
        Reschedule a foreshadowing item to a future episode in the repository.

        Args:
            foreshadowing_id: ID of the foreshadowing
            current_episode: Current episode
            repo: Foreshadowing repository
            max_episode: Maximum episode bound（None = 上限なし）

        Returns:
            New target episode, or None if failed / postponement impossible
        """
        new_target = cls.find_next_suitable_episode(current_episode, max_episode)
        if new_target is None:
            # 延期できないなら「延期成功」をログしてはいけない（KPI の水増しになる）
            logger.info(
                "延期不能・回収期限切れ確定: foreshadowing id=%s (ep=%s / 上限=%s)",
                foreshadowing_id,
                current_episode,
                max_episode,
            )
            return None
        try:
            updater = getattr(repo, "update_target_episode", None)
            if updater is None:
                # v5.2 まで: DbForeshadowingRepository に本メソッドが無く、
                # hasattr ガードでサイレント no-op になりつつ成功ログだけが
                # 出力されていた。v5.3 で実 API を追加した。
                logger.warning(
                    "Reschedule skipped: repository %s has no update_target_episode",
                    type(repo).__name__,
                )
                return None
            updated = await updater(foreshadowing_id, new_target)
            if not updated:
                logger.warning(
                    f"Reschedule rejected for foreshadowing id={foreshadowing_id} "
                    f"(ep={current_episode} -> target_ep={new_target})"
                )
                return None
            logger.info(
                f"Rescheduled foreshadowing id={foreshadowing_id} from ep={current_episode} to target_ep={new_target}"
            )
            return new_target
        except Exception as e:
            logger.warning(f"Failed to reschedule foreshadowing id={foreshadowing_id}: {e}")
            return None
