import asyncio
import datetime
import json
import logging
import math
import os
import uuid
from typing import Any

from config import MODEL_EMBEDDING

logger = logging.getLogger(__name__)

#: バックグラウンドタスクの生存を保証するための強参照集合。
#: これを持たないと `asyncio.create_task` の戻り値は即座に参照カウントが減り、
#: 実行前に GC されてサイレントに消える (公式ドキュメントの既知の落とし穴)。
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn_background(coro: Any, name: str) -> asyncio.Task:
    """バックグラウンドタスクを起動し、例外をログに記録して強参照を保持する."""
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    def _handle_done(t: asyncio.Task) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background task %s failed", name)

    task.add_done_callback(_handle_done)
    return task


async def cancel_all_prefetch() -> int:
    """`_BACKGROUND_TASKS` に入っているタスクを全て取り消す（PLAN_W6 Step 6）。

    FastAPI の `lifespan` shutdown から呼ばれる。プロセス終了時に
    バックグラウンドタスクが中断されると RAG 検索中の DB 接続がリークするとくため、
    明示的に取り消す。返り値は実際に取り消した本数。例外は送出しない。
    """
    targets = [t for t in list(_BACKGROUND_TASKS) if not t.done()]
    for t in targets:
        t.cancel()
    if targets:
        await asyncio.gather(*targets, return_exceptions=True)
    _BACKGROUND_TASKS.clear()
    if targets:
        logger.info("[SEMANTIC CACHE] cancelled %d background task(s) on shutdown", len(targets))
    return len(targets)


async def close_background_tasks() -> int:
    """`cancel_all_prefetch` の別名（命名の一貫性用）。ロジックは増やさない。"""
    return await cancel_all_prefetch()


def is_draft_prefetch_enabled() -> bool:
    """次話の執筆プロンプトを投機生成する機能。既定 OFF（PLAN_W6 Step 4）。

    `prefetch_next` は **次話のプロンプト（本文未確定）を描画して** その embedding を温める。
    リテイクで必ず無駄になり、しかも L1 を温めないため検索ヒット率向上が実質ゼロ、
    embedding API コストだけが残る。よって既定で止める。
    静的ナレッジのウォームアップは `RagPrefetchService` 側が担当する。
    """
    return os.environ.get("ENABLE_SEMANTIC_PREFETCH_DRAFT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


import hashlib

try:
    from cachetools import LRUCache
except ImportError:
    from collections import OrderedDict

    class LRUCache(OrderedDict):  # type: ignore[no-redef]
        def __init__(self, maxsize: int = 1000, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.maxsize = maxsize

        def __setitem__(self, key: Any, value: Any) -> None:
            if len(self) >= self.maxsize and key not in self:
                self.popitem(last=False)
            super().__setitem__(key, value)

        def __getitem__(self, key: Any) -> Any:
            value = super().__getitem__(key)
            self.move_to_end(key)
            return value

        def get(self, key: Any, default: Any = None) -> Any:
            try:
                return self[key]
            except KeyError:
                return default


class SemanticCacheManager:
    """
    セマンティック・キャッシュ（意味的キャッシュ）管理クラス。
    ChromaDB と Gemini Embedding API を活用し、意味的に類似した過去の生成結果をキャッシュする。
    L1キャッシュとしてインメモリの完全一致キャッシュ（LRUCache）を前段に挟む。
    """

    COLLECTION_NAME = "semantic_cache"

    def __init__(self, vector_store: Any, client: Any, embedding_model: str = MODEL_EMBEDDING):
        """
        Args:
            vector_store: ChromaVectorStore 等のインスタンス
            client: genai.Client (Gemini API クライアント)
            embedding_model: 埋め込みモデル名
        """
        self.vector_store = vector_store
        self.client = client
        self.embedding_model = embedding_model
        # L1 インメモリキャッシュ (最大1000件)
        self._l1_cache = LRUCache(maxsize=1000)
        # L2-B (Fast-Path) インメモリ・ベクトルキャッシュ
        # 重複するプロンプトの埋め込み計算を省くため、直近の embedding を保持
        self._l2_embedding_cache = LRUCache(maxsize=500)

    def _get_l1_key(self, prompt: str, task_type: str, genre: str, temperature: float) -> str:
        """プロンプトおよびパラメータのハッシュ値からL1キャッシュキーを生成"""
        key_str = f"{prompt}:{task_type}:{genre}:{temperature}"
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    async def _get_embedding(self, text: str) -> list[float]:
        """Gemini API を使用してプロンプトの埋め込み（ベクトル）を生成。L2-Bキャッシュを適用。"""
        # L2-B キャッシュチェック (完全一致ハッシュ)
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if text_hash in self._l2_embedding_cache:
            logger.debug("[SEMANTIC CACHE] L2-B Embedding Cache Hit!")
            return self._l2_embedding_cache[text_hash]

        try:

            def _call():
                return self.client.models.embed_content(model=self.embedding_model, contents=[text])

            from src.core.executor_manager import executor_manager

            res = await executor_manager.run_cpu(_call)
            vec = res.embeddings[0].values

            # L2-B キャッシュに保存
            self._l2_embedding_cache[text_hash] = vec
            return vec
        except Exception as e:
            logger.error(f"[SEMANTIC CACHE] Embedding generation failed: {e}")
            return []

    async def search(
        self,
        prompt: str,
        task_type: str,
        genre: str = "general",
        temperature: float = 0.7,
        threshold: float = 0.95,
        **kwargs: Any,
    ) -> Any | None:
        """
        類似したキャッシュエントリを検索する。
        """
        # 1. L1 完全一致インメモリキャッシュチェック
        l1_key = self._get_l1_key(prompt, task_type, genre, temperature)
        if l1_key in self._l1_cache:
            logger.info(
                f"🧠 [L1 EXACT CACHE HIT] Bypassing Embedding API & ChromaDB! (task_type={task_type})"
            )
            return self._l1_cache[l1_key]

        if not self.vector_store or not self.client:
            return None

        # 埋め込みベクトルの生成
        vec = await self._get_embedding(prompt)
        if not vec:
            return None

        # ハイブリッド検索フィルタリング (task_type と genre の完全一致)
        where = {"$and": [{"task_type": task_type}, {"genre": genre}]}

        # コサイン類似度の閾値判定
        # cosine distance = 1 - cosine_similarity
        # cosine_similarity >= threshold  =>  cosine_distance <= (1 - threshold)
        max_distance = 1.0 - threshold

        # コサイン空間コレクションを取得または作成
        self.vector_store.get_collection(self.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

        results = await self.vector_store.search(
            collection_name=self.COLLECTION_NAME, query_embedding=vec, top_k=5, where=where
        )

        best_hit = None
        best_distance = 999.0
        input_len = len(prompt)

        for res in results:
            dist = res.get("distance", 1.0)
            meta = res.get("metadata", {})

            # cosine類似度の閾値判定
            if dist > max_distance:
                continue

            # 追加のメタデータフィルタ: 入力文字数の極端な乖離を防ぐ (±50%)
            cached_input_length = meta.get("input_length", 0)
            if cached_input_length > 0:
                len_diff_ratio = abs(input_len - cached_input_length) / max(1, cached_input_length)
                if len_diff_ratio > 0.5:
                    logger.debug(
                        f"[SEMANTIC CACHE] Rejected hit due to input length difference: {input_len} vs {cached_input_length}"
                    )
                    continue

            if dist < best_distance:
                best_distance = dist
                best_hit = res

        if best_hit:
            doc_id = best_hit["id"]
            meta = best_hit["metadata"]
            meta["last_accessed"] = datetime.datetime.now().isoformat()

            # 非同期でアクセス日時を更新して保存
            _spawn_background(
                self.vector_store.add_documents(
                    collection_name=self.COLLECTION_NAME,
                    ids=[doc_id],
                    documents=[best_hit["content"]],
                    embeddings=[vec],
                    metadatas=[meta],
                ),
                name="semantic_cache.touch",
            )

            logger.info(
                f"🧠 [SEMANTIC CACHE HIT] Similarity: {1.0 - best_distance:.4f} (task_type={task_type})"
            )

            content_str = best_hit["content"]
            if meta.get("is_json"):
                try:
                    return json.loads(content_str)
                except Exception:
                    return content_str
            return content_str

        return None

    async def add(
        self,
        prompt: str,
        response: Any,
        task_type: str,
        genre: str = "general",
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> None:
        """
        キャッシュを追加する。
        """
        # L1キャッシュへの登録
        l1_key = self._get_l1_key(prompt, task_type, genre, temperature)
        self._l1_cache[l1_key] = response

        if not self.vector_store or not self.client:
            return

        vec = await self._get_embedding(prompt)
        if not vec:
            return

        doc_id = str(uuid.uuid4())
        is_json = False
        if isinstance(response, (dict, list)):
            is_json = True
            content_str = json.dumps(response, ensure_ascii=False)
        else:
            content_str = str(response)

        metadata = {
            "task_type": task_type,
            "genre": genre,
            "temperature": temperature,
            "input_length": len(prompt),
            "is_json": is_json,
            "created_at": datetime.datetime.now().isoformat(),
            "last_accessed": datetime.datetime.now().isoformat(),
        }

        # コサイン空間コレクションを確保
        self.vector_store.get_collection(self.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

        # ChromaDBへ保存
        await self.vector_store.add_documents(
            collection_name=self.COLLECTION_NAME,
            ids=[doc_id],
            documents=[content_str],
            embeddings=[vec],
            metadatas=[metadata],
        )
        logger.info(f"[SEMANTIC CACHE ADD] task_type={task_type}, length={len(content_str)}")

        # LRUエビクションチェック
        _spawn_background(self.evict_if_needed(), name="semantic_cache.evict")

    async def evict_if_needed(self, max_items: int = 1000) -> None:
        """
        キャッシュサイズが上限を超えた場合、最も古くアクセスされていない（LRU）キャッシュを自動削除する。
        """
        try:
            collection = self.vector_store.get_collection(
                self.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
            )
            if not collection:
                return

            def _get_all():
                return collection.get(include=["metadatas"])

            from src.core.executor_manager import executor_manager

            data = await executor_manager.run_io(_get_all)
            ids = data.get("ids", [])
            metadatas = data.get("metadatas", [])

            if len(ids) <= max_items:
                return

            items = []
            for i in range(len(ids)):
                meta = metadatas[i] if metadatas else {}
                last_accessed = meta.get("last_accessed", meta.get("created_at", ""))
                items.append((ids[i], last_accessed))

            # 古い順（昇順）にソート
            items.sort(key=lambda x: x[1])

            to_delete_count = len(ids) - max_items
            delete_ids = [x[0] for x in items[:to_delete_count]]

            if delete_ids:
                await self.vector_store.delete_by_id(self.COLLECTION_NAME, delete_ids)
                logger.info(
                    f"[SEMANTIC CACHE EVICTION] Evicted {len(delete_ids)} old cache entries."
                )

        except Exception:
            # exception（トレースバック付き）で記録する。
            #
            # 旧実装は `logger.error(f"...: {e}")` でメッセージ本文だけを
            # 記録していたため、原因の特定ができなかった。
            # 2026-10-04 の公開前調査では、この握り潰しによって
            # `executor_manager` が lifespan shutdown 後に恒久的に使用不能である
            # 事実（`RuntimeError: cannot schedule new futures after shutdown`）が
            # 伏せられ、`evict_if_needed` が無言で 0 件しか処理しないため、
            # 呼び出し側のテストが opaque な原因で失敗していた。
            #
            # 驱逐は性能重視の経路（eviction 失敗してもキャッシュ本体は動く）なので
            # 例外は伝播させない。ただし「何が起きたか」を必ず残す。
            logger.exception("[SEMANTIC CACHE EVICTION] Failed")

    async def prefetch_next(
        self,
        book_id: int,
        current_ep_num: int,
        task_types: list[str],
        genre: str = "general",
        temperature: float = 0.7,
    ) -> None:
        """
        予測プリフェッチ: 次のエピソード用のプロンプトテンプレートを先行レンダリングしてキャッシュする。
        これにより、次のエピソード生成開始時にプロンプトレンダリングのレイテンシを隠蔽できる。

        Args:
            book_id: 書籍ID
            current_ep_num: 現在生成中のエピソード番号
            task_types: プリフェッチ対象タスクタイプのリスト (例: ["drafting", "polishing"])
            genre: ジャンル
            temperature: 生成温度
        """
        if not is_draft_prefetch_enabled():
            return  # 静的なウォームアップは RagPrefetchService 側が担当する

        from prompts.manager import PromptManager

        pm = PromptManager()

        next_ep = current_ep_num + 1
        prefetch_prompts = []

        for task_type in task_types:
            if task_type == "drafting":
                # 次のエピソードのドラフティングプロンプトを先行レンダリング
                try:
                    prompt = await pm.build_drafting_prompt(
                        ep_num=next_ep,
                        plot_data={},  # プレースホルダー
                        script_text="",
                        target_word_count=3000,
                        book_id=book_id,
                    )
                    prefetch_prompts.append((task_type, prompt))
                except Exception as e:
                    logger.debug(
                        f"[PREFETCH] Could not prefetch drafting prompt for ep{next_ep}: {e}"
                    )

            elif task_type == "polishing":
                # -Polishing プロンプトも先行レンダリング
                try:
                    prompt = await pm.build_polishing_prompt(
                        draft_content="",
                        target_word_count=3000,
                        style_key="default",
                        prose_sample="",
                        book_id=book_id,
                    )
                    prefetch_prompts.append((task_type, prompt))
                except Exception as e:
                    logger.debug(
                        f"[PREFETCH] Could not prefetch polishing prompt for ep{next_ep}: {e}"
                    )

        # プリフェッチしたプロンプトをL1キャッシュに Warming として登録
        # (実際のEmbedding計算はバックグラウンドで実行される)
        for task_type, prompt in prefetch_prompts:
            # プロンプトのハッシュをキーとして、プレースホルダー値を登録
            l1_key = self._get_l1_key(prompt, task_type, genre, temperature)
            # 実際のEmbedding計算は非同期でバックグラウンド実行
            _spawn_background(
            self._prefetch_embedding(prompt, task_type, genre, temperature),
            name="semantic_cache.prefetch",
        )
            logger.info(
                f"[PREFETCH] Queued prefetch for ep{next_ep} task={task_type}, key={l1_key[:16]}..."
            )

    async def _prefetch_embedding(
        self, prompt: str, task_type: str, genre: str, temperature: float
    ) -> None:
        """バックグラウンドでEmbeddingを計算し、キャッシュをウォーミングする"""
        try:
            vec = await self._get_embedding(prompt)
            if vec:
                logger.debug(f"[PREFETCH] Embedding computed for {task_type}, warming cache...")
                # L2-Bキャッシュには既に登録されているが、
                # 次のsearchでChromaDBへアクセスする前にL1でWarm状態にする
        except Exception as e:
            logger.debug(f"[PREFETCH] Embedding computation failed: {e}")

    async def prefetch_by_pattern(
        self,
        book_id: int,
        ep_range_start: int,
        ep_range_end: int,
        task_types: list[str],
        genre: str = "general",
    ) -> dict[str, int]:
        """
        エピソード範囲全体のプリフェッチを実行する。
        現在生成中のエピソードの後続エピソード群を一括でウォームアップする。

        Args:
            book_id: 書籍ID
            ep_range_start: 開始エピソード番号
            ep_range_end: 終了エピソード番号
            task_types: プリフェッチ対象タスクタイプ
            genre: ジャンル

        Returns:
            プリフェッチ結果のサマリー
        """
        results = {"total": 0, "succeeded": 0, "failed": 0}

        for ep_num in range(ep_range_start, ep_range_end + 1):
            results["total"] += 1
            try:
                await self.prefetch_next(book_id, ep_num, task_types, genre)
                results["succeeded"] += 1
            except Exception as e:
                logger.warning(f"[PREFETCH] Failed to prefetch ep{ep_num}: {e}")
                results["failed"] += 1

        logger.info(f"[PREFETCH] Batch prefetch completed: {results}")
        return results

    async def get_cache_warmth(self, task_type: str, genre: str) -> dict[str, Any]:
        """
        キャッシュのウォーム度を取得する。
        特定のtask_type+genreの組み合わせで、どれくらいキャッシュがウォームかを示す。

        Returns:
            {"warmth_score": 0.0-1.0, "l1_size": int, "l2_size": int, "estimated_coverage": float}
        """
        # L1キャッシュのサイズ
        l1_size = len(self._l1_cache)
        l1_max = self._l1_cache.maxsize

        # L2Embeddingキャッシュのサイズ
        l2_size = len(self._l2_embedding_cache)
        l2_max = self._l2_embedding_cache.maxsize

        # ウォーム度スコア (L1とL2のカバー率を합算)
        warmth_score = (l1_size / l1_max * 0.7) + (l2_size / l2_max * 0.3)

        return {
            "warmth_score": min(1.0, warmth_score),
            "l1_size": l1_size,
            "l1_max": l1_max,
            "l2_size": l2_size,
            "l2_max": l2_max,
            "estimated_coverage": warmth_score,
        }

    async def compute_similarity(self, text1: str, text2: str) -> float:
        """
        2つのテキスト間のコサイン類似度 (0.0-1.0) を計算する。
        埋め込みベクトル取得コスト高いため、同一テキストの場合は 1.0 を直接返す最適化を含む。
        """
        if text1 == text2:
            return 1.0

        vec1 = await self._get_embedding(text1)
        vec2 = await self._get_embedding(text2)

        norm1 = math.sqrt(sum(v * v for v in vec1))
        norm2 = math.sqrt(sum(v * v for v in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        dot = sum(a * b for a, b in zip(vec1, vec2))
        return dot / (norm1 * norm2)
