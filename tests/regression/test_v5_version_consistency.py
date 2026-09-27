"""tests/regression/test_v5_version_consistency.py.

v5系のリリース整合性を担保するため、全設定ファイル・主要コードエントリポイントにおける
バージョン番号が寸分違わず一致していることを検証するリグレッション防止テスト。

版数の正となる情報源は ``pyproject.toml`` の ``project.version`` のみである。
他のファイルにはバージョンをリテラルでハードコードせず、すべてこの値と比較する。
これにより、リリース時に編集すべき箇所は ``pyproject.toml`` の 1 行だけになる。
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def mock_llm_adapter() -> None:  # noqa: D103
    """conftest の autouse LLM モックを本モジュールのみ無効化する。

    本テストはファイル文字列とバージョン定数の照合のみを行い、LLM・DB・ネットワークを
    一切使用しない。conftest 側の autouse フィクスチャは `src.services.llm` を import する
    ため、LLM 依存が未インストールの環境では静的な整合性チェックまで collection error に
    なる。モジュールスコープの同名フィクスチャで上書きすることで、依存関係に左右されずに
    リリース整合性を検証できるようにする。
    """
    return None


def _read_pyproject() -> dict:
    pyproject_path = ROOT_DIR / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml が存在しません"
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def authoritative_version() -> str:
    """版数の唯一の正となる pyproject.toml の project.version を返す."""
    version = _read_pyproject().get("project", {}).get("version")
    assert version, "pyproject.toml に project.version がありません"
    return str(version)


def test_pyproject_declares_authoritative_version(authoritative_version: str) -> None:
    """pyproject.toml が版数の正であり、SemVer 形式であること."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", authoritative_version), (
        f"project.version は SemVer (X.Y.Z) であるべきですが {authoritative_version} です"
    )


def test_frontend_package_json_version(authoritative_version: str) -> None:
    """frontend/package.json のバージョンが正と一致すること."""
    package_json_path = ROOT_DIR / "frontend" / "package.json"
    assert package_json_path.exists(), "frontend/package.json が存在しません"
    with open(package_json_path, "r", encoding="utf-8") as f:
        version = json.load(f).get("version")
    assert version == authoritative_version, (
        f"package.json version は {authoritative_version} であるべきですが {version} です"
    )


def test_cli_version(authoritative_version: str) -> None:
    """src/cli/main.py の __version__ が正と一致すること."""
    from src.cli.main import __version__

    assert __version__ == authoritative_version, (
        f"src.cli.main.__version__ は {authoritative_version} であるべきですが {__version__} です"
    )


def test_backend_init_version(authoritative_version: str) -> None:
    """src/backend/__init__.py の __version__ が正と一致すること."""
    import src.backend

    version = getattr(src.backend, "__version__", None)
    assert version == authoritative_version, (
        f"src.backend.__version__ は {authoritative_version} であるべきですが {version} です"
    )


def test_prod_compose_image_tags(authoritative_version: str) -> None:
    """docker-compose.prod.yml のイメージタグが正と一致すること.

    unpinned な ``:latest`` タグ (開発用 docker-compose.yml) は本テストの対象外。
    """
    compose_path = ROOT_DIR / "docker-compose.prod.yml"
    assert compose_path.exists(), "docker-compose.prod.yml が存在しません"
    content = compose_path.read_text(encoding="utf-8")

    tags = re.findall(r"^\s*image:\s*autonovel-[\w-]+:(\S+)\s*$", content, re.MULTILINE)
    assert tags, "docker-compose.prod.yml に autonovel-* イメージタグが見つかりません"

    mismatched = [t for t in tags if t != authoritative_version]
    assert not mismatched, (
        f"docker-compose.prod.yml のイメージタグが {authoritative_version} と不一致: {mismatched}"
    )


def test_readme_version_matches(authoritative_version: str) -> None:
    """README.md のバージョンバッジとリリースタグが正と一致すること."""
    readme_path = ROOT_DIR / "README.md"
    assert readme_path.exists(), "README.md が存在しません"
    content = readme_path.read_text(encoding="utf-8")

    assert f"version-{authoritative_version}-brightgreen" in content, (
        f"README.md のバージョンバッジが {authoritative_version} ではありません"
    )
    assert f"releases/tag/v{authoritative_version}" in content, (
        f"README.md のリリースリンクが v{authoritative_version} を指していません"
    )


def test_changelog_has_entry_for_authoritative_version(authoritative_version: str) -> None:
    """CHANGELOG.md に正のバージョンに対応するエントリが存在すること."""
    changelog_path = ROOT_DIR / "CHANGELOG.md"
    assert changelog_path.exists(), "CHANGELOG.md が存在しません"
    content = changelog_path.read_text(encoding="utf-8")

    assert re.search(rf"^##\s*\[{re.escape(authoritative_version)}\]", content, re.MULTILINE), (
        f"CHANGELOG.md に [{authoritative_version}] のエントリがありません"
    )


def test_documents_referenced_by_readme_exist() -> None:
    """README.md がリンクしているリポジトリ内ファイルが実在すること."""
    readme_path = ROOT_DIR / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    linked = re.findall(r"\]\((?!https?://)([^)#]+)\)", content)
    missing = sorted({t for t in linked if not (ROOT_DIR / t).exists()})

    assert not missing, f"README.md が参照しているが存在しないファイル: {missing}"


if __name__ == "__main__":
    _v = str(_read_pyproject().get("project", {}).get("version"))
    test_pyproject_declares_authoritative_version(_v)
    test_frontend_package_json_version(_v)
    test_cli_version(_v)
    test_backend_init_version(_v)
    test_prod_compose_image_tags(_v)
    test_readme_version_matches(_v)
    test_changelog_has_entry_for_authoritative_version(_v)
    test_documents_referenced_by_readme_exist()
    print(f"ALL VERSION CONSISTENCY TESTS PASSED! (v{_v})")
