# Retrieval Quality

## Problem

Semantic vector search is the only retrieval mechanism, which creates blind spots for exact keyword matches (technical identifiers, table names, specific error messages) and limits result quality as the store grows. Several architectural choices that were pragmatic at small scale — JSON-encoded tags with post-query filtering, heading paths stored in metadata but not in embedded content, minimal auto-tagging — degrade retrieval precision and recall as memory volume increases. Three reviewers independently identified hybrid search as a gap, and Claude's review identified specific embedding and filtering improvements that would compound over time.

## Requirements

Hybrid search: combine vector similarity with full-text search (BM25 or similar) for better recall. Vector search misses exact keyword matches; full-text misses semantic similarity. Use reciprocal rank fusion or a similar technique to merge both ranking signals. This is the single highest-impact retrieval improvement.

Heading context in embeddings: when chunking markdown, prepend the heading path to the chunk content before embedding. Currently a section like "## Architecture > ### Frontend" with content "Uses React and Next.js" embeds only the content — the heading path is in the `source` metadata but invisible to the embedding model. Prepending gives "Architecture > Frontend: Uses React and Next.js", making semantic search for "what framework does the architecture use" much more likely to match.

Tag filtering at the database layer: tags are currently stored as a JSON string with post-query filtering and a 3x over-fetch heuristic. As the store grows, this misses relevant results when many chunks share popular tags. Consider storing tags as individual metadata keys (`tag_billing: true`, `tag_auth: true`) so ChromaDB's native `where` filter can handle tag selection without over-fetching.

Richer auto-tagging: `_derive_tags` only produces three auto-tags (`indexed`, `agent-config`, `docs`). Files like `CONTRIBUTING.md`, `CHANGELOG.md`, `architecture.md`, `*.spec.ts` could get more useful tags. Also derive tags from directory names (files under `docs/` get `docs`, files under `tests/` get `tests`).

Shared ChromaDB client: each `MemoryStore` creates its own `PersistentClient`, which loads its own connection pool and ONNX model. Multiple clients pointing at the same `data_dir` is officially supported but wasteful. Share a single client across all stores, calling `get_or_create_collection()` per project on the shared instance.

Dedup threshold tuning: the 0.95 cosine similarity threshold for near-duplicate detection was chosen without calibration data. May be too aggressive (rejecting distinct memories) or too loose (allowing near-duplicates). Needs real-world data to evaluate — track rejected duplicates and false positives.

Stale memory detection: surface memories that haven't matched any search in a long time. Add a `last_accessed_at` field updated on search hits, and a `stale_memories(project, older_than_days)` tool for agent-driven curation.

Memory expiry / cleanup: as the store grows, retrieval quality degrades from noise. Provide mechanisms for time-based expiry, manual cleanup tools, or automatic decay of low-priority memories.

## Prior art

Backlog items: "Hybrid search", "Tune the dedup threshold", "Evaluate retrieval quality", "Stale memory detection", "Memory expiry / cleanup".

Agent feedback: Claude's review items 10-13 (shared client, tag filtering at scale, _derive_tags, heading context in embeddings). Claude item 14 (hybrid search). Claude item 15 (staleness tracking). All three reviewers identified hybrid search as a gap.

## Priority

P2 — Hybrid search and heading context in embeddings are the highest-leverage items. Tag filtering at the database layer and shared ChromaDB client are performance/scaling improvements that become important as memory volume grows. Stale memory detection and dedup tuning are calibration tasks that require real-world usage data.
