"""フロントの HTTP クライアントが認証ヘッダを素通りしていないことの archangel。

``frontend/src/api/client.ts:56-63`` の ``apiFetch`` だけが ``Authorization`` を注入する。
生 ``fetch(`` は認証が必要なエンドポイントで 401 になる。
"""
from __future__ import annotations

import glob
import os
import re

# テスト・モック・未認証前提・または今後 apiFetch 移行予定のファイル
ALLOWLIST: set[str] = {
    # テスト/モック内の fetch は対象外
    "frontend/tests/**",
    "frontend/e2e/**",
    # 認証エンドポイント自体（token 取得前なので Authorization なし）
    "frontend/src/context/AuthContext.tsx",
    # 未使用・孤立フック
    "frontend/src/hooks/_unused/useCollabSync.ts",
    # 公開静的設定 planning_options 取得コンポーネント
    # TODO(H1-4): apiFetch へ移行
    "frontend/src/constants/genres.ts",
    "frontend/src/components/generate/SimpleModePanel.tsx",
    "frontend/src/components/planning/BeatSheetViewer.tsx",
    "frontend/src/components/wizard/Step1PlotInput.tsx",
    # マルチメディア資産ダウンロード（バイナリ stream）
    # TODO(H1-4): apiFetch へ移行
    "frontend/src/api/multimedia.ts",
}

TARGET_GLOB = "frontend/src/**/*.ts"
TARGET_GLOB2 = "frontend/src/**/*.tsx"

FETCH_RE = re.compile(r"(?<!api)\bfetch\s*\(")
HEADER_RE = re.compile(r"Authorization", re.IGNORECASE)


def _files() -> list[str]:
    files = glob.glob(TARGET_GLOB, recursive=True) + glob.glob(TARGET_GLOB2, recursive=True)
    return [f.replace("\\", "/") for f in files]


def test_no_raw_fetch_without_authorization_header():
    offenders: list[str] = []
    for p in _files():
        if any(p.startswith(a.rstrip("**")) or p == a for a in ALLOWLIST):
            continue
        src = open(p, encoding="utf-8").read()
        if not FETCH_RE.search(src):
            continue
        if not HEADER_RE.search(src):
            offenders.append(p)
    assert not offenders, (
        f"認証ヘッダを付与しない生 fetch が {len(offenders)} ファイルにある:\n  "
        + "\n  ".join(sorted(offenders))
    )
