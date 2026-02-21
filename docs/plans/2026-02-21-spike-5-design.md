# Spike 5 Design — Operational Hardening + Search Quality

## Goal

Get Annal into a state where the codebase is trustworthy (no known bugs) and search is noticeably good (heading context, temporal filtering, structured output). This is the substance spike — spike 6 will handle polish and packaging for public sharing.

## Scope

Two phases, shipped sequentially with a clean commit boundary between them.

### Phase 1: Operational Hardening

Fix every known bug from the spike 4 code review and the multi-agent feedback round. These are trust issues — nothing new should ship on top of broken foundations.

#### 1. Unify StorePool (P0)

`create_server()` currently creates its own `StorePool` internally (server.py:142). `main()` then creates a second pool for the dashboard (server.py:533). They operate on independent ChromaDB connections, causing stale dashboard reads and divergent watcher/indexing state.

Fix: change `create_server()` to accept an optional `pool: StorePool | None` parameter. When provided, use it; when not, create one internally (preserves backward compat for tests). `main()` creates a single pool and passes it to both `create_server()` and `_start_dashboard()`. Also eliminates the double config load at server.py:529-530.

```python
def create_server(
    config_path: str = DEFAULT_CONFIG_PATH,
    pool: StorePool | None = None,
) -> tuple[FastMCP, StorePool]:
    config = AnnalConfig.load(config_path)
    if pool is None:
        pool = StorePool(config)
    ...
    return mcp, pool
```

Tests that call `create_server()` without a pool continue to work unchanged.

#### 2. `_startup_reconcile` error handling

The startup reconciliation loop (server.py:146-153) has no per-project error handling. If one project throws, the remaining projects are never reconciled and never get watchers started.

Fix: wrap the per-project loop body in try/except. Log the error, emit an `index_failed` event (see item 4), and continue to the next project.

#### 3. Activity-indicator element (P1)

`memories.html:153-160` references `getElementById('activity-indicator')` but no such element exists in the DOM. Every SSE index event throws a TypeError.

Fix: add `<span id="activity-indicator" class="activity-badge"></span>` to the page header in `memories.html`, next to the memory count. Style it to show/hide with the `.active` class the JS already toggles.

#### 4. `index_failed` event (P1)

The design doc specifies `index_failed` but it's never emitted. If reconciliation crashes, the dashboard badge stays stuck at "indexing..." indefinitely.

Fix: in `reconcile_project_async`'s `_run()` method (pool.py:68), add an except clause that emits `Event(type="index_failed", project=project, detail=str(e))`. Update the dashboard JS to handle `sse:index_failed` — clear the "indexing..." badge and show an error state.

Also add `index_failed` to the Event docstring in events.py.

#### 5. Narrow SSE exception catch (P2)

routes.py:232 catches bare `Exception` when it should catch `queue.Empty` specifically. Other exceptions (bugs in event serialization, etc.) are silently swallowed as keepalives.

Fix: change `except Exception:` to `except queue.Empty:`.

#### 6. `_index_locks` thread safety (P2)

`defaultdict(threading.Lock)` at pool.py:26 is safe under CPython's GIL but fragile under free-threaded Python (PEP 703).

Fix: replace with an explicit method:
```python
def _get_index_lock(self, project: str) -> threading.Lock:
    with self._lock:
        if project not in self._index_locks:
            self._index_locks[project] = threading.Lock()
        return self._index_locks[project]
```

Update all callers (`reconcile_project_async`, `is_indexing`) to use `_get_index_lock()`.

#### 7. Dead code and dependency cleanup (P3)

Remove `get_file_mtime` from store.py (superseded by `get_all_file_mtimes()`, no callers).

Add `httpx` to `[project.optional-dependencies].dev` in pyproject.toml (used by dashboard SSE tests, currently only available transitively).

#### 8. README accuracy (P3)

Change "95 tests" to reflect actual count or remove the hard number. Currently 75 tests; this will grow during the spike.

### Phase 2: Search & Retrieval

Three features that make the tool feel smart and work for all agents.

#### 1. Heading context in embeddings

When `index_file()` stores a chunk, the heading path (`README.md > Architecture > Frontend`) goes into the `source` metadata field but is invisible to the embedding model. The embedded document is just the raw section content. This means a search for "what framework does the frontend use" has to match on body text alone — the heading context that would disambiguate it is lost.

Fix: in `index_file()` (indexer.py), prepend the heading path to the chunk content before storing:

```python
# Before embedding, add heading context
heading_context = chunk["heading"]
embedded_content = f"{heading_context}: {chunk['content']}"
store.store(content=embedded_content, ...)
```

The `source` field keeps its existing `file:path|heading` format for identification. The change only affects what gets embedded.

Existing file-indexed chunks will have stale embeddings. Recommend documenting a one-time `index_files` call per project in the changelog. Reconciliation will also catch changed files naturally.

#### 2. Temporal filtering

Add optional `after` and `before` parameters to `search_memories` (ISO 8601 date strings, e.g. `"2026-02-01"` or `"2026-02-15T00:00:00"`).

`created_at` is stored as an ISO 8601 string. Lexicographic comparison on ISO 8601 is well-defined (they sort correctly as strings), so we can use ChromaDB's `$gte`/`$lte` on the string field directly — no migration to epoch floats needed.

In `store.search()`, build a ChromaDB `where` filter:
```python
where_conditions = {}
if after:
    where_conditions["created_at"] = {"$gte": after}
if before:
    if "created_at" in where_conditions:
        # Both after and before — use $and
        where_conditions = {"$and": [
            {"created_at": {"$gte": after}},
            {"created_at": {"$lte": before}},
        ]}
    else:
        where_conditions["created_at"] = {"$lte": before}
```

Pass this to `self._collection.query(where=where_conditions)`. The existing post-query tag filtering still applies on top.

MCP tool signature becomes:
```python
def search_memories(
    project: str,
    query: str,
    tags: list[str] | str | None = None,
    limit: int = 5,
    mode: str = "full",
    min_score: float = 0.0,
    after: str | None = None,
    before: str | None = None,
) -> str:
```

#### 3. Structured JSON output

Add an optional `output` parameter to `search_memories` and `expand_memories` accepting `"text"` (default) or `"json"`.

When `output="json"`, return a JSON-encoded string instead of formatted text:

```json
{
  "results": [
    {
      "id": "abc-123",
      "content": "full content (full mode)",
      "content_preview": "first 200 chars... (probe mode)",
      "tags": ["decision", "auth"],
      "score": 0.82,
      "source": "agent:code-reviewer",
      "created_at": "2026-02-20T14:30:00+00:00",
      "updated_at": "2026-02-20T16:45:00+00:00"
    }
  ],
  "meta": {
    "query": "authentication approach",
    "mode": "full",
    "project": "myapp",
    "total": 12,
    "returned": 5
  }
}
```

In probe + json mode, results include `content_preview` (first 200 chars) but omit full `content`. In full + json mode, both fields are present.

`expand_memories` with `output="json"` returns the same `results` structure without `score` or `meta.query`.

Text mode remains the default. No existing behavior changes.

## Testing

Phase 1 tests:
- Verify single StorePool shared between server and dashboard
- `_startup_reconcile` continues after one project fails
- `index_failed` event emitted on reconciliation error
- SSE keepalive only on `queue.Empty`, not on other exceptions

Phase 2 tests:
- Heading context appears in stored content for file-indexed chunks
- `after`/`before` filters narrow search results by date
- Combined `after` + `before` produces a date range
- `output="json"` returns valid JSON with expected structure
- `output="json"` + `mode="probe"` includes `content_preview`, omits `content`
- `output="text"` (default) returns same format as current behavior

## Version

Ship as 0.3.0 — this is a feature release with new search parameters and structured output.

## Non-goals for this spike

- Cross-project search (spike 6 or later)
- Bulk operations (spike 6 or later)
- Dashboard pagination improvements
- Hybrid search (BM25) — larger effort, separate spike
- Tag filtering at the database layer — requires migration
- CLI subcommands, import/export
