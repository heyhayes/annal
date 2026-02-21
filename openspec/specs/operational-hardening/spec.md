# Operational Hardening

## Problem

The spike 4 code review identified several bugs and code quality issues that affect reliability in production. These range from a P0 bug (duplicate StorePool creating stale dashboard reads) to P2 thread-safety concerns that are safe under CPython's GIL but fragile under free-threaded Python. Additionally, `init_project` is not fully idempotent, and some error handling is too broad. These are not features — they are correctness and robustness fixes that should ship before new functionality.

## Requirements

Duplicate StorePool fix (P0): `main()` creates its own StorePool for the dashboard, separate from the one inside `create_server()`. Both operate on independent ChromaDB connections, causing stale dashboard reads. Fix: expose the pool from `create_server` so the dashboard and MCP tools share a single pool.

Activity-indicator element (P1): `memories.html` calls `getElementById('activity-indicator')` but no such element exists in the DOM. Every index event throws a TypeError. Add the missing element or remove the dead JS reference.

`index_failed` event (P1): the design doc specifies an `index_failed` event but it is never emitted. If reconciliation crashes, the dashboard badge stays stuck at "indexing..." indefinitely. Emit `index_failed` with error details when reconciliation throws, and update the dashboard to handle it.

Broad exception catch (P2): the SSE endpoint catches `Exception` when it should catch `queue.Empty` specifically. Other exceptions are silently swallowed as keepalives. Narrow the catch clause.

`_index_locks` defaultdict race (P2): safe under CPython GIL but fragile under free-threaded Python (PEP 703). Protect with the existing `_lock` or use explicit lock creation.

`_index_started` / `_last_reconcile` reads without locks (P2): written by the reconcile thread, read by `index_status`. Atomic under GIL but inconsistent with the project's thread-safety-by-contract approach. Protect with appropriate synchronization.

`config.save()` under lock (P3): YAML serialization + file I/O while holding the pool lock. Move save outside the lock to avoid blocking other threads on slow filesystems.

Dead code removal (P3): `get_file_mtime` is superseded by `get_all_file_mtimes()` with no remaining callers. Remove it.

Missing dev dependency (P3): `httpx` is used by SSE dashboard tests but only available transitively. Add to dev dependencies explicitly.

`init_project` idempotency: calling `init_project` with different parameters on an existing project should update the config cleanly, not create duplicate entries or silently ignore changes. Verify and fix the merge behavior.

Reconcile creates throwaway FileWatcher (P3): `pool.reconcile_project` instantiates a full FileWatcher just to call `.reconcile()`, then discards it. `start_watcher` then creates another one. The reconcile logic could be a standalone function or live on the pool directly.

README test count staleness (P3): README says "95 tests" but the actual count drifts as tests are added/removed. Either make this dynamic, remove the number, or just say "comprehensive test coverage".

Python classifier mismatch (P3): `requires-python = ">=3.11"` but classifiers only list 3.12. Add `Programming Language :: Python :: 3.11` or bump the minimum to 3.12.

Missing type hints on dashboard factory (P3): `create_dashboard_app(pool, config)` in `dashboard/__init__.py` has no type hints on parameters.

SERVER_INSTRUCTIONS store nudge (P3): the decision verification section instructs agents to search for prior decisions, but doesn't instruct them to store decisions they make. Add a complementary nudge so the decision loop is bidirectional.

## Prior art

All items come from the spike 4 code review (`docs/plans/2026-02-20-feature-backlog.md`, "From spike 4 code review" section). The review is also documented in `docs/plans/REVIEW.md`.

Agent feedback: Codex items 6-7 (robustness, error handling). Claude's review confirmed all spike 4 review items and added the throwaway FileWatcher observation, README staleness, classifier mismatch, and type hint gaps. ChatGPT independently confirmed the duplicate StorePool as P0.

## Priority

P0 — These are bugs and code quality issues, not features. The duplicate StorePool and missing index_failed event should be fixed before shipping new capabilities that depend on correct store and event behavior.
