r"""PowerShell スクリプトに UTF-8 BOM を付与する。

Windows PowerShell 5.1 は日本語システムでは .ps1 を既定で Shift-JIS(ANSI) として読む。
UTF-8 のまま BOM 無しで保存すると、日本語を含む文字列リテラルが壊れて
変数に null が入る・引用符が消えるといった不可解なエラーになる。

使い方:
    python scripts/fix_ps1_encoding.py            # scripts\ 配下とリポジトリ直下を処理
    python scripts/fix_ps1_encoding.py --check    # BOM が無いファイルを報告するだけ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"
SKIP_DIRS = {"node_modules", ".git", ".venv", "__pycache__", "dist", "build", "storage", "logs"}


def iter_scripts() -> list[Path]:
    targets: list[Path] = []
    # リポジトリ直下（日本語名の .bat/.ps1 を含む）
    for path in sorted(ROOT.iterdir()):
        if path.is_file() and path.suffix.lower() in {".ps1", ".bat"}:
            targets.append(path)
    for base in (ROOT / "scripts", ROOT / "docker", ROOT / "deploy"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".ps1", ".bat"}:
                targets.append(path)
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, do not modify")
    args = parser.parse_args()

    missing: list[Path] = []
    for path in iter_scripts():
        raw = path.read_bytes()
        if raw.startswith(BOM):
            continue
        missing.append(path)
        if not args.check:
            path.write_bytes(BOM + raw)

    if not missing:
        print("[OK] all .ps1 / .bat files already have a UTF-8 BOM")
        return 0

    verb = "missing BOM" if args.check else "BOM added"
    print(f"[{verb}] {len(missing)} file(s):")
    for path in missing:
        print(f"  {path.relative_to(ROOT)}")

    if args.check:
        print("")
        print("fix: python scripts/fix_ps1_encoding.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
