"""`Base.metadata` の自己完結性を保証するゲート。

何が起きたか
------------
2026-10-04 の公開前残存タスク調査で、`src/backend/database/models.py` が
`books.tenant_id = Column(Integer, ForeignKey("tenants.id"))` を宣言しているのに
`models_tenant` を副作用 import していなかったため、`tenants` テーブルが
`Base.metadata` に登録されていない状態だった。

結果として:

1. 開発用フォールバック経路 `InfraBase.metadata.create_all(engine)`
   （`src/backend/database/core.py`）が
   `sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column
   'books.tenant_id' could not find table 'tenants'` で失敗する
2. `tests/regression/test_v53_concurrent_transition.py` が部分スキーマを
   自作するため単独実行で 7 件失敗し、他のテストが `models_tenant` を
   import している時だけ通る**順序依存**になっていた

なぜ一般的なゲートなのか
--------------------
「今回 1 テーブルだけ直せばよい」という局所的な見落としを避ける。
このテストは**すべての FK 参照先**について同じ検査を行うため、
今後，新增されずに漏れたテーブルも検出できる。
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def metadata():
    """全テーブルが登録済みの `Base.metadata`。

    `src.backend.database.models` の import 副作用で登録されるため、
    ここで明示的に import する（テスト側の自律性を保証）。
    """
    import src.backend.database.models  # noqa: F401  (登録副作用)
    from src.infrastructure.database.models.base_orm import Base

    return Base.metadata


class TestMetadataSelfContained:
    """`Base.metadata` だけで全テーブルを create_all できること。"""

    def test_tenant_table_is_registered(self, metadata) -> None:
        """`tenants` テーブルが登録されていること（今回漏れていた実例）。"""
        assert "tenants" in metadata.tables, (
            "tenants テーブルが Base.metadata に未登録。"
            "src/backend/database/models.py に models_tenant の import が必要"
        )

    def test_all_foreign_key_targets_resolve(self, metadata) -> None:
        """登録済みテーブルが参照する全 FK 先が metadata に存在すること。

        `create_all()` は FK 解決できない時点で失敗する。
        したがってこれは「create_all が成功する」ことの直接的な代理検査。
        """
        from sqlalchemy import ForeignKey

        missing: list[str] = []
        for table_name, table in metadata.tables.items():
            for column in table.columns:
                for fk in column.foreign_keys:
                    target = str(fk.column)
                    # target は "schema.table.column" 形式
                    parts = target.split(".")
                    if len(parts) >= 2:
                        target_table = ".".join(parts[:-1])
                        if target_table not in metadata.tables:
                            missing.append(
                                f"{table_name}.{column.name} -> {target_table}"
                            )

        assert not missing, (
            "外部キー参照先が Base.metadata に存在しません（create_all が失敗します）:\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    def test_create_all_does_not_raise(self, metadata) -> None:
        """`metadata.create_all()` が NoReferencedTableError を投げないこと。

        一時 SQLite に実際に create_all を実行して確認する。
        これは上記の代理検査に加え、実 BIA による最終確認となる。
        """
        from sqlalchemy import create_engine

        engine = create_engine("sqlite:///:memory:")
        try:
            metadata.create_all(engine)
        finally:
            engine.dispose()

    def test_foreign_key_import_is_present_in_models_module(self, metadata) -> None:
        """`models.py` が `models_tenant` を import していることを静的確認。

        将来誰かが「不要だ」と import を削除しても、
        このテストと上の実 BIA テストで検出できる。
        """
        from pathlib import Path

        import src.backend.database.models as models_mod

        source = Path(models_mod.__file__).read_text(encoding="utf-8")
        assert "models_tenant" in source, (
            "src/backend/database/models.py から models_tenant の import が消えている。"
            "副作用 import なので __all__ からは見えない"
        )
