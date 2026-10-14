"""全プロジェクトの文字化け（ハングル・簡体字中国語・置換文字）スキャンツール。

使用法: python -X utf8 scripts/scan_project_garble.py
終了コード: 検出 0 件なら 0、1 件以上なら 1（CI 組み込み可能）。
"""

from __future__ import annotations

import pathlib
import re
import sys

SKIP_DIRS = (
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "autonovel_qa",
    "docs",
    "artifacts",
    "reports",
    "output",
    "monitoring",
)

# 置換文字（U+FFFD）・ハングル（日本語コードベースには出現しない）
HARD_BAD = re.compile("[\ufffd\uac00-\ud7af]")

# 簡体字中国語専用字（日本語では使わない誤混入頻出字）
CN_ONLY = re.compile(
    "[\u4eec\u6837\u8fd9\u8bf4\u8fc7\u8fd8\u8bc6\u89c9\u5f00\u5173"
    "\u5fc6\u996e\u9505\u70e7\u6da8\u542f\u52a8\u5e94\u8be5\u5b83]"
)


def scan() -> list[str]:
    hits: list[str] = []
    for p in pathlib.Path(".").rglob("*"):
        if p.suffix not in (".py", ".yaml", ".j2", ".yml", ".json", ".ts", ".tsx"):
            continue
        if any(x in str(p) for x in SKIP_DIRS):
            continue
        if "test" in str(p).lower():
            continue
        if p.name.startswith("scan_"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if HARD_BAD.search(line) or CN_ONLY.search(line):
                hits.append(f"{p}:{i}: {line.strip()[:110]}")
    return hits


def main() -> int:
    hits = scan()
    print(f"total: {len(hits)}")
    for h in hits:
        print(h)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
