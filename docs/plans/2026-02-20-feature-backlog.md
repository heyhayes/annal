# Annal Feature Backlog

Compiled from the initial spike. Items marked with [field] are things to validate during real-world use before committing to implementation.

## Shipped (spike 2 — 2026-02-20)

- ~~Probe/expand retrieval~~ — `mode="probe"` on `search_memories` + `expand_memories` tool
- ~~Dedup check only examines limit=1~~ — now searches limit=5 and scans through file-indexed chunks
- ~~Empty collection search~~ — early return when collection count is 0
- ~~Lower requires-python to >=3.11~~ — no 3.12-specific features in use
- ~~Recall triggers in SERVER_INSTRUCTIONS~~ — added "When to search" section with probe mode guidance
- ~~Memory dashboard~~ — HTMX + Jinja2 + Starlette dashboard on background thread (browse, search, delete, stats, bulk delete by filter, expandable content)
- ~~Depth-independent vendor excludes~~ — `**/node_modules/**` instead of `node_modules/**`
- ~~`init_project` patterns/excludes~~ — accepts `watch_patterns` and `watch_exclude` params
- ~~`index_files` clears stale chunks~~ — deletes all `file:` chunks before re-reconciling

## Shipped (spike 3 — 2026-02-20)

- ~~Tags input normalization~~ — accept `string | list[str]` for tags param, coerce to list internally. P0 fix from Codex battle test.
- ~~Default min_score cutoff~~ — suppress negative-score results from probe search by default, add optional `min_score` param. P0 fix.
- ~~Dashboard SSE live updates~~ — push events via Server-Sent Events when memories are stored/deleted/indexed, using HTMX `hx-ext="sse"`. Activity indicator for reconciliation in progress.
- ~~Watcher resilience~~ — wrap `index_file` calls in try/except so permission errors, broken symlinks, or bad files log and continue instead of crashing the watcher thread.
- ~~`update_memory` tool~~ — revise content/tags on an existing memory without losing ID or `created_at`. Uses ChromaDB update.
- ~~`annal install` one-shot setup~~ — detect OS, create service file (systemd/launchd/Windows), write `~/.mcp.json` for Claude Code, add Codex and Gemini config entries, start the daemon. One command from `pip install annal` to running.

## Parked

- `annal --install-service` CLI command — detect OS and generate/install the appropriate service file (systemd, launchd, or Windows scheduled task) automatically instead of requiring manual setup from contrib/

## Dashboard

- Live updates via SSE — dashboard is static right now, no feedback when memories are being stored/deleted/indexed in the background. Use HTMX's `hx-ext="sse"` to push events from the server when the store changes, so the table and counts update in real time. Gives visibility into whether indexing is running and what agents are learning as it happens.
- Activity indicator — show when file reconciliation or indexing is in progress (spinner, progress bar, or log stream).
- [field] Performance with large result sets — browse loads all matching items into memory for client-side pagination. May need server-side cursor pagination for projects with thousands of chunks.

## From battle testing (Codex, 2026-02-20)

- Input normalization for tags — Codex sent `tags="dashboard"` (bare string) instead of `["dashboard"]`, causing a validation error. Accept `string | list[str]` and coerce to list internally. P0.
- Default min_score cutoff — probe search returned results with negative scores (-0.03, -0.06) which are pure noise. Add an optional `min_score` param to `search_memories` and suppress negatives by default. P0.
- Structured JSON responses — Codex suggested returning `{results: [{id, content_preview, tags, score}], meta: {query, mode, total}}` alongside or instead of formatted text. Worth considering for non-Claude clients that want to process results programmatically. P2.

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
- SERVER_INSTRUCTIONS don't reach subagents — verified that the MCP server correctly delivers instructions in the `initialize` response (confirmed via raw HTTP test), and the primary Claude Code session receives them (visible in system prompt under "MCP Server Instructions"). However, subagents spawned via the Task tool reported not seeing them. This means for multi-agent workflows, SERVER_INSTRUCTIONS only influence the primary agent. The CLAUDE.md `<annal_semantic_memory>` section is the reliable path for all agents. Implication: critical behaviour nudges (like decision verification, recall triggers) should live in CLAUDE.md, not only in SERVER_INSTRUCTIONS. SERVER_INSTRUCTIONS are a bonus for the primary session, not the sole instruction surface.

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

## From spike 3 code reviews

- `updated_at` inconsistency — `get_by_ids` returns `updated_at` but `search()` and `browse()` do not. Memories that have been updated show the field in `expand_memories` but not in `search_memories` or the dashboard. Add `updated_at` to all retrieval methods for consistency.
- EventBus thread safety — `_queues` list is mutated from multiple threads. CPython GIL makes this safe in practice, but a `threading.Lock` around subscribe/unsubscribe/push would make it correct by contract.
- SSE slow client handling — `run_in_executor(None, q.get)` blocks a thread pool thread indefinitely if no events are pushed and the client disconnects. Use `q.get(timeout=N)` in a loop so threads can check for cancellation.
- HTMX SSE trigger redundancy — `memories.html` uses both `sse-swap` and `hx-trigger` for the same event (`memory_stored`), which is confusing. Simplify to use only `hx-trigger` with `sse-connect`.
- `_annal_executable()` fallback breaks launchd — the `python -m annal.server` fallback returns a single string that becomes one `<string>` element in the plist, but launchd needs separate elements per argument. Only affects users running from raw checkouts (not `pip install`).
- Test gaps: no tests for `update_memory` with nonexistent ID, no-op update_memory guard, update of source-only, Codex/Gemini uninstall cleanup, install idempotency (calling install twice).
- `annal serve` subcommand may be dead weight — existing service files and scripts use bare `annal --transport ...`. The `serve` subcommand adds argparse complexity for no current consumers.

## Future considerations (not for next spike)

- pgvector migration path — if ChromaDB becomes a bottleneck at scale, the MemoryStore interface is clean enough to swap backends. Don't build this until it's actually needed.
- Knowledge graph / entity linking — connecting memories by entities (people, systems, decisions) rather than just vector proximity. Significant complexity, only worth it if retrieval quality plateaus.
- Memory dashboard — web UI for reviewing and managing what agents are learning. Browse memories by project/agent/tag, search, view similarity clusters, delete noise, and spot patterns in what's being stored. Primary value is human oversight of agent knowledge — seeing what they're actually retaining and correcting course when needed. Could be a lightweight local server (Flask/FastAPI + HTMX or similar) served alongside the MCP daemon.
