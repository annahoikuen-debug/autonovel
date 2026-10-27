"""0032 で tenant FK が定義されていることの静的確認 + head 一意性。"""
from __future__ import annotations

import ast
import glob
import re

HEADS = {"0031_episode_digests"}


def test_0032_declares_fk_for_all_tenant_tables():
    path = "src/backend/alembic/versions/0032_tenant_user_fk.py"
    src = open(path, encoding="utf-8").read()
    for table in ("books", "branches", "chapters"):
        assert f"fk_{table}_user_id_users" in src, f"{table} の FK が未定義"


def test_0032_down_revision_is_current_head():
    src = open("src/backend/alembic/versions/0032_tenant_user_fk.py", encoding="utf-8").read()
    assert re.search(r'down_revision\s*=\s*"0031_episode_digests"', src)


def test_alembic_has_single_head():
    """Alembic チェーンに head が 1 つのみであること（分岐は禁止）。"""
    revisions: set[str] = set()
    down: set[str] = set()
    for path in glob.glob("src/backend/alembic/versions/*.py"):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if getattr(t, "id", None) == "revision":
                        revisions.add(ast.literal_eval(node.value))
                    if getattr(t, "id", None) == "down_revision":
                        try:
                            down.add(ast.literal_eval(node.value))
                        except ValueError:
                            pass
    heads = revisions - down
    assert len(heads) == 1, f"Alembic の head が {len(heads)} 個ある: {sorted(heads)}"
