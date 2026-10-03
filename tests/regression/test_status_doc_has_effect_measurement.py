"""docs/STATUS.md に v6 効果測定の実測値が載っていることの回帰テスト。

T6 Step 15 の回帰防止。

親計画 Step 36 の主要な成果物「効果測定表」が**未作成**だった。
本テストは (1) 節の存在、(2) 推測値の混入防止、
(3) バージョンの正準との一致を固定する。
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "docs" / "STATUS.md"


def _text() -> str:
    return STATUS.read_text(encoding="utf-8")


def test_status_doc_has_effect_measurement_section():
    """効果測定の節が存在すること。"""
    text = _text()
    assert "v6 効果測定" in text, "docs/STATUS.md に効果測定の節が無い"


def test_effect_measurement_table_has_all_metrics():
    """効果測定表の主要指標が揃っていること。"""
    text = _text()
    section = text.split("v6 効果測定", 1)[-1]
    for metric in ("LLM 呼出回数", "監査レイテンシ", "再生成比率", "コスト"):
        assert metric in section, f"効果測定表に「{metric}」の行が無い"


def test_unmeasured_items_are_declared_not_guessed():
    """未計測項目は `未計測` と明記されていること（推測の混入防止）。"""
    text = _text()
    section = text.split("v6 効果測定", 1)[-1]
    assert "未計測" in section, (
        "未計測の項目が明示されていない。"
        "推測値を効果測定表に載せることになる"
    )
    # プレースホルダ（未解決の記入）が残っていないこと
    assert "(Step 13)" not in section, "未計測セルが未解決のまま残っている"
    assert "TODO" not in section, "TODO が残ったまま"

    # 未計測の4項目がそれぞれ明記されていること
    for item in ("実ネットワークでの監査レイテンシ", "本番データでの1話コスト", "長編完走率"):
        assert item in section, f"未計測項目「{item}」の記載が無い"


def test_structural_estimate_is_not_used_as_measurement():
    """構造推計を実測値として載せていないこと。"""
    text = _text()
    section = text.split("v6 効果測定", 1)[-1]
    assert "構成推計" in section, "構成推計の区別が記載されていない"
    assert "用いない" in section, "構成推計を使わない旨が明記されていない"


def test_version_section_matches_pyproject():
    """バージョン節が pyproject（唯一の正）と一致すること。"""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(version["project"]["version"])
    text = _text()
    section = text.split("## 1. バージョン", 1)[-1].split("\n---", 1)[0]
    assert f"**{version}**" in section, (
        f"バージョン節が pyproject の {version} と一致しない"
    )
    # 旧バージョンが 正として残っていないこと
    assert "**5.3.0**" not in section, "旧バージョンが正として残っている"


def test_measured_values_have_citations():
    """実測値には出典テストが明記されていること。"""
    text = _text()
    section = text.split("v6 効果測定", 1)[-1]
    for citation in ("test_v6_llm_call_budget.py", "test_v6_audit_latency_and_regen.py"):
        assert citation in section, f"出典 {citation} が記載されていない"
