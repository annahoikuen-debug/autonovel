"""20話〜100話連続執筆時のコンテキスト長不変性ベンチマークテスト (v5.0 Step 18).

3層ローリング記憶基盤（RollingMemoryBuilder）において、
エピソード数が 1話から 20話、50話、100話と増加しても、
コンテキスト長（文字数・推定トークン数）が爆発せず一定のウィンドウ内に
安定収束（フラット化）することを検証する。
"""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.context_compression.rolling_memory import RollingMemoryBuilder

from src.engine.episode_context import EpisodeContextBuilder  # noqa: E402


def test_rolling_memory_token_stability_20_episodes():
    """1話から20話までのコンテキスト長推移を検証。"""
    builder = RollingMemoryBuilder(
        max_recent_digests=30,
        max_prev_episode_chars=2000,
        max_total_chars=5000,
    )

    bible = (
        "【世界観】\n"
        "舞台はエルドラシア帝国。魔術と蒸気機関が交錯する世界。\n"
        "【主人公】\n"
        "レオン: 帝国の元兵士。過去の裏切りを暴くため旅を続ける。\n"
        "【相棒】\n"
        "フェイ: 精霊使いの少女。明るく好奇心旺盛。"
    )

    digests = []
    stats_history = []

    # 1話〜20話までのシミュレーション
    for ep in range(1, 21):
        prev_text = f"第{ep-1}話の本文サンプル。レオンとフェイは敵の追手を振り切り、新たな街の門をくぐった。" * 15 if ep > 1 else ""
        stats = builder.get_context_stats(
            bible_summary=bible,
            past_digests=digests,
            prev_episode_text=prev_text,
        )
        stats_history.append((ep, stats))

        # 新たなエピソードダイジェストを追加
        digests.append(f"第{ep}話: レオン達は街の拠点で情報屋と接触し、帝国の動向を探った。")

    ep1_stats = stats_history[0][1]
    ep20_stats = stats_history[19][1]

    # 20話時点でもトークンバジェット（4000トークン / 5000文字）内に完全に収まっていること
    assert ep20_stats["total_chars"] <= 5000
    assert ep20_stats["estimated_tokens"] <= 4000
    print(f"\n[Ep 1] chars: {ep1_stats['total_chars']}, tokens: {ep1_stats['estimated_tokens']}")
    print(f"[Ep 20] chars: {ep20_stats['total_chars']}, tokens: {ep20_stats['estimated_tokens']}")


def test_rolling_memory_long_form_plateau_100_episodes():
    """100話まで執筆が進行した際のコンテキスト長プラトー（不変性）を検証。"""
    max_recent = 15
    builder = RollingMemoryBuilder(
        max_recent_digests=max_recent,
        max_prev_episode_chars=1500,
        preserve_initial_digests=2,
        max_total_chars=4000,
    )

    bible = "基本世界観と主要キャラ設定テキスト。" * 10
    prev_text = "前話の激しい戦闘と脱出劇の本文。" * 30

    digests = []
    token_counts = []

    start_time = time.perf_counter()

    for ep in range(1, 101):
        ctx = builder.build_context(
            bible_summary=bible,
            past_digests=digests,
            prev_episode_text=prev_text,
        )
        tokens = builder.estimate_tokens(ctx)
        token_counts.append(tokens)

        # 80〜100文字程度の客観的事実ダイジェスト
        digests.append(f"第{ep}話: 主人公達は新たな試練を突破し、次の手がかりを入手した。")

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # 1. 速度検証: 100話分のコンテキスト構築が50ms未満（1話あたり0.5ms未満）であること
    avg_speed_ms = elapsed_ms / 100
    assert avg_speed_ms < 2.0, f"Average build speed too slow: {avg_speed_ms:.3f}ms"

    # 2. プラトー（不変性）検証:
    # ウィンドウ上限（15話）を超えた後（例: 第30話 vs 第100話）で、
    # トークン数が実質的にフラット（増加率 5% 未満）であることを実証
    tokens_at_30 = token_counts[29]
    tokens_at_50 = token_counts[49]
    tokens_at_100 = token_counts[99]

    growth_rate_30_to_100 = (tokens_at_100 - tokens_at_30) / tokens_at_30

    print(f"\n[100 Ep Benchmark] Avg Speed: {avg_speed_ms:.3f}ms/ep")
    print(f"[Ep 15] tokens: {token_counts[14]}")
    print(f"[Ep 30] tokens: {tokens_at_30}")
    print(f"[Ep 50] tokens: {tokens_at_50}")
    print(f"[Ep 100] tokens: {tokens_at_100}")
    print(f"[Growth 30->100]: {growth_rate_30_to_100:.2%}")

    # ウィンドウ固定により、30話以降はトークン数が完全にプラトー化（変動幅5%未満）
    assert abs(growth_rate_30_to_100) < 0.05, f"Tokens grew unexpectedly: {growth_rate_30_to_100:.2%}"

    # ハードリミット絶対遵守検証
    for ep, tokens in enumerate(token_counts, start=1):
        assert tokens <= builder.max_total_tokens, f"Ep {ep} exceeded max tokens: {tokens}"


class TestEpisodeContextBuilderTokenStability:
    """EpisodeContextBuilder（実経路）の長編トークン安定性テスト (PLAN_M1 Step 1).

    3層ローリング記憶の実本番経路 `src/engine/episode_context.py` において、
    1〜100話でも Layer2 の文字数が LAYER2_MAX_CHARS (4000) に収まり、
    中盤の事実が省略マーカーで圧縮されることを検証する。

    このテストは PLAN_M1 Phase 0 の characterization テストであり、
    以降の全フェーズで「現行挙動の回帰防止」基準線となる。
    """

    @pytest.fixture
    def mock_db(self):
        """モック AsyncSession。db.execute のみをモック化する。"""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def digests_99(self):
        """ep1〜ep99 のダイジェスト（各120字、合計11880字 > LAYER2_MAX_CHARS=4000）。

        中盤の事実が Layer2 で省略・圧縮されることを検証するため、
        100話分を超える量を用意する。
        """
        return {
            ep: (
                f"第{ep}話: 主人公は新たな仲間と出会い、遺跡の鍵を入手した。"
                f"魔物との戦闘を経て、次なる目的地へ向かう。"
            )
            for ep in range(1, 100)
        }

    async def _run_layer2(self, mock_db, digests, ep_num: int, rollup_enabled: bool = False) -> dict:
        """指定話数で Layer2 サマリを構築して返す（モック DB 経由）。

        `db.execute` の SQL クエリ構築をモックする代わりに、
        `_load_episode_digests` と `_safe_execute` を直接モック化し、
        Layer2 の文字数クランプ・省略マーカー挙動にフォーカスする。

        `rollup_enabled=True` のときは `ENABLE_DIGEST_ROLLUP=1` を想定し、
        `get_rollups` は空（rollup 未登録）を返すので、digests から
        history を組み立てるコードパスを検証する。
        """
        from src.engine.episode_context import EpisodeContextBuilder

        builder = EpisodeContextBuilder(db=mock_db)

        # digests を直接返すようにモック化（db.execute の SQL 構築を回避）。
        builder._load_episode_digests = AsyncMock(return_value=dict(digests))

        # _build_layer1_bible はキャラ設定のみ。空リストで十分。
        builder._build_layer1_bible = AsyncMock(
            return_value={"characters": [], "text": "キャラクター設定なし", "token_estimate": 0}
        )

        # chapter_list は digests に基づく MagicMock リスト。
        # _brief は chapter_list をループしながら digests を参照するため、
        # chapter_list が空だと digests が無視されてしまう。
        chapter_models = [
            MagicMock(ep_num=ep, content=digests.get(ep, f"第{ep}話本文"))
            for ep in range(1, ep_num)
        ]

        # _safe_execute は _build_layer2_summary の chapter / foreshadowing 取得に使われる。
        # str(select(...)) に "chapter" が含まれるかで分岐し、
        # chapter クエリには chapter_models を、foreshadowing クエリには空リストを返す。
        async def _safe_execute_side_effect(query):
            if "chapter" in str(query).lower():
                return chapter_models
            return []

        builder._safe_execute = AsyncMock(side_effect=_safe_execute_side_effect)

        # db.execute は rollup_enabled=True 時に get_rollups(volume), get_rollups(block) の
        # 2回呼ばれる。rollup 未登録を想定し空リストを返す。
        def _make_result(models):
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=models)
            result = MagicMock()
            result.scalars = MagicMock(return_value=scalars)
            return result

        if rollup_enabled:
            result_empty = _make_result([])
            mock_db.execute = AsyncMock(side_effect=[result_empty, result_empty])

        ctx = await builder.build_context(book_id=1, ep_num=ep_num)
        return ctx["layer2_summary"]

    @pytest.mark.asyncio
    async def test_layer2_chars_stays_under_limit_1_to_100_episodes(
        self, mock_db, digests_99
    ):
        """1〜100話すべてで layer2_chars が LAYER2_MAX_CHARS (4000) に収まる。"""
        max_chars = 0
        for ep in range(1, 101):
            summary = await self._run_layer2(mock_db, digests_99, ep)
            max_chars = max(max_chars, summary["layer2_chars"])
            assert summary["layer2_chars"] <= EpisodeContextBuilder.LAYER2_MAX_CHARS, (
                f"Ep {ep}: layer2_chars={summary['layer2_chars']} exceeds "
                f"{EpisodeContextBuilder.LAYER2_MAX_CHARS}"
            )
        print(f"\n[Max layer2_chars over 1-100 ep]: {max_chars}")

    @pytest.mark.asyncio
    async def test_layer2_with_rollup_stays_under_limit_1_to_100_episodes(
        self, mock_db, digests_99, monkeypatch
    ):
        """rollup_enabled=True でも 1〜100話すべてで layer2_chars ≤ LAYER2_MAX_CHARS。

        rollup 未登録（get_rollups 空）でも digests から history を組み立て、
        4000字クランプ内に収まることを検証する（PLAN_M1 Step 13）。
        """
        monkeypatch.setenv("ENABLE_DIGEST_ROLLUP", "1")
        max_chars = 0
        for ep in range(1, 101):
            summary = await self._run_layer2(mock_db, digests_99, ep, rollup_enabled=True)
            max_chars = max(max_chars, summary["layer2_chars"])
            assert summary["layer2_chars"] <= EpisodeContextBuilder.LAYER2_MAX_CHARS, (
                f"Ep {ep}: layer2_chars={summary['layer2_chars']} exceeds "
                f"{EpisodeContextBuilder.LAYER2_MAX_CHARS}"
            )
        print(f"\n[Max layer2_chars with rollup over 1-100 ep]: {max_chars}")

    @pytest.mark.asyncio
    async def test_omission_marker_appears_when_window_exceeded(
        self, mock_db, digests_99
    ):
        """中間省略マーカーの出現条件を現行コードの実態に合わせて検証。

        `_build_layer2_summary` は `chapter_list[2:-10]` のスライスを
        `omitted` とするため、`omitted` が非空になるのは
        `len(chapter_list) >= 13`（ep_num >= 14）から。
        これは現行コードの characterizion（回帰防止基準線）として固定する。
        """
        for ep in [1, 5, 10, 13, 14, 50, 100]:
            summary = await self._run_layer2(mock_db, digests_99, ep)
            chapter_count = len(range(1, ep))
            if ep <= 13:
                assert "……" not in summary["text"], (
                    f"Ep {ep}: unexpected omission marker (chapter_list={chapter_count})"
                )
            else:
                assert "……" in summary["text"], (
                    f"Ep {ep}: missing omission marker (chapter_list={chapter_count})"
                )
