"""`hasattr(self, "logger")` のデッドガードが復活していないことの回帰テスト。

T6 Step 2 の回帰防止。

`BaseAgent` はモジュールレベル `logger` のみを持ち、`self.logger` 属性は存在しない。
そのため `if hasattr(self, "logger"):` は常に False で、
伏線回収・ダイジェスト永続化・セッション型不一致などの警告が**恒久的に無言化**していた。

本テストは構造を検証することで、誰かが `self.logger` を再導入した瞬間に落ちる。
"""

import ast
import importlib
from pathlib import Path

TARGETS = [
    Path("src/agents/writing/episode_writer.py"),
    Path("src/agents/context_builder_agent.py"),
    Path("src/agents/audit_agent.py"),
    Path("src/agents/illustration_agent.py"),
]


def _iter_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "hasattr"
        ):
            yield node


def test_no_dead_logger_guard_remains():
    """`hasattr(self, "logger")` による無言化ガードが 1 件も存在しないこと。"""
    offenders = []
    for path in TARGETS:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _iter_calls(tree):
            if (
                len(node.args) == 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "self"
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "logger"
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert not offenders, f"デッドガードが残存: {offenders}"


def test_no_self_logger_attribute_access():
    """`self.logger.*` アクセスが残っていないこと（BaseAgent に属性は無い）。"""
    offenders = []
    for path in TARGETS:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "logger"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
            ):
                offenders.append(f"{path}:{node.lineno}")
    assert not offenders, f"self.logger 参照が残存: {offenders}"


def test_migrated_files_never_assign_self_logger():
    """移行対象ファイルが `self.logger = ...` を作っていないこと。

    代入があると上記2テストが false negative になる（屬性が生まれてしまう）ため、
    「属性を生む側」も同時に封印する。

    なお `src/backend/background.py` と `src/generation/fallback_generator.py` は
    正当に `self.logger` を生成して**実際に使用**しているため、
    本不変条件の対象外（移行対象は BaseAgent 継承のエージェント実装である）。
    """
    offenders = []
    for path in TARGETS:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            for tgt in targets:
                if (
                    isinstance(tgt, ast.Attribute)
                    and tgt.attr == "logger"
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "self"
                ):
                    offenders.append(f"{path}:{node.lineno}")
    assert not offenders, (
        "移行対象ファイルが self.logger を生成している"
        "（デッドガードの再導入に直結）: "
        f"{offenders}"
    )


def test_migrated_modules_still_import():
    """移行後も対象モジュールが import できること（構文の健全性）。"""
    for mod in (
        "src.agents.writing.episode_writer",
        "src.agents.context_builder_agent",
    ):
        importlib.import_module(mod)


def test_migrated_files_resolve_module_level_logger():
    """移行したファイルが、参照に使うモジュールレベル `logger` を実際に解決できること。

    文字列の出現ではなく **import して参照解決できる**ことを確認する。
    （ローカル変数 `logger = logging.getLogger(...)` が本文中に有ると、
    文字列マッチだと気づかない false negative になる。）
    """
    import importlib

    for mod in (
        "src.agents.writing.episode_writer",
        "src.agents.context_builder_agent",
    ):
        module = importlib.import_module(mod)
        resolved = getattr(module, "logger", None)
        assert resolved is not None, (
            f"{mod} にモジュールレベル logger が無い"
            "（置換結果が NameError になる）"
        )
        import logging

        assert isinstance(resolved, logging.Logger), (
            f"{mod}.logger が logging.Logger ではない: {type(resolved)}"
        )
