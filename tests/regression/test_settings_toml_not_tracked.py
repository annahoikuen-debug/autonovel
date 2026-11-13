"""Step 6 (H5): config/settings.toml の git 追跡禁止と APIキー永続化除外。

H5: GlobalConfig.update() / _persist_to_toml() が openai_api_key 等の秘密情報を
config/settings.toml に書き出し、ファイルが git 追跡下にあるため
コミットによる秘密鍵漏洩リスクがあった。修正：
- settings.toml を .gitignore に追加
- _persist_to_toml で *_api_key フィールドを除外
- ProjectContext.set_setting のログで値をマスク化
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.config.project_context import GlobalConfig


def test_settings_toml_not_git_tracked():
    """config/settings.toml が git 追跡下にない（H5）。"""
    result = subprocess.run(
        ["git", "ls-files", "config/settings.toml"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.stdout.strip() == "", (
        f"config/settings.toml が git 追跡下にある: {result.stdout.strip()}"
    )


def test_update_excludes_api_keys_from_toml(tmp_path, monkeypatch):
    """GlobalConfig.update() が openai_api_key を TOML に書き出さない（H5）。"""
    # _persist_to_toml の書き出し先を一時ファイルに差し替え
    from src.config.constants import BASE_DIR

    real_base_dir = BASE_DIR
    monkeypatch.setattr(
        "src.infrastructure.config.project_context.BASE_DIR", tmp_path
    )
    # 設定ファイルパスも一時ディレクトリに
    toml_path = tmp_path / "config" / "settings.toml"
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text('general = {openai_api_key = ""}\n', encoding="utf-8")

    try:
        cfg = GlobalConfig()
        # API キーを含む設定を更新
        cfg.update(openai_api_key="sk-test-secret-key-12345")

        # TOML ファイルに openai_api_key が書き込まれていないことを確認
        content = toml_path.read_text(encoding="utf-8")
        assert "sk-test-secret-key-12345" not in content
        assert "openai_api_key" not in content
    finally:
        monkeypatch.setattr("src.infrastructure.config.project_context.BASE_DIR", real_base_dir)


def test_set_setting_masks_secret_values():
    """ProjectContext.set_setting が秘密キーの値をマスクする（H5）。"""
    from unittest.mock import patch
    from src.infrastructure.config.project_context import ProjectContext

    with patch("src.infrastructure.config.project_context.logger") as mock_logger:
        ProjectContext.set_setting("openai_api_key", "sk-secret-value")
        # ログ呼び出しに sk-secret-value が含まれていない
        log_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert not any("sk-secret-value" in c for c in log_calls), (
            "set_setting のログに秘密値がプレーン出力されている"
        )
        # *** マスクが含まれている
        assert any("***" in c for c in log_calls)
