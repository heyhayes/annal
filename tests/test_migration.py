"""Tests for migration between backends."""

import pytest

from annal.embedder import OnnxEmbedder
from annal.backends.chromadb import ChromaBackend
from annal.migrate import migrate


@pytest.fixture(scope="module")
def embedder():
    return OnnxEmbedder()


def test_migrate_chromadb_to_chromadb(tmp_path, embedder):
    """Migration preserves all documents and metadata."""
    src = ChromaBackend(path=str(tmp_path / "src"), collection_name="test", dimension=embedder.dimension)
    dst = ChromaBackend(path=str(tmp_path / "dst"), collection_name="test", dimension=embedder.dimension)

    for i in range(10):
        emb = embedder.embed(f"memory {i}")
        src.insert(
            f"m{i}", f"memory {i}", emb,
            {"tags": ["test", "batch"], "chunk_type": "agent-memory", "created_at": "2026-01-01T00:00:00"},
        )

    count = migrate(src, dst, embedder)
    assert count == 10
    assert dst.count() == 10

    # Verify content and metadata preserved
    for i in range(10):
        results = dst.get([f"m{i}"])
        assert len(results) == 1
        assert results[0].text == f"memory {i}"
        assert results[0].metadata["tags"] == ["test", "batch"]
        assert results[0].metadata["chunk_type"] == "agent-memory"


def test_migrate_empty_source(tmp_path, embedder):
    """Migrating from an empty backend should succeed with 0 count."""
    src = ChromaBackend(path=str(tmp_path / "src"), collection_name="test", dimension=embedder.dimension)
    dst = ChromaBackend(path=str(tmp_path / "dst"), collection_name="test", dimension=embedder.dimension)

    count = migrate(src, dst, embedder)
    assert count == 0
    assert dst.count() == 0


def test_migrate_preserves_ids(tmp_path, embedder):
    """Document IDs should be preserved during migration."""
    src = ChromaBackend(path=str(tmp_path / "src"), collection_name="test", dimension=embedder.dimension)
    dst = ChromaBackend(path=str(tmp_path / "dst"), collection_name="test", dimension=embedder.dimension)

    src.insert("custom-id-123", "test doc", embedder.embed("test doc"), {"tags": [], "created_at": "2026-01-01T00:00:00"})

    migrate(src, dst, embedder)

    results = dst.get(["custom-id-123"])
    assert len(results) == 1
    assert results[0].id == "custom-id-123"
