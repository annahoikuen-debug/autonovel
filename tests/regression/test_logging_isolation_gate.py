"""Alembic が既存のロガーを一括無効化していないことのゲート。

何が起きたか
------------
2026-10-04 の公開前調査で、`tests/regression/test_v53_long_form_integrity.py` の
2 件が**単独では PASS なのに、他のテストを先に実行すると FAIL する**ことが判明した。

連鎖（実測で特定）:

1. `tests/unit/core/test_core_without_plugins.py:59` と
   `tests/unit/api/test_plugin_conditional_routing.py:24` が
   `sys.modules.pop("src.backend.server")` → 再 import
2. `tests/unit/test_graphrag.py` の `client` フィクスチャが `with TestClient(app)` で
   lifespan を発火
3. lifespan → `init_db()` → `_run_alembic_upgrade()`
   → `src/backend/alembic/env.py` が `logging.config.fileConfig(...)` を呼ぶ
4. `fileConfig` の `disable_existing_loggers` 既定が **True** のため、
   それまでに生成済みのロガー（実測 500 個）が**すべて** `disabled=True` になる
5. `caplog.at_level(...)` は level だけを下げ `disabled` は解除しないため、
   以降のログ依存テストが無言で失敗する

最小再現（修正前）:
    pytest tests/unit/core/test_core_without_plugins.py \
           tests/unit/test_graphrag.py::test_graph_router \
           tests/regression/test_v53_long_form_integrity.py
    → 2 failed（disabled_loggers: 0 → 286）

修正: `env.py` に `disable_existing_loggers=False` を明示。

本ファイルは再発防止の**静的ゲート**である。実際のプロセス内変化ではなく、
ソースが意図どおりの引数を持つことを確認する。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ENV_PY = Path("src/backend/alembic/env.py")


@pytest.mark.integration
class TestAlembicDoesNotDisableExistingLoggers:
    """`fileConfig` 呼び出しが既存ロガーを無効化しないこと。"""

    def test_env_py_exists(self) -> None:
        assert ENV_PY.exists(), f"{ENV_PY} が見つからない"

    def test_fileconfig_call_passes_disable_existing_loggers_false(self) -> None:
        """`logging.config.fileConfig(...)` に `disable_existing_loggers=False` が渡ること。

        Python 標準の既定は True なので、明示されていない限り
        プロセス内の全ロガーが無効化される。これは意図した挙動ではない。
        """
        source = ENV_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)

        fileconfig_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # logging.config.fileConfig(...) または fileConfig(...)
            is_fileconfig = (
                isinstance(func, ast.Attribute) and func.attr == "fileConfig"
            ) or (isinstance(func, ast.Name) and func.id == "fileConfig")
            if is_fileconfig:
                fileconfig_calls.append(node)

        assert fileconfig_calls, (
            f"{ENV_PY} に fileConfig の呼び出しが見つからない。"
            "テストの前提が古くなっている可能性"
        )

        offenders = []
        for call in fileconfig_calls:
            kwargs = {k.arg: k.value for k in call.keywords if k.arg}
            node_value = kwargs.get("disable_existing_loggers")
            if node_value is None or not (
                isinstance(node_value, ast.Constant) and node_value.value is False
            ):
                offenders.append(ast.dump(call)[:120])

        assert not offenders, (
            "fileConfig に disable_existing_loggers=False が明示されていない呼び出しがあります。"
            "Python の既定は True で、プロセス内の全ロガーが無言で無効化されます:\n"
            + "\n".join(offenders)
        )

    def test_no_bare_fileconfig_remains(self) -> None:
        """引数なしの `fileConfig(path)` 形式の呼び出しが残っていないこと。"""
        source = ENV_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_fileconfig = (
                isinstance(func, ast.Attribute) and func.attr == "fileConfig"
            ) or (isinstance(func, ast.Name) and func.id == "fileConfig")
            if not is_fileconfig:
                continue
            assert len(node.args) == 1, (
                "fileConfig の呼び出し形が想定と異なる。"
                "disable_existing_loggers の明示を追加したか確認すること"
            )
