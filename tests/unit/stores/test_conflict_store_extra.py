"""src/stores/conflict_store.py と graph_store / vector_store の追加テスト。"""
from __future__ import annotations

import json

from src.fusion.models import Conflict
from src.pipeline.emotional_residue import EmotionType
from src.stores.conflict_store import ConflictStore


def _conflict(src="A", val=0.5, conf=1.0, conflict_id=""):
    return Conflict(
        pair=(src, "B"),
        emotion=EmotionType.AFFECTION,
        sources=[(src, val, conf)],
        conflict_id=conflict_id,
    )


class TestConflictStore:
    def test_record_and_query(self, tmp_path):
        store = ConflictStore(tmp_path / "conflicts.jsonl")
        store.record_conflicts([_conflict("A")], episode=1)
        store.record_conflicts([_conflict("C")], episode=2)

        assert len(store.get_all_conflicts()) == 2
        assert len(store.get_conflicts_by_episode(1)) == 1
        assert store.get_conflicts_by_episode(99) == []

    def test_record_empty(self, tmp_path):
        store = ConflictStore(tmp_path / "conflicts.jsonl")
        store.record_conflicts([], episode=1)
        assert not (tmp_path / "conflicts.jsonl").exists()

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "conflicts.jsonl"
        store = ConflictStore(path)
        c = _conflict("A")
        store.record_conflicts([c], episode=7)
        reloaded = ConflictStore(path)
        got = reloaded.get_conflict(c.conflict_id)
        assert got is not None
        assert got.pair == ("A", "B")
        assert got.emotion is EmotionType.AFFECTION
        assert reloaded.get_conflicts_by_episode(7)[0].conflict_id == c.conflict_id

    def test_get_conflict_missing(self, tmp_path):
        store = ConflictStore(tmp_path / "conflicts.jsonl")
        assert store.get_conflict("nope") is None

    def test_resolution_roundtrip(self, tmp_path):
        store = ConflictStore(tmp_path / "conflicts.jsonl")
        store.resolve_conflict("cid", "manual", manual_value=0.25)
        res = store.get_resolution("cid")
        assert res == {"conflict_id": "cid", "resolution": "manual", "manual_value": 0.25}
        assert store.get_resolution("other") is None

    def test_default_path(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        store = ConflictStore()
        assert store.file_path.name == "conflicts.jsonl"

    def test_load_skips_blank_and_malformed(self, tmp_path):
        path = tmp_path / "conflicts.jsonl"
        c = _conflict("A")
        path.write_text(
            json.dumps(c.to_dict()) + "\n\n" + "not-json\n" + json.dumps({"episode": 1}) + "\n",
            encoding="utf-8",
        )
        store = ConflictStore(path)
        assert len(store.get_all_conflicts()) == 1
