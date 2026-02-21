"""Tests for QdrantBackend implementing VectorBackend protocol."""

import uuid

import pytest

from annal.backend import OnnxEmbedder

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

pytestmark = pytest.mark.skipif(not _qdrant_available(), reason="Qdrant not available")


@pytest.fixture(scope="module")
def embedder():
    return OnnxEmbedder()


@pytest.fixture
def backend(embedder):
    """Create a QdrantBackend with a unique collection, clean up after."""
    collection = f"test_{uuid.uuid4().hex[:8]}"
    b = QdrantBackend(
        url="http://localhost:6333",
        collection_name=collection,
        dimension=embedder.dimension,
    )
    yield b
    # Cleanup
    try:
        QdrantClient(url="http://localhost:6333").delete_collection(collection)
    except Exception:
        pass


def test_insert_and_query(backend, embedder):
    emb = embedder.embed("authentication decision about JWT")
    backend.insert(
        "m1",
        "authentication decision about JWT",
        emb,
        {"tags": ["auth"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"},
    )
    results = backend.query(emb, limit=5)
    assert len(results) == 1
    assert results[0].id == "m1"
    assert results[0].text == "authentication decision about JWT"
    assert results[0].metadata["tags"] == ["auth"]


def test_insert_and_get(backend, embedder):
    emb = embedder.embed("some memory")
    backend.insert("m1", "some memory", emb, {"tags": ["test"], "created_at": "2026-01-01T00:00:00"})
    results = backend.get(["m1"])
    assert len(results) == 1
    assert results[0].id == "m1"
    assert results[0].text == "some memory"
    assert results[0].metadata["tags"] == ["test"]


def test_get_empty(backend):
    results = backend.get(["nonexistent"])
    assert len(results) == 0


def test_scan(backend, embedder):
    for i in range(5):
        emb = embedder.embed(f"memory {i}")
        backend.insert(f"m{i}", f"memory {i}", emb, {"tags": ["test"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})
    results, total = backend.scan(offset=0, limit=3)
    assert len(results) == 3
    assert total == 5


def test_scan_with_where(backend, embedder):
    backend.insert("m1", "agent mem", embedder.embed("agent mem"), {"tags": ["a"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "file chunk", embedder.embed("file chunk"), {"tags": ["b"], "chunk_type": "file-indexed", "created_at": "2026-01-01T00:00:00"})
    results, total = backend.scan(offset=0, limit=10, where={"chunk_type": "agent-memory"})
    assert total == 1
    assert results[0].id == "m1"


def test_count(backend, embedder):
    assert backend.count() == 0
    backend.insert("m1", "test", embedder.embed("test"), {"tags": [], "created_at": "2026-01-01T00:00:00"})
    assert backend.count() == 1


def test_count_with_where(backend, embedder):
    backend.insert("m1", "a", embedder.embed("a"), {"tags": [], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "b", embedder.embed("b"), {"tags": [], "chunk_type": "file-indexed", "created_at": "2026-01-01T00:00:00"})
    assert backend.count(where={"chunk_type": "agent-memory"}) == 1


def test_delete(backend, embedder):
    backend.insert("m1", "test", embedder.embed("test"), {"tags": [], "created_at": "2026-01-01T00:00:00"})
    backend.delete(["m1"])
    assert backend.count() == 0


def test_update_text_and_metadata(backend, embedder):
    emb = embedder.embed("original")
    backend.insert("m1", "original", emb, {"tags": ["old"], "created_at": "2026-01-01T00:00:00"})
    new_emb = embedder.embed("updated")
    backend.update("m1", text="updated", embedding=new_emb, metadata={"tags": ["new"], "created_at": "2026-01-01T00:00:00"})
    results = backend.get(["m1"])
    assert results[0].text == "updated"
    assert results[0].metadata["tags"] == ["new"]


def test_update_metadata_only(backend, embedder):
    emb = embedder.embed("content stays")
    backend.insert("m1", "content stays", emb, {"tags": ["old"], "created_at": "2026-01-01T00:00:00"})
    backend.update("m1", text=None, embedding=None, metadata={"tags": ["new"], "created_at": "2026-01-01T00:00:00"})
    results = backend.get(["m1"])
    assert results[0].text == "content stays"
    assert results[0].metadata["tags"] == ["new"]


def test_query_with_tag_filter(backend, embedder):
    """Tag filtering happens server-side in Qdrant via MatchAny."""
    backend.insert("m1", "auth stuff", embedder.embed("auth stuff"), {"tags": ["auth", "decision"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "frontend stuff", embedder.embed("frontend stuff"), {"tags": ["frontend"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})
    results = backend.query(embedder.embed("stuff"), limit=10, where={"tags": {"$contains_any": ["auth"]}})
    assert len(results) == 1
    assert results[0].id == "m1"


def test_query_with_source_prefix(backend, embedder):
    backend.insert("m1", "file content", embedder.embed("file content"), {"tags": [], "source": "file:/home/user/project/README.md|intro", "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "other content", embedder.embed("other content"), {"tags": [], "source": "file:/home/user/other/file.md", "created_at": "2026-01-01T00:00:00"})
    results = backend.query(embedder.embed("content"), limit=10, where={"source": {"$prefix": "file:/home/user/project"}})
    assert len(results) == 1
    assert results[0].id == "m1"


def test_query_with_date_range(backend, embedder):
    backend.insert("m1", "old", embedder.embed("old"), {"tags": [], "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "new", embedder.embed("new"), {"tags": [], "created_at": "2026-02-15T00:00:00"})
    results = backend.query(embedder.embed("content"), limit=10, where={"created_at": {"$gt": "2026-02-01T00:00:00"}})
    assert len(results) == 1
    assert results[0].id == "m2"


def test_scan_with_source_prefix(backend, embedder):
    backend.insert("m1", "file a", embedder.embed("file a"), {"tags": [], "source": "file:/project/a.md", "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "file b", embedder.embed("file b"), {"tags": [], "source": "file:/other/b.md", "created_at": "2026-01-01T00:00:00"})
    results, total = backend.scan(offset=0, limit=10, where={"source": {"$prefix": "file:/project"}})
    assert total == 1
    assert results[0].id == "m1"


def test_scan_with_tag_filter(backend, embedder):
    backend.insert("m1", "tagged", embedder.embed("tagged"), {"tags": ["auth"], "created_at": "2026-01-01T00:00:00"})
    backend.insert("m2", "untagged", embedder.embed("untagged"), {"tags": ["other"], "created_at": "2026-01-01T00:00:00"})
    results, total = backend.scan(offset=0, limit=10, where={"tags": {"$contains_any": ["auth"]}})
    assert total == 1
    assert results[0].id == "m1"


def test_hybrid_search_boosts_keyword_match(embedder):
    """BM25 hybrid search should boost documents containing the exact query term."""
    collection = f"test_{uuid.uuid4().hex[:8]}"
    b = QdrantBackend(
        url="http://localhost:6333",
        collection_name=collection,
        dimension=embedder.dimension,
        hybrid=True,
    )
    try:
        b.insert("m1", "The HNSW algorithm uses hierarchical navigable small world graphs",
                 embedder.embed("The HNSW algorithm uses hierarchical navigable small world graphs"),
                 {"tags": ["tech"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})
        b.insert("m2", "We decided to use PostgreSQL for the user database",
                 embedder.embed("We decided to use PostgreSQL for the user database"),
                 {"tags": ["tech"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"})

        results = b.query(embedder.embed("HNSW"), limit=5, query_text="HNSW")
        assert results[0].id == "m1"
    finally:
        QdrantClient(url="http://localhost:6333").delete_collection(collection)
