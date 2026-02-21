# Memory Relationships

## Problem

Memories exist as isolated documents with no way to express that one supersedes another, that two memories contradict each other, or that a memory carries more weight than others. When an architectural decision is revised, the old decision still surfaces in search results with no indication that it has been replaced. Agents encountering contradictory memories cannot distinguish which is current without reading both and reasoning about timestamps. This undermines trust in the memory store as a source of truth.

## Requirements

Supersession: a `supersede(project, old_id, new_id)` tool that marks an old memory as replaced by a new one. Implemented as a `superseded_by` metadata field on the old memory. Search results flag superseded memories so agents can follow the chain to the latest version. Superseded memories are excluded from search results by default, with an `include_superseded` flag to surface them when needed.

Structured metadata: extend memory metadata beyond flat tags to support key-value pairs. An optional `metadata` dict parameter on `store_memory` and `update_memory` for structured fields like `priority`, `domain`, `scope`. Stored as individual ChromaDB metadata fields (not JSON-encoded) so they can participate in ChromaDB's native `where` filters.

Memory priority/weight: a `priority` field (`normal`, `important`, `critical`) that influences search result ranking. Critical memories receive a score boost, ensuring high-value architectural decisions outrank casual observations. Can be set at store time or promoted after the fact via `update_memory`.

Contradiction detection: at store time, search for semantically similar existing memories with conflicting tags or content. If a new `decision` memory closely matches an existing `decision` memory (above a configurable threshold), flag the potential contradiction in the store response rather than silently adding both. The agent can then choose to supersede the old memory or store both.

## Prior art

Backlog items: "Memory supersession" (lightweight `supersede(old_id, new_id)` with `superseded_by` metadata), "Memory pinning / weight" (priority field with score boost, `pin_memory` tool). The backlog notes that supersession is deliberately simpler than full knowledge-graph linking.

Agent feedback: Gemini item 4 (structured relationships), Claude's contradiction detection request.

## Priority

P3 — Important for long-term memory quality but more complex than search and bulk operation improvements. Supersession is the most immediately practical piece and could ship independently of the rest.
