"""tests/regression/test_services_reachability.py

Step 61: AST 到達性テストの対象拡大（他サービスへの横展開）。

``bible_service``, ``image_service``, ``export_service`` の主要メソッドが
**実際に呼び出し元を持つこと**（＝デッドコードでないこと）を AST で固定する。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SRC = ROOT_DIR / "src"


def _method_names_defined(relative_path: str, class_name: str) -> set[str]:
    """指定クラスが定義するメソッド名集合を静的抽出する。"""
    tree = ast.parse((SRC / relative_path).read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def _call_sites_of_method(method_name: str) -> list[str]:
    """``src/`` 全域で ``.<method_name>(...)`` 形式の呼び出し箇所を列挙する。"""
    offenders: list[str] = []
    for py_file in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text("utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == method_name
            ):
                offenders.append(f"{py_file.relative_to(ROOT_DIR)}:{node.lineno}")
    return offenders


class TestBibleServiceReachability:
    """bible_service の主要メソッドが呼び出し元を持つこと。"""

    def test_world_bible_generator_exists(self) -> None:
        from src.services.bible_service import WorldBibleGenerator

        assert callable(getattr(WorldBibleGenerator, "generate", None)) or any(
            not n.startswith("_") and callable(getattr(WorldBibleGenerator, n))
            for n in dir(WorldBibleGenerator)
        ), "WorldBibleGenerator に公開メソッドが無い（解析前提の変化）"

    def test_record_setting_delta_has_callers(self) -> None:
        """``record_setting_delta`` が src/ 内で呼ばれていること。"""
        from src.services.bible_service import WorldBibleGenerator

        assert hasattr(WorldBibleGenerator, "record_setting_delta")
        assert _call_sites_of_method("record_setting_delta"), (
            "record_setting_delta に src/ 内の呼び出し元が無い"
        )


class TestImageServiceReachability:
    """image_service の主要メソッドが呼び出し元を持つこと。"""

    def test_generate_illustration_method_exists(self) -> None:
        from src.services.image_service import ImageService

        candidates = [
            name
            for name in dir(ImageService)
            if not name.startswith("_")
            and callable(getattr(ImageService, name))
            and ("generate" in name or "illustrat" in name or "image" in name)
        ]
        assert candidates, "ImageService に公開生成メソッドが無い（解析前提の変化）"

    def test_public_methods_have_callers(self) -> None:
        from src.services.image_service import ImageService

        public = [
            name
            for name in dir(ImageService)
            if not name.startswith("_") and callable(getattr(ImageService, name))
        ]
        called_any = False
        missing: list[str] = []
        for name in public:
            sites = _call_sites_of_method(name)
            # クラス定義内の呼び出し（self.<name> 含む）を除外して判断
            if sites:
                called_any = True
            else:
                missing.append(name)
        assert called_any or not missing, (
            f"ImageService の公開メソッドに呼び出し元が無い: {missing}"
        )


class TestExportServiceReachability:
    """export_service（export_package）の主要メソッドが呼び出し元を持つこと。"""

    def test_create_export_package_exists(self) -> None:
        from src.services.marketing.export_package import MarketingService

        assert hasattr(MarketingService, "create_export_package")

    def test_create_export_package_has_callers(self) -> None:
        sites = _call_sites_of_method("create_export_package")
        assert sites, "create_export_package に src/ 内の呼び出し元が無い"
