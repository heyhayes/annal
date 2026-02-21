# Bulk Operations

## Problem

Agents managing memory hygiene have only `delete_memory` (single ID) and the dashboard's bulk-delete-by-filter. There is no programmatic way to batch-delete by tags, source, or ID list, nor to batch-update tags across multiple memories. When an agent realizes a set of memories should have had a `billing` tag, or wants to clear all file-indexed chunks for a specific path, the only recourse is repeated single-ID operations. Two of three agents requested bulk delete capabilities.

## Requirements

Batch delete by IDs: `delete_memories(project, ids)` — delete multiple memories in one call. Uses the existing `store.delete_many()` batching (groups of 5000) internally.

Delete by tags: `delete_by_tags(project, tags)` — delete all memories matching the given tags. Performs a metadata scan, collects matching IDs, then batch-deletes. Returns count of deleted items.

Delete by source: `delete_by_source(project, source_prefix)` — delete all memories whose `source` metadata starts with the given prefix. Primary use case: clearing all chunks from a specific file (`source_prefix="file:/path/to/doc.md"`) or all agent memories from a specific role (`source_prefix="agent:code-reviewer"`).

Tag management: `add_tags(project, ids, tags)` and `remove_tags(project, ids, tags)` — modify tags on existing memories without touching content. Implemented as ChromaDB metadata updates on the JSON-encoded tags field.

All bulk operations return a summary: `{deleted: N}` or `{updated: N}` with the count of affected memories.

## Prior art

Backlog items: "add_tags / retag_memory" in the New tools section. The store layer already has `delete_many()` with batching in groups of 5000 and `_iter_metadata()` for paginated metadata scans — both designed for bulk operations. The dashboard's bulk-delete-by-filter exercises similar logic at the HTTP layer.

Agent feedback: Codex item 8, Claude's delete_by_tags/delete_by_source request.

## Priority

P2 — Two agents want this, and the store layer already has the building blocks. Implementation is primarily wiring existing internals into new MCP tool endpoints.
