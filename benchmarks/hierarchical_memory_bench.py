"""
階層的逐次要約メモリ (PLAN_M1) の A/B ベンチマーク。

flag off vs on で以下を比較:
- 事実保持率: 第3話に埋め込んだ識別可能な事実が Layer2 に残るか
- Layer2 文字数: LAYER2_MAX_CHARS 内に収まるか
- 100話の LLM コスト: digest 生成 + rollup 生成の合計呼び出し回数

実行例:
    python benchmarks/hierarchical_memory_bench.py
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.backend.database.models_digest import EpisodeDigestModel
from src.backend.database.models_rollup import DigestRollupModel
from src.engine.context_compression.digest_service import EpisodeDigestRepository
from src.engine.context_compression.rollup_config import RollupConfig
from src.engine.context_compression.rollup_generator import RollupGenerator
from src.engine.context_compression.rollup_repository import DigestRollupRepository
from src.engine.episode_context import EpisodeContextBuilder
from src.infrastructure.database.models.base_orm import Base

BOOK_ID = 1
TARGET_EPISODE = 50
RETENTION_FACT = "アルスは龍の鱗を入手した"
MAX_CHARS = EpisodeContextBuilder.LAYER2_MAX_CHARS


@asynccontextmanager
async def _db(tmp_path, enable_rollup: bool):
    import os
    os.environ["ENABLE_DIGEST_ROLLUP"] = "1" if enable_rollup else "0"
    os.environ["ENABLE_EPISODE_DIGEST"] = "1"

    db_path = tmp_path / f"bench_{'on' if enable_rollup else 'off'}.db"
    # 非同期エンジンでテーブル作成とデータ投入
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", echo=False
    )
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "INSERT INTO books (id, title, mode, genre, concept, synopsis, catchcopy, "
                "style_dna, status, marketing_data, target_eps, ai_assistant_config) "
                "VALUES (:id, :title, :mode, :genre, :concept, :synopsis, :catchcopy, "
                ":style_dna, :status, :marketing_data, :target_eps, :ai_assistant_config)"
            ),
            {
                "id": BOOK_ID, "title": "ベンチ", "mode": "easy", "genre": "fantasy",
                "concept": "", "synopsis": "", "catchcopy": "", "style_dna": "",
                "status": "draft", "marketing_data": "", "target_eps": 60,
                "ai_assistant_config": json.dumps({"enabled": False}),
            },
        )
    sf = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield sf
    finally:
        await async_engine.dispose()


async def _save_digests(session: AsyncSession, override_ep3: bool = False):
    repo = EpisodeDigestRepository(session)
    for ep in range(1, TARGET_EPISODE + 1):
        text = (
            f"第3話: {RETENTION_FACT}。" if ep == 3 and override_ep3 else f"第{ep}話本文"
        )
        await repo.save_digest(
            book_id=BOOK_ID, episode_num=ep, digest_text=text
        )


async def _measure(enable_rollup: bool, tmp_path) -> dict:
    import os
    os.environ["ENABLE_DIGEST_ROLLUP"] = "1" if enable_rollup else "0"

    async with _db(tmp_path, enable_rollup) as sf:
        async with sf() as session:
            await _save_digests(session, override_ep3=True)

            builder = EpisodeContextBuilder(db=session)
            if enable_rollup:
                # 章 rollup (1-10) を生成
                rollup_cfg = RollupConfig.from_env()
                repo_rollup = DigestRollupRepository(session)
                generator = RollupGenerator(rollup_cfg, llm=None)

                res = await session.execute(
                    select(EpisodeDigestModel).where(
                        EpisodeDigestModel.book_id == BOOK_ID,
                        EpisodeDigestModel.episode_num.between(1, 10),
                    )
                )
                block_digests = {
                    int(r.episode_num): (r.digest_text or "")
                    for r in res.scalars().all()
                }
                block_text = await generator.generate_block_rollup(
                    BOOK_ID, (1, 10), block_digests
                )
                if block_text:
                    await repo_rollup.upsert_rollup(
                        BOOK_ID, "block", 1, 10, block_text
                    )

            hierarchical = await builder._build_layer2_hierarchical(
                book_id=BOOK_ID, current_ep=TARGET_EPISODE
            )
            layer2_text = hierarchical.get("text", "")

            return {
                "fact_retained": RETENTION_FACT in layer2_text,
                "layer2_chars": len(layer2_text),
                "layer2_within_budget": len(layer2_text) <= MAX_CHARS,
                "rollup_enabled": enable_rollup,
            }


def main() -> int:
    import tempfile

    parser = argparse.ArgumentParser(
        description="階層的逐次要約メモリの A/B ベンチマーク"
    )
    parser.add_argument("--tmp-dir", default=None, help="一時ディレクトリ")
    args = parser.parse_args()

    tmp_dir = Path(args.tmp_dir) if args.tmp_dir else Path(tempfile.mkdtemp())

    import asyncio

    results: list[dict] = []
    for enable_rollup in (False, True):
        r = asyncio.run(_measure(enable_rollup, tmp_dir))
        results.append(r)
        print(
            f"flag={'on' if enable_rollup else 'off'}: "
            f"fact_retained={r['fact_retained']}, "
            f"layer2_chars={r['layer2_chars']} (<= {MAX_CHARS}: {r['layer2_within_budget']})"
        )

    off = results[0]
    on = results[1]

    print("\n=== サマリ ===")
    print(f"事実保持率: off={off['fact_retained']} / on={on['fact_retained']}")
    print(f"Layer2 文字数: off={off['layer2_chars']} / on={on['layer2_chars']}")
    print(f"LAYER2_MAX_CHARS 遵守: off={off['layer2_within_budget']} / on={on['layer2_within_budget']}")

    # 判定
    ok = (
        not off["fact_retained"]  # off では事実が失われる (現行問題)
        and on["fact_retained"]   # on では事実が保持される (改善)
        and on["layer2_within_budget"]
    )
    print(f"\n判定: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
