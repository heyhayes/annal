# Spike 6 Design — Bug Sweep + Fuzzy Tags + Cross-Project Search

Big push: fold in uncommitted install enhancements, fix all outstanding bugs from spike 4 and 5 code reviews, fill test coverage gaps, then ship two features — fuzzy tag matching and cross-project search.

## Phase 1: Fold in uncommitted work

Commit the existing `cli.py` and `test_cli.py` changes as-is. These add CLAUDE.md agent instructions snippet, post-commit hook script creation, and uninstall cleanup to `annal install`/`annal uninstall`. Already written and tested.

## Phase 2: Bug fixes

### `before` date filter loses last day (P1)

In `store.py` `search()`, normalize date-only inputs before comparison. If `after` doesn't contain a `T`, append `T00:00:00`. If `before` doesn't contain a `T`, append `T23:59:59`. This way `before="2026-02-28"` includes the entire day.

Files: `src/annal/store.py`

### Dual `AnnalConfig` (P2)

`main()` creates one config, `create_server()` loads another from the same path. `init_project` mutates the closure config but the dashboard's reference never sees new projects.

Fix: `create_server()` accepts an optional `config` parameter (the actual object, not just the path). `main()` passes its config directly so both share the same instance.

Files: `src/annal/server.py`

### Startup reconcile skips index lock (P2)

`_startup_reconcile` calls `pool.reconcile_project()` (synchronous) which doesn't acquire the per-project index lock. If `init_project` or `index_files` fires during startup, two reconciliations race.

Fix: have `_startup_reconcile` use `reconcile_project_async` instead, which already acquires the lock. Wait for completion via events or just let it run — the async path already handles errors and emits events.

Files: `src/annal/server.py`

### `_index_started`/`_last_reconcile` reads without locks (P2)

Written by reconcile thread, read by `index_status`. Atomic under GIL but inconsistent with the spike 4 thread-safety-by-contract goal.

Fix: protect reads/writes of `_index_started` and `_last_reconcile` with `self._lock`.

Files: `src/annal/pool.py`

### `config.save()` under `_lock` (P3)

In `get_store()`, YAML serialization + file I/O happens while holding the pool lock.

Fix: move `config.save()` outside the `with self._lock` block. Collect what needs saving inside the lock, do the I/O after releasing.

Files: `src/annal/pool.py`

### `browse()` loads entire collection (P2)

Replace "fetch everything, slice in Python" with ChromaDB's `get(offset=, limit=)` for the unfiltered path. For filtered queries (tags, source_prefix), the scan approach stays — ChromaDB can't filter on JSON-encoded tag lists natively. But the common unfiltered dashboard case gets fast.

Files: `src/annal/store.py`

## Phase 3: Test coverage gaps

All additions to existing test files.

- Invalid date format tests (P2) — validate ISO 8601 format, test that garbage like `"yesterday"` is handled gracefully (reject or return empty, not silently wrong results).
- Empty-results JSON path (P2) — `search_memories(output="json")` with no matches returns correct `{"results": [], "meta": {...}}` structure.
- Tags + temporal filters combined (P3) — store memories with different tags and dates, search with both filters, verify composition.
- Over-fetch at scale (P3) — store 20+ memories, search with tag filter to exercise `limit * 3` over-fetch.
- Heading context test tightening (P3) — check full `doc.md > Heading` format, not just `startswith("doc.md")`.
- Concurrent `_get_index_lock` test (P3) — two threads call `_get_index_lock` for the same project, verify same lock object returned.

## Phase 4: Fuzzy tag matching

### Problem

Tag filtering requires exact string matches. `tags=["auth"]` won't find memories tagged `authentication`. Agents never converge on one exact tag string.

### Approach

Use embedding similarity on tag strings at query time. When a search has a `tags` filter, embed the filter tags and compare against all known tags in the project (from `list_topics()`). Any known tag above a similarity threshold gets included in the expanded match set.

### Design

Where: in `store.py`'s `search()` method, before the post-query tag filter loop. Build the expanded tag set once per query, then the existing `any(t in mem_tags for t in expanded_tags)` logic stays the same.

Embeddings: use `chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2()` instantiated once per `MemoryStore` to keep it clean (avoid private API). Same model ChromaDB uses internally for document embeddings.

Threshold: 0.75 cosine similarity as the default. Tight enough that `auth` won't match `caching`, loose enough to catch `auth` → `authentication`. Internal for now — no user-facing parameter until we have evidence it needs tuning.

Caching: cache known tags and their embeddings per-store. Invalidate on store/update/delete (clear the cache, rebuild lazily on next filtered search). For a store with 50 unique tags, embedding them all is ~1ms.

Default behaviour: fuzzy matching is the default for all tag-filtered searches. No opt-in flag needed. Could add `tag_match="exact"` later if someone needs it.

### Files

- `src/annal/store.py` — `_expand_tags()` method, tag embedding cache, modified `search()` and `browse()` tag filter
- `tests/test_store.py` — fuzzy matching tests

## Phase 5: Cross-project search

### Problem

Knowledge is siloed per project. An agent working in project Y can't access patterns learned in project X without knowing to switch projects.

### Approach

Fan-out query across multiple project collections, merge results by similarity score.

### Design

API: add `projects: list[str] | str | None = None` to `search_memories`. When `None` (default), single-project search (unchanged). When `"*"`, search all configured projects. When a list, search those specific projects. The `project` parameter stays required as the primary/default.

Fan-out: in `server.py` at the tool level. Iterate over requested projects via `pool.get_store()`, query each with the same params, collect results. Each `MemoryStore` stays single-project.

Merging: combine all results into one list, sort by score descending, take top `limit`. Each result gets a `project` field so the agent knows the source.

Tag/temporal filtering: applied per-project before merging. Fuzzy tag matching works per-project since each has its own tag vocabulary.

Output: results include `project` field. Probe mode: `[0.87] (memex) (decision, auth) "..."`. JSON mode: `"project": "memex"` on each result. Meta block shows `"projects_searched": ["memex", "classmanager"]`.

SERVER_INSTRUCTIONS: add a section documenting cross-project search.

### Files

- `src/annal/server.py` — modified `search_memories` tool, output formatting
- `tests/test_server.py` or `tests/test_store.py` — cross-project search tests
