import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

logger = logging.getLogger(__name__)


class ExecutorManager:
    """
    役割別に最適化されたThreadPoolExecutorを管理するシングルトンクラス。
    asyncio.to_thread (デフォルトプール) への依存を減らし、
    I/Oバウンド処理とCPUバウンド処理を分離して効率化する。
    """

    _instance = None

    IO_WORKERS = 32
    CPU_WORKERS = 8

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._shutdown = False
            cls._instance._create_pools()
            logger.info("ExecutorManager initialized with IO and CPU pools.")
        return cls._instance

    def _create_pools(self) -> None:
        """（再）生成する。シャットダウン済みでも呼び出せる。"""
        # I/Oバウンド処理用: 待機時間が長いため、多めのスレッドを確保
        self.io_executor = ThreadPoolExecutor(
            max_workers=self.IO_WORKERS, thread_name_prefix="LLM_IO_Pool"
        )
        # CPUバウンド処理用: 計算負荷が高いため、コア数に近い数に制限してコンテキストスイッチを抑制
        # (Embedding計算などの重い処理用)
        self.cpu_executor = ThreadPoolExecutor(
            max_workers=self.CPU_WORKERS, thread_name_prefix="LLM_CPU_Pool"
        )

    def _ensure_pools(self) -> None:
        """シャットダウン済みなら再生成する。

        なぜ必要か
        --------
        `shutdown()` 後、`ThreadPoolExecutor` は恒久的に使用不能になり、
        `run_in_executor` は `RuntimeError: cannot schedule new futures after
        shutdown` を投げる。`ExecutorManager` はプロセス寿命のシングルトンなので、
        一度 lifespan shutdown が走ると、**同じプロセス内の後続処理が
        すべて同一例外で死ぬ**。

        2026-10-04 の公開前調査で実際に観測された: FastAPI の lifespan shutdown
        (`src/backend/server.py`) が `executor_manager.shutdown()` を呼び、
        同じテストプロセス内の後続テストが `semantic_cache.evict_if_needed` で
        無言（bare except で握り潰され）失敗した。

        shutdown は「アプリ終了」の意味なので、その後に処理が続く
        （テストの次のケース、Celery/Huey ワーカー内の再入など）前提下で、
        必要になった時点で再生成する。
        """
        if getattr(self, "_shutdown", False):
            self._create_pools()
            self._shutdown = False
            logger.info("ExecutorManager pools re-created after shutdown.")

    async def run_io(self, func: Callable, *args, **kwargs) -> Any:
        """I/Oバウンドな処理をIOプールで実行する"""
        self._ensure_pools()
        loop = asyncio.get_running_loop()
        # partialを使用してkwargsを関数にバインド
        p_func = partial(func, *args, **kwargs)
        return await loop.run_in_executor(self.io_executor, p_func)

    async def run_cpu(self, func: Callable, *args, **kwargs) -> Any:
        """CPUバウンドな処理をCPUプールで実行する"""
        self._ensure_pools()
        loop = asyncio.get_running_loop()
        p_func = partial(func, *args, **kwargs)
        return await loop.run_in_executor(self.cpu_executor, p_func)

    def shutdown(self):
        """プールのシャットダウン（冪等）"""
        if getattr(self, "_shutdown", False):
            logger.debug("ExecutorManager already shut down; ignoring.")
            return
        self.io_executor.shutdown(wait=True)
        self.cpu_executor.shutdown(wait=True)
        self._shutdown = True
        logger.info("ExecutorManager pools shutdown complete.")


# シングルトンインスタンスを提供
executor_manager = ExecutorManager()
