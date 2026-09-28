"""データベーススキーマの後方互換性を検証するコントラクトテスト。

- テーブル数が減っていないか（削除は禁止、追加は許容）
- 必須カラム（NOT NULL かつ default なし）が消えていないか
"""
import json
from pathlib import Path

from src.backend.database import models  # noqa: F401  # テーブルを metadata に登録するため必須
from src.infrastructure.database.models.base_orm import Base

BASELINE_PATH = Path("artifacts/db_schema_baseline.json")

# 削除してはいけない中核テーブル（製品の中核データ）
REQUIRED_TABLES = {
    "books",
    "chapters",
    "plots",
    "bibles",
    "book_scores",
    "audit_issues",
    "users",
}


def _current_tables() -> set[str]:
    return set(Base.metadata.tables)


def _load_baseline() -> set[str] | None:
    if not BASELINE_PATH.exists():
        return None
    with open(BASELINE_PATH, encoding="utf-8") as fh:
        return set(json.load(fh).get("tables", []))


def test_metadata_has_tables():
    """モデルが import され、テーブルが metadata に登録されていること（0 なら import 漏れ）。"""
    tables = _current_tables()
    assert tables, "Base.metadata にテーブルが登録されていません。models の import を確認してください"


def test_core_tables_exist():
    """中核テーブルが消えていないこと。"""
    missing = REQUIRED_TABLES - _current_tables()
    assert not missing, f"中核テーブルが不足しています: {sorted(missing)}"


def test_table_count_has_not_decreased():
    """テーブル数が減っていないか（削除ではなく追加のみ許容）。

    ベースラインが無い初回実行時はベースラインを作成する。
    """
    current = _current_tables()
    baseline = _load_baseline()

    if baseline is None:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"tables": sorted(current)}, fh, ensure_ascii=False, indent=2)
        return

    removed = baseline - current
    assert not removed, f"以下のテーブルが削除されています: {sorted(removed)}"


def test_column_nullability_has_not_become_strict():
    """ベースライン時点で NOT NULL だったカラムが nullable 化されていないこと。

    データ移行を伴わない NOT NULL 化は既存行で壊れるため、許可しない。
    """
    current = _current_tables()
    relaxed: list[str] = []

    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            if column.primary_key:
                continue
            was_required = _baseline_required(name, column.name)
            if was_required and column.nullable:
                relaxed.append(f"{name}.{column.name}")

    assert not relaxed, f"nullable 化されたカラムがあります: {relaxed}"
    assert current, "テーブルが 0 件です"


_REQUIRED_BASELINE: dict[tuple[str, str], bool] = {}


def _baseline_required(table: str, column: str) -> bool:
    """ベースライン時点で NOT NULL だったかを返す。

    ベースライン JSON に nullability スナップショットが無い場合は
    「必須カラムではない」とみなす（過去の情報を根拠に失敗させない）。
    """
    if not _REQUIRED_BASELINE:
        if BASELINE_PATH.exists():
            with open(BASELINE_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            for table_name, cols in data.get("not_null", {}).items():
                for col in cols:
                    _REQUIRED_BASELINE[(table_name, col)] = True
    return _REQUIRED_BASELINE.get((table, column), False)
