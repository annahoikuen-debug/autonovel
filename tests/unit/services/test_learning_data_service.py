"""Tests for src/services/learning_data_service.py."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock


from src.services.learning_data_service import LearningDataService


def make_repo(review=None, execute=None):
    repo = MagicMock()
    repo.misc = MagicMock()
    repo.misc.get_patch_review = AsyncMock(return_value=review)
    repo.session = MagicMock()
    repo.session.execute = AsyncMock(return_value=execute)
    return repo


class TestRecordNegativeSample:
    async def test_no_repo(self):
        svc = LearningDataService()
        assert await svc.record_negative_sample(1, "rejected") is None

    async def test_review_missing(self):
        svc = LearningDataService(repo=make_repo(review=None))
        assert await svc.record_negative_sample(1, "rejected") is None

    async def test_rejected_labels_negative(self):
        review = {
            "audit_issue_ids": [1, 2],
            "learning_metadata": {"negative_sample_candidates": ["consistency"]},
            "diff_json": {"a": 1},
        }
        repo = make_repo(review=review)
        svc = LearningDataService(repo=repo, chroma_client=MagicMock())
        assert await svc.record_negative_sample(5, "rejected", "u1", "bad") == 1
        stmt = repo.session.execute.await_args.args[0]
        assert "patch_reviews" in str(stmt)
        params = stmt.compile().params
        payload = params["learning_metadata"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert payload["learned_patterns"][0]["label"] == "negative"
        assert payload["learned_patterns"][0]["resolution"] == "rejected"

    async def test_approved_labels_positive(self):
        review = {"learning_metadata": {"negative_sample_candidates": ["tone"]}}
        repo = make_repo(review=review)
        svc = LearningDataService(repo=repo)
        assert await svc.record_negative_sample(5, "approved") == 1

    async def test_modified_labels_positive(self):
        review = {"learning_metadata": {"negative_sample_candidates": ["tone", "plot"]}}
        repo = make_repo(review=review)
        svc = LearningDataService(repo=repo)
        assert await svc.record_negative_sample(5, "modified") == 2

    async def test_no_candidates(self):
        repo = make_repo(review={"learning_metadata": {}})
        svc = LearningDataService(repo=repo)
        assert await svc.record_negative_sample(5, "rejected") == 0

    async def test_existing_learned_patterns_appended(self):
        review = {
            "learning_metadata": {
                "negative_sample_candidates": ["x"],
                "learned_patterns": [{"audit_type": "old"}],
            }
        }
        repo = make_repo(review=review)
        svc = LearningDataService(repo=repo)
        assert await svc.record_negative_sample(5, "rejected") == 1
        stmt = repo.session.execute.await_args.args[0]
        payload = stmt.compile().params["learning_metadata"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert len(payload["learned_patterns"]) == 2


class TestStoreLearningVector:
    async def test_no_client(self):
        svc = LearningDataService()
        assert await svc._store_learning_vector({"audit_type": "x"}) is None

    async def test_stores_vector(self):
        collection = MagicMock()
        chroma = MagicMock()
        chroma.get_or_create_collection.return_value = collection
        svc = LearningDataService(chroma_client=chroma)
        await svc._store_learning_vector(
            {
                "patch_review_id": 3,
                "audit_type": "tone",
                "label": "negative",
                "resolution": "rejected",
                "reviewer_id": None,
                "original_feedback": {"k": "v"},
                "created_at": "now",
            }
        )
        chroma.get_or_create_collection.assert_called_once_with("audit_learning_samples")
        kwargs = collection.add.call_args.kwargs
        assert "audit_type:tone" in kwargs["documents"][0]
        assert kwargs["metadatas"][0]["label"] == "negative"

    async def test_string_feedback(self):
        collection = MagicMock()
        chroma = MagicMock()
        chroma.get_or_create_collection.return_value = collection
        svc = LearningDataService(chroma_client=chroma)
        await svc._store_learning_vector(
            {
                "patch_review_id": 3,
                "audit_type": "tone",
                "label": "positive",
                "resolution": "approved",
                "original_feedback": "plain",
                "created_at": "now",
            }
        )
        assert "plain" in collection.add.call_args.kwargs["documents"][0]

    async def test_exception_swallowed(self):
        chroma = MagicMock()
        chroma.get_or_create_collection.side_effect = RuntimeError("bad")
        svc = LearningDataService(chroma_client=chroma)
        assert await svc._store_learning_vector({"audit_type": "a", "label": "negative"}) is None


class TestPatternQueries:
    async def test_no_client_negative(self):
        svc = LearningDataService()
        assert await svc.get_negative_patterns("tone") == []

    async def test_no_client_positive(self):
        svc = LearningDataService()
        assert await svc.get_positive_patterns("tone") == []

    async def test_negative_patterns(self):
        collection = MagicMock()
        collection.query.return_value = {"metadatas": [[{"audit_type": "tone", "label": "negative"}]]}
        chroma = MagicMock()
        chroma.get_collection.return_value = collection
        svc = LearningDataService(chroma_client=chroma)
        result = await svc.get_negative_patterns("tone", limit=3)
        assert result == [{"audit_type": "tone", "label": "negative"}]
        assert collection.query.call_args.kwargs["n_results"] == 3

    async def test_positive_patterns(self):
        collection = MagicMock()
        collection.query.return_value = {"metadatas": [[{"audit_type": "tone", "label": "positive"}]]}
        chroma = MagicMock()
        chroma.get_collection.return_value = collection
        svc = LearningDataService(chroma_client=chroma)
        assert await svc.get_positive_patterns("tone") == [{"audit_type": "tone", "label": "positive"}]

    async def test_empty_collection(self):
        chroma = MagicMock()
        chroma.get_collection.return_value = None
        svc = LearningDataService(chroma_client=chroma)
        assert await svc.get_negative_patterns("tone") == []
        assert await svc.get_positive_patterns("tone") == []

    async def test_no_metadatas_key(self):
        collection = MagicMock()
        collection.query.return_value = {}
        chroma = MagicMock()
        chroma.get_collection.return_value = collection
        svc = LearningDataService(chroma_client=chroma)
        assert await svc.get_negative_patterns("tone") == []

    async def test_exception_returns_empty(self):
        chroma = MagicMock()
        chroma.get_collection.side_effect = RuntimeError("x")
        svc = LearningDataService(chroma_client=chroma)
        assert await svc.get_negative_patterns("tone") == []
        assert await svc.get_positive_patterns("tone") == []


class TestStatsAndSkip:
    async def test_stats_without_repo(self):
        assert await LearningDataService().get_audit_precision_stats() == {}

    async def test_stats_shape(self):
        svc = LearningDataService(repo=MagicMock())
        stats = await svc.get_audit_precision_stats(1)
        assert stats["total_reviews"] == 0
        assert "precision_by_type" in stats

    async def test_skip_no_patterns(self):
        svc = LearningDataService()
        assert await svc.should_skip_audit_type("tone") == (False, 0.0)

    async def test_skip_when_negative_dominates(self):
        svc = LearningDataService()
        svc.get_negative_patterns = AsyncMock(return_value=[{} for _ in range(6)])
        svc.get_positive_patterns = AsyncMock(return_value=[{}])
        assert await svc.should_skip_audit_type("tone", field_path="a.b") == (True, -0.3)

    async def test_moderate_negative_lowers_confidence(self):
        svc = LearningDataService()
        svc.get_negative_patterns = AsyncMock(return_value=[{} for _ in range(3)])
        svc.get_positive_patterns = AsyncMock(return_value=[{} for _ in range(2)])
        assert await svc.should_skip_audit_type("tone") == (False, -0.15)

    async def test_balanced(self):
        svc = LearningDataService()
        svc.get_negative_patterns = AsyncMock(return_value=[{} for _ in range(2)])
        svc.get_positive_patterns = AsyncMock(return_value=[{} for _ in range(2)])
        assert await svc.should_skip_audit_type("tone") == (False, 0.0)

    async def test_many_positive_no_adjustment(self):
        svc = LearningDataService()
        svc.get_negative_patterns = AsyncMock(return_value=[{}])
        svc.get_positive_patterns = AsyncMock(return_value=[{} for _ in range(10)])
        assert await svc.should_skip_audit_type("tone") == (False, 0.0)
