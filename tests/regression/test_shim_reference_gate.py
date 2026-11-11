r"""R2 ゲート: 各 shim の旧パス参照がベースラインと一致することを強制する。

- 増加: 新しい旧パス参照が出たら fail（削除前の R2 達成を強制）
- 減少: 参照が解消されたら fail（ベースライン引き下げを促し、ラチェットが自走する）
- スキャン範囲: git ls-files で追跡済み .py を全件列挙（ルートの手動列挙を禁止）

設計上の注意:
- ``src.config.X`` が ``config.X`` の部分一致で誤検出されないよう、負の先読み
  ``(?<![\w.])`` と単語境界 ``\b`` を付けてパターンを構築する。
- strict (実 import) と loose (文字列 mentions / docstring / monkeypatch 等) を
  別々に集合比較する。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "shim_registry.json"
BASELINE_PATH = ROOT / "config" / "shim_reference_baseline.json"

registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
SHIMS: list[str] = registry["shims"]

baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
BASELINE_VIOLATIONS: dict = baseline.get("violations", {})
BASELINE_MENTIONS: dict = baseline.get("mentions", {})


def _tracked_py_files() -> list[Path]:
    """git ls-files で追跡済み .py を全件取得（ルート手動列挙禁止）。"""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    return [ROOT / p for p in result.stdout.split("\x00") if p]


def _strict_imports(content: str) -> set[str]:
    """ast で import 文を走査し、import 対象モジュールのフルパスを返す。"""
    found: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _scan(shim_path: str) -> tuple[set[str], set[str]]:
    """指定 shim の strict imports / loose mentions をスキャンする。

    Returns:
        (strict_files, mention_files): 相対パス文字列の集合。
    """
    if not shim_path.endswith(".py"):
        return set(), set()
    # shim_path は 'config/constants.py' 形式 → モジュールパス 'config.constants'
    mod = shim_path[:-3].replace("/", ".")
    needle = mod
    # 負の先読み + 単語境界で 'src.config.X' や 'config.X_y' の誤検出を防ぐ
    strict_pat = re.compile(rf"(?<![\w.]){re.escape(needle)}\b")
    strict_files: set[str] = set()
    mention_files: set[str] = set()
    for py_file in _tracked_py_files():
        if str(py_file) == str(ROOT / shim_path):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if needle not in content:
            continue  # high-speed pre-filter before ast parse
        imports = _strict_imports(content)
        if mod in imports:
            strict_files.add(str(py_file.relative_to(ROOT)))
        if strict_pat.search(content):
            mention_files.add(str(py_file.relative_to(ROOT)))
    return strict_files, mention_files


def _all_shim_scans() -> dict[str, tuple[set[str], set[str]]]:
    """全 shim のスキャン結果を {shim_path: (strict, mentions)} で返す。"""
    result: dict[str, tuple[set[str], set[str]]] = {}
    for shim_path in SHIMS:
        result[shim_path] = _scan(shim_path)
    return result


def _diff_message(
    shim_path: str,
    kind: str,
    actual: set[str],
    expected: set[str],
) -> str:
    added = sorted(actual - expected)
    removed = sorted(expected - actual)
    lines = [f"{shim_path}: {kind} 一致不全"]
    if added:
        lines.append(f"  新規違反（ベースラインに無い参照）: {added}")
    if removed:
        lines.append(f"  解消済み（ベースラインから削除が必要）: {removed}")
    lines.append("  shim_reference_baseline.json を同一コミットで更新すること。")
    return "\n".join(lines)


@pytest.mark.parametrize("shim_path", SHIMS)
def test_shim_strict_references_match_baseline(shim_path):
    """strict imports がベースラインと完全に一致すること。

    baseline に登録されている shim のみチェック対象とし、
    baseline 未登録（R2 対象外／未着手）の shim は skip する。
    baseline に登録済みで strict import が増減した場合は fail し、
    削除前の R2 達成とベースライン引き下げを強制する。
    """
    if shim_path not in BASELINE_VIOLATIONS:
        pytest.skip(f"{shim_path}: baseline に violations エントリが無い（R2 未着手）")
    actual_strict, _ = _scan(shim_path)
    expected = set(BASELINE_VIOLATIONS[shim_path]["files"])
    if actual_strict != expected:
        pytest.fail(_diff_message(shim_path, "strict imports", actual_strict, expected))


@pytest.mark.parametrize("shim_path", SHIMS)
def test_shim_loose_mentions_match_baseline(shim_path):
    """loose mentions (文字列出現/docstring/monkeypatch 等) がベースラインと一致すること。

    baseline に登録がない shim はノイズ源（docstring 等）になりうるため
    チェック対象外とし、baseline 登録済みのみ集合比較する。
    """
    if shim_path not in BASELINE_MENTIONS:
        pytest.skip(f"{shim_path}: baseline に mentions エントリが無い（チェック対象外）")
    _, actual_mentions = _scan(shim_path)
    expected = set(BASELINE_MENTIONS.get(shim_path, []))
    if actual_mentions != expected:
        pytest.fail(_diff_message(shim_path, "loose mentions", actual_mentions, expected))


def test_baseline_entries_have_required_fields():
    """baseline の各違反エントリに reason と todo があること（理由なし例外禁止）。"""
    for shim_path, entry in BASELINE_VIOLATIONS.items():
        assert isinstance(entry, dict), f"{shim_path}: エントリがオブジェクトでない"
        assert entry.get("reason"), f"{shim_path}: reason が未記入"
        assert entry.get("todo"), f"{shim_path}: todo (TODO(R3-NN)) が未記入"
        assert "TODO(R3-" in entry["todo"], f"{shim_path}: todo の形式が不正: {entry['todo']}"


def test_baseline_commit_recorded():
    """baseline_commit が記録されていること。"""
    assert baseline.get("baseline_commit"), "baseline_commit が未記録"


def test_scan_note_recorded():
    """scan_note が記録されていること。"""
    assert baseline.get("scan_note"), "scan_note が未記録"
