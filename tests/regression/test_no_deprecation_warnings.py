"""import 時 DeprecationWarning ゼロを担保する常設ゲート。

PLAN_Q3 §5「DeprecationWarning は抑制ではなく消す」の実装。
src/ 配下のモジュールを import した際に DeprecationWarning が発生しないことを検証する。

既知の例外（KNOWN_DEPRECATION_SOURCES）は理由付きで明示的に管理する。
例外に登録したモジュールも次第に解消し、最終的に空リストにする。
"""

from __future__ import annotations

import importlib
import subprocess
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 既知の DeprecationWarning 発生源（理由と解消先を明記）。
# PLAN_Q3 Step 7-9 で順次解消する TODO として残す。
KNOWN_DEPRECATION_SOURCES: dict[str, str] = {
    "src.agents.context_builder": "旧クラスへの後方互換 shim（src.agents.context_builder_agent に移設済み）",
    "src.agents.audit.logical_auditor": "旧 LogicalAuditor shim（src.audit に移設済み）",
    "src.backend.database.core": "旧 DatabaseManager shim（src.infrastructure.database.core に移設済み）",
    "src.backend.writing_service": "旧 WritingService shim（src.domain.writing に移設済み）",
    "src.backend.config": "旧 settings shim（src.infrastructure.config.settings に移設済み、TODO(H3-9)）",
    "src.backend.engine_context": "旧 EngineContext shim",
    "src.core.container.__init__": "make_container() 関数のみ（クラスは正規）",
    "src.llm.adapters.base": "旧 BaseLLMAdapter 参照注意メッセージ",
    "src.services.audit_adapter": "旧 audit_adapter shim",
    "src.integrations.age_client": "旧 age_client shim",
    "src.security.input_validation": "Pydantic v1 @validator デコレータの内部警告（Pydantic v2 への移行 TODO）",
}


def _module_matches_warning(warning_source: str, known_key: str) -> bool:
    """warning の発生源が既知のキーに一致するか判定する。

    warning_source はファイルパス（例: src/security/input_validation.py）。
    known_key はモジュールパス（例: src.security.input_validation）。
    両者はパス形式が異なるため、known_key をファイルパス形式に変換して比較する。
    """
    # known_key（モジュールパス）をファイルパス形式に変換
    known_as_file = known_key.replace(".", "/")
    # warning_source（ファイルパス）をモジュールパス形式に変換
    source_as_module = (
        warning_source.replace("/", ".")
        .replace(".py", "")
        .replace(".__init__", "")
    )
    return (
        known_as_file in warning_source
        or source_as_module == known_key
        or known_key in source_as_module
    )


def _import_modules_and_collect_deprecation_warnings() -> dict[str, list[str]]:
    """src/ 配下の import 可能なモジュールを全て import し、
    発生した DeprecationWarning を発生源ごとに収集する。"""
    import os

    warnings_map: dict[str, list[str]] = {}
    src_dir = REPO_ROOT / "src"

    module_names: list[str] = []
    for path in src_dir.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        module = str(rel.with_suffix("")).replace("/", ".")
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        # テストや __main__、migrations は対象外
        if any(
            part in module
            for part in ("__main__", "migrations", "tests")
        ):
            continue
        module_names.append(module)

    # 重複排除とソート
    module_names = sorted(set(module_names))

    for module_name in module_names:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            try:
                importlib.import_module(module_name)
            except Exception:
                # import 失敗はこのテストの関心事ではない（別のテストで検証する）
                continue
        for w in caught:
            if issubclass(w.category, DeprecationWarning):
                source_file = getattr(w, "filename", "") or ""
                # src/ 配下の warning のみを対象とする
                if str(REPO_ROOT) in source_file:
                    rel_source = source_file.replace(str(REPO_ROOT) + "/", "")
                    warnings_map.setdefault(rel_source, []).append(module_name)

    return warnings_map


def test_no_deprecation_warnings() -> None:
    """src/ 配下の import 時に DeprecationWarning が発生しないこと。

    既知の例外（KNOWN_DEPRECATION_SOURCES）は許容する。
    それ以外の DeprecationWarning は新規 shim 導入とみなして fail にする。
    """
    git_check = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    if git_check.returncode != 0:
        pytest.skip("git が利用できないためスキャンをスキップします")

    warnings_map = _import_modules_and_collect_deprecation_warnings()

    unknown_warnings: dict[str, list[str]] = {}
    known_ignored = 0
    for source_file, modules in warnings_map.items():
        # 既知の例外とマッチするか判定
        matched = any(
            _module_matches_warning(source_file, known)
            for known in KNOWN_DEPRECATION_SOURCES
        )
        if matched:
            known_ignored += len(modules)
        else:
            unknown_warnings[source_file] = modules

    assert not unknown_warnings, (
        f"import 時 DeprecationWarning が {len(unknown_warnings)} 件のファイルで発生しています。\n"
        "新規 shim 導入は原則禁止（PLAN_Q3 方針）。\n"
        "既知の例外に追加する場合は、理由と解消先を KNOWN_DEPRECATION_SOURCES に記載し、\n"
        "PLAN_Q3 の残 TODO として管理してください。\n"
        f"詳細: {unknown_warnings}"
    )
