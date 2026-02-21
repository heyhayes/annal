# Vector Backend Abstraction Layer

|||
|---|---|
| Title | Vector Backend Abstraction Layer |
| Status | Implemented (spike 8, v0.6.0) |
| Created | 2026-02-21 |

## Abstract

Annal currently uses ChromaDB as its sole vector storage backend. ChromaDB uses SQLite internally, which limits concurrency to a single process and degrades under multi-agent workloads. This proposal introduces a `VectorBackend` protocol that decouples Annal's business logic from the storage implementation, enabling support for Qdrant and PostgreSQL with pgvector alongside the existing ChromaDB backend.

## Motivation

ChromaDB was the right choice for prototyping: zero configuration, bundled ONNX embeddings, pip install and go. But it has structural limitations that surface as Annal's workload grows.

Concurrent access is the primary issue. ChromaDB's PersistentClient uses SQLite, which doesn't support concurrent writers. The current workaround is funneling all access through a single server process, which serializes reads and writes. This works for one developer with a couple of sessions but becomes a bottleneck with multiple agents running in parallel, especially when file indexing competes with search queries.

Tag filtering is a secondary issue. ChromaDB doesn't natively support list-valued metadata, so tags are stored as JSON strings and filtered post-query in Python. This means Annal over-fetches results (3x the requested limit) and discards non-matching entries, wasting both embedding comparison work and memory.

Both Qdrant and pgvector solve these problems natively: concurrent access by design, and first-class support for array/set metadata filtering.

## Design

### Architecture layers

The current `MemoryStore` class mixes three concerns: embedding generation, vector storage operations, and business logic (fuzzy tag expansion, date normalization, file mtime tracking). The proposal separates these into three layers:

```
┌─────────────────────────────────────┐
│           MemoryStore               │  Business logic: fuzzy tags, date
│   store / search / browse / ...     │  filtering, file mtime management
├─────────────────────────────────────┤
│            Embedder                 │  Text → vector. Shared across
│      embed() / embed_batch()        │  all backends.
├─────────────────────────────────────┤
│          VectorBackend              │  Storage operations against a
│  insert / query / scan / delete     │  specific vector database.
└─────────────────────────────────────┘
```

### VectorBackend protocol

```python
from dataclasses import dataclass

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

The interface deals exclusively in pre-computed embeddings (as `list[float]`). Embedding generation is handled one layer up by the `Embedder`, ensuring all backends receive identical vectors regardless of which storage engine is in use.

### Where clause grammar

The `where` parameter uses a minimal dict-based grammar that all three backends can implement:

```python
# Equality
{"chunk_type": "agent-memory"}

# Prefix match
{"source": {"$prefix": "file:/home/user/project"}}

# Range (ISO 8601 strings, lexicographic comparison)
{"created_at": {"$gt": "2026-01-01T00:00:00"}}
{"created_at": {"$lt": "2026-03-01T00:00:00"}}

# Tag containment (any of the listed tags present)
{"tags": {"$contains_any": ["decision", "auth"]}}

# Compound (implicit AND)
{"chunk_type": "agent-memory", "tags": {"$contains_any": ["bug"]}}
```

This grammar is intentionally limited. Expanding it to support OR, NOT, nested conditions, or full-text search would leak backend-specific capabilities into the abstraction. Annal's filtering needs are simple and unlikely to require more.

### Embedder protocol

```python
class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

The default implementation wraps the same ONNX MiniLM-L6-V2 model that ChromaDB uses internally. Pulling it out as a separate concern means the same model produces the same vectors regardless of backend, so search quality doesn't change when switching storage engines.

The `dimension` property is needed because Qdrant and pgvector require the vector dimension at collection/table creation time, whereas ChromaDB infers it.

### Embedder in MemoryStore

`MemoryStore` takes both dependencies at construction:

```python
class MemoryStore:
    def __init__(self, backend: VectorBackend, embedder: Embedder) -> None:
        self._backend = backend
        self._embedder = embedder

    def store(self, content: str, tags: list[str], source: str = "",
              chunk_type: str = "agent-memory", file_mtime: float | None = None) -> str:
        mem_id = str(uuid.uuid4())
        embedding = self._embedder.embed(content)
        metadata = {
            "tags": tags,           # native list, not JSON string
            "source": source,
            "chunk_type": chunk_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if file_mtime is not None:
            metadata["file_mtime"] = file_mtime
        self._backend.insert(mem_id, content, embedding, metadata)
        return mem_id

    def search(self, query: str, limit: int = 5,
               tags: list[str] | None = None, after: str | None = None,
               before: str | None = None) -> list[dict]:
        embedding = self._embedder.embed(query)
        where = self._build_where(tags=tags, after=after, before=before)
        results = self._backend.query(embedding, limit=limit, where=where)
        return [self._format_result(r) for r in results]
```

Note that tags become a native `list[str]` in metadata rather than a JSON-encoded string. The ChromaDB backend serializes/deserializes tags internally (because ChromaDB doesn't support list metadata), but Qdrant and pgvector store them natively.

### Fuzzy tag expansion

The `_expand_tags` logic stays in `MemoryStore`. It uses the `Embedder` to compute cosine similarity between filter tags and known tags in the store. This is business logic, not storage, and works identically regardless of backend.

For backends that support server-side tag filtering (Qdrant, pgvector), the expanded tag set goes into the `where` clause via `$contains_any`. For ChromaDB, the backend still post-filters, but that happens behind the abstraction.

### Backend implementations

#### ChromaBackend

Wraps the existing ChromaDB PersistentClient. Minimal change from current code — the main difference is that embeddings arrive pre-computed rather than being generated by ChromaDB's internal embedding function. Tags are stored as JSON strings in metadata and deserialized on read (ChromaDB limitation). The `$contains_any` filter is handled post-query, same as the current implementation.

```python
class ChromaBackend:
    def __init__(self, path: str, collection_name: str) -> None:
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def insert(self, id: str, text: str, embedding: list[float], metadata: dict) -> None:
        meta = dict(metadata)
        meta["tags"] = json.dumps(meta["tags"])  # ChromaDB can't store lists
        self._collection.add(ids=[id], documents=[text], embeddings=[embedding], metadatas=[meta])

    def query(self, embedding: list[float], limit: int, where: dict | None = None) -> list[VectorResult]:
        chroma_where, post_filters = self._split_where(where)
        n = limit * 3 if post_filters else limit  # over-fetch for post-filtering
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(n, self._collection.count()) or 1,
            where=chroma_where or None,
        )
        # ... post-filter tags/prefix, return VectorResult list
```

#### QdrantBackend

Talks to a Qdrant server via `qdrant-client`. Tags are stored as a payload field with native array support. Filtering uses Qdrant's `Filter` and `FieldCondition` models, which map directly to the where grammar. No post-query filtering needed.

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchAny, Range

class QdrantBackend:
    def __init__(self, url: str, collection_name: str, dimension: int) -> None:
        self._client = QdrantClient(url=url)
        self._collection = collection_name
        self._ensure_collection(dimension)

    def query(self, embedding: list[float], limit: int, where: dict | None = None) -> list[VectorResult]:
        qfilter = self._build_filter(where)
        results = self._client.search(
            collection_name=self._collection,
            query_vector=embedding,
            limit=limit,
            query_filter=qfilter,
        )
        return [VectorResult(id=r.id, text=r.payload["text"],
                             metadata=r.payload, distance=r.score) for r in results]
```

#### PgvectorBackend

Uses psycopg (sync) or asyncpg with pgvector extension. Tags are stored as a `text[]` column. Filtering is pure SQL with `@>` for tag containment, `LIKE` for prefix match, and standard comparison operators for date ranges.

```python
class PgvectorBackend:
    def __init__(self, dsn: str, table_name: str, dimension: int) -> None:
        self._conn = psycopg.connect(dsn)
        self._table = table_name
        self._ensure_table(dimension)

    def query(self, embedding: list[float], limit: int, where: dict | None = None) -> list[VectorResult]:
        conditions, params = self._build_sql_where(where)
        sql = f"""
            SELECT id, content, metadata, embedding <=> %s AS distance
            FROM {self._table}
            {('WHERE ' + ' AND '.join(conditions)) if conditions else ''}
            ORDER BY distance
            LIMIT %s
        """
        # ... execute and return VectorResult list
```

Schema:

```sql
CREATE TABLE annal_memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    embedding   vector(384) NOT NULL,
    tags        TEXT[] DEFAULT '{}',
    source      TEXT DEFAULT '',
    chunk_type  TEXT DEFAULT 'agent-memory',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    file_mtime  DOUBLE PRECISION,
    metadata    JSONB DEFAULT '{}'
);

CREATE INDEX ON annal_memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON annal_memories USING gin (tags);
CREATE INDEX ON annal_memories (chunk_type);
CREATE INDEX ON annal_memories (source text_pattern_ops);
```

### Split backends by chunk type

File-indexed content and agent memories have fundamentally different access patterns. File indexing is high-volume and latency-sensitive — reconciliation inserts hundreds of chunks in a batch, and the source files are already local. Agent memories are low-volume but high-value, worth persisting somewhere durable and accessible across machines.

The storage layer supports this by allowing each chunk type to use a different backend. `MemoryStore` holds two backend references and routes operations based on the `chunk_type` field:

```python
class MemoryStore:
    def __init__(self, memory_backend: VectorBackend,
                 index_backend: VectorBackend, embedder: Embedder) -> None:
        self._memory_backend = memory_backend
        self._index_backend = index_backend
        self._embedder = embedder

    def _backend_for(self, chunk_type: str) -> VectorBackend:
        if chunk_type == "file-indexed":
            return self._index_backend
        return self._memory_backend

    def store(self, content: str, tags: list[str], source: str = "",
              chunk_type: str = "agent-memory", ...) -> str:
        backend = self._backend_for(chunk_type)
        embedding = self._embedder.embed(content)
        backend.insert(mem_id, content, embedding, metadata)
        ...

    def search(self, query: str, limit: int = 5, ...) -> list[dict]:
        # Search both backends, merge by distance
        embedding = self._embedder.embed(query)
        mem_results = self._memory_backend.query(embedding, limit=limit, where=where)
        idx_results = self._index_backend.query(embedding, limit=limit, where=where)
        merged = sorted(mem_results + idx_results, key=lambda r: r.distance or 1.0)
        return [self._format_result(r) for r in merged[:limit]]
```

When both backends point to the same instance (the common case for local-only setups), this is transparent — two references to the same object. The split only matters when they differ.

A practical deployment: local Qdrant for file indexing (fast bulk inserts, no network round-trip), Qdrant Cloud free tier for agent memories (durable, accessible from any machine, low volume so the free tier is plenty).

`browse` and `stats` already filter by chunk type, so routing those to the correct backend is straightforward. Cross-backend operations like `search` (which should return results from both memories and indexed files) merge results by distance score.

### Configuration

```yaml
storage:
  # Simple: single backend for everything
  backend: qdrant-local

  # Split: different backends per chunk type
  memory_backend: qdrant-cloud
  index_backend: qdrant-local

  backends:
    qdrant-local:
      type: qdrant
      url: http://localhost:6333

    qdrant-cloud:
      type: qdrant
      url: https://xyz.us-east4-0.gcp.cloud.qdrant.io
      api_key: ${QDRANT_API_KEY}

    chromadb:
      type: chromadb
      path: ~/.annal/data

    pgvector:
      type: pgvector
      dsn: postgresql://localhost/annal

embedder:
  model: all-MiniLM-L6-v2    # ONNX model name
```

When only `backend` is set, both `memory_backend` and `index_backend` default to it. When `memory_backend` and `index_backend` are set explicitly, they can reference different named backends. This keeps the simple case simple (one line) while enabling the split when needed.

Backend selection happens at startup. The `StorePool` resolves the backend names, instantiates the appropriate implementations, and passes them to `MemoryStore`. Each project gets its own collection/table (namespaced as `annal_{project}`), same as today.

### Migration

Moving data between backends is a scan-and-reinsert operation. Since `MemoryStore` owns the embedding step, migration reads from the old backend via `scan`, re-embeds each document (or preserves stored vectors if available), and inserts into the new backend.

A `annal migrate --from chromadb --to qdrant-local` CLI command would handle this. For large stores, it should batch inserts and show progress. The `--type` flag can restrict migration to a specific chunk type, which is useful when splitting: `annal migrate --from chromadb --to qdrant-cloud --type agent-memory` moves only memories to cloud while leaving file-indexed content to be migrated separately (or re-indexed from source files, which is simpler for file content since the files are still local).

### What doesn't change

The MCP tool interface, dashboard routes, file watcher, and indexer are unaffected. They all talk to `MemoryStore`, which presents the same public API regardless of which backend is underneath. The `StorePool` still manages per-project `MemoryStore` instances. The only difference is what it passes to the constructor.

## Trade-offs

Tags as native lists vs JSON strings is the biggest internal change. The current codebase stores tags as `json.dumps(tags)` everywhere because of ChromaDB's limitation. With the abstraction, `MemoryStore` works with native `list[str]` and the ChromaDB backend handles serialization internally. This means the ChromaDB backend is slightly more complex, but every other backend (and all business logic) gets simpler.

The where grammar is deliberately minimal. A richer query language would let the dashboard do more server-side filtering, but it would also make new backend implementations harder to write and test. The current grammar covers everything Annal does today.

Async vs sync is left to each backend's discretion. The current codebase is synchronous (ChromaDB is sync-only). Qdrant's client supports both. Pgvector with asyncpg would be naturally async. The protocol doesn't mandate either — `MemoryStore` calls backends synchronously today, and adding async support would be a separate concern.

## Recommended first step

Add the `VectorBackend` and `Embedder` protocols, refactor the current ChromaDB code into `ChromaBackend`, and update `MemoryStore` to use the new interfaces. This is a pure refactor with no new dependencies and no behaviour change. It validates the abstraction against the existing test suite before adding new backends.

Qdrant would be the natural second backend to implement — it's conceptually closest to what exists (a vector store with metadata), requires minimal schema design, and solves both the concurrency and tag filtering limitations.
