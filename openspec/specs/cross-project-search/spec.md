# Cross-Project Search

## Problem

Agents working across multiple codebases cannot leverage knowledge learned in one project when working in another. A business analyst who discovered domain patterns in project X has no way to surface that knowledge when starting project Y. Each project's ChromaDB collection is an isolated silo, and `search_memories` only queries one collection at a time. Two of three field-testing agents requested this capability.

## Requirements

Multi-project query: an optional `projects` parameter on `search_memories` accepting a list of project names, or `"*"` for all registered projects. When provided, the query fans out across the specified project collections in parallel and merges results by similarity score.

Per-project attribution: each result in the merged set includes its source project name, so agents can distinguish where knowledge originated.

Optional per-project weights: an advanced `project_weights` parameter (dict of project name to float multiplier) that adjusts similarity scores before merging. Allows agents to prefer knowledge from the current project while still surfacing cross-project matches.

Result limit applies globally: the `limit` parameter caps the total merged result set, not per-project. The merge selects the top-N across all collections.

## Prior art

Backlog item: "Cross-project search" in the Architecture section describes the fan-out approach — query all (or specified) project collections in parallel, merge by similarity score. Notes that this is simpler than agent-scoped collections because agents don't need to decide at storage time whether knowledge is portable.

Agent feedback: Codex item 10, Claude's cross-project request.

## Priority

P2 — Two agents want this. More complex than single-collection features but well-scoped. The `StorePool` already manages multiple project stores, providing a natural fan-out point.
