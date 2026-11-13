"""Step 14 (H13): asset_pack.generate_pack の create_ebook_exporter シグネチャ不整合修正。

H13: create_ebook_exporter(self.genre, self.preset) は正シグネチャ (EbookMetadata, Path)
と不整合で AttributeError でクラッシュしていた。EbookMetadata を生成して渡すように修正。
"""
from __future__ import annotations

import inspect

from src.easy_mode.phase3 import asset_pack


def test_asset_pack_uses_ebook_metadata():
    """create_ebook_exporter に EbookMetadata と output_dir を渡す（H13）。"""
    src = inspect.getsource(asset_pack)
    # 文字列を直接渡す旧パターンが削除されている
    assert "create_ebook_exporter(self.genre, self.preset)" not in src, (
        "asset_pack.py に create_ebook_exporter(self.genre, self.preset) が残っている (H13)"
    )
    # EbookMetadata を生成して渡している
    assert "EbookMetadata(title=series.title" in src, (
        "asset_pack.py で EbookMetadata を生成していない (H13)"
    )
    # _init_components が output_dir を受け取っている
    assert "def _init_components(self, series: SeriesResult, output_dir: Path)" in src, (
        "_init_components が output_dir を受け取っていない (H13)"
    )
