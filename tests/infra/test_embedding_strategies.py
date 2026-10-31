"""Unit tests for vector embedding strategies and factory provider (offline, no network)."""

import math
from unittest.mock import MagicMock
import pytest

from app.infra.embedding_provider import get_vector_strategy, reset_vector_strategy
from app.infra.providers.auto_embedding import AutoEmbeddingStrategy
from app.infra.providers.base import EmbeddingError, run_with_backoff
from app.infra.providers.mock_embedding import MockEmbeddingStrategy, cosine_similarity
from app.infra.providers.self_embedding import SelfEmbeddingStrategy


@pytest.fixture(autouse=True)
def clean_strategy_cache():
    """Ensure cached strategy is reset before and after every test."""
    reset_vector_strategy()
    yield
    reset_vector_strategy()


class TestMockEmbeddingStrategy:
    """Tests for MockEmbeddingStrategy and cosine_similarity."""

    def test_mock_vectors_are_deterministic(self):
        strategy = MockEmbeddingStrategy(dimensions=128)
        text = "Peanut allergy with severe throat swelling"
        v1 = strategy.embed_query(text)
        v2 = strategy.embed_query(text)
        assert len(v1) == 128
        assert v1 == v2

    def test_mock_vectors_are_normalized(self):
        strategy = MockEmbeddingStrategy(dimensions=64)
        v = strategy.embed_query("Gluten free pizza crust")
        norm = math.sqrt(sum(x * x for x in v))
        assert math.isclose(norm, 1.0, rel_tol=1e-5)

    def test_empty_text_vector_is_normalized_and_deterministic(self):
        strategy = MockEmbeddingStrategy(dimensions=64)
        v1 = strategy.embed_query("")
        v2 = strategy.embed_query("    ")
        assert len(v1) == 64
        assert v1 == v2
        norm = math.sqrt(sum(x * x for x in v1))
        assert math.isclose(norm, 1.0, rel_tol=1e-5)

    def test_similar_texts_score_higher_than_unrelated_texts(self):
        strategy = MockEmbeddingStrategy(dimensions=256)
        query = "severe peanut allergy anaphylaxis"
        similar = "anaphylaxis reaction to severe peanut intake"
        unrelated = "authentic Italian carbonara pasta with pecorino cheese"

        q_vec = strategy.embed_query(query)
        sim_vec = strategy.embed_query(similar)
        unrelated_vec = strategy.embed_query(unrelated)

        sim_score = cosine_similarity(q_vec, sim_vec)
        unrelated_score = cosine_similarity(q_vec, unrelated_vec)

        assert sim_score > unrelated_score
        assert sim_score > 0.5

    def test_mock_prepare_document_adds_embedding(self):
        strategy = MockEmbeddingStrategy(dimensions=256, text_path="text")
        doc = {"_id": "mem_01", "text": "Patient cannot eat shellfish", "status": "active"}
        prepared = strategy.prepare_document(doc)

        assert "embedding" in prepared
        assert len(prepared["embedding"]) == 256
        assert prepared["text"] == "Patient cannot eat shellfish"
        # Original document is unmodified
        assert "embedding" not in doc

    def test_mock_build_index_definition(self):
        strategy = MockEmbeddingStrategy(dimensions=256)
        index_def = strategy.build_index_definition(["user_id", "status", "type"])

        assert "fields" in index_def
        fields = index_def["fields"]
        assert fields[0] == {
            "type": "vector",
            "path": "embedding",
            "numDimensions": 256,
            "similarity": "cosine",
        }
        assert fields[1] == {"type": "filter", "path": "user_id"}
        assert fields[2] == {"type": "filter", "path": "status"}
        assert fields[3] == {"type": "filter", "path": "type"}

    def test_mock_build_vector_search_stage(self):
        strategy = MockEmbeddingStrategy(
            dimensions=128, index_name="custom_index", num_candidates=50
        )
        stage = strategy.build_vector_search_stage(
            query_text="no dairy",
            filters={"user_id": "usr_123", "status": "active", "type": ["dietary", "allergy"]},
            limit=5,
            num_candidates=80,
        )

        assert "$vectorSearch" in stage
        vs = stage["$vectorSearch"]
        assert vs["index"] == "custom_index"
        assert vs["path"] == "embedding"
        assert "queryVector" in vs
        assert len(vs["queryVector"]) == 128
        assert vs["limit"] == 5
        assert vs["numCandidates"] == 80
        assert vs["filter"]["user_id"] == "usr_123"
        assert vs["filter"]["status"] == "active"
        assert vs["filter"]["type"] == {"$in": ["dietary", "allergy"]}


class TestAutoEmbeddingStrategy:
    """Tests for AutoEmbeddingStrategy (Atlas Automated Embedding)."""

    def test_auto_prepare_document_leaves_document_unchanged(self):
        strategy = AutoEmbeddingStrategy(model_name="voyage-3.5-lite", text_path="text")
        doc = {
            "_id": "mem_02",
            "text": "Prefers plant-based meals",
            "type": "preference",
            "status": "active",
        }
        prepared = strategy.prepare_document(doc)

        assert prepared == doc
        assert "embedding" not in prepared

    def test_auto_prepare_document_removes_embedding_if_present(self):
        strategy = AutoEmbeddingStrategy(model_name="voyage-3.5-lite")
        doc = {"text": "hello", "embedding": [0.1, 0.2]}
        prepared = strategy.prepare_document(doc)
        assert "embedding" not in prepared

    def test_auto_embed_query_returns_none(self):
        strategy = AutoEmbeddingStrategy(model_name="voyage-3.5-lite")
        assert strategy.embed_query("vegetarian meal plans") is None

    def test_auto_build_index_definition(self):
        strategy = AutoEmbeddingStrategy(
            model_name="voyage-3.5",
            text_path="text",
        )
        index_def = strategy.build_index_definition(["user_id", "status"])

        assert "fields" in index_def
        fields = index_def["fields"]
        assert fields[0] == {
            "type": "text",
            "path": "text",
            "model": "voyage-3.5",
        }
        assert fields[1] == {"type": "filter", "path": "user_id"}
        assert fields[2] == {"type": "filter", "path": "status"}

    def test_auto_build_vector_search_stage(self):
        strategy = AutoEmbeddingStrategy(
            model_name="voyage-3.5-lite",
            index_name="auto_vector_idx",
            text_path="text",
            num_candidates=100,
        )
        stage = strategy.build_vector_search_stage(
            query_text="low sodium dinner",
            filters={"user_id": "usr_999", "status": "active"},
            limit=10,
        )

        assert "$vectorSearch" in stage
        vs = stage["$vectorSearch"]
        assert vs["index"] == "auto_vector_idx"
        assert vs["path"] == "text"
        assert vs["query"] == "low sodium dinner"
        assert "queryVector" not in vs
        assert vs["limit"] == 10
        assert vs["numCandidates"] == 100
        assert vs["filter"]["user_id"] == "usr_999"

    def test_auto_invalid_model_raises_error(self):
        with pytest.raises(ValueError, match="Unsupported Voyage model"):
            AutoEmbeddingStrategy(model_name="unsupported-model-v1")


class TestSelfEmbeddingStrategy:
    """Tests for SelfEmbeddingStrategy."""

    def test_self_missing_api_key_raises_error(self):
        with pytest.raises(EmbeddingError, match="VOYAGE_API_KEY is required"):
            SelfEmbeddingStrategy(api_key="")

    def test_self_prepare_document_with_mocked_client(self):
        strategy = SelfEmbeddingStrategy(
            model_name="voyage-3.5-lite",
            dimensions=4,
            api_key="mock_voyage_key",
        )

        # Mock the internal client
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.embeddings = [[0.1, 0.2, 0.3, 0.4]]
        mock_client.embed.return_value = mock_res
        strategy._client = mock_client

        doc = {"text": "Keto meal preferences"}
        prepared = strategy.prepare_document(doc)

        assert "embedding" in prepared
        assert prepared["embedding"] == [0.1, 0.2, 0.3, 0.4]
        mock_client.embed.assert_called_once_with(
            ["Keto meal preferences"],
            model="voyage-3.5-lite",
            input_type="document",
            output_dimension=4,
        )

    def test_self_dimension_mismatch_raises_error(self):
        strategy = SelfEmbeddingStrategy(
            model_name="voyage-3.5-lite",
            dimensions=1024,
            api_key="mock_voyage_key",
        )
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.embeddings = [[0.1, 0.2]]  # Only 2 dims instead of 1024
        mock_client.embed.return_value = mock_res
        strategy._client = mock_client

        with pytest.raises(EmbeddingError, match="Vector dimension mismatch"):
            strategy.embed_query("Test query")


class TestVectorStrategyFactory:
    """Tests for get_vector_strategy factory and caching."""

    def test_factory_returns_mock_strategy(self):
        strategy = get_vector_strategy({"EMBEDDING_MODE": "mock", "EMBEDDING_DIMENSIONS": 128})
        assert isinstance(strategy, MockEmbeddingStrategy)
        assert strategy.mode == "mock"
        assert strategy.dimensions == 128

    def test_factory_returns_auto_strategy(self):
        strategy = get_vector_strategy(
            {"EMBEDDING_MODE": "auto", "EMBEDDING_MODEL": "voyage-3.5"}
        )
        assert isinstance(strategy, AutoEmbeddingStrategy)
        assert strategy.mode == "auto"
        assert strategy.model_name == "voyage-3.5"

    def test_factory_returns_self_strategy(self):
        strategy = get_vector_strategy(
            {
                "EMBEDDING_MODE": "self",
                "EMBEDDING_MODEL": "voyage-3.5-lite",
                "EMBEDDING_DIMENSIONS": 512,
                "VOYAGE_API_KEY": "fake_test_key",
            }
        )
        assert isinstance(strategy, SelfEmbeddingStrategy)
        assert strategy.mode == "self"
        assert strategy.dimensions == 512

    def test_factory_invalid_mode_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported EMBEDDING_MODE"):
            get_vector_strategy({"EMBEDDING_MODE": "unknown_mode"})

    def test_factory_invalid_auto_model_raises_error(self):
        with pytest.raises(ValueError, match="Unsupported Voyage model"):
            get_vector_strategy(
                {"EMBEDDING_MODE": "auto", "EMBEDDING_MODEL": "invalid-voyage-model"}
            )

    def test_factory_missing_self_api_key_raises_error(self):
        with pytest.raises(EmbeddingError, match="VOYAGE_API_KEY is required"):
            get_vector_strategy({"EMBEDDING_MODE": "self", "VOYAGE_API_KEY": ""})

    def test_factory_caches_singleton_instance(self):
        reset_vector_strategy()
        s1 = get_vector_strategy()
        s2 = get_vector_strategy()
        assert s1 is s2


class TestRunWithBackoff:
    """Tests for run_with_backoff helper."""

    def test_backoff_retries_and_succeeds(self):
        attempts = 0

        def flaky_task():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("Temporary timeout")
            return "success"

        result = run_with_backoff(
            flaky_task,
            max_attempts=4,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),
        )
        assert result == "success"
        assert attempts == 3

    def test_backoff_exhausts_and_raises(self):
        def failing_task():
            raise TimeoutError("Never succeeds")

        with pytest.raises(TimeoutError):
            run_with_backoff(
                failing_task,
                max_attempts=2,
                base_delay=0.01,
                retryable_exceptions=(TimeoutError,),
            )

