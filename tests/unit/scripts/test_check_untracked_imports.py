"""scripts/check_untracked_imports.py の感度テスト。

--strict で allowlist に実在モジュールが含まれる（陳腐化）場合に exit 1 にすることを検証する。
"""

import json
from pathlib import Path

from scripts import check_untracked_imports


def _write_allowlist(tmp_path, extra_entries=None):
    """デフォルト allowlist をコピーして extra_entries を追加した一時ファイルを返す。"""
    default = Path("config/untracked_imports_allowlist.json")
    data = json.loads(default.read_text(encoding="utf-8"))
    if extra_entries:
        data["entries"].extend(extra_entries)
    p = tmp_path / "allowlist.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(p)


def test_strict_mode_fails_on_stale_allowlist(tmp_path, monkeypatch):
    """--strict で allowlist に実在モジュールが含まれると exit 1 になること。"""
    allowlist_path = _write_allowlist(
        tmp_path,
        [
            {
                "test": "tests/unit/publishing/exporters/exporters/test_base.py",
                "module": "src.publishing.exporters.base",  # 実在モジュール
            }
        ],
    )

    monkeypatch.setattr(
        "sys.argv",
        ["check_untracked_imports.py", "--strict", "--allowlist", allowlist_path],
    )
    rc = check_untracked_imports.main()
    assert rc == 1


def test_non_strict_mode_passes_on_stale_allowlist(tmp_path, monkeypatch):
    """通常実行（--strict なし）では陳腐化 allowlist でも exit 0 になること。"""
    allowlist_path = _write_allowlist(
        tmp_path,
        [
            {
                "test": "tests/unit/publishing/exporters/exporters/test_base.py",
                "module": "src.publishing.exporters.base",  # 実在モジュール
            }
        ],
    )

    monkeypatch.setattr(
        "sys.argv",
        ["check_untracked_imports.py", "--allowlist", allowlist_path],
    )
    rc = check_untracked_imports.main()
    assert rc == 0
