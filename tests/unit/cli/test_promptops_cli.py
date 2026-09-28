"""src/cli/promptops.py の単体テスト。"""
from __future__ import annotations

import sys

import pytest

from src.cli import promptops


def test_init_command_creates_scaffold(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    promptops.init_command(None)
    out = capsys.readouterr().out
    assert "scaffold created successfully" in out
    assert (tmp_path / "src" / "promptops" / "__init__.py").exists()
    assert (tmp_path / "src" / "promptops" / "registry.py").exists()
    assert (tmp_path / "tests" / "promptops" / "test_registry.py").exists()
    # 2 回目はスキャフォールドファイルが既存なので作られない
    promptops.init_command(None)
    assert "Created: src/promptops/registry.py" not in capsys.readouterr().out


def test_list_templates_missing_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    promptops.list_templates_command(None)
    assert "No prompts directory found." in capsys.readouterr().out


def test_list_templates_no_templates(tmp_path, monkeypatch, capsys):
    (tmp_path / "prompts").mkdir()
    monkeypatch.chdir(tmp_path)
    promptops.list_templates_command(None)
    assert "No .j2 templates found" in capsys.readouterr().out


def test_list_templates_with_files(tmp_path, monkeypatch, capsys):
    (tmp_path / "prompts" / "sub").mkdir(parents=True)
    (tmp_path / "prompts" / "a.j2").write_text("x", encoding="utf-8")
    (tmp_path / "prompts" / "sub" / "b.j2").write_text("y", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    promptops.list_templates_command(None)
    out = capsys.readouterr().out
    assert "a.j2" in out
    assert "sub" in out


def test_version_command(capsys, monkeypatch):
    module = type(sys)("src.promptops.registry")
    module.__version__ = "9.9.9"
    monkeypatch.setitem(sys.modules, "src.promptops.registry", module)
    promptops.version_command(None)
    assert "PromptOps 9.9.9" in capsys.readouterr().out


class TestPromptOpsMain:
    def test_version(self, monkeypatch, capsys):
        module = type(sys)("src.promptops.registry")
        module.__version__ = "1.2.3"
        monkeypatch.setitem(sys.modules, "src.promptops.registry", module)
        monkeypatch.setattr(sys, "argv", ["promptops", "version"])
        assert promptops.main() is None
        assert "PromptOps 1.2.3" in capsys.readouterr().out

    def test_list_templates(self, monkeypatch, capsys, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["promptops", "list-templates"])
        promptops.main()
        assert "No prompts directory found." in capsys.readouterr().out

    def test_init(self, monkeypatch, capsys, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["promptops", "init"])
        promptops.main()
        assert (tmp_path / "src" / "promptops").is_dir()

    def test_required_subcommand(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["promptops"])
        with pytest.raises(SystemExit):
            promptops.main()

    def test_unknown_command_branch(self, monkeypatch, capsys):
        import argparse
        import types as _types

        class FakeParser:
            def __init__(self):
                self.printed = False

            def add_subparsers(self, **kw):
                return self

            def add_parser(self, name, **kw):
                return argparse.ArgumentParser()

            def parse_args(self, argv=None):
                return argparse.Namespace(command="nope")

            def print_help(self):
                self.printed = True

        fake = _types.SimpleNamespace(ArgumentParser=lambda **kw: FakeParser())
        monkeypatch.setattr(promptops, "argparse", fake)
        monkeypatch.setattr(sys, "argv", ["promptops", "nope"])
        with pytest.raises(SystemExit):
            promptops.main()
