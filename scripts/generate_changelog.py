#!/usr/bin/env python3
"""CHANGELOG 自動生成スクリプト（TRACK-R R4）。

Conventional Commits 形式の git コミットログを解析し、
CHANGELOG.md を自動生成する。

使い方:
    python scripts/generate_changelog.py           # CHANGELOG.md を出力（stdout）
    python scripts/generate_changelog.py --write   # CHANGELOG.md を直接更新
    python scripts/generate_changelog.py --tag v6.0.0  # 特定タグまでの変更を生成
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_PATH = ROOT / "CHANGELOG.md"

# Conventional Commits タイプの日本語表示名
TYPE_LABELS: dict[str, str] = {
    "feat": "機能追加",
    "fix": "バグ修正",
    "docs": "ドキュメント",
    "style": "コードスタイル",
    "refactor": "リファクタリング",
    "perf": "パフォーマンス改善",
    "test": "テスト",
    "chore": "雑務・ビルド",
    "ci": "CI/CD",
    "build": "ビルド",
    "revert": "リバート",
    "security": "セキュリティ",
}


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def _get_git_log(from_ref: str | None = None, to_ref: str = "HEAD") -> str:
    """git log を取得する。from_ref が指定されればその範囲、なければ全履歴."""
    if from_ref:
        cmd = ["git", "log", f"{from_ref}..{to_ref}", "--format=%s"]
    else:
        cmd = ["git", "log", "--format=%s"]
    return _run(cmd)


def _parse_commits(log_output: str) -> dict[str, list[tuple[str, str]]]:
    """コミットログをタイプ別にグループ化する.

    戻り値: {タイプ: [(スコープ, 件名), ...]}
    """
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    pattern = re.compile(r"^(?P<type>[a-z]+)(\((?P<scope>[^)]+)\))?: (?P<subject>.+)$")

    for line in log_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if not m:
            continue
        ctype = m.group("type")
        scope = m.group("scope") or ""
        subject = m.group("subject")
        grouped[ctype].append((scope, subject))

    return grouped


def _format_changelog_entry(version: str, grouped: dict[str, list[tuple[str, str]]]) -> str:
    """1 バージョン分の CHANGELOG エントリをフォーマットする."""
    lines: list[str] = []
    lines.append(f"## [{version}]")
    lines.append("")

    # タイプ順序（重要度の高い順）
    type_order = ["feat", "fix", "security", "perf", "refactor", "style", "test", "docs", "chore", "ci", "build", "revert"]

    for ctype in type_order:
        if ctype not in grouped:
            continue
        label = TYPE_LABELS.get(ctype, ctype)
        lines.append(f"### {label}")
        for scope, subject in grouped[ctype]:
            scope_text = f" ({scope})" if scope else ""
            lines.append(f"- {subject}{scope_text}")
        lines.append("")

    return "\n".join(lines)


def _get_latest_tag() -> str | None:
    """最新のタグを取得する."""
    try:
        return _run(["git", "describe", "--tags", "--abbrev=0"]).strip()
    except subprocess.CalledProcessError:
        return None


def generate_changelog(version: str = "Unreleased", from_ref: str | None = None) -> str:
    """CHANGELOG の更新エントリを生成する."""
    log_output = _get_git_log(from_ref)
    grouped = _parse_commits(log_output)

    if not grouped:
        return f"## [{version}]\n\n(変更なし)\n"

    return _format_changelog_entry(version, grouped)


def main() -> int:
    parser = argparse.ArgumentParser(description="CHANGELOG 自動生成スクリプト")
    parser.add_argument("--write", action="store_true", help="CHANGELOG.md を直接更新")
    parser.add_argument("--tag", default=None, help="生成対象のタグ名（指定すればそのタグまでの変更を生成）")
    args = parser.parse_args()

    version = args.tag or "Unreleased"
    from_ref = args.tag if args.tag else None

    changelog_entry = generate_changelog(version, from_ref)

    if args.write:
        # 既存の CHANGELOG.md を読み込み、先頭に新規エントリを挿入
        existing = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else ""
        # 既存の [Unreleased] セクションがあれば置き換え
        if "## [Unreleased]" in existing:
            parts = existing.split("## [Unreleased]", 1)
            header = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            # 次の ## [バージョン] または ## [Unreleased] までを旧エントリとして扱う
            new_content = header + changelog_entry + "\n" + rest
        else:
            new_content = existing + "\n" + changelog_entry + "\n"
        CHANGELOG_PATH.write_text(new_content, encoding="utf-8")
        print(f"CHANGELOG.md を更新しました（バージョン: {version}）")
    else:
        print(changelog_entry)

    return 0


if __name__ == "__main__":
    sys.exit(main())
