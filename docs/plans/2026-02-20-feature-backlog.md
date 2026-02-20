# Annal Feature Backlog

Compiled from the initial spike. Items marked with [field] are things to validate during real-world use before committing to implementation.

## Parked from this session

- `annal --install-service` CLI command — detect OS and generate/install the appropriate service file (systemd, launchd, or Windows scheduled task) automatically instead of requiring manual setup from contrib/

## Bugs

- Dedup check only examines limit=1 — `store_memory` searches for near-duplicates with `limit=1`, but the nearest result might be a file-indexed chunk (which gets skipped by the `chunk_type == "agent-memory"` check). An actual near-duplicate agent memory at position 2 or 3 would never be seen. Fix: increase the dedup search limit to 3-5 and check all results, or add a `where` filter for `chunk_type`.
- Empty collection search — `store.search` on an empty collection falls through to querying for 1 result via the `or 1` fallback. ChromaDB may raise or return unexpected results. Should short-circuit with `if self._collection.count() == 0: return []`.
- Lower requires-python to >=3.11 — the codebase uses `from __future__ import annotations` everywhere and no 3.12-specific features. Currently excludes 3.11 users unnecessarily.

## Retrieval quality

- Hybrid search — combine vector similarity with full-text search (BM25 or similar) for better recall. Vector search misses exact keyword matches; full-text misses semantic similarity. Fusing both (reciprocal rank fusion or similar) would improve retrieval without adding infrastructure.
- [field] Tune the dedup threshold — currently 0.95 cosine similarity. Might be too aggressive (rejecting distinct memories) or too loose (allowing near-duplicates). Needs real-world data to calibrate.
- [field] Evaluate retrieval quality — are agents finding what they need? Track cases where relevant memories aren't surfacing and identify patterns.

## LLM enrichment

- Summarize the "why" from business documents — point a lightweight model at requirements docs, specs, meeting notes and extract intent, constraints, trade-offs. Store enriched summaries alongside raw content so semantic search catches the reasoning, not just the text.
- [field] Figure out where the "why" comes from — code analysis alone won't give you intent. The richest source is agent-user conversations where decisions happen. Consider: should agents be better at recognizing "this is a moment worth recording" rather than enriching after the fact?

## Adoption and agent behaviour

- Passive vs active memory problem — observed in real use: an LLM defaulted to its built-in passive memory system (MEMORY.md, always loaded in the system prompt, zero-effort writes) over making active tool calls to Annal, despite Annal being configured and the instructions saying to use it. The passive system won because it requires no decisions about when to store, what to tag, or when to search. This is a fundamental UX friction for any tool-call-based memory system. Possible directions: make storage more automatic (agent hooks that trigger on certain events?), reduce the tagging burden (infer tags from content?), or find ways to make the value of semantic search over flat files more immediately obvious to the agent.
- [field] Agent compliance with memory instructions — do agents actually follow the SERVER_INSTRUCTIONS to search before starting work and store findings as they go? Track how often agents use Annal when it's available vs ignoring it. The instructions may need to be more prescriptive or the friction lower.
- Recall triggers in SERVER_INSTRUCTIONS — the current instructions have a "When to store" section but no "When to search" guidance. Observed in real use: an agent answered "what did you just do?" by reaching for git log instead of Annal, because recall-oriented questions weren't listed as search triggers. The instructions should explicitly list question patterns that should prompt a memory search: "what were we working on?", "what did we decide?", "where did we leave off?", "have we seen this before?", "what's the context on X?" — any question about prior work, decisions, or session history. This is separate from the session-start search; it's about recognizing mid-conversation moments where memory recall is the right first move.

## Developer experience

- Platform-native default paths — use `platformdirs` to place config and data in OS-appropriate locations (`~/.config/annal/` + `~/.local/share/annal/` on Linux, `~/Library/Application Support/annal/` on macOS, `%APPDATA%\annal\` on Windows) instead of hardcoding `~/.annal/`. Needs data migration from existing `~/.annal/` installs.
- `.gitignore` for `~/.annal/data` or equivalent — make sure ChromaDB storage doesn't accidentally get committed if someone puts a project inside a repo
- [field] Cross-platform path handling — test on macOS and Windows. File watcher paths, config paths, and `os.path` usage should work across all three OSes.
- Project name sanitization — collection names are `annal_{project}`, but project names aren't validated. Spaces, slashes, or special characters in project names will produce invalid collection names or ChromaDB errors. Add a slugify step (lowercase, `[a-z0-9_-]`, collapse others to `_`) and store the original display name separately if needed.
- Markdown chunking heading depth — indexer currently matches `#{1,3}` only. Should go to `#{1,6}` since `####` through `######` are common in ADRs, specs, and detailed docs.
- [field] mtime comparison on Windows/network mounts — reconciliation uses exact float equality for mtime checks. Some filesystems have coarse or drifty mtime precision. May need `round(mtime, 3)` or an epsilon comparison to avoid unnecessary re-indexing.
- [field] Cold start performance — first query loads the ONNX embedding model. Is the delay acceptable? Does it cause MCP timeouts?
- Watcher resilience — `index_file` can raise on permission errors, broken symlinks, or unexpected file types. The watcher's `on_modified`/`on_created` handlers don't wrap the call in try/except, so a single bad file crashes the watcher thread. Add error handling so the watcher logs and continues.
- [field] Large repo behavior — what happens with a repo that has thousands of markdown files? Does reconciliation block for too long? Is the mtime check fast enough at scale?

## New tools

- `update_memory` — revise an existing memory's content and/or tags without losing its ID or `created_at` timestamp. Tracks an `updated_at` alongside the original. Straightforward since ChromaDB supports upsert. Currently agents have to delete and re-store, which loses identity.
- `add_tags` / `retag_memory` — modify tags on an existing memory after storage. If an agent realizes a set of memories should have had a `billing` tag, there's currently no recourse. Just a metadata update on the ChromaDB document.
- `index_status` — return per-project diagnostics: how many files are being watched, how many chunks indexed, when reconciliation last ran, which files failed (if error tracking is added). Agents are currently flying blind about what's in the file-indexed portion of the store.
- Source-scoped search — add an optional `source_prefix` filter to `search_memories` so agents can search within a specific file's chunks or only within agent memories. Useful when the agent knows the knowledge came from a specific document.
- Probe/expand retrieval — add `mode="probe"` to `search_memories` that returns truncated content (title/heading + 2-line summary + tags + date + ID), plus an `expand_memories(ids=[...])` tool to fetch full content on demand. Prevents context flooding on large stores. Two independent reviewers flagged this as high-value.
- Time window filter — add optional `after` / `before` date parameters to `search_memories`. ChromaDB metadata supports `$gte`/`$lte` on `created_at`, so this is low-cost. Useful for scoping searches to recent decisions or filtering out stale context.
- CLI subcommands — extend the `annal` entry point beyond just running the server. Add `annal search "query" --project foo --tags decision`, `annal store --project foo --tags decision`, `annal topics --project foo`. Makes Annal usable from the terminal without the agent stack, good for debugging and manual curation.
- Import/export — export a project to JSONL (id, text, metadata), import from JSONL. Useful for testing, portability, backups, and open-source readiness. Simple format, no external dependencies.
- `init_project` patterns/excludes — the tool currently accepts `watch_paths` but not `watch_patterns` or `watch_exclude`, so users have to hand-edit the YAML config for those. Accept them as optional parameters so setup is a single tool call.

## Data management

- Migration tooling — when config paths or collection naming changes (like the memex → annal rename), provide a way to migrate existing data rather than starting fresh
- Memory pinning / weight — not all memories are equal. An architectural decision should outrank a casual session observation. A `priority` metadata field (`normal`, `important`, `critical`) that boosts search scores would let agents surface high-value memories first. Could be set on store or promoted after the fact with a `pin_memory` tool.
- Stale memory detection — surface memories that haven't matched any search in a long time or were stored many sessions ago. A `stale_memories(project, older_than_days)` tool would help agents curate the store. Needs a `last_accessed_at` field updated on search hits.
- Memory supersession — a lightweight `supersede(old_id, new_id)` that marks an old memory as replaced without deleting it. Simpler than full knowledge graph linking but solves the key problem: agents can follow the chain to find the latest version of a decision. Could be as simple as a `superseded_by` metadata field that search results flag.
- Memory expiry / cleanup — should old memories decay? Or should there be a manual cleanup tool? As the store grows, retrieval quality may degrade from noise.
- [field] Backup and restore — is ChromaDB's file-based storage easy to back up? Can you just tar ~/.annal/data?

## Architecture

- [field] Concurrent write safety — multiple agents storing memories simultaneously via the HTTP daemon. Does ChromaDB handle this gracefully or do we need locking?
- [field] Memory isolation between agents — the tag conventions (agent:role-name) provide soft isolation. Is that sufficient or do agents pollute each other's search results?
- Store pool thread safety — the StorePool dict isn't protected by a lock. If two requests hit get_store for a new project simultaneously, could we get a race condition?
- Reconcile creates throwaway FileWatcher — `pool.reconcile_project` instantiates a full FileWatcher just to call `.reconcile()`, then discards it. `start_watcher` then creates another one. The reconcile logic could be a standalone function or live on the pool directly.
- Cross-project search — allow agents to search across multiple project collections so experience from one codebase can inform work in another. A BA agent who learned domain patterns in project X should be able to draw on that knowledge in project Y. Fan-out approach: query all (or specified) project collections in parallel, merge results by similarity score. Simpler than agent-scoped collections because agents don't need to decide at storage time whether knowledge is "project-specific" or "portable." Could add an optional `projects` parameter to `search_memories` (list of project names, or `"*"` for all).

## Future considerations (not for next spike)

- pgvector migration path — if ChromaDB becomes a bottleneck at scale, the MemoryStore interface is clean enough to swap backends. Don't build this until it's actually needed.
- Knowledge graph / entity linking — connecting memories by entities (people, systems, decisions) rather than just vector proximity. Significant complexity, only worth it if retrieval quality plateaus.
- Memory dashboard — web UI for reviewing and managing what agents are learning. Browse memories by project/agent/tag, search, view similarity clusters, delete noise, and spot patterns in what's being stored. Primary value is human oversight of agent knowledge — seeing what they're actually retaining and correcting course when needed. Could be a lightweight local server (Flask/FastAPI + HTMX or similar) served alongside the MCP daemon.
