# Advanced Search

## Problem

Agents frequently need to scope searches by time range or file origin, but `search_memories` currently only supports semantic similarity with optional tag filtering. Three common scenarios are unsupported: retrieving recent decisions (temporal filtering), searching within a specific document's chunks (source/path filtering), and getting result counts without full content (count-only mode). All three field-testing agents independently requested temporal filtering, making it the most converged-upon gap in the current tool surface.

## Requirements

Temporal filtering: `after` and `before` date parameters on `search_memories`, implemented as ChromaDB `$gte`/`$lte` metadata filters on `created_at`. Accepts ISO 8601 date strings, converted to epoch floats internally.

Source/path filtering: `source_prefix` parameter on `search_memories` that restricts results to memories whose `source` metadata starts with the given prefix. Enables searching within a specific file's chunks (`source_prefix="file:/path/to/doc.md"`) or only agent memories (`source_prefix="agent:"`).

Sort options: results currently return in similarity-score order. Add an optional `sort` parameter supporting `score` (default) and `created_at` (chronological), useful for reviewing the evolution of decisions over time.

Count-only mode: `mode="count"` on `search_memories` that returns only the number of matching results without fetching content. Lightweight way for agents to check whether relevant memories exist before committing to a full search.

## Prior art

Backlog items: "Time window filter", "Source-scoped search" (New tools section). ChromaDB already supports `$gte`/`$lte` on numeric metadata fields, so temporal filtering is low-cost to implement. The existing post-query tag filtering pattern in `store.py` provides a model for adding source prefix filtering in the same pass.

Agent feedback: Codex items 1-4 (temporal queries, source filtering, sort, count). Claude's temporal querying request. All three agents cited the inability to scope searches by recency as a friction point.

## Priority

P1 — All three agents converge on temporal filtering. Source/path filtering and count-only mode are small additions with high practical value that compose naturally with the temporal work.
