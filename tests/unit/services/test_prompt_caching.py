"""src/services/prompt_caching.py (LRUCache / CachedContent / PromptCacheManager) の単体テスト."""

from __future__ import annotations

import pytest

from src.services.prompt_caching import (
    CachedContent,
    ContextCachingNotSupportedError,
    PromptCacheManager,
    caching,
)


class TestLRUFallbackCache:
    """cachetools が unavailable の場合の LRUCache フォールバック実装のテスト."""

    def test_lru_cache_basic_get_set(self):
        from src.services.prompt_caching import LRUCache as _LRUCache

        cache = _LRUCache(maxsize=3)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3
        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("z", "default") == "default"

    def test_lru_cache_eviction(self):
        from src.services.prompt_caching import LRUCache as _LRUCache

        cache = _LRUCache(maxsize=2)
        cache["a"] = 1
        cache["b"] = 2
        # 3番目を追加して最も古い "a" が追い出される
        cache["c"] = 3
        assert cache.get("a") is None  # evicted
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_lru_cache_update_existing(self):
        from src.services.prompt_caching import LRUCache as _LRUCache

        cache = _LRUCache(maxsize=2)
        cache["a"] = 1
        cache["a"] = 100  # 更新（eviction の対象にならない）
        cache["b"] = 2
        assert cache.get("a") == 100

    def test_lru_cache_access_moves_to_end(self):
        from src.services.prompt_caching import LRUCache as _LRUCache

        cache = _LRUCache(maxsize=2)
        cache["a"] = 1
        cache["b"] = 2
        # "a" にアクセスして最新にする
        _ = cache.get("a")
        # "c" を追加して "b" が追い出される
        cache["c"] = 3
        assert cache.get("a") == 1
        assert cache.get("b") is None  # evicted
        assert cache.get("c") == 3


class TestCachedContent:
    """CachedContent スタブのテスト."""

    def test_create_raises_not_supported(self):
        with pytest.raises(ContextCachingNotSupportedError):
            CachedContent.create("key", ["content"])

    def test_create_raises_with_args(self):
        with pytest.raises(ContextCachingNotSupportedError):
            CachedContent.create("key", ["c"], model_name="gemini", ttl_minutes=30)


class TestPromptCacheManager:
    """PromptCacheManager のテスト."""

    def test_get_or_create_cache_returns_cached(self):
        manager = PromptCacheManager()
        # まず直接キャッシュマップに入れる
        manager._cache_map["key1"] = "cached_value"
        result = manager.get_or_create_cache("key1", ["contents"])
        assert result == "cached_value"

    def test_get_or_create_cache_raises_when_uncached(self):
        manager = PromptCacheManager()
        with pytest.raises(ContextCachingNotSupportedError):
            manager.get_or_create_cache("new_key", ["contents"])

    def test_clear_cache_removes_entry(self):
        manager = PromptCacheManager()
        manager._cache_map["key1"] = "value"
        assert "key1" in manager._cache_map
        manager.clear_cache("key1")
        assert "key1" not in manager._cache_map

    def test_clear_cache_missing_key_no_error(self):
        manager = PromptCacheManager()
        # 存在しないキーをクリアしてもエラーにならない
        manager.clear_cache("nonexistent")

    def test_caching_placeholder_available_false(self):
        assert caching.available is False
        assert caching.CachedContent is CachedContent
