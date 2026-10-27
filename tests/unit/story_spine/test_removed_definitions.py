"""削除した定義が復活していないことの回帰テスト。"""

import config
import config.archetypes_new as archetypes_new
from config.story_spine import PATTERNS
from src.models.beat_sheet import EpisodeBeat


def test_plot_structures_removed_from_archetypes_new():
    assert not hasattr(archetypes_new, "PLOT_STRUCTURES"), (
        "参照 0 件だった旧 PLOT_STRUCTURES（3件）が復活している。"
        "構造は config/story_spine/patterns.yaml（38件）に一本化すること。"
    )


def test_plot_structures_not_reexported_from_config():
    assert not hasattr(config, "PLOT_STRUCTURES"), (
        "config/__init__.py の re-export が復活している"
    )


def test_episode_beat_has_no_upper_bound():
    from pathlib import Path

    src = Path("src/models/beat_sheet.py").read_text(encoding="utf-8")
    assert "le=40" not in src, "EpisodeBeat.ep_num の le=40 が再発している"


def test_episode_beat_accepts_300():
    b = EpisodeBeat(
        ep_num=300, phase="終盤", mission="最終決戦",
        tension_target=0.95, visual_scene_focus="黒幕との対決",
    )
    assert b.ep_num == 300


def test_episode_beat_still_rejects_zero():
    """下限は残すこと（話数 0 は無意味）。"""
    import pytest

    with pytest.raises(Exception):
        EpisodeBeat(
            ep_num=0, phase="x", mission="y", tension_target=0.5, visual_scene_focus="z",
        )


def test_no_consumer_imports_plot_structures():
    from pathlib import Path

    offenders = [
        str(p) for p in Path("src").rglob("*.py")
        if "PLOT_STRUCTURES" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, f"PLOT_STRUCTURES の参照が残存: {offenders}"


def test_patterns_yaml_supersedes_the_old_json():
    """旧 `config/data/archetypes.json` の 31 パターンが patterns.yaml へ移っていること。"""
    from config.story_spine.beat import BEAT_VOCABULARY

    assert len(PATTERNS) >= 38
    for key, pat in PATTERNS.items():
        assert pat.get("beats"), f"{key} に beats が無い"
        for b in pat["beats"]:
            assert b["key"] in BEAT_VOCABULARY, f"{key}.{b['key']} が語彙に無い"


def test_story_archetypes_still_importable():
    """A6 で PLOT_STRUCTURES を消しても config パッケージは壊れない。"""
    assert len(config.STORY_ARCHETYPES) > 0
