# Spike 8 Design — Vector Backend Abstraction + Qdrant + Hybrid Search

Introduce a `VectorBackend` protocol to decouple storage from business logic, implement Qdrant as the first alternative backend, and add hybrid search (BM25 + vector fusion) which Qdrant supports natively.

## Phase 1: Abstraction layer

Extract two protocols from the current `MemoryStore`: `VectorBackend` (storage operations) and `Embedder` (text → vector). Refactor the existing ChromaDB code into `ChromaBackend`. `MemoryStore` becomes a thin business-logic layer that delegates storage to whichever backend is configured.

### VectorBackend protocol

```python
@dataclass
class VectorResult:
    id: str
    text: str
    metadata: dict
    distance: float | None = None

class VectorBackend(Protocol):
    def insert(self, id: str, text: str, embedding: list[float], metadata: dict) -> None: ...
    def update(self, id: str, text: str | None, embedding: list[float] | None, metadata: dict | None) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def query(self, embedding: list[float], limit: int, where: dict | None = None) -> list[VectorResult]: ...
    def get(self, ids: list[str]) -> list[VectorResult]: ...
    def scan(self, offset: int, limit: int, where: dict | None = None) -> tuple[list[VectorResult], int]: ...
    def count(self, where: dict | None = None) -> int: ...
```

### Embedder protocol

```python
class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

Default implementation wraps `ONNXMiniLM_L6_V2` — same model ChromaDB uses internally. Pulled out so all backends receive identical vectors.

### Where clause grammar

Minimal dict-based grammar all backends can implement:

```python
{"chunk_type": "agent-memory"}                                # equality
{"source": {"$prefix": "file:/home/user/project"}}            # prefix match
{"created_at": {"$gt": "2026-01-01T00:00:00"}}                # range
{"tags": {"$contains_any": ["decision", "auth"]}}             # tag containment
{"chunk_type": "agent-memory", "tags": {"$contains_any": ["bug"]}}  # compound (AND)
```

### ChromaBackend

Wraps the existing ChromaDB PersistentClient. Tags stored as JSON strings (ChromaDB limitation), deserialized on read. `$contains_any` handled post-query. Embeddings arrive pre-computed (no longer using ChromaDB's internal embedding function). This is a pure refactor of the existing code.

### MemoryStore changes

Constructor changes from `MemoryStore(data_dir, project)` to `MemoryStore(backend, embedder)`. Public API (`store`, `search`, `browse`, `delete`, `update`, `stats`, `count`, etc.) stays identical. Tags become native `list[str]` in the MemoryStore interface; the ChromaBackend handles JSON serialization internally.

Fuzzy tag expansion (`_expand_tags`) stays in MemoryStore — it's business logic that uses the Embedder.

### StorePool changes

`get_store()` currently creates `MemoryStore(data_dir, project)`. After refactor it creates the appropriate backend based on config, instantiates the shared Embedder, and passes both to `MemoryStore(backend, embedder)`.

### Files

- New: `src/annal/backend.py` — `VectorBackend` protocol, `VectorResult` dataclass, `Embedder` protocol, `OnnxEmbedder` default implementation
- New: `src/annal/backends/chromadb.py` — `ChromaBackend`
- Modify: `src/annal/store.py` — `MemoryStore` delegates to backend + embedder
- Modify: `src/annal/pool.py` — backend instantiation in `get_store()`
- Modify: `src/annal/config.py` — `storage.backend` config field

## Phase 2: Qdrant backend

### Installation

Download the Qdrant binary for Linux x86_64 from GitHub releases. Run as a systemd user service on port 6333. Add `qdrant-client` to project dependencies.

### QdrantBackend implementation

```python
class QdrantBackend:
    def __init__(self, url: str, collection_name: str, dimension: int) -> None: ...
```

Tags stored as a native list payload field. `$contains_any` maps to Qdrant's `MatchAny` filter condition — server-side, no post-query filtering. `$prefix` maps to `MatchText` with prefix mode. `$gt`/`$lt` map to `Range`.

`query()` uses `client.query_points()`. `scan()` uses `client.scroll()`. `count()` uses `client.count()`.

Collection created on first use with cosine distance metric and the dimension from the Embedder.

### Configuration

```yaml
storage:
  backend: qdrant         # or "chromadb"

  backends:
    qdrant:
      url: http://localhost:6333
    chromadb:
      path: ~/.annal/data

embedder:
  model: all-MiniLM-L6-v2
```

When `backend` is not set, defaults to `chromadb` for backwards compatibility.

### Files

- New: `src/annal/backends/qdrant.py` — `QdrantBackend`
- Modify: `src/annal/config.py` — storage config parsing
- Modify: `src/annal/pool.py` — backend selection logic

## Phase 3: Migration tooling

CLI command to move data between backends:

```bash
annal migrate --from chromadb --to qdrant
```

Reads all documents from the source backend via `scan()`, re-embeds each (or carries stored vectors if available), inserts into the target backend. Batches inserts in groups of 100 for Qdrant's `upsert` efficiency. Shows progress bar via stderr.

### Files

- Modify: `src/annal/cli.py` — `migrate` subcommand
- New: `src/annal/migrate.py` — migration logic

## Phase 4: Hybrid search

Qdrant supports sparse vectors (BM25) alongside dense vectors, with built-in reciprocal rank fusion. This means hybrid search doesn't require a separate full-text engine — it's a single Qdrant query that fuses both result sets.

### Approach

Add a BM25 sparse vector alongside the existing dense vector in the Qdrant collection. At index time, store both the dense embedding (from the Embedder) and a BM25 sparse vector (computed by Qdrant from the document text). At query time, use Qdrant's `prefetch` with both dense and sparse queries, fused via reciprocal rank fusion.

### Qdrant collection config

```python
from qdrant_client.models import (
    VectorParams, SparseVectorParams, Distance, Modifier
)

client.create_collection(
    collection_name=name,
    vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
    sparse_vectors_config={
        "bm25": SparseVectorParams(modifier=Modifier.IDF),
    },
)
```

### QdrantBackend.query changes

When hybrid search is enabled, the query method uses Qdrant's Query API with prefetch:

```python
from qdrant_client.models import Prefetch, FusionQuery, Fusion

results = client.query_points(
    collection_name=self._collection,
    prefetch=[
        Prefetch(query=dense_embedding, using="", limit=limit),
        Prefetch(query=sparse_query, using="bm25", limit=limit),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=limit,
    query_filter=qfilter,
)
```

### MemoryStore integration

The hybrid search is transparent to `MemoryStore`. `QdrantBackend.query()` handles the fusion internally. For `ChromaBackend`, the `query()` method continues doing pure vector search — hybrid is Qdrant-only since ChromaDB has no full-text capability.

The `search_memories` MCP tool doesn't need a new parameter. Hybrid search is the default behaviour on backends that support it.

### Files

- Modify: `src/annal/backends/qdrant.py` — sparse vector handling in `insert`, `update`, `query`
- Tests: `tests/test_qdrant.py` — hybrid search tests

## Phase 5: Test suite

### Unit tests

Each backend gets its own test file that exercises the `VectorBackend` protocol:

- `tests/test_backend_chromadb.py` — existing store tests refactored to test via ChromaBackend
- `tests/test_backend_qdrant.py` — same test patterns against QdrantBackend (requires running Qdrant)

### Integration tests

- `tests/test_store.py` — existing tests continue to work (MemoryStore with ChromaBackend is the default)
- `tests/test_migration.py` — migrate from ChromaDB to Qdrant, verify data integrity

### Qdrant test fixture

Qdrant tests require a running instance. Use a pytest fixture that checks for Qdrant availability and skips if not present:

```python
@pytest.fixture
def qdrant_backend(request):
    try:
        client = QdrantClient(url="http://localhost:6333")
        client.get_collections()
    except Exception:
        pytest.skip("Qdrant not available")
    # ... create test collection, yield, cleanup
```

## Phase 6: Backlog, version bump, docs

- Update `docs/plans/2026-02-20-feature-backlog.md` with shipped items
- Bump version to `0.6.0`
- Update README with backend configuration section
- Update `docs/proposals/vector-backend-abstraction.md` status to "Implemented"

## What's NOT in this spike

- Split backends (different backend per chunk type) — config and routing concern, easy to add later
- Qdrant Cloud / remote backends — local only for now
- pgvector backend — Qdrant first, pgvector if needed later
- CLI subcommands beyond migrate (`annal search`, `annal topics`, etc.)
- Import/export to JSONL

## Verification

- `pytest -v` — all existing tests pass with ChromaDB backend (pure refactor)
- `pytest tests/test_backend_qdrant.py -v` — Qdrant backend tests pass against local instance
- `annal migrate --from chromadb --to qdrant` — migrates existing data successfully
- Restart server with `backend: qdrant` config, verify dashboard works
- Semantic search returns results — both pure vector and hybrid (BM25 + vector)
- Tag filtering is server-side on Qdrant (no over-fetch visible in logs)
- Multiple concurrent Claude sessions can search and store without errors
