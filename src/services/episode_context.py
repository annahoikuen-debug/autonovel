"""
src/services/episode_context.py — エピソードコンテキスト生成サービス

3層ローリング記憶 (Layer 1: バイブル, Layer 2: 100字要約, Layer 3: 直前生文) を構築する。
同期呼び出し（メモリ履歴）と非同期呼び出し（DBセッション連携）の両方に対応。
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database.models import Character as CharacterModel
from src.backend.database.models_foreshadowing import ForeshadowingModel

logger = logging.getLogger(__name__)


class EpisodeContextBuilder:
    """3層ローリング記憶ビルダー

    Layer 1（バイブル）: キャラクター・世界観設定（約1,000トークン）
    Layer 2（全話要約）: 過去全話の100文字事実要約＋未回収伏線一覧（累積しても数千トークン）
    Layer 3（直前文脈）: 直前1エピソードの生テキスト
    上記を合体させたプロンプトコンテキストを構築する。
    """

    def __init__(self, db: AsyncSession | None = None):
        """初期化"""
        self.db = db
        self._episode_history: list[dict[str, Any]] = []

    async def build_context(
        self,
        book_id: int,
        ep_num: int,
        target_word_count: int = 3000,
        previous_episode: dict[str, Any] | None = None,
        previous_episode_text: str | None = None,
    ) -> Any:
        """コンテキストをビルドする。

        v5.3 / Step 10: 常に coroutine を返す（`async def` に統一）。
        従来は `db is None` のとき dict を返す同期分岐があり、
        呼び出し側の `await` が `TypeError: 'dict' object can't be awaited`
        になっていた（M7）。
        """
        if self.db is None:
            return self._sync_build_context(
                book_id=book_id,
                ep_num=ep_num,
                target_word_count=target_word_count,
                previous_episode=previous_episode,
            )
        return await self._async_build_context(
            book_id=book_id,
            ep_num=ep_num,
            target_word_count=target_word_count,
            previous_episode_text=previous_episode_text,
        )

    def _sync_build_context(
        self,
        book_id: int,
        ep_num: int,
        target_word_count: int = 3000,
        previous_episode: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        is_first = ep_num == 1
        is_last = False

        context: dict[str, Any] = {
            "book_id": book_id,
            "ep_num": ep_num,
            "is_first": is_first,
            "is_last": is_last,
            "target_word_count": target_word_count,
        }

        if previous_episode is not None:
            prev = dict(previous_episode)
            if "title" not in prev:
                prev["title"] = f"第{ep_num - 1}話"
            if "key_events" not in prev:
                prev["key_events"] = []
            context["previous_episode"] = prev
        elif not is_first:
            last_summary = self._get_last_episode_summary()
            context["previous_episode"] = {
                "title": last_summary.get("title", ""),
                "ending": last_summary.get("ending", ""),
                "summary": last_summary.get("summary", ""),
                "key_events": last_summary.get("key_events", []),
            }

        self._add_to_history(ep_num, context)

        # v5.3 / Step 10: 3層コンテキストのキーを必ず返す。
        # 従来は Layer1/2/3 のキーが一切無く、`PromptComposer
        # ._format_three_layer_context` が無言で空文字を返していた。
        # DB 非接続時は「層情報を取得できない」ことを明示する。
        unavailable = {"text": "", "available": False}
        context.setdefault("layer1_bible", unavailable)
        context.setdefault("layer2_summary", unavailable)
        context.setdefault("layer3_previous", unavailable)
        context.setdefault("layer3_raw", "")
        return context

    async def _async_build_context(
        self,
        book_id: int,
        ep_num: int,
        target_word_count: int = 3000,
        previous_episode_text: str | None = None,
    ) -> dict[str, Any]:
        """3層コンテキストをビルド"""
        is_first = ep_num == 1
        is_last = False

        layer1_bible = await self._build_layer1_bible(book_id)
        layer2_summary = await self._build_layer2_summary(book_id, ep_num)
        layer3_raw = previous_episode_text or ""

        context = {
            "book_id": book_id,
            "ep_num": ep_num,
            "is_first": is_first,
            "is_last": is_last,
            "target_word_count": target_word_count,
            "layer1_bible": layer1_bible,
            "layer2_summary": layer2_summary,
            "layer3_raw": layer3_raw,
            # v5.3: プロンプト注入用の整形済みテキスト層。
            # v5.2 までは `three_layer_context` が組み立てられるだけで
            # PromptComposer まで届かず、3層記憶が実運用で未使用だった。
            "layer3_previous": {"text": layer3_raw},
            "previous_episode": {
                "summary": layer2_summary.get("last_episode_summary", "") if layer2_summary else "",
                "ending": layer3_raw[-500:] if layer3_raw else "",
            } if not is_first else {},
        }
        self._add_to_history(ep_num, context)
        return context

    def _add_to_history(self, ep_num: int, context: dict[str, Any]):
        """履歴に追加"""
        self._episode_history.append({"ep_num": ep_num, "context": context})
        if len(self._episode_history) > 10:
            self._episode_history = self._episode_history[-10:]

    def _get_last_episode_summary(self) -> dict[str, str]:
        """最後のエピソードの概要を取得"""
        if not self._episode_history:
            return {"title": "", "ending": "", "summary": ""}
        last = self._episode_history[-1]
        prev = last["context"].get("previous_episode", {})
        return {
            "title": prev.get("title", ""),
            "ending": prev.get("ending", ""),
            "summary": prev.get("summary", ""),
        }

    def get_history(self) -> list[dict[str, Any]]:
        """履歴を取得"""
        return self._episode_history.copy()

    def clear_history(self):
        """履歴をクリア"""
        self._episode_history = []

    def set_final_episode(self, ep_num: int):
        """最終話フラグを設定"""
        for item in self._episode_history:
            if item["ep_num"] == ep_num:
                item["context"]["is_last"] = True

    async def _safe_execute(self, query: Any) -> list[Any]:
        """安全にクエリを実行してエンティティリストを返す（AsyncSession, Sync, Mock両対応）"""
        import inspect
        if self.db is None or not hasattr(self.db, "execute"):
            return []
        try:
            res = self.db.execute(query)
            if inspect.isawaitable(res):
                res = await res
            if hasattr(res, "scalars"):
                scalars_res = res.scalars()
                if hasattr(scalars_res, "all"):
                    return list(scalars_res.all())
            return []
        except Exception:
            return []

    async def _build_layer1_bible(self, book_id: int) -> dict[str, Any]:
        """Layer 1: バイブル（キャラクター・世界観設定）を構築"""
        character_list = await self._safe_execute(
            select(CharacterModel).where(CharacterModel.book_id == book_id)
        )

        character_bible = []
        for char in character_list:
            character_bible.append(
                f"【{char.name}】\n"
                f"役割: {char.role or '不明'}\n"
                f"性格: {char.personality or '未設定'}\n"
                f"能力: {char.ability or '未設定'}\n"
            )

        bible_text = "\n".join(character_bible) if character_bible else "キャラクター設定なし"

        return {
            "characters": [
                {
                    "id": getattr(char, "id", None),
                    "name": getattr(char, "name", "不明"),
                    "role": getattr(char, "role", ""),
                    "personality": getattr(char, "personality", ""),
                    "ability": getattr(char, "ability", ""),
                }
                for char in character_list
            ],
            "text": bible_text,
            "token_estimate": len(bible_text) // 2,
        }

    # ── v5.3 長編耐性: Layer 2 のトークンバジェット制御 ─────────────

    #: 直近◯話は全文ダイジェスト（可読性優先）
    RECENT_FULL_DIGEST_EPISODES = 10

    #: これより古い話は省略マーカーで圧縮（最初◯話は設定の原点として保持）
    PRESERVE_INITIAL_EPISODES = 2

    #: Layer 2 に割り当てる最大文字数（3層合計バジェットの一部）
    LAYER2_MAX_CHARS = 4000

    #: 過去話要約と未回収伏線一覧の文字数配分（合計 = LAYER2_MAX_CHARS）
    HISTORY_BUDGET_RATIO = 0.5
    FORESHADOWING_BUDGET_RATIO = 0.5

    #: 未回収伏線セクションに無理に収める最大行数（超過分はサマリ1行に圧縮）
    MAX_FORESHADOWING_LINES = 12

    #: 1行あたりの文字数（伏線1行の描画を見積もるための係数）
    FORESHADOWING_LINE_CHARS = 60

    #: 過去話1行の見積もり文字数
    HISTORY_LINE_CHARS = 110

    # T6 Step 3: ここに `_resolve_session` の重複実装を置いていたが削除した。
    # 当初の目的（M8: 伏線側 `or repo.session` とダイジェスト側
    # `artifacts.get("session")` の食い違い解消）は
    # `src/agents/writing/episode_writer.py` のモジュールレベル
    # `_resolve_session(repo, session)` で**実際に達成済み**であり、
    # 伏線・ダイジェスト双方へ同じ解決結果を渡している。
    # かつ本クラスは `ctx` を一切受け取らず、
    # セッションは `__init__(session)` で注入される `self.db` であるため、
    # `ctx.artifacts` 前提のこの実装は構造上呼び出せなかった（死んだコード）。

    async def _load_episode_digests(self, book_id: int, current_ep: int) -> dict[int, str]:
        """`episode_digests` テーブルから `{ep_num: digest_text}` を取得する。

        Layer2 のデータ源はダイジェストが正（本文冒頭100字はフォールバック）。
        ダイジェストは Step 32 で本文から LLM 生成・永続化されるが、
        既存作品やダイジェスト無効化（ENABLE_EPISODE_DIGEST=0）では空になり得る。
        """
        if self.db is None:
            return {}
        try:
            from src.services.context_compression.digest_service import (
                EpisodeDigestRepository,
            )

            records = await EpisodeDigestRepository(self.db).get_digests(book_id)
        except Exception as e:
            logger.debug("Failed to load episode digests for book %s: %s", book_id, e)
            return {}
        return {
            int(r.episode_num): (r.digest_text or "")
            for r in records
            if getattr(r, "episode_num", None) is not None
            and int(r.episode_num) < current_ep
            and (r.digest_text or "").strip()
        }

    async def _build_layer2_summary(
        self, book_id: int, current_ep: int, max_chars: int | None = None
    ) -> dict[str, Any]:
        """Layer 2: 全話要約＋未回収伏線一覧を構築

        v5.3: 無制限に過去話全文（各100字）を積み上げていた仕様を
        トークンバジェット付きに変更。話数がどれだけ増えても文字数が一定に収まる。

        Args:
            book_id: 作品ID
            current_ep: 現在の話数
            max_chars: Layer 2 の最大文字数（既定は LAYER2_MAX_CHARS）
        """
        from src.backend.database.models import Chapter as ChapterModel

        budget = max_chars if max_chars is not None else self.LAYER2_MAX_CHARS
        history_budget = int(budget * self.HISTORY_BUDGET_RATIO)
        foreshadowing_budget = int(budget * self.FORESHADOWING_BUDGET_RATIO)

        chapter_list = await self._safe_execute(
            select(ChapterModel)
            .where(ChapterModel.book_id == book_id)
            .where(ChapterModel.ep_num < current_ep)
            .order_by(ChapterModel.ep_num)
        )

        # v5.3 / Step 32: データ源は `episode_digests`（話ごとに生成・永続化される
        # 100字の確定事実ダイジェスト）を優先し、未登録の話だけ本文冒頭へ
        # フォールバックする。従来は常に `Chapter.content[:100]` を読んでおり、
        # コメントが「Layer2 は episode_digests をデータ源とする」と述べていた
        # 実態と食い違っていた。
        digests = await self._load_episode_digests(book_id, current_ep)

        def _brief(ch: Any) -> str:
            ep_num = getattr(ch, "ep_num", None)
            if ep_num is not None:
                digest = digests.get(int(ep_num))
                if digest:
                    return digest.replace("\n", " ")
            content = getattr(ch, "content", None)
            return content[:100].replace("\n", " ") + "..." if content else "(本文未登録)"

        # 直近◯話は全文ダイジェスト、より古い話は省略マーカーで圧縮
        if len(chapter_list) > self.RECENT_FULL_DIGEST_EPISODES:
            head = chapter_list[: self.PRESERVE_INITIAL_EPISODES]
            omitted = chapter_list[self.PRESERVE_INITIAL_EPISODES : -self.RECENT_FULL_DIGEST_EPISODES]
            tail = chapter_list[-self.RECENT_FULL_DIGEST_EPISODES :]
            episode_summaries = [f"第{getattr(ch, 'ep_num', '?')}話: {_brief(ch)}" for ch in head]
            if omitted:
                first = getattr(omitted[0], "ep_num", "?")
                last = getattr(omitted[-1], "ep_num", "?")
                episode_summaries.append(
                    f"……（第{first}話〜第{last}話の確定事実は省略）……"
                )
            episode_summaries += [f"第{getattr(ch, 'ep_num', '?')}話: {_brief(ch)}" for ch in tail]
        else:
            episode_summaries = [
                f"第{getattr(ch, 'ep_num', '?')}話: {_brief(ch)}" for ch in chapter_list
            ]

        foreshadowing_list = await self._safe_execute(
            select(ForeshadowingModel)
            .where(ForeshadowingModel.book_id == book_id)
            .where(ForeshadowingModel.status.in_(["planted", "progressed"]))
            .order_by(ForeshadowingModel.planted_episode)
        )

        def _target_of(f: Any) -> int | None:
            target = getattr(f, "target_episode", None)
            return target if isinstance(target, int) else None

        def _fs_line(f: Any) -> str:
            overdue = (
                " ⚠期限超過"
                if _target_of(f) is not None and _target_of(f) < current_ep
                else ""
            )
            return (
                f"  - 「{f.title}」（第{f.planted_episode}話設置"
                f"{f', 第{f.target_episode}話回収目標' if f.target_episode else ''}"
                f"{overdue}）"
            )

        # v5.3 / Step 31: 未回収伏線セクションは「予算クランプの後」に連結していたため
        # 実測 21149 字 / 予算 4000 字という長編破綻を起こしていた。
        # ここでは (1) 予算を過去話要約と 50/50 に分ける、(2) 伏線側もクランプする、
        # (3) 期限超過の情報（長編破綻の最重要シグナル）を必ず残す。
        fs_header = "\n\n【未回収伏線一覧】\n"
        # 省略サマリ1行分を先に確保しておく（「期限超過M件」の Signals を失わないため）
        summary_reserve = 48
        available = max(0, foreshadowing_budget - len(fs_header) - summary_reserve)

        def _is_overdue(f: Any) -> bool:
            return _target_of(f) is not None and _target_of(f) < current_ep

        # 期限超過を最優先、残りは target_episode 昇順（回収期限が近い順）
        ordered = sorted(
            foreshadowing_list, key=lambda f: (0 if _is_overdue(f) else 1, _target_of(f) or 10**9)
        )
        total_overdue = sum(1 for f in foreshadowing_list if _is_overdue(f))

        kept: list[str] = []
        used = 0
        for f in ordered:
            line = _fs_line(f)
            cost = len(line) + 1
            if used + cost <= available:
                kept.append(line)
                used += cost
        omitted_count = len(ordered) - len(kept)
        omitted_overdue = total_overdue - sum(
            1 for f in ordered[: len(kept)] if _is_overdue(f)
        )

        fs_body = "\n".join(kept) if kept else "(なし)"
        if omitted_count:
            # 省略が発生したらサマリ行を必ず残す（期限超過本数の信号的情報を失わない）
            fs_body += f"\n……他{omitted_count}件の未回収伏線あり（うち期限超過{omitted_overdue}件）……"
        elif total_overdue:
            fs_body += f"\n※ うち期限超過の伏線が{total_overdue}件あります。"
        fs_section = fs_header + fs_body

        last_episode_summary = ""
        if chapter_list:
            last_ch = chapter_list[-1]
            last_episode_summary = last_ch.content[:200] if last_ch.content else ""

        history_section = (
            "【過去エピソード要約】\n" + "\n".join(episode_summaries)
            if episode_summaries
            else "【過去エピソード要約】\n(過去エピソードなし)"
        )
        if len(history_section) > history_budget:
            history_section = history_section[:history_budget].rstrip() + "……（以下略）"
        summary_text = history_section + fs_section

        return {
            "episode_summaries": episode_summaries,
            "unresolved_foreshadowings": [
                {
                    "id": f.id,
                    "title": f.title,
                    "planted_episode": f.planted_episode,
                    "target_episode": f.target_episode,
                    "status": f.status,
                }
                for f in foreshadowing_list
            ],
            "text": summary_text,
            "last_episode_summary": last_episode_summary,
            "token_estimate": len(summary_text) // 2,
            "layer2_chars": len(summary_text),
            "history_chars": len(history_section),
            "foreshadowing_chars": len(fs_section),
            "foreshadowing_omitted": omitted_count,
            "foreshadowing_overdue": sum(
                1
                for f in foreshadowing_list
                if _target_of(f) is not None and _target_of(f) < current_ep
            ),
        }
