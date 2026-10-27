"""依存宣言の二重管理に対するドリフト検知。

``pyproject.toml`` と ``requirements.txt`` の2箇所に依存パッケージが宣言されて
いるため、片方だけ追記すると Docker/CI の依存インストールが壊れる。実例:

- ``src/backend/routers/billing_webhook.py`` はモジュール直下で ``import stripe`` する
- ``src/backend/server.py`` は必ず ``billing_webhook.router`` を登録する
- にもかかわらず ``stripe`` はどちらの宣言ファイルにも存在しなかった

このテストは「pyproject に宣言された依存が requirements.txt にも存在する」ことを
強制し、再び片方だけの追記を CI で検出できるようにする。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]


def _canonical(name: str) -> str:
    """配布名の大文字小文字・セパレータ差異を吸収して正規化する。

    ``PyJWT`` / ``pyjwt`` / ``py-jwt`` を同一視する。
    """
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _pyproject_dependencies() -> set[str]:
    """``[project.dependencies]``（= ランタイム必須の依存）だけを返す。

    ``optional-dependencies`` (extras) は意図的に Dockerfile の
    ``pip install -r requirements.txt`` 対象外であり、該当コード側も
    try/except でガードしている。そのため extras まで要求すると
    本来の「起動に必須な依存が漏れている」という検出目的から外れる。
    """
    with open(ROOT_DIR / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    raw: list[str] = list(data["project"]["dependencies"])
    return {_canonical(re.split(r"[<>=!~\[ ]", d, maxsplit=1)[0]) for d in raw if d.strip()}


def _requirements_names() -> set[str]:
    names: set[str] = set()
    for line in (ROOT_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # "pkg[extra]>=1.0" / "pkg @ url" などの形式でもパッケージ名部分だけを取る
        head = re.split(r"[<>=!~\[ ;@]", stripped, maxsplit=1)[0]
        if head:
            names.add(_canonical(head))
    return names


def test_requirements_txt_exists() -> None:
    assert (ROOT_DIR / "requirements.txt").exists(), (
        "Dockerfile は requirements.txt のみを pip install するため、このファイルが必須です"
    )


@pytest.mark.parametrize("dep", sorted(_pyproject_dependencies()))
def test_pyproject_dependency_present_in_requirements(dep: str) -> None:
    """pyproject.toml の依存が requirements.txt にも存在する."""
    assert dep in _requirements_names(), (
        f"'{dep}' は pyproject.toml には宣言されていますが requirements.txt にありません。"
        f" Dockerfile は requirements.txt のみをインストールするため、"
        f" 本番コンテナは '{dep}' 不足で起動できません。"
    )


def test_billing_webhook_dependencies_are_declared() -> None:
    """決済機能がモジュール直下で import するパッケージは必ず宣言されている.

    実際に起動を落とす既知の欠落 (stripe) の再発を、名前の列挙ではなく
    コードの import 文から機械的に導出して検出する。
    """
    webhook = ROOT_DIR / "src" / "backend" / "routers" / "billing_webhook.py"
    source = webhook.read_text(encoding="utf-8")

    module_roots = re.findall(r"^import\s+([A-Za-z_][\w]*)", source, flags=re.MULTILINE)
    third_party = {
        m
        for m in module_roots
        # 標準ライブラリと自前パッケージを除く
        if m not in {"asyncio", "inspect", "logging", "datetime", "json", "os", "typing"}
        and not m.startswith("src")
    }

    declared = _requirements_names()
    for module_root in sorted(third_party):
        assert _canonical(module_root) in declared, (
            f"billing_webhook.py がモジュール直下で import する '{module_root}' が "
            f" requirements.txt に宣言されていません"
        )
