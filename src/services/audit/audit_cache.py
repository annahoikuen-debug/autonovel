"""監査結果キャッシュモジュール（TRACK-C C3: LLMコスト最適化）。

原稿テキストの SHA-256 ハッシュをキーに監査結果をキャッシュし、
同一原稿の 2 回目以降の監査では LLM 呼び出しをスキップして
キャッシュ済みの結果を返す。

`src.services.semantic_cache` のセマンティックキャッシュ（類似ベース）
の活用も検討対象だが、監査結果は同一原稿に対して同一であるべき
厳密一致が求められるため、本モジュールでは原稿ハッシュによる
完全一致キャッシュを採用する。必要に応じて L2 層として
セマンティックキャッシュを重ねる拡張を想定している。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Tuple

from cachetools import LRUCache

logger = logging.getLogger(__name__)

DEFAULT_MAXSIZE = 1000


def compute_manuscript_hash(text: str) -> str:
    """原稿テキストの SHA-256 ハッシュ（16 進文字列）を返す。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuditCache:
    """AuditService 互換の監査サービスをラップし、原稿ハッシュで結果をキャッシュする。

    キャッシュヒット時は下層サービス（およびその先の LLM）を呼び出さず、
    直前の監査結果をそのまま返す。これにより同一原稿の再監査における
    LLM 呼び出しを 0 に削減する。

    Attributes:
        service: ラップ対象の監査サービス（`AuditService` 等）。
        maxsize: キャッシュ最大エントリ数（LRU で eviction）。
    """

    def __init__(self, service: Any, maxsize: int = DEFAULT_MAXSIZE) -> None:
        self._service = service
        self._cache: LRUCache[str, Any] = LRUCache(maxsize=maxsize)
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # 統計情報
    # ------------------------------------------------------------------
    @property
    def hits(self) -> int:
        """キャッシュヒット回数。"""
        return self._hits

    @property
    def misses(self) -> int:
        """キャッシュミス（下層サービス呼び出し）回数。"""
        return self._misses

    @property
    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": self.size,
            "maxsize": self._cache.maxsize,
        }

    def clear(self) -> None:
        """キャッシュをクリアし統計をリセットする。"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # 内部ヘルパ
    # ------------------------------------------------------------------
    def _make_key(self, operation: str, *parts: str) -> str:
        """操作名と原稿部分文字列からキャッシュキーを生成する。"""
        combined = "\x00".join([operation, *parts])
        return compute_manuscript_hash(combined)

    # ------------------------------------------------------------------
    # 公開 API（AuditService と同シグネチャ）
    # ------------------------------------------------------------------
    async def screen_plot(self, blueprint: str) -> Tuple[bool, str]:
        key = self._make_key("screen_plot", blueprint)
        if key in self._cache:
            self._hits += 1
            logger.debug("[AUDIT CACHE] HIT screen_plot key=%s", key[:16])
            return self._cache[key]  # type: ignore[return-value]
        self._misses += 1
        result = await self._service.screen_plot(blueprint)
        self._cache[key] = result
        return result

    async def audit_ability(
        self, blueprint: str, settings_json: str, characters_json: str
    ) -> Tuple[bool, str, str]:
        key = self._make_key("audit_ability", blueprint, settings_json, characters_json)
        if key in self._cache:
            self._hits += 1
            logger.debug("[AUDIT CACHE] HIT audit_ability key=%s", key[:16])
            return self._cache[key]  # type: ignore[return-value]
        self._misses += 1
        result = await self._service.audit_ability(
            blueprint, settings_json, characters_json
        )
        self._cache[key] = result
        return result

    async def audit_deai(self, content: str) -> Tuple[bool, str]:
        key = self._make_key("audit_deai", content)
        if key in self._cache:
            self._hits += 1
            logger.debug("[AUDIT CACHE] HIT audit_deai key=%s", key[:16])
            return self._cache[key]  # type: ignore[return-value]
        self._misses += 1
        result = await self._service.audit_deai(content)
        self._cache[key] = result
        return result
