"""``src/backend/routers/*.py`` のうち ``server.py`` でマウントされていないものを検出する。

``orchestrated.py`` は frontend から実際に呼ばれていたがマウントされておらず、
常に 404 になっていた。本テストはその classes of 不一致を恒久的に検出する。
"""
from __future__ import annotations

import glob
import os
import re

# 同一 basename が 2 つ以上 ROUTERS ディレクトリに存在しない前提
ROUTER_DIR = "src/backend/routers"
SERVER = "src/backend/server.py"


def _router_files():
    return {
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(ROUTER_DIR, "*.py"))
        if not os.path.basename(p).startswith("__")
    }


def _mounted_names() -> set[str]:
    src = open(SERVER, encoding="utf-8").read()
    return set(re.findall(r"include_router\(\s*([a-z_0-9]+)\.router", src))


def test_every_router_module_is_mounted_or_explicitly_allowlisted():
    mounted = _mounted_names()
    unmounted = sorted(_router_files() - mounted)
    # metrics は server.py:223 の独立 /metrics エンドポイントと役割が重複するため
    # 「意図的にマウントしない」ことが文書化されている。
    allowlist = {"metrics"}
    unexpected = sorted(set(unmounted) - allowlist)
    assert not unexpected, (
        "マウントされていない router がある（フロントは 404 になる）: "
        f"{unexpected}。server.py に include_router を追加するか、allowlist に明記すること。"
    )


def test_orchestrated_is_mounted():
    src = open(SERVER, encoding="utf-8").read()
    assert "orchestrated" in src, "orchestrated router が server.py に存在しない"
