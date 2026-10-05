"""B-T3: 「死んだコード」の再発防止（AST 静的テスト）。

今回 `EpisodeWriter.build_context()` は **呼び出し元 0 件**で、
契約伏線 ID・3層記憶がプロンプトに載らないまま dead-letter になっていた。
同じ症状（定義はあるが誰も呼ばない）が再発しないことを AST で固定する。

対象:
  - `EpisodeWriter.build_context()`（旧 `_build_full_context` 相当）
    に **呼び出し元が 1 件以上**あること
  - その呼び出しが `run()` 経路からuelleこと
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EPISODE_WRITER_PY = ROOT / "src" / "agents" / "writing" / "episode_writer.py"
GENERATOR_PY = ROOT / "src" / "agents" / "writing" / "generator.py"


def _method_call_sites(relative_path: str, method_name: str) -> list[tuple[str, int]]:
    """``self.<method_name>(...)`` の呼び出し箇所を ``(関数名, 行番号)`` で返す。"""
    tree = ast.parse((ROOT / relative_path).read_text("utf-8"))
    sites: list[tuple[str, int]] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == method_name
                and isinstance(func.value, ast.Name)
                and func.value.id == "self"
            ):
                sites.append((".".join(self.scope) or "<module>", node.lineno))
            self.generic_visit(node)

    _Visitor().visit(tree)
    return sites


def _defines_method(relative_path: str, class_name: str, method_name: str) -> bool:
    tree = ast.parse((ROOT / relative_path).read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == method_name
                for item in node.body
            )
    return False


class TestBuildContextIsReachable:
    def test_build_context_is_defined(self) -> None:
        assert _defines_method(
            "src/agents/writing/episode_writer.py", "EpisodeWriter", "build_context"
        ), "EpisodeWriter.build_context が定義されていない（前提の変化）"

    def test_build_context_has_at_least_one_call_site(self) -> None:
        """B-T3 核心: 呼び出し元 0 件 = 死んだコード。1件以上 있어야 한다。"""
        sites = _method_call_sites(
            "src/agents/writing/episode_writer.py", "build_context"
        )
        assert sites, (
            "EpisodeWriter.build_context() の呼び出し元が 0 件。"
            "契約伏線 ID / 3層記憶がプロンプトに載らない dead-letter に regress した。"
        )

    def test_build_context_called_from_run(self) -> None:
        """統合点は `run()` 経路であること（=` write() から直接ではない）。"""
        sites = _method_call_sites(
            "src/agents/writing/episode_writer.py", "build_context"
        )
        # `build_context` は `_merge_full_context` から呼ばれ、
        # `_merge_full_context` は `run()` から呼ばれる（2段配線）。
        assert any(
            scope.endswith("_merge_full_context") for scope, _ in sites
        ), f"build_context の呼び出し元が _merge_full_context ではない: {sites}"

        merge_sites = _method_call_sites(
            "src/agents/writing/episode_writer.py", "_merge_full_context"
        )
        assert any(scope.endswith("run") for scope, _ in merge_sites), (
            f"_merge_full_context が run() から呼ばれていない: {merge_sites}"
        )

    def test_generator_defines_writing_generator(self) -> None:
        """前提の固定: `generator.py` に `WritingGenerator` があること。"""
        assert _defines_method(
            "src/agents/writing/generator.py", "WritingGenerator", "_write_single_episode_core"
        )


class TestNoWholesaleContextReplacement:
    """B-T4 の静的側面: マージは「置換」ではないこと。"""

    def test_run_does_not_assign_raw_context_builder_output(self) -> None:
        """`run()` が `build_context()` の戻り値を `writing_context` に
        **直接代入**していないこと（直接代入 = 既存 context の丸ごと置換で退行する）。

        許可されるのは `_merge_full_context()`（マージ関数）経由の代入のみ。
        """
        source = EPISODE_WRITER_PY.read_text("utf-8")
        tree = ast.parse(source)

        run_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
                run_fn = node
                break
        assert run_fn is not None, "EpisodeWriter.run が見つからない"

        direct_assignment = False
        for node in ast.walk(run_fn):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if not isinstance(value, (ast.Call, ast.Await)):
                continue
            call = value.value if isinstance(value, ast.Await) else value
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr != "build_context":
                continue
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "writing_context":
                    direct_assignment = True

        assert not direct_assignment, (
            "run() が build_context() の戻り値を writing_context に直接代入している。"
            "既存 context（target_word_count 等）の丸ごと置換になる。"
        )
        assert "_merge_full_context" in source
