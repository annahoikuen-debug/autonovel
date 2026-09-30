"""/api/config/planning_options が 500 でなく 200 を返すことの契約テスト。"""
import asyncio
from pathlib import Path


def test_planning_options_does_not_raise():
    """**既存バグの直接の回帰テスト**。旧実装は ImportError で落ちていた。"""
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    assert isinstance(result, dict)


def test_legacy_keys_are_preserved():
    """既存 FE が使うキーが消えていないこと。"""
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    for key in ("easy_genres", "story_archetypes", "style_definitions"):
        assert key in result, f"既存キー {key!r} が消えている"


def test_new_spine_keys_present():
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    for key in ("cards", "lengths", "markets", "patterns", "genres"):
        assert key in result, f"新キー {key!r} が無い"


def test_new_spine_keys_have_expected_types():
    """中身为空でも（TRACK-A の Wave2 完了前はそうなる）型は崩さない。"""
    from src.backend.routers.misc import get_planning_options

    result = asyncio.run(get_planning_options())
    for key in ("cards", "lengths", "markets", "patterns", "genres"):
        assert isinstance(result[key], dict), f"{key!r} は dict であるべき"
    assert isinstance(result["beat_vocabulary"], dict)


def test_no_planning_presets_import_remains():
    """壊れた import が復活していないこと。"""
    src = Path("src/backend/routers/misc.py").read_text(encoding="utf-8")
    assert "PLANNING_PRESETS" not in src


def test_beat_vocabulary_entries_are_frontend_usable():
    """BEAT_VOCABULARY 要約（key/label/role/tension/artifact）を含むこと。"""
    from src.backend.routers.misc import get_planning_options

    vocab = asyncio.run(get_planning_options())["beat_vocabulary"]
    assert vocab, "beat_vocabulary が空"
    first = next(iter(vocab.values()))
    for field in ("key", "label", "role", "tension", "artifact"):
        assert field in first, f"beat_vocabulary に {field!r} が無い"


def test_genres_payload_comes_from_registry():
    """genres は GENRE_REGISTRY のエントリがそのまま載ること。"""
    from config.story_spine.genre_registry import GENRE_REGISTRY
    from src.backend.routers.misc import get_planning_options

    genres = asyncio.run(get_planning_options())["genres"]
    assert set(genres) == set(GENRE_REGISTRY)
    for key, entry in genres.items():
        for field in ("label", "domain", "preset_key", "rating", "aliases"):
            assert field in entry, f"genres[{key!r}] に {field!r} が無い"
