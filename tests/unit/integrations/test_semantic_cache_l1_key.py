"""semantic_cache L1 キー生成の一致を回帰検証する。

SemanticCacheManager.search(prompt, task_type, genre, temperature, ...) の
キーワード引数と、src/services/redis_cache.py の L3 呼び出し側
(self.semantic.search(...)) が一致することを AST で静的に検証する。

検証の背景:
  - SemanticCacheManager._get_l1_key(prompt, task_type, genre, temperature) は
    search 側と prefetch 側で同一関数・同一引数順で呼ばれている。
  - 残る不確実性は、redis_cache.py の呼び出しが search のキーワード引数
    (prompt=..., task_type=..., genre=..., temperature=...) に一致するか
    の文字列一致のみ。ここがズレると L1 キャッシュキーが不整合になり、
    キャッシュヒット/ミスが意図しない動作になる。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _search_call_keywords(text: str) -> list[str]:
    """redis_cache.py 内の self.semantic.search(...) 呼び出しのキーワード引数名を返す。"""
    tree = ast.parse(text)
    keywords: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "search"
            and node.keywords
        ):
            continue
        # self.semantic.search(...) または semantic.search(...) の呼び出しのみ対象
        if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "semantic":
            keywords.extend(kw.arg for kw in node.keywords if kw.arg is not None)
    return keywords


def _search_signature_params(text: str) -> list[str]:
    """semantic_cache.py の async def search(...) のパラメータ名(self 除く)を返す。"""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "search":
            return [a.arg for a in node.args.args if a.arg != "self"]
    raise AssertionError("async def search(...) が見つかりませんでした")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_redis_cache_semantic_search_keywords_match_signature():
    """redis_cache の self.semantic.search 呼び出しが search のシグネチャと一致する。"""
    redis_text = _read("src/services/redis_cache.py")
    semantic_text = _read("src/integrations/semantic_cache.py")

    keywords = _search_call_keywords(redis_text)
    params = _search_signature_params(semantic_text)

    assert keywords, "redis_cache.py に self.semantic.search(...) の呼び出しが見つかりませんでした"

    missing = [kw for kw in keywords if kw not in params]
    assert not missing, (
        f"redis_cache.py の semantic.search 呼び出しに、search シグネチャにない "
        f"キーワード引数が含まれています: {missing} (params={params})"
    )

    # L1 キー生成に必須の 4 引数が必ず含まれることを特に検証する。
    required = {"prompt", "task_type", "genre", "temperature"}
    missing_required = required - set(keywords)
    assert not missing_required, (
        f"redis_cache.py の semantic.search 呼び出しに L1 キー生成に必須の引数が不足: "
        f"{missing_required} (keywords={keywords})"
    )


def test_redis_cache_semantic_search_uses_required_l1_args():
    """L1 キャッシュキー生成に必須の 4 引数が redis_cache の呼び出しに含まれる。"""
    redis_text = _read("src/services/redis_cache.py")
    keywords = _search_call_keywords(redis_text)

    for arg in ("prompt", "task_type", "genre", "temperature"):
        assert arg in keywords, f"semantic.search 呼び出しに '{arg}' が含まれていません: keywords={keywords}"
