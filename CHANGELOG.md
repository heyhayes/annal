# Changelog

All notable changes to Annal are documented here. This project uses [semantic versioning](https://semver.org/).

## 0.7.1 — 2026-02-23

Added `__main__.py` so `python -m annal` works as a fallback when the `annal` script isn't on PATH (common on Windows with Microsoft Store Python).

## 0.7.0 — 2026-02-23

Search Improvements & Stale Memory Management.

`store_batch` tool for efficient multi-memory storage. Hit tracking on agent memories — `search_memories`, `expand_memories`, and `get_by_ids` record `hit_count` and `last_accessed_at`. Overfetch cap on tag-filtered searches to bound post-filter work. `prune_stale` tool for reviewing and deleting memories that haven't been accessed in a configurable number of days (dry-run by default). `index_status` now reports stale and never-accessed memory counts. Dashboard stale column on project overview, "Show stale only" filter on the memories page, and stale/never-accessed badges on memory rows. GitHub Actions CI and PyPI publish workflows.

## 0.6.3 — 2026-02-22

Memory Supersession.

`supersedes` parameter on `store_memory` marks old memories as replaced. Superseded memories hidden from search/browse by default, visible with `include_superseded=True`. `$not_exists` post-filter operator for both backends. Similarity hints (0.80–0.95) suggest supersession to agents. Dashboard "Show superseded" toggle. Backend conformance test suite extracted into parametrized shared tests.

## 0.6.2 — 2026-02-22

Hardening + Export/Import.

Export/import CLI (`annal export`, `annal import`) for JSONL-based backup and restore. Bug fixes for dedup, tag normalization, and startup reconciliation. Backend conformance improvements.

## 0.6.1 — 2026-02-22

Retag + Dashboard UX.

`retag_memory` tool for incremental tag editing. Dashboard improvements: project overview table, clickable tag pills, cross-project search. Search default mode changed from `full` to `summary`.

## 0.6.0 — 2026-02-21

Vector Backend Abstraction + Qdrant.

VectorBackend protocol with pluggable backends. ChromaDB extracted behind protocol. QdrantBackend with native tag filtering, hybrid BM25+vector search via RRF, deterministic UUID mapping. Config-driven backend selection. Migration CLI (`annal migrate`).

## 0.5.0 — 2026-02-21

Stress-Test Bug Sweep.

Seven fixes from stress testing: min_score no longer masks fuzzy tag matches, cross-project search always includes primary project, empty parent heading chunks skipped, invalid dates raise errors instead of silently returning empty, dedup checks all agent-memory candidates, daemon threads joined on shutdown, fuzzy tag threshold lowered to 0.72.

## 0.4.0 — 2026-02-20

Bug Sweep + Features.

Six bug fixes (date filter, dual config, startup lock, pool lock safety, browse pagination, config I/O under lock). Fuzzy tag matching via ONNX embeddings. Cross-project search with fan-out and score-based merge.

## 0.3.0 — 2026-02-20

Search & Retrieval.

Temporal filtering, structured JSON output, heading context in embeddings.

## 0.2.0 — 2026-02-19

Operational Readiness.

Async indexing, thread safety, index_status diagnostics, mtime cache performance, optional file watching.

## 0.1.0 — 2026-02-19

Foundation.

Core memory store, semantic search, file indexing, MCP server, web dashboard, one-shot install.
