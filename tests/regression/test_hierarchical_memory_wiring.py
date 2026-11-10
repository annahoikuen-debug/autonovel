"""配線リグレッションテスト (PLAN_M1 Step 9).

`tests/regression/test_v53_wiring_reachability.py` の AST 手法を踏襲し、
階層的逐次要約メモリの配線が正しく到達可能であることを実行時静的検証する。

検証項目:
1. `episode_writer._persist_episode_digest` が RollupGenerator / DigestRollupRepository /
   upsert_rollup を呼んでいる（配線到達）
2. `RollupConfig` の env 読み取りは `rollup_config.py` のみ（SSOT）
3. 死蔵コードの `RollingMemoryBuilder` が本番モジュールから import されていない
4. `episode_writer.py` が rollup 生成を try/except で囲んでいる（fail-open）
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SRC = ROOT_DIR / "src"


def _source_of(relative_path: str) -> str:
    return (SRC / relative_path).read_text(encoding="utf-8")


def _tree_of(relative_path: str) -> ast.Module:
    return ast.parse(_source_of(relative_path))


def _find_function(tree: ast.Module, name: str) -> ast.AST | None:
    """関数名で AST ノードを探す（async def も含む）。"""
    func_types = (ast.FunctionDef, getattr(ast, "AsyncFunctionDef", ast.FunctionDef))
    for node in ast.walk(tree):
        if isinstance(node, func_types) and node.name == name:
            return node
    return None


def _called_attrs(node: ast.AST) -> set[str]:
    """AST 内で呼び出されている属性名（メソッド呼び出し）の集合。"""
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            calls.add(child.func.attr)
    return calls


class TestRollupConfigSsoT:
    """RollupConfig の env 読み取りが rollup_config.py のみに集約されている。"""

    def test_rollup_config_env_read_only_in_rollup_config(self):
        """os.getenv / getenv による rollup 関連 env は rollup_config.py のみ。"""
        rollup_config_tree = _tree_of("engine/context_compression/rollup_config.py")
        rollup_config_calls = _called_attrs(rollup_config_tree)

        # rollup_config.py 自体は getenv を使う（許可）
        assert "getenv" in rollup_config_calls, "rollup_config.py should call os.getenv"

        # 他の本番モジュールでは rollup 関連 env を直接読まない
        rollup_env_names = {
            "ENABLE_DIGEST_ROLLUP",
            "DIGEST_EPISODES_PER_BLOCK",
            "DIGEST_BLOCKS_PER_VOLUME",
            "ENABLE_PINNED_FACTS_EDGES",
            "DIGEST_COD_ROUNDS",
            "DIGEST_BLOCK_MAX_CHARS",
            "DIGEST_VOLUME_MAX_CHARS",
        }

        for py_file in SRC.rglob("*.py"):
            if "test" in py_file.parts:
                continue
            rel = py_file.relative_to(SRC)
            if str(rel) == "engine/context_compression/rollup_config.py":
                continue
            source = py_file.read_text(encoding="utf-8")
            for env_name in rollup_env_names:
                assert env_name not in source, (
                    f"{rel} directly references rollup env {env_name}; "
                    f"use RollupConfig.from_env() instead"
                )


class TestPersistEpisodeDigestWiring:
    """`_persist_episode_digest` に rollup 生成が配線されている。"""

    def test_persist_episode_digest_calls_rollup_methods(self):
        tree = _tree_of("agents/writing/episode_writer.py")
        func = _find_function(tree, "_persist_episode_digest")
        assert func is not None, "_persist_episode_digest not found"

        calls = _called_attrs(func)
        assert "generate_block_rollup" in calls, (
            "_persist_episode_digest が generate_block_rollup を呼んでいない"
        )
        assert "generate_volume_rollup" in calls, (
            "_persist_episode_digest が generate_volume_rollup を呼んでいない"
        )
        assert "upsert_rollup" in calls, (
            "_persist_episode_digest が upsert_rollup を呼んでいない"
        )

    def test_rollup_config_imported_in_episode_writer(self):
        tree = _tree_of("agents/writing/episode_writer.py")
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        modules = {node.module for node in imports}
        assert "src.engine.context_compression.rollup_config" in modules, (
            "episode_writer.py が RollupConfig を import していない"
        )

    def test_rollup_generation_is_fail_open(self):
        """rollup 生成が try/except で囲まれている（fail-open）。"""
        source = _source_of("agents/writing/episode_writer.py")
        tree = _tree_of("agents/writing/episode_writer.py")
        func = _find_function(tree, "_persist_episode_digest")
        assert func is not None

        # メソッド内に try ノードが存在する
        has_try = any(isinstance(node, ast.Try) for node in ast.walk(func))
        assert has_try, "_persist_episode_digest に try/except がない（fail-open でない）"


class TestRollingMemoryNotInProduction:
    """死蔵コードの RollingMemoryBuilder が本番モジュールに混入していない。"""

    def test_rolling_memory_builder_not_imported_outside_test_and_self(self):
        for py_file in SRC.rglob("*.py"):
            if "test" in py_file.parts:
                continue
            rel = py_file.relative_to(SRC)
            if str(rel) == "engine/context_compression/rolling_memory.py":
                continue
            source = py_file.read_text(encoding="utf-8")
            assert "RollingMemoryBuilder" not in source, (
                f"{rel} imports RollingMemoryBuilder (dead code in production)"
            )
