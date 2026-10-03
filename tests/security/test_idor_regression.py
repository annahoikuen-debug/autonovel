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
    # NOTE: "collab" と "marketing" も 2026-10-03 の公開前監査で削除済み。
    #   従来 TODO(H1-2) として allow-list に居たが、その状態では
    #   guard が意図的に目を閉じており、実質的に以下の IDOR を許していた:
    #     - POST /api/marketing/export_package/{book_id}
    #       （認証・所有権なし。任意の認証ユーザーが任意の book_id の
    #        ZIP = 本文/設定/プロットを一括取得できる。GET 版は検証済みだった）
    #     - PATCH/DELETE /api/collab/comments/{comment_id}
    #       （comment_id から book_id を辿らず所有権検証なし）
    #   いずれも修正済み。allow-list への再追加はしないこと。
    #
    # TODO(H1-2): books.py の get_book / delete_book は所有権検証を
    #   BookUseCases へ委譲しており、ガード呼び出しがリテラルに現れないため
    #   ここでは素朴な文字列一致で依然としてフラグが立つ（実際の検証は
    #   tests/security/test_router_ownership_matrix.py 側で担保している）。
    "books",
    # TODO(H1-2): branches.py の node 以外のブランチ操作系ハンドラへの検証共通化
    "branches",
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

# 所有権ガードの実装は router ごとに異なる:
#   - verify_book_ownership : owner_guard.py の標準ガード
#   - _verify_book_access   : collab.py 内のコラボ権限 専用ガード
#   - _require_book_scope   : graph.py の RAG 系 専用ガード
# これらを「所有権検証あり」として認識しないと同じ。既知の IDOR が
# allow-list 依存で生き残る構造になる。
OWNERSHIP_MARKERS = (
    "verify_book_ownership",
    "verify_book_ownership_sync",
    "_verify_book_access",
    "_require_book_scope",
)


def _book_id_handlers(path: str):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and "book_id" in [a.arg for a in node.args.args]:
            out.append((node, ast.get_source_segment(src, node) or ""))
    return out


def _calls_any_marker(func_node: ast.AST, markers: tuple[str, ...]) -> bool:
    """関数本体が guard を**実際に呼んでいる**かを AST で判定する。

    なぜ AST なのか
    --------------
    旧実装はソース文字列の単純一致（`"verify_book_ownership" in body`）で判定
    していたが、`body` には docstring とコメントも含まれる。そのため
    「docstring にガードの名前を書いただけ」で検証済みと誤判定された。

    実際、2026-10-03 の公開前監査で `marketing.py` の docstring に
    `verify_book_ownership` と記載したところ、ガードが IDOR を検出できなくなった。
    ガードが文字列一致で判定されている限り、allow-list 依存で既知の IDOR が
    生き残る構造になるため、`Call` ノードを見る方式に改める。
    """
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name and any(m.lstrip("_") == name.lstrip("_") for m in markers):
            return True
    return False


# docstring だけが guard 名を書いているだけの handler を検出できることの
    # 自己テスト。これが無いとガードの偽陽性を検出できない。
    src = '''
async def handler(book_id: int, current_user=None):
    """この関数は verify_book_ownership を使う（docstring の mere 言及のみ）。"""
    return book_id


async def real_handler(book_id: int, current_user=None):
    """実際にガードを呼ぶ。"""
    await verify_book_ownership(book_id, current_user)
    return book_id
'''
    tree = ast.parse(src)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
    assert _calls_any_marker(funcs["handler"], OWNERSHIP_MARKERS) is False, (
        "docstring のみの言及を所有権検証と誤判定している"
    )
    assert _calls_any_marker(funcs["real_handler"], OWNERSHIP_MARKERS) is True


def test_no_router_exposes_book_id_without_ownership_check():
    offenders: list[str] = []
    for p in glob.glob(os.path.join(ROUTER_DIR, "*.py")):
        name = os.path.splitext(os.path.basename(p))[0]
        if name in NO_OWNERSHIP_NEEDED:
            continue
        for node, _body in _book_id_handlers(p):
            # ガード関数そのものはハンドラではない。
            # `_verify_book_access(book_id, ...)` は所有権検証の実装であり、
            # これを「検証が無い handler」として報告すると誤検出になる。
            # 私有（_ 接頭辞）の helper も内部処理なので同様に除外する。
            if node.name.startswith("_"):
                continue
            if not _calls_any_marker(node, OWNERSHIP_MARKERS):
                offenders.append(f"{p}:{node.lineno} {node.name}")
    assert not offenders, (
        "book_id を受けるのに所有者検証が無いハンドラ:\n  " + "\n  ".join(offenders)
    )


# ------------------------------------------------------------------
# comment_id / member_id 型の IDOR ゲート
#
# `test_no_router_exposes_book_id_without_ownership_check` は `book_id` を
# 引数に取るハンドラしか対象としない。影響を受ける側の ID が別（例:
# `comment_id`）の場合、その ID から book_id を辿って所有権検証する
# 経路を一般情况下通用的には扱えないため、上記ゲートでは検出できない。
#
# 2026-10-03 の公開前監査で `PATCH/DELETE /api/collab/comments/{comment_id}` が
# ちょうどこの形状の IDOR venturalier  있었다（comment_id から book_id を
# 辿らず、任意の認証ユーザーが他人のレビューコメントを握り潰せた）。
# この形を再発させないため、変更系リポジトリメソッドを呼ぶハンドラに
# 所有権ガードを要求する。
# ------------------------------------------------------------------
GUARDED_MUTATIONS = (
    "resolve_comment",
    "delete_comment",
    "remove_member",
)


def _calls_repo_mutation(func_node: ast.AST, names: tuple[str, ...]) -> bool:
    """関数が指定したリポジトリ変更メソッドを呼んでいるか。"""
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in names:
            return True
    return False


def test_entity_id_mutations_require_ownership_check():
    """entity_id（comment_id 等）を受ける変更ハンドラには所有権ガードが必要。

    `test_no_router_exposes_book_id_without_ownership_check` は `book_id` を
    引数に取るハンドラしか対象としない。影響を受ける側の ID が別の形
    （例: `comment_id`）だと、その ID から book_id を辿る経路を
    静的には追えないため、前段ゲートでは検出できない。

    2026-10-03 の公開前監査で `PATCH/DELETE /api/collab/comments/{comment_id}` が
    ちょうどこの形状の IDOR を持っていた（comment_id から book_id を辿らず、
    任意の認証ユーザーが他人のレビューコメントを握り潰せた）。
    この形の再発を機械的に防ぐ。
    """
    offenders: list[str] = []
    for p in glob.glob(os.path.join(ROUTER_DIR, "*.py")):
        src = open(p, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            args = [a.arg for a in node.args.args]
            if not any(a.endswith("_id") for a in args):
                continue
            if not _calls_repo_mutation(node, GUARDED_MUTATIONS):
                continue
            if not _calls_any_marker(node, OWNERSHIP_MARKERS):
                offenders.append(f"{p}:{node.lineno} {node.name}")

    assert not offenders, (
        "entity_id を受ける変更系ハンドラに所有権ガードが無い:\n  "
        + "\n  ".join(offenders)
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
