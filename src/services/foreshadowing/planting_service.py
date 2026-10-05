"""伏線自動設置エンジン (roadmap -> foreshadowings)。

伏線の「回収側（payoff）」は完成していたが「設置側（planting）」は空洞だった。
`DbForeshadowingRepository.add()` の呼び出し元が `src/` 全体で 0 件、
つまり「回収対象となる行」自体が作られていなかった。

本モジュールは `Bible.settings.full_story_roadmap` の各行
(`RoadmapItem.foreshadowing_setup`) から伏線を設置する唯一の入口にする。

設計上の要点:
    1. **既定で何もしない**（`planting_enabled=False`）。
       ロールバック可能性＝フラグを OFF にするだけで完全に元に戻せる。
    2. **冪等**。DB に同じ `(planted_episode, title)` が既にあればスキップする。
       `INSERT OR IGNORE` ではなくアプリ側判定にして、
       なぜスキップしたかがログとして残るようにする。
    3. **必ず `repo.add()` / `repo.add_many()` を通す**。
       raw `insert()` を使うと設置 KPI（`foreshadowing_planted_total`）が脱落する。
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from src.backend.database.models_foreshadowing import ForeshadowingModel
from src.services.foreshadowing.flags import is_foreshadowing_planting_enabled
from src.services.foreshadowing.planner import plan_foreshadowing

logger = logging.getLogger(__name__)

#: `foreshadowing_setup` がこの値なら「この話では伏線を撒かない」を意味する。
NO_SETUP = "なし"

#: `title` に使う長さの上限（DB は String(100)）。
MAX_TITLE_LEN = 100

#: 説明文に載せる roadmap 側のフィールドの上限。
MAX_DESCRIPTION_LEN = 2000


def _get(item: Any, name: str, default: Any = None) -> Any:
    """roadmap 行から値を安全に読む（属性 / dict / pydantic を吸収する）。"""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _is_no_setup(setup: Any) -> bool:
    """「この話では伏線を撒かない」判定。"""
    if setup is None:
        return True
    text = str(setup).strip()
    if not text:
        return True
    return text == NO_SETUP


def _derive_title(setup: str, planted_episode: int) -> str:
    """`foreshadowing_setup` から伏線タイトルを作る。

    roadmap の setup は自由記述で長さも一定でないため、
    1行目に切り詰めて `String(100)` に収める。
    """
    first_line = next((line.strip() for line in setup.splitlines() if line.strip()), setup.strip())
    title = first_line
    if len(title) > MAX_TITLE_LEN:
        title = title[:MAX_TITLE_LEN].rstrip()
    if not title:
        title = f"第{planted_episode}話の伏線"
    return title


def _derive_description(item: Any) -> str:
    """`description` を roadmap の setup / payoff から組み立てる。"""
    setup = str(_get(item, "foreshadowing_setup", "") or "").strip()
    payoff = str(_get(item, "foreshadowing_payoff", "") or "").strip()
    parts = [setup]
    if payoff and payoff != NO_SETUP:
        parts.append(f"回収予定: {payoff}")
    text = "\n".join(parts)
    if len(text) > MAX_DESCRIPTION_LEN:
        text = text[:MAX_DESCRIPTION_LEN].rstrip()
    return text


def _planted_episode(item: Any, fallback: int) -> int:
    """設置話数を roadmap 行から取り出す（1-indexed）。"""
    raw = _get(item, "ep_num")
    if raw is None:
        raw = _get(item, "episode_num")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _keywords_for(item: Any) -> list[str]:
    """その伏線の検索手がかり語を作る。

    roadmap 側の `foreshadowing_setup` / `one_line_summary` を、
    空白・句読点で割った小片をキーワードにする。
    専用カラム（`keywords` / `foreshadowing_keywords`）があればそちらを優先する。
    """
    for field in ("keywords", "foreshadowing_keywords"):
        raw = _get(item, field)
        if raw:
            if isinstance(raw, str):
                parts = [p.strip() for p in raw.split("\n")]
            else:
                parts = [str(p).strip() for p in raw]
            return [p for p in parts if p]
    seeds = [
        str(_get(item, "foreshadowing_setup", "") or ""),
        str(_get(item, "one_line_summary", "") or ""),
    ]
    tokens: list[str] = []
    for seed in seeds:
        for chunk in seed.replace("、", " ").replace("。", " ").replace("，", " ").split():
            cleaned = chunk.strip("「」『』\"'()（）【】[]")
            if cleaned and cleaned not in tokens:
                tokens.append(cleaned)
    return tokens


async def plant_from_roadmap(
    repo,
    book_id: int,
    roadmap_items: Optional[Iterable[Any]],
    total_episodes: int,
    *,
    planting_enabled: bool = True,
) -> list[ForeshadowingModel]:
    """ロードマップから伏線を設置する（冪等）。

    Args:
        repo: `DbForeshadowingRepository`（`add` / `add_many` / `get_by_book_id` を持つ）
        book_id: 対象作品ID
        roadmap_items: `Bible.settings.full_story_roadmap` の行（`RoadmapItem` / dict 可）
        total_episodes: 作品全体の予定話数（`plan_foreshadowing` にそのまま渡す）
        planting_enabled: フラグ。**False なら何もせず空リストを返す**
            （＝DB への副作用ゼロ。ロールバックの担保）。

    Returns:
        今回 **新規に** 設置した `ForeshadowingModel` のリスト。
        既に設置済みでスキップしたものは含まない。

    Note:
        冪等キーは `(planted_episode, title)`。同一ロードマップを再実行しても
        行は増えない。roadmap 側が伏線の書き換えで setup の文言を変えた場合だけ
        「別の伏線」として扱われ、追加される（意図的に別物として扱う）。

        `repo.add()` と同じく **commit しない**（`flush()` まで）。
        呼び出し側が `await repo.commit()` を明示すること。
    """
    if not planting_enabled:
        logger.debug(
            "foreshadowing planting disabled (flag=%s); skipping book_id=%s",
            planting_enabled,
            book_id,
        )
        return []

    if not roadmap_items:
        return []

    # 冪等判定用の既存キー。DB 側判定にして、スキップ理由がログに残るようにする。
    existing = {
        (row.planted_episode, row.title)
        for row in await repo.get_by_book_id(book_id)
    }

    pending: list[dict] = []
    seen_in_batch: set = set()
    skipped_no_setup = 0
    skipped_duplicate = 0

    for index, item in enumerate(roadmap_items):
        planted_episode = _planted_episode(item, fallback=index + 1)
        setup = _get(item, "foreshadowing_setup")
        if _is_no_setup(setup):
            skipped_no_setup += 1
            continue

        setup_text = str(setup).strip()
        title = _derive_title(setup_text, planted_episode)
        key = (planted_episode, title)
        if key in existing or key in seen_in_batch:
            skipped_duplicate += 1
            logger.info(
                "Skip already-planted foreshadowing: book_id=%s planted_ep=%s title=%r",
                book_id,
                planted_episode,
                title,
            )
            continue
        seen_in_batch.add(key)

        plan = plan_foreshadowing(planted_episode, total_episodes)
        pending.append(
            {
                "book_id": book_id,
                "title": title,
                "description": _derive_description(item),
                "planted_episode": planted_episode,
                "target_episode": plan.target_episode,
                "scope": plan.scope,
                "keywords": _keywords_for(item),
            }
        )

    if not pending:
        logger.info(
            "foreshadowing planting produced no new rows: book_id=%s "
            "(no_setup=%s duplicate=%s)",
            book_id,
            skipped_no_setup,
            skipped_duplicate,
        )
        return []

    planted = await repo.add_many(pending)
    logger.info(
        "Planted %s foreshadowing(s): book_id=%s (no_setup=%s duplicate=%s)",
        len(planted),
        book_id,
        skipped_no_setup,
        skipped_duplicate,
    )
    return planted


def is_planting_enabled() -> bool:
    """`FORESHADOW_PLANTING` フラグの読み取り（統合担当が使う入口）。"""
    return is_foreshadowing_planting_enabled()
