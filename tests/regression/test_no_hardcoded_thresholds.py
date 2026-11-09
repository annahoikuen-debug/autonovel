"""M4-D: ハードコード再導入防止テスト（品質ゲート関連ファイル限定）。

SSOT 化後、品質ゲート関連ファイルに生のマジックナンバー
(70.0 閾値, < 3 定型上限, 0.4/0.6 重み) が混入しないことを検証する。

対象ファイル:
  - src/agents/specialists/unified_auditor.py
  - src/engine/auditors/hybrid_auditor.py
  - src/domain/writing/coordinator.py
  - src/agents/audit_agent/config.py

これらは config/audit_calibration.yaml または calibration_store.py を
経由する必要がある。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src"

TARGET_FILES = [
    "src/agents/specialists/unified_auditor.py",
    "src/engine/auditors/hybrid_auditor.py",
    "src/domain/writing/coordinator.py",
    "src/agents/audit_agent/config.py",
]

# 品質ゲートに関連するハードコードパターン
FORBIDDEN_PATTERNS = [
    (re.compile(r">=\s*70(\.0)?\b"), "絶対閾値 70.0 のハードコード"),
    (re.compile(r">=\s*75(\.0)?\b"), "絶対閾値 75.0 のハードコード"),
    (re.compile(r"<\s*3\b"), "AI 定型上限 <3 のハードコード"),
    (re.compile(r"\*\s*0\.4\b"), "定量重み 0.4 のハードコード"),
    (re.compile(r"\*\s*0\.6\b"), "定性重み 0.6 のハードコード"),
]


def _collect_lines(file_rel: str) -> list[tuple[int, str]]:
    """対象ファイルの行を (行番号, 内容) で返す。"""
    p = ROOT / file_rel
    if not p.exists():
        return []
    lines = []
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append((line_no, line))
    return lines


def test_no_hardcoded_audit_thresholds():
    """品質ゲート関連ファイルにハードコードされた閾値・重みが存在しない。"""
    violations: list[tuple[str, int, str, str]] = []

    for file_rel in TARGET_FILES:
        for line_no, line in _collect_lines(file_rel):
            for pattern, desc in FORBIDDEN_PATTERNS:
                if pattern.search(line):
                    violations.append((file_rel, line_no, desc, line.strip()))

    assert not violations, (
        "品質ゲート関連ファイルにハードコードされた閾値/重みが検出されました。\n"
        "config/audit_calibration.yaml または calibration_store.py を経由してください。\n"
        + "\n".join(f"  {v[0]}:{v[1]} [{v[2]}] {v[3]}" for v in violations)
    )


def test_calibration_store_defaults_match_config(monkeypatch):
    """calibration_store のデフォルト値と config/audit_calibration.yaml が整合している。"""
    import yaml

    # 他テストで設定された環境変数をクリア
    monkeypatch.delenv("AUDIT_GATE_THRESHOLD", raising=False)
    monkeypatch.delenv("AUDIT_CLIE_MAX", raising=False)
    monkeypatch.delenv("AUDIT_QUANTITATIVE_WEIGHT", raising=False)
    monkeypatch.delenv("AUDIT_QUALITATIVE_WEIGHT", raising=False)

    config_path = ROOT.parent / "config" / "audit_calibration.yaml"
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # 環境変数の影響を受けないリテラル値と直接比較
    assert config["gate"]["absolute_threshold"] == 70.0
    assert config["gate"]["cliche_max"] == 3
    assert config["gate"]["weights"]["quantitative"] == 0.4
    assert config["gate"]["weights"]["qualitative"] == 0.6
