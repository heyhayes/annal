# Spike 4: Async Indexing, Operational Visibility, Thread Safety

## Context

Field testing Annal against the kubernetes/kubernetes repo (~80k files) revealed that `init_project` and `index_files` block the entire MCP server for the duration of reconciliation. With three agents (Claude, Gemini, Codex) hitting the server simultaneously, one agent's `init_project` call starved the other two of any tool access for 15+ minutes. The journal went silent, the dashboard showed nothing, and agents received empty responses with no explanation of what was happening.

This spike fixes the blocking problem and addresses the related visibility, thread safety, and code quality issues that surfaced during spike 3 reviews.

## Goals

1. Make `init_project` and `index_files` non-blocking — return immediately, reconcile in the background.
2. Give both agents and humans visibility into indexing progress.
3. Fix confirmed thread safety issues in StorePool and EventBus.
4. Clean up spike 3 code review findings.
5. Fix markdown heading depth so `####`–`######` get indexed.

## Design

### Async Indexing

`init_project` saves the config, spawns a daemon thread running `_reconcile_and_watch`, and returns immediately with `"Project 'kubernetes' initialized. Indexing in progress — use index_status to check progress."` The same pattern applies to `index_files`.

The reconcile thread acquires a per-project `threading.Lock` before starting, runs reconciliation with progress events pushed through the EventBus every N files, then starts the file watcher and releases the lock. If a second request arrives for the same project while indexing is in progress, it either blocks on the lock (serialized) or returns early with "indexing already in progress" — whichever feels better in practice. Starting with block-and-wait since it's simpler and still correct.

Per-project locks live on the StorePool as a `defaultdict(threading.Lock)`, created alongside stores.

### index_status Tool

New MCP tool returning per-project diagnostics:

- Whether indexing is currently running (attempted non-blocking lock acquire)
- Total chunks in the collection (via `store.count()`)
- Breakdown by type (file-indexed vs agent-memory)
- Last reconcile timestamp and file count (stored on the StorePool after each reconcile completes)

### Progress Events

The reconcile loop already iterates files one by one. Add an `index_progress` event pushed every 50 files with the current count. Event types become: `index_started`, `index_progress`, `index_complete`, `index_failed`.

### Dashboard Visibility

The dashboard index page already shows per-project stats cards. Add:

- An "Indexing..." badge on projects currently reconciling, driven by SSE (`index_started` shows it, `index_complete`/`index_failed` hides it).
- A progress counter updated by `index_progress` events showing "N files processed" ticking up in real time.

### Thread Safety

StorePool: wrap `_stores` dict access in `get_store` with a `threading.Lock`. The per-project locks for indexing are separate from this — the store-level lock protects dict mutation, the project-level locks protect reconciliation.

EventBus: wrap `_queues` list mutation in `subscribe`/`unsubscribe`/`push` with a `threading.Lock`. CPython's GIL made this work in practice, but the lock makes it correct by contract.

### Spike 3 Code Review Fixes

- `updated_at` inconsistency: add `updated_at` to `search()` and `browse()` return values, not just `get_by_ids()`.
- SSE slow client handling: replace `q.get()` with `q.get(timeout=30)` in a loop so threads can check for cancellation and don't block indefinitely.
- HTMX SSE trigger redundancy: simplify `memories.html` to use only `hx-trigger` with `sse-connect`, remove redundant `sse-swap`.
- `_annal_executable()` launchd fallback: return a list `[sys.executable, "-m", "annal.server"]` instead of a single string, so launchd plist gets separate `<string>` elements per argument.
- Test gaps: add tests for `update_memory` with nonexistent ID, no-op `update_memory` guard, install idempotency (calling install twice).

### Heading Depth

Change the indexer's heading regex from `#{1,3}` to `#{1,6}`. One-line change that matters for kubernetes KEPs, ADRs, and detailed docs that use `####` through `######`.

## Non-Goals

- Task queue / job system — overkill for current usage. Background thread + lock is sufficient.
- Async/await refactor of MCP tools — fights FastMCP's sync handler model.
- Server-side pagination for large browse results — separate concern, not triggered by this test.

## Verification

- Run against kubernetes repo: `init_project` returns immediately, `index_status` shows progress, dashboard shows indexing badge.
- Three concurrent agents can all use tools while indexing runs.
- `pytest -v` passes with all new and existing tests.
- Journal shows per-file progress during reconciliation instead of silence.
