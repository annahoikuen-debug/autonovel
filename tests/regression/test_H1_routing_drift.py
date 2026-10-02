"""vite dev proxy と FastAPI の mount point のドリフトを双方向に検出する。

``frontend/vite.config.ts`` の proxy prefix と ``src/backend/server.py`` の
``include_router`` prefix は手動で同期されており、片方だけ直すと
「dev だけ 404」「dev だけ CORS」になる。ここでは両方向を機械的に突き合わせる。

- 前方: proxy しているのに backend が一切持たないパス（死んだ設定）
- 後方: backend が持つルートプレフィックスで proxy していないパス（dev で到達不能）
"""
from __future__ import annotations

import re

VITE = "frontend/vite.config.ts"
SERVER = "src/backend/server.py"

# FastAPI の組み込みドキュメント系。vite 自身が別のものを出すため対象外。
BUILTIN_PREFIXES = {"/docs", "/redoc", "/openapi.json"}

# server.py で条件付きマウントされる router。plugin_registry の設定に依存するため、
# 実行環境の app には現れないことがある。理由 必须。
CONDITIONAL_MOUNTS: dict[str, str] = {
    "/multimedia": "server.py:190 `plugin_registry.is_enabled('multimedia')` が true のときだけマウント",
}


def _vite_prefixes() -> set[str]:
    src = open(VITE, encoding="utf-8").read()
    return set(re.findall(r'^\s*["\']([^"\']+)["\']:\s*\{', src, re.M))


def _server_paths() -> set[str]:
    """app に実際に載っているルートパス（include_router 後の実測値）。"""
    from src.backend.server import app

    return {
        r.path for r in app.routes if isinstance(getattr(r, "path", None), str) and r.path.startswith("/")
    }


def _root_prefixes(paths: set[str]) -> set[str]:
    out = set()
    for p in paths:
        root = "/" + p.strip("/").split("/")[0]
        if root in BUILTIN_PREFIXES:
            continue
        out.add(root)
    return out


def _matches(prefix: str, paths: set[str]) -> list[str]:
    base = prefix.rstrip("/")
    return sorted(p for p in paths if p == base or p.startswith(base + "/"))


def test_every_vite_proxy_prefix_exists_on_the_server():
    """死んだ proxy 設定が無いこと（backend に 1 本も無い prefix を叩いても 404）。"""
    vite = _vite_prefixes()
    paths = _server_paths()
    dead = sorted(p for p in vite if not _matches(p, paths) and p not in CONDITIONAL_MOUNTS)
    assert not dead, (
        f"vite proxy にあるが backend が持たない prefix: {dead}。"
        " 該当 prefix の API が /api 配下へ移ったなら proxy 定義を削除すること。"
    )


def test_every_backend_root_prefix_is_proxied():
    """backend のルートプレフィックスがすべて dev proxy を通ること。

    漏れると dev だけ vite の index.html が返り、FE が JSON parse で落ちる。
    """
    vite = _vite_prefixes()
    server = _root_prefixes(_server_paths())
    unproxied = sorted(p for p in server if p not in vite and p not in CONDITIONAL_MOUNTS)
    assert not unproxied, (
        f"backend が持つが vite proxy に無い prefix: {unproxied}（dev からは到達不能）"
    )


def test_vite_proxy_has_no_typo_in_changeorigin():
    src = open(VITE, encoding="utf-8").read()
    assert "changeOrigin" in src, "vite proxy に changeOrigin が無い（host 変更が意図通りに動かない）"


def test_conditional_mounts_are_still_documented_in_vite_config():
    """条件付きマウントを allowlist に挙げたなら、vite 側にも理由コメントを残す。"""
    src = open(VITE, encoding="utf-8").read()
    for prefix, reason in CONDITIONAL_MOUNTS.items():
        assert f'"{prefix}"' in src, f"{prefix} の proxy が消えている（{reason}）"
        assert "plugin" in src.lower(), "条件付きマウントの理由コメントが vite.config.ts に無い"
