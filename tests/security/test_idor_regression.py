"""IDOR（cross-tenant アクセス）の一括ガード。

本プロジェクト歴史上の 4 件の IDOR を恒久的に検出する。
新規 router を追加したとき、本テストが ownership 不足を検出する。
"""
from __future__ import annotations

import ast
import glob
import os

ROUTER_DIR = "src/backend/routers"

# 所有者検証が「意図的に」不要または次回計画で対応予定の router を明示的に列挙。
# ここに無い router に book_id ハンドラが無症状で現れたらテストが赤になる。
NO_OWNERSHIP_NEEDED: set[str] = {
    # misc / novel は authz 修正（Fix batch G）で全ハンドラに
    # get_current_user と verify_book_ownership が入ったため、allow-list から削除済み。
    #
    # TODO(H1-2): books.py の get_book / delete_book は所有権検証を
    #   BookUseCases へ委譲しており、ガード呼び出しがリテラルに現れないため
    #   ここでは素朴な文字列一致で依然としてフラグが立つ（実際の検証は
    #   tests/security/test_router_ownership_matrix.py 側で担保している）。
    "books",
    # TODO(H1-2): branches.py の node 以外のブランチ操作系ハンドラへの検証共通化
    "branches",
    # TODO(H1-2): collab.py のコラボレーション権限検証の統合
    "collab",
    # TODO(H1-2): commercial.py の商用機能エンドポイントの所有権検証
    "commercial",
    # TODO(H1-2): commercial_planning.py の async 化および所有権検証
    "commercial_planning",
    # TODO(H1-2): cost.py の予算消費比率エンドポイントの所有権検証
    "cost",
    # TODO(H1-2): easy_mode.py のエクスポートおよび生成エンドポイントの認証・所有権検証
    "easy_mode",
    # TODO(H1-2): episodes.py の内部ヘルパー _cancel_prefetch_for_book
    "episodes",
    # graph.py の RAG 系は `_require_book_scope` ヘルパー経由で所有権検証するため、
    # ガード呼び出しがリテラルに現れず、ここでは依然としてフラグが立つ。
    # TODO(H1-2): graph.py の知識グラフ・伏線エンドポイントの認証・所有権検証
    "graph",
    # TODO(H1-2): marketing.py のパッケージエクスポートエンドポイントの所有権検証
    "marketing",
    # TODO(H1-2): orchestrated.py のエクスポートエンドポイントの所有権検証
    "orchestrated",
    # TODO(H1-2): pipeline_stream.py のストリーミングエンドポイントの検証共通化
    "pipeline_stream",
    # TODO(H1-2): publishing.py のパブリッシングプレビュー検証の統合
    "publishing",
    # TODO(H1-2): stream_writing.py の執筆ストリーミング検証の統合
    "stream_writing",
    # TODO(H1-2): system.py の再計算・改善優先度エンドポイントの認証・所有権検証
    "system",
}

NO_AUTH_NEEDED: set[str] = {
    # TODO(H1-2): easy_mode.py のルータレベル認証依存追加
    "easy_mode",
    # TODO(H1-2): graph.py のルータレベル認証依存追加
    # NOTE: 修正後は各ハンドラが `get_current_user` を Declaring するため
    #   AUTH_MARKERS の一致で検出できるが、`retrieve_for_episode` だけは
    #   `_require_book_scope` ヘルパー経由で検証するため allow-list に残す。
    "graph",
    # TODO(H1-2): system.py のルータレベル認証依存追加
    "system",
}

AUTH_MARKERS = ("get_current_user", "enforce_book_ownership", "requires_book_ownership")


def _book_id_handlers(path: str):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and "book_id" in [a.arg for a in node.args.args]:
            out.append((node, ast.get_source_segment(src, node) or ""))
    return out


def test_no_router_exposes_book_id_without_ownership_check():
    offenders: list[str] = []
    for p in glob.glob(os.path.join(ROUTER_DIR, "*.py")):
        name = os.path.splitext(os.path.basename(p))[0]
        if name in NO_OWNERSHIP_NEEDED:
            continue
        for node, body in _book_id_handlers(p):
            if "verify_book_ownership" in body and "verify_book_ownership_sync" in body:
                offenders.append(f"{p}:{node.lineno} {node.name} (sync 版のみ)")
            elif "verify_book_ownership" not in body:
                offenders.append(f"{p}:{node.lineno} {node.name}")
    assert not offenders, (
        "book_id を受けるのに所有者検証が無いハンドラ:\n  " + "\n  ".join(offenders)
    )


def test_every_router_with_book_id_also_requires_authentication():
    offenders: list[str] = []
    for p in glob.glob(os.path.join(ROUTER_DIR, "*.py")):
        name = os.path.splitext(os.path.basename(p))[0]
        if name in NO_AUTH_NEEDED:
            continue
        src = open(p, encoding="utf-8").read()
        if not any("book_id" in b for _, b in _book_id_handlers(p)):
            continue
        if not any(m in src for m in AUTH_MARKERS):
            offenders.append(p)
    assert not offenders, f"認証依存が無いのに book_id を取り扱う router: {offenders}"
