"""README / STATUS.md が主張する数値が実測と一致することの archangel。

文書が古ipticると「緑が緑を保証しない」典型例になるため、数値は必ず
機械的に数えて更新し、本テストで固定する（PLAN_H1 R4）。
"""
from __future__ import annotations

import glob
import os
import re


def _router_file_count() -> int:
    """``src/backend/routers/*.py`` から ``__init__.py`` を除いたモジュール数。"""
    return len(
        [
            p
            for p in glob.glob("src/backend/routers/*.py")
            if not os.path.basename(p).startswith("__")
        ]
    )


def test_readme_router_module_count_matches_reality():
    readme = open("README.md", encoding="utf-8").read()
    actual = _router_file_count()
    claims = [int(m) for m in re.findall(r"API ルーター群（(\d+)\s*モジュール）", readme)]
    claims += [int(m) for m in re.findall(r"(\d+)\s*個の API ルーター", readme)]
    assert claims, "README に API ルーター数の記載が無い（回帰防止の観測点が消えている）"
    bad = [c for c in claims if c != actual]
    assert not bad, (
        f"README のルータ数 {bad} が実測 {actual} と不一致"
        "（D11: 必ず server.py / routers/ を機械的に数えて書くこと）"
    )


def _include_router_count() -> int:
    """ルーター登録（``include_router``）が書かれている組み立て箇所の呼び出し数。

    TRACK-A9 で起動ロジックが ``src/interfaces/api/app_factory.py`` へ移動し、
    ``src/backend/server.py`` は後方互換 shim になったため、両方を見る。
    """
    total = 0
    for path in ("src/backend/server.py", "src/interfaces/api/app_factory.py"):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            total += len(re.findall(r"\.include_router\(", f.read()))
    return total


def test_readme_routes_are_wired_to_the_registry():
    """アプリ組み立て箇所に include_router が実在し、ルーター数と釣り合うこと。"""
    n_include = _include_router_count()
    n_files = _router_file_count()
    assert n_include >= 1, (
        "include_router がどこにも無い（server.py / app_factory.py の"
        "いずれにもルーター登録が存在しない）"
    )
    # routers ディレクトリには __init__.py があるので必ず 1 以上少ない。
    assert n_include <= n_files + 10, (
        f"include_router が {n_include} 回あるが router モジュールは {n_files} 個"
    )


def test_status_md_ci_command_matches_workflow():
    """STATUS.md が説明する CI の pytest コマンドが ci.yml と一致すること。"""
    status = open("docs/STATUS.md", encoding="utf-8").read()
    wf = open(".github/workflows/ci.yml", encoding="utf-8").read()
    m_wf = re.search(r"pytest -q -m \"([^\"]+)\"", wf)
    assert m_wf, "ci.yml に -m フィルタが無い"
    m_doc = re.search(r"pytest -q -m \"([^\"]+)\"", status)
    assert m_doc, "STATUS.md に CI の pytest コマンド記載が無い"
    assert m_doc.group(1) == m_wf.group(1), (
        f"STATUS.md のマーカー式 {m_doc.group(1)!r} が ci.yml の "
        f"{m_wf.group(1)!r} と不一致"
    )


def test_status_md_does_not_claim_black_gate():
    """D06 で black は ruff format に統一済み。旧記載が残っていないこと。"""
    status = open("docs/STATUS.md", encoding="utf-8").read()
    makefile = open("Makefile", encoding="utf-8").read()
    assert "black-check" not in makefile, "Makefile に black-check が残っている"
    assert "black-check" not in status, (
        "STATUS.md に black-check の記載が残っている（D06: ruff format に統一済み）"
    )


def test_openapi_json_version_matches_pyproject():
    """``docs/openapi.json`` が現行バージョンであること（5.0.3 のまま放置されていた）。"""
    import json
    import tomllib

    version = str(tomllib.loads(open("pyproject.toml", encoding="utf-8").read())["project"]["version"])
    spec = json.loads(open("docs/openapi.json", encoding="utf-8").read())
    assert spec["info"]["version"] == version, (
        f"docs/openapi.json の version が {spec['info']['version']} のまま。"
        f" `py scripts/generate_openapi.py` で再生成すること（現在 {version}）"
    )


def test_openapi_json_is_not_missing_the_orchestrated_routes():
    """H7 で prefix を直した orchestrated が OpenAPI にも反映されていること。"""
    import json

    spec = json.loads(open("docs/openapi.json", encoding="utf-8").read())
    orchestrated = sorted(p for p in spec["paths"] if p.startswith("/orchestrated"))
    assert orchestrated, (
        "docs/openapi.json に /orchestrated/* が無い。"
        "`py scripts/generate_openapi.py` で再生成すること"
    )


def test_openapi_json_has_no_path_drift_against_the_app():
    """``docs/api.md:209`` が（約束していた）OpenAPI drift 検出を実際に行う。

    仕様書の path 集合が app の route 集合と乖離していれば CI を落とす。
    WebSocket ルートは OpenAPI 仕様書を持たない（HTTP 仕様ではない）ため対象外。
    FastAPI 0.141 以降の ``_IncludedRouter`` 遅延展開に依存せず、
    ``app.openapi()``（prefix 適用済み）を正とする。
    """
    import json

    from src.backend.server import app

    spec = json.loads(open("docs/openapi.json", encoding="utf-8").read())
    documented = {
        p for p in spec["paths"] if not p.startswith(("/openapi", "/docs", "/redoc"))
    }
    live = {
        p
        for p in app.openapi()["paths"]
        if not p.startswith(("/openapi", "/docs", "/redoc"))
    }
    missing = sorted(live - documented)
    extra = sorted(documented - live)
    assert not missing and not extra, (
        "docs/openapi.json と app の route が drift している。\n"
        f"  app にあるが仕様に無い: {missing}\n"
        f"  仕様にあるが app に無い: {extra}\n"
        "  `python scripts/generate_openapi.py` で再生成してコミットすること"
    )
