"""絶対話数バグの回帰防止。本計画の最重要リグレッションテスト群。"""

import ast
from pathlib import Path

import pytest

from src.backend.engine_narrative import PacingGraph


# --- 1. PacingGraph が話数非依存であること ---


@pytest.mark.parametrize("eps", [8, 20, 40, 100, 300])
def test_instruction_depends_only_on_relative_position(eps):
    """同じ相対位置なら同じ指示であること。

    相対位置は (ep-1)/total_eps なので、(k, N) と (2k, 2N) は同値になる。
    ep=1 は意図的に特別扱いされているので比較対象にしない。
    """
    for k, m in ((2, 3), (3, 5), (4, 7)):
        a = PacingGraph.get_instruction(k, total_eps=eps)["instruction"]
        b = PacingGraph.get_instruction(m, total_eps=2 * eps)["instruction"]
        assert a == b, f"eps={eps}: ({k},{eps}) と ({m},{2 * eps}) は同位置なのに指示が違う"


@pytest.mark.parametrize("eps", [20, 40, 100, 300])
def test_climax_cluster_scales_with_length(eps):
    """クライマックスクラスタが「終盤」に固定されていること。"""
    hits = [
        ep for ep in range(1, eps + 1)
        if "クライマックス" in PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
    ]
    assert hits, f"eps={eps} でクライマックスが見つからない"
    assert max(hits) / eps >= 0.70, f"eps={eps}: クライマックスが {max(hits) / eps:.0%} 位置"


@pytest.mark.parametrize("eps", [20, 40, 100])
def test_first_explosion_scales_with_length(eps):
    """第1の爆発が序盤（10〜25%）に固定されていること。"""
    hits = [
        ep for ep in range(1, eps + 1)
        if "第1の爆発" in PacingGraph.get_instruction(ep, total_eps=eps)["instruction"]
    ]
    assert hits, f"eps={eps} で第1の爆発が見つからない"
    rel = hits[0] / eps
    assert 0.05 <= rel <= 0.30, f"eps={eps}: 第1の爆発の相対位置が {rel:.2f}"


def test_instruction_is_stable_for_every_length():
    """すべての話数で必ずいずれかの指示が返ること（分岐の抜け漏れ防止）。"""
    for eps in (1, 2, 5, 8, 20, 40, 100, 300):
        for ep in range(1, eps + 1):
            got = PacingGraph.get_instruction(ep, total_eps=eps)
            assert got.get("instruction"), f"eps={eps} ep={ep} で指示が空"
            assert 0.0 <= got.get("temp", 0) <= 1.0


def _pacing_graph_class_node():
    """engine_narrative.py 内の PacingGraph クラス定義ノードを取り出す。"""
    src = Path("src/backend/engine_narrative.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef) and node.name == "PacingGraph":
            return node
    pytest.fail("PacingGraph が見つからない")


def test_no_absolute_episode_literals_in_pacing_graph():
    """`ep_num == 5` のような絶対比較が PacingGraph 内に残っていないこと。"""
    offenders = []
    for node in ast.walk(_pacing_graph_class_node()):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name):
            if node.left.id != "ep_num":
                continue
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, int) and comp.value != 1:
                    offenders.append(f"line {node.lineno}: ep_num == {comp.value}")
    assert not offenders, f"PacingGraph に絶対話数比較が残存: {offenders}"


def test_episode_one_is_the_only_allowed_literal():
    """`ep_num == 1`（第1話）だけは意図的に残してよい。"""
    allowed = {1}
    seen = 0
    for node in ast.walk(_pacing_graph_class_node()):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "ep_num":
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, int):
                    assert comp.value in allowed, f"line {node.lineno}: 許されない {comp.value}"
                    seen += 1
    assert seen >= 1, "第1話の特別扱いが見つからない（テストが意図を反映していない）"


# --- 2. EP_* 定数が消えていること ---


def test_episode_constants_removed():
    """8話固定の EP_* 定数が残っていないこと。"""
    import config.constants as c

    for name in ("EP_HUMILIATION", "EP_TRIGGER", "EP_MUSOU_START", "EP_FINAL", "EP_CLIMAX"):
        assert not hasattr(c, name), f"{name} がまだ残っている"


def test_no_module_imports_episode_constants():
    """リポジトリ全体で EP_* 定数を**参照**していないこと（コメントは対象外）。"""
    targets = {"EP_HUMILIATION", "EP_TRIGGER", "EP_MUSOU_START", "EP_FINAL", "EP_CLIMAX"}
    offenders = []
    for path in list(Path("src").rglob("*.py")) + list(Path("config").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.alias):
                name = node.asname or node.name
            if name in targets:
                offenders.append(f"{path}:{node.lineno}: {name}")
    assert not offenders, f"EP_* への参照が残存: {offenders}"


# --- 3. 長尺が構造上通ること ---


def test_episode_beat_accepts_100():
    """40話上限の撤去（長編対応の回帰）。"""
    from src.models.beat_sheet import EpisodeBeat

    beat = EpisodeBeat(
        ep_num=100, phase="終盤", mission="決戦",
        tension_target=0.9, visual_scene_focus="黒幕との対決",
    )
    assert beat.ep_num == 100
