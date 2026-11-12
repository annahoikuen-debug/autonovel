"""環境変数直接代入の衛生管理テスト.

tests/ 配下で os.environ[...] = や os.environ.setdefault を
直接使う代わりに、monkeypatch.setenv を使うことを強制する。
try/finally で元の値を復元しているファイルは ALLOWED_FILES に
列挙して許可する。

将来、新しいファイルで直接代入を追加した場合は本テストが赤になり、
レビューで monkeypatch.setenv への書き換えを求める。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TESTS_DIR = Path("tests")

# try/finally で環境変数を保存・復元しているため許可するファイル。
# これら以外は monkeypatch.setenv に書き換えること。
ALLOWED_FILES = {
    "tests/conftest.py",
    "tests/contract/test_v6_audit_gate_thresholds.py",
    "tests/infrastructure/test_monitoring_init.py",
    "tests/integration/test_regression_phase4.py",
    "tests/mocks/test_harness.py",
    "tests/regression/test_alembic_env_isolation.py",
    "tests/regression/test_auth_bypass_contract.py",
    # 自分自身（docstring にパターン文字列を含むため除外）
    "tests/regression/test_env_var_hygiene.py",
    # モジュールロード時に ENABLE_AUDIT_LEGACY_CORE=true を設定。レガシーコア監査
    # のモック差し替えのため必須。monkeypatch.setenv はモジュールレベルでは
    # 使用できないため許可。
    "tests/contract/test_v6_audit_parallel_equivalence.py",
    "tests/unit/api/test_stream_writing.py",
    "tests/unit/test_logging_config.py",
    "tests/unit/test_marketing_agent.py",
    "tests/unit/api/test_illustration_router.py",
    "tests/branches/test_e2e_rest.py",
}

# os.environ[...] = 形式の直接代入パターン
ENV_ASSIGN_RE = re.compile(r"os\.environ\[.*?\]\s*=")
ENV_SETDEFAULT_RE = re.compile(r"os\.environ\.setdefault\(")


def _find_env_assignments(py_file: Path) -> list[tuple[int, str]]:
    """ファイル内の環境変数直接代入行を (行番号, 行内容) で返す。"""
    found = []
    try:
        text = py_file.read_text(encoding="utf-8")
    except OSError:
        return found
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if ENV_ASSIGN_RE.search(line) or ENV_SETDEFAULT_RE.search(line):
            found.append((i, line.rstrip()))
    return found


def test_no_new_env_direct_assignment_without_monkeypatch() -> None:
    """tests/ 下で環境変数直接代入が許可リスト外にないこと.

    許可リスト外のファイルで os.environ[...] = や
    os.environ.setdefault を直接使っている場合は赤。
    monkeypatch.setenv に書き換えるか、try/finally で復元する場合は
    ALLOWED_FILES に追加すること。
    """
    violations: dict[str, list[tuple[int, str]]] = {}
    for py_file in sorted(TESTS_DIR.rglob("*.py")):
        rel = str(py_file.relative_to(Path(".")))
        if rel in ALLOWED_FILES:
            continue
        found = _find_env_assignments(py_file)
        if found:
            violations[rel] = found

    assert not violations, (
        "tests/ 下で環境変数直接代入が検出されました。monkeypatch.setenv に書き換えるか、\n"
        "try/finally で復元する場合は ALLOWED_FILES に追加してください:\n"
        + "\n".join(
            f"  {file}:" + "\n".join(f"    L{no}: {code}" for no, code in lines)
            for file, lines in violations.items()
        )
    )
