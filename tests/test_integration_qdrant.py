"""Integration tests for MemoryStore + QdrantBackend."""

import uuid

import pytest

try:
    from qdrant_client import QdrantClient
    from annal.backends.qdrant import QdrantBackend

    def _qdrant_available():
        try:
            QdrantClient(url="http://localhost:6333").get_collections()
            return True
        except Exception:
            return False
except ImportError:
    _qdrant_available = lambda: False

from annal.backend import OnnxEmbedder
from annal.store import MemoryStore

pytestmark = pytest.mark.skipif(not _qdrant_available(), reason="Qdrant not available")


@pytest.fixture(scope="module")
def embedder():
    return OnnxEmbedder()


@pytest.fixture
def store(embedder):
    """Create a MemoryStore backed by Qdrant, clean up after."""
    collection = f"test_{uuid.uuid4().hex[:8]}"
    backend = QdrantBackend(
        url="http://localhost:6333",
        collection_name=collection,
        dimension=embedder.dimension,
        hybrid=True,
    )
    yield MemoryStore(backend, embedder)
    try:
        QdrantClient(url="http://localhost:6333").delete_collection(collection)
    except Exception:
        pass


def test_store_and_search(store):
    store.store("JWT auth decision for the API gateway", tags=["auth", "decision"])
    results = store.search("authentication", limit=5)
    assert len(results) == 1
    assert "JWT" in results[0]["content"]


def test_search_with_fuzzy_tags(store):
    store.store("OAuth2 is used for authentication", tags=["authentication"])
    results = store.search("auth", tags=["auth"], limit=5)
    assert len(results) == 1  # fuzzy match: auth → authentication


def test_browse_with_type_filter(store):
    store.store("Agent memory", tags=["decision"])
    store.store("File chunk", tags=["indexed"], source="file:/project/README.md|intro", chunk_type="file-indexed")
    results, total = store.browse(chunk_type="agent-memory")
    assert total == 1
    assert "Agent memory" in results[0]["content"]


def test_browse_with_tag_filter(store):
    store.store("Auth decision", tags=["auth"])
    store.store("Frontend decision", tags=["frontend"])
    results, total = store.browse(tags=["auth"])
    assert total == 1
    assert "Auth" in results[0]["content"]


def test_delete(store):
    mem_id = store.store("To be deleted", tags=["temp"])
    store.delete(mem_id)
    results = store.get_by_ids([mem_id])
    assert len(results) == 0


def test_update(store):
    mem_id = store.store("Original content", tags=["v1"])
    store.update(mem_id, content="Updated content", tags=["v2"])
    results = store.get_by_ids([mem_id])
    assert results[0]["content"] == "Updated content"
    assert results[0]["tags"] == ["v2"]


def test_stats(store):
    store.store("Memory one", tags=["auth"])
    store.store("Memory two", tags=["auth", "decision"])
    stats = store.stats()
    assert stats["total"] >= 2
    assert stats["by_type"].get("agent-memory", 0) >= 2
    assert stats["by_tag"].get("auth", 0) >= 2


def test_list_topics(store):
    store.store("Auth decision", tags=["auth"])
    store.store("Deploy config", tags=["deploy"])
    topics = store.list_topics()
    assert "auth" in topics
    assert "deploy" in topics


def test_search_with_temporal_filter(store):
    store.store("Old memory", tags=["test"])
    results = store.search("memory", after="2020-01-01", limit=5)
    assert len(results) >= 1
    results = store.search("memory", after="2099-01-01", limit=5)
    assert len(results) == 0


def test_browse_with_source_prefix(store):
    store.store("File content", tags=[], source="file:/project/README.md|intro")
    store.store("Other content", tags=[], source="file:/other/file.md")
    results, total = store.browse(source_prefix="file:/project")
    assert total == 1
    assert "File content" in results[0]["content"]
