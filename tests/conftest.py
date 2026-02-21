import pytest

from annal.backend import OnnxEmbedder
from annal.backends.chromadb import ChromaBackend
from annal.store import MemoryStore

# Shared embedder instance across all tests (expensive to create)
_shared_embedder = None


def _get_shared_embedder():
    global _shared_embedder
    if _shared_embedder is None:
        _shared_embedder = OnnxEmbedder()
    return _shared_embedder


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for ChromaDB."""
    return str(tmp_path / "annal_data")


@pytest.fixture
def tmp_config_path(tmp_path):
    """Provide a temporary config file path."""
    return str(tmp_path / "config.yaml")


def make_store(data_dir: str, project: str) -> MemoryStore:
    """Factory to create a MemoryStore with ChromaBackend for tests."""
    embedder = _get_shared_embedder()
    backend = ChromaBackend(
        path=data_dir,
        collection_name=f"annal_{project}",
        dimension=embedder.dimension,
    )
    return MemoryStore(backend, embedder)
