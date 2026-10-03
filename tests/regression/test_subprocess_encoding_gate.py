"""Windows 環境での subprocess エンコーディング事故再発防止ゲート。

何が起きたか
------------
`tests/regression/test_status_md_counts_match_reality.py` は pytest を
サブプロセスで起動してテスト件数を数えていたが、`text=True` のみで
`encoding=` を指定していなかった。

Windows の既定エンコーディングは CP932（日本語 Shift_JIS）だが、
pytest の出力は UTF-8。日本語を含むテスト名を含む出力に対して
`UnicodeDecodeError: 'cp932' codec can't decode byte 0x82` が発生し、
**リグレッションゲート自体が collection 不能になって黙って無効化された**。

このテストは、pytest を起動する subprocess 呼び出しが `encoding=` を
明示していないことを静的検査し、再発を機械的に防ぐ。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path("tests")

_SUBPROCESS_METHODS = {"run", "check_output", "check_call", "Popen"}


def _iter_subprocess_calls() -> list[tuple[str, int, ast.Call]]:
    """tests/ 配下の subprocess 呼び出しを (ファイル, 行, Call) で列挙する。"""
    found: list[tuple[str, int, ast.Call]] = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            # collection で落ちるファイルは別のゲートが扱う
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_METHODS
            ):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "subprocess":
                continue
            found.append((str(path), node.lineno, node))
    return found


def _invokes_pytest(call: ast.Call) -> bool:
    """その呼び出しが pytest を起動しているかを保守的に判定する。"""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if "pytest" in arg.value:
                return True
    first = call.args[0] if call.args else None
    if isinstance(first, (ast.List, ast.Tuple)):
        for element in first.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                token = element.value
                if token == "pytest" or token.endswith("pytest.exe"):
                    return True
                # `python -m pytest` 形式
                if token == "-m" or token.endswith("-m"):
                    return True
    return False


def _is_text_mode(call: ast.Call) -> bool:
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    for name in ("text", "universal_newlines"):
        node = kw.get(name)
        if isinstance(node, ast.Constant) and node.value is True:
            return True
    return False


@pytest.mark.integration
class TestSubprocessEncodingIsExplicit:
    """pytest を起動する subprocess は必ず encoding= を明示すること。"""

    def test_no_pytest_subprocess_call_without_encoding(self) -> None:
        offenders: list[str] = []
        for path, lineno, call in _iter_subprocess_calls():
            if not _is_text_mode(call):
                continue
            if "encoding" in {k.arg for k in call.keywords if k.arg}:
                continue
            if not _invokes_pytest(call):
                continue
            offenders.append(f"{path}:{lineno}: pytest を text=True で起動し encoding= がない")

        assert not offenders, (
            "pytest サブプロセスに encoding= がありません。"
            "Windows(CP932) では UTF-8 出力をデコードできず、"
            "対象のゲートが collection ERROR で黙って無効化されます:\n"
            + "\n".join(offenders)
        )

    def test_gate_detects_the_known_offender_pattern(self) -> None:
        """ゲートが実際の問題のある呼び出しを検出できることを自己確認。

        ゲート自身が無条件に通る実装だと何も防げないため、
        検出ロジックが機能していることを最小の入力で確認する。
        """
        code = (
            "import subprocess\n"
            "subprocess.run(['-m', 'pytest', '--collect-only'], text=True)\n"
        )
        call = next(
            node
            for node in ast.walk(ast.parse(code))
            if isinstance(node, ast.Call)
        )
        assert _is_text_mode(call) is True
        assert _invokes_pytest(call) is True
        assert "encoding" not in {k.arg for k in call.keywords if k.arg}

    def test_this_gate_itself_is_importable(self) -> None:
        """ゲート自身が collection 不能になっていないことの確認。"""
        # 到達できれば collection は成功している
        assert _iter_subprocess_calls() is not None
