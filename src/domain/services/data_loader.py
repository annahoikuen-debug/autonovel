import json
from pathlib import Path
from typing import Any

"""Loads and caches JSON configurations for rule externalization.

F4 フェーズ: src/services/data_loader.py から domain/services へ移設。
旧パスは後方互換のため shim として残す。
"""


class DataLoader:
    """Loads and caches JSON configurations for rule externalization."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._cache: dict[str, Any] = {}

    def load(self, filename: str) -> Any:
        if filename not in self._cache:
            filepath = self.data_dir / filename
            if filepath.exists():
                with open(filepath, encoding="utf-8") as f:
                    self._cache[filename] = json.load(f)
            else:
                self._cache[filename] = {}
        return self._cache[filename]
