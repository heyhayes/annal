"""Qdrant-specific backend tests.

Shared conformance tests live in test_backend_conformance.py.
This file contains tests for Qdrant-only features (hybrid search).
"""

import uuid

import pytest

try:
    from qdrant_client import QdrantClient
    from annal.backends.qdrant import QdrantBackend
    from annal.embedder import OnnxEmbedder

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
