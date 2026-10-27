"""
tests/infrastructure/test_clean_architecture_integrity.py
Part 5 (Step 16-18) リグレッション防止テスト:
二重化解消（src.agent -> src.agents）、レガシー database/core.py 撤廃後の
モジュールインポート健全性とクリーンアーキテクチャ整合性を検証。
"""

import importlib
import sys
import pytest


def test_src_agent_package_is_purged():
    """二重化解消（src.agent -> src.agents）後、レガシー `src.agent` は存在しないことを検証。

    以前は `import src.agent` が DeprecationWarning を伴って `src.agents` に解決される
    ことを期待していたが、v5 ファイナライゼーションで conftest の sys.modules エイリアス
    shim を撤去したため、その前提は失われた。現行の正しい状態は「旧パッケージが完全に
    消えている」ことなので、そのように検証する。
    """
    # 正規のモジュールは存在する
    agents_pkg = importlib.import_module("src.agents")
    assert agents_pkg is not None

    # レガシー名は sys.modules に残っていない（shim 撤去の回帰防止）
    assert "src.agent" not in sys.modules

    # レガシー名は import できない
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.agent")


def test_no_broken_database_imports_across_project():
    """ルート直下の database.core が撤廃され、narrative_metrics_db が新基盤 Base を継承していることを検証"""
    # 旧 database.core は存在しないこと
    with pytest.raises(ModuleNotFoundError):
        import database.core  # noqa

    # narrative_metrics_db が正常に読み込めること
    from src.models.narrative_metrics_db import NarrativeMetric
    from src.infrastructure.database.models import Base
    assert issubclass(NarrativeMetric, Base)


def test_core_orm_models_load_cleanly():
    """主要ドメインモデルがクリーンに読み込めることを検証"""
    from src.backend.database.models import Book, Chapter, Character, Plot
    from src.infrastructure.database.models.task import Task
    assert Book.__tablename__ == "books"
    assert Chapter.__tablename__ == "chapters"
    assert Character.__tablename__ == "characters"
    assert Plot.__tablename__ == "plots"
    assert Task.__tablename__ == "tasks"
