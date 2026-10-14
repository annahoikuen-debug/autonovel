"""官能関連ファイルの文字化け（ハングル・中国語簡体字・置換文字）スキャン一次ツール。"""

from __future__ import annotations

import pathlib
import re
import sys

SKIP = (".git", "node_modules", "__pycache__", ".venv", "autonovel_qa")
HANGUL = re.compile(r"[\uac00-\ud7af]")
# 日本語テキストでは通常出現しない中国語簡体字・常用外の頻出誤用字
CN = re.compile(
    "[\u4eec\u6837\u8fd9\u8bf4\u5bf9\u73b0\u8fc7\u8fd8\u8bc6\u89c9\u8111"
    "\u76ae\u80a4\u989c\u989d\u9888\u8109\u94c6\u6270\u6ed1\u6da6\u6e7f"
    "\u6c57\u6f02\u8131\u94fe\u94c1\u9519\u952e\u8bef]"
)
REPL = "\ufffd"


def main() -> int:
    hits: list[str] = []
    for p in pathlib.Path(".").rglob("*"):
        if p.suffix not in (".py", ".yaml", ".j2", ".json"):
            continue
        if any(x in str(p) for x in SKIP):
            continue
        if "test" in str(p).lower():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if HANGUL.search(line) or CN.search(line) or REPL in line:
                hits.append(f"{p}:{i}: {line.strip()[:100]}")
    print(f"total: {len(hits)}")
    for h in hits[:80]:
        print(h)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
