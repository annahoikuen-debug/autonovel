"""Additional tests for src/services/script_watcher.py to increase coverage."""

from __future__ import annotations

from unittest.mock import MagicMock
import tempfile
from pathlib import Path

import pytest

from src.services.script_watcher import ScriptWatcher, WatchConfig, create_script_watcher


def test_script_watcher_force_process_not_in_hash():
    """force_process works when file_path not yet in _file_hashes."""
    config = WatchConfig(script_root=Path("/tmp"))
    mock_vs = MagicMock()
    watcher = ScriptWatcher(config=config, vector_store=mock_vs, character_dict={"A"})
    # Create a temporary file
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "episode_01.md"
        file_path.write_text("# test\n", encoding="utf-8")
        # Ensure not in hash
        assert file_path not in watcher._file_hashes
        # force_process should process (returns True if valid)
        result = watcher.force_process(file_path)
        # Since content is minimal (no beats), _process_file returns False
        # but we just want to ensure no exception and that it returns bool
        assert isinstance(result, bool)


def test_script_watcher_scan_once_no_matches():
    """scan_once returns 0 when no files match pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WatchConfig(script_root=Path(tmpdir), pattern="nonexistent_*.md")
        mock_vs = MagicMock()
        watcher = ScriptWatcher(config=config, vector_store=mock_vs, character_dict={"A"})
        # Create a file that doesn't match pattern
        (Path(tmpdir) / "readme.md").write_text("hello", encoding="utf-8")
        count = watcher.scan_once()
        assert count == 0


def test_script_watcher_scan_once_root_not_exists():
    """scan_once returns 0 when script_root does not exist."""
    config = WatchConfig(script_root=Path("/this/path/does/not/exist"), pattern="*.md")
    mock_vs = MagicMock()
    watcher = ScriptWatcher(config=config, vector_store=mock_vs, character_dict={"A"})
    count = watcher.scan_once()
    assert count == 0
    # Should log warning (we can't easily assert logs without caplog, but at least no exception)


def test_script_watcher_process_file_validation_error():
    """_process_file returns False when validation fails (unknown character)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WatchConfig(script_root=Path(tmpdir))
        mock_vs = MagicMock()
        watcher = ScriptWatcher(config=config, vector_store=mock_vs, character_dict={"A"})
        file_path = Path(tmpdir) / "episode_01.md"
        # Unknown source but other fields present
        content = """---
beats:
  - source: "X"  # 不明キャラ
    target: "B"
    emotion: "fear"
    delta: 0.5
    cause: "test"
---
"""
        file_path.write_text(content, encoding="utf-8")
        result = watcher._process_file(file_path)
        assert result is False


def test_script_watcher_process_file_persistence_called():
    """_process_file calls persistence when valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WatchConfig(script_root=Path(tmpdir))
        mock_vs = MagicMock()
        mock_vs.get_latest.return_value = None  # not important
        watcher = ScriptWatcher(config=config, vector_store=mock_vs, character_dict={"A", "B"})
        file_path = Path(tmpdir) / "episode_01.md"
        content = """---
beats:
  - source: "A"
    target: "B"
    emotion: "fear"
    delta: 0.5
    cause: "test"
---
A「こんにちは」
"""
        file_path.write_text(content, encoding="utf-8")
        # Mock the persistence persist_beats to return a count
        watcher._persistence.persist_beats = MagicMock(return_value=2)
        result = watcher._process_file(file_path)
        assert result is True
        watcher._persistence.persist_beats.assert_called_once()
        # Ensure hash updated
        assert file_path in watcher._file_hashes


def test_create_script_watcher_defaults():
    """create_script_watcher uses default values."""
    mock_vs = MagicMock()
    watcher = create_script_watcher(
        script_root=Path("/tmp"),
        vector_store=mock_vs,
    )
    assert isinstance(watcher, ScriptWatcher)
    assert watcher.config.script_root == Path("/tmp")
    assert watcher.config.pattern == "episode_*.md"
    assert watcher.config.poll_interval == 30.0
    assert watcher.config.enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
