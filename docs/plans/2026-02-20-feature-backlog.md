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

## Shipped (spike 4 — 2026-02-21)

- ~~Async indexing~~ — `init_project` and `index_files` return immediately, reconciliation runs on a background thread with progress events
- ~~`index_status` tool~~ — per-project diagnostics: chunk counts, indexing state with elapsed time, last reconcile timestamp
- ~~StorePool thread safety~~ — `_stores` dict access protected by `threading.Lock`
- ~~EventBus thread safety~~ — `_queues` list protected by `threading.Lock`
- ~~Dashboard indexing badges~~ — SSE-driven badges show real-time indexing state on the dashboard index page
- ~~`updated_at` in search/expand output~~ — search (full + probe) and expand now surface `updated_at` timestamps
- ~~Mtime cache optimization~~ — `get_all_file_mtimes()` builds a source→mtime map in one O(m) pass instead of O(n*m) per-file scans. Kubernetes reconciliation went from 21+ minutes to 4 seconds.
- ~~Optional file watching~~ — `watch: false` in project config skips watchdog/inotify for large repos. Agents use `index_files` for on-demand re-indexing.
- ~~Heading depth fix~~ — indexer recognizes `#{1,6}` (was `#{1,3}`)
- ~~`_annal_executable` launchd fix~~ — returns list for ProgramArguments compatibility
- ~~Startup reconciliation events~~ — pushes `index_started`/`index_complete` events so dashboard shows activity during startup
- ~~SSE slow client fix~~ — `q.get(timeout=30)` with keepalive instead of indefinite blocking
- ~~HTMX SSE trigger cleanup~~ — removed redundant `sse-swap`, use only `hx-trigger`
- ~~Spike 3 test gaps~~ — added tests for nonexistent update, no-op update, install idempotency, executable return type, h4-h6 headings
- ~~Mtime float tolerance~~ — `abs(stored - current) < 0.5` instead of `==` for ChromaDB roundtrip precision

## Shipped (spike 5 — 2026-02-21)

- ~~Duplicate StorePool in `main()`~~ — `create_server()` now returns `(mcp, pool)` tuple, `main()` shares a single pool with both server and dashboard. P0.
- ~~`activity-indicator` JS references nonexistent element~~ — added `<span id="activity-indicator">` to the page header, fixed JS to use defensive `var el` pattern. P1.
- ~~No `index_failed` event~~ — `reconcile_project_async` now catches exceptions and emits `index_failed`. Startup reconciliation wraps each project in try/except. P1.
- ~~`_index_locks` defaultdict race~~ — replaced with `_get_index_lock()` method protected by `self._lock`. P2.
- ~~SSE catches `Exception` too broadly~~ — narrowed to `queue.Empty`. P2.
- ~~`get_file_mtime` dead code~~ — removed. P3.
- ~~`httpx` missing from dev deps~~ — added. P3.
- ~~Heading context in embeddings~~ — file-indexed chunks now prepend heading path to content for better retrieval quality.
- ~~Temporal filtering~~ — `after`/`before` ISO 8601 date params on `search_memories`, post-query filtering on `created_at`.
- ~~Structured JSON output~~ — `output="json"` param on `search_memories` and `expand_memories`.

## From spike 4 code review (remaining)

- `_index_started` / `_last_reconcile` read without locks — written by the reconcile thread, read by `index_status`. Atomic under GIL but inconsistent with the spike's thread-safety-by-contract goal. P2.
- `config.save()` under `_lock` — YAML serialization + file I/O while holding the pool lock. Could block other threads if filesystem is slow. Move save outside the lock. P3.
- `browse()` loads entire collection — every page request fetches all chunks into memory, then slices. Known limitation (noted as non-goal in spike 4 design) but problematic for kubernetes-scale projects on the dashboard. P2.

## From spike 5 code review

- `before` date filter loses last day with date-only strings — `"2026-02-28T..." > "2026-02-28"` lexicographically, so date-only `before` values exclude the entire last day. Fix: normalize date-only inputs (append `T23:59:59` to `before`, `T00:00:00` to `after`). P1.
- Dual `AnnalConfig` — `main()` creates one config, `create_server()` loads another from same path. `init_project` mutates the closure config but the dashboard's reference never sees new projects. Not a crash, but a drift source. P2.
- `_startup_reconcile` skips index lock — calls synchronous `reconcile_project()` without acquiring the per-project index lock. If `init_project`/`index_files` is called during startup, two reconciliations can race on the same project. P2.

## From spike 5 test coverage review

- No invalid-input tests for temporal date formats — `after="yesterday"` silently does a string comparison with nonsensical results. P2.
- Empty-results JSON path untested — `search_memories` with `output="json"` on no results returns a specific `empty_json` structure but has no test. P2.
- Tags + temporal filters untested in combination — both are post-query filters in the same loop, composition never verified. P3.
- Over-fetch strategy untested at scale — tests store 1-2 memories; the `limit * 3` over-fetch for filtered queries is never exercised meaningfully. P3.
- Heading context test too loose — checks `startswith("doc.md")` not the full heading path format. P3.
- No concurrent test for `_get_index_lock` — identity tests are single-threaded, the race guard is unexercised. P3.

## Parked

- ~~`annal --install-service` CLI command~~ — shipped as `annal install` in spike 3

## Dashboard

- Live updates via SSE — dashboard is static right now, no feedback when memories are being stored/deleted/indexed in the background. Use HTMX's `hx-ext="sse"` to push events from the server when the store changes, so the table and counts update in real time. Gives visibility into whether indexing is running and what agents are learning as it happens.
- Activity indicator — show when file reconciliation or indexing is in progress (spinner, progress bar, or log stream).
- [field] Performance with large result sets — browse loads all matching items into memory for client-side pagination. May need server-side cursor pagination for projects with thousands of chunks.
- Cursor-based pagination — replace offset/limit with opaque cursor tokens for stable pagination that doesn't skip or duplicate items on mutation. ChromaDB doesn't support cursors natively, so this would need a custom layer using `created_at` or document ID as sort key with `where` filtering. Not needed in alpha (offset/limit is fine for now), but worth building if dashboard performance degrades with large collections or if the API is ever exposed externally.

## From battle testing (Codex, 2026-02-20)

- Input normalization for tags — Codex sent `tags="dashboard"` (bare string) instead of `["dashboard"]`, causing a validation error. Accept `string | list[str]` and coerce to list internally. P0.
- Default min_score cutoff — probe search returned results with negative scores (-0.03, -0.06) which are pure noise. Add an optional `min_score` param to `search_memories` and suppress negatives by default. P0.
- ~~Structured JSON responses~~ — shipped in spike 5: `output="json"` on `search_memories` and `expand_memories`

## Retrieval quality

- Fuzzy tag matching — tag filtering currently requires exact string matches, which means `auth` won't find memories tagged `authentication`. Use embedding similarity on tag strings at query time to expand filters to semantically equivalent tags (e.g. embed `"auth"`, compare against all known tags from `list_topics`, include anything above a similarity threshold). Local ONNX embeddings make the extra call negligible. Addresses the fundamental problem that LLMs will never converge on one exact tag string. P2.
- Type tag validation on store — the type tags (`memory`, `decision`, `pattern`, `bug`, `spec`, `preference`) are a fixed vocabulary. Soft-reject unknown type tags at store time with a suggestion ("did you mean `decision`?") to prevent drift. Domain tags remain free-form. P3.
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
- ~~Markdown chunking heading depth~~ — fixed in spike 4: `#{1,6}`
- ~~mtime comparison precision~~ — fixed in spike 4: tolerance-based `abs(stored - current) < 0.5`
- [field] Cold start performance — first query loads the ONNX embedding model. Is the delay acceptable? Does it cause MCP timeouts?
- ~~Watcher resilience~~ — shipped in spike 3
- ~~Large repo behavior~~ — addressed in spike 4: mtime cache optimization (O(n+m) instead of O(n*m)), optional `watch: false` for large repos, async reconciliation

## New tools

- ~~`update_memory`~~ — shipped in spike 3
- `add_tags` / `retag_memory` — modify tags on an existing memory after storage. If an agent realizes a set of memories should have had a `billing` tag, there's currently no recourse. Just a metadata update on the ChromaDB document.
- ~~`index_status`~~ — shipped in spike 4
- Source-scoped search — add an optional `source_prefix` filter to `search_memories` so agents can search within a specific file's chunks or only within agent memories. Useful when the agent knows the knowledge came from a specific document.
- ~~Time window filter~~ — shipped in spike 5: `after`/`before` params on `search_memories`
- CLI subcommands — extend the `annal` entry point beyond just running the server. Add `annal search "query" --project foo --tags decision`, `annal store --project foo --tags decision`, `annal topics --project foo`. Makes Annal usable from the terminal without the agent stack, good for debugging and manual curation.
- Import/export — export a project to JSONL (id, text, metadata), import from JSONL. Useful for testing, portability, backups, and open-source readiness. Simple format, no external dependencies.
- ~~`init_project` patterns/excludes~~ — shipped in spike 2

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
- ~~Store pool thread safety~~ — fixed in spike 4: `threading.Lock` on `_stores` dict
- Reconcile creates throwaway FileWatcher — `pool.reconcile_project` instantiates a full FileWatcher just to call `.reconcile()`, then discards it. `start_watcher` then creates another one. The reconcile logic could be a standalone function or live on the pool directly.
- Cross-project search — allow agents to search across multiple project collections so experience from one codebase can inform work in another. A BA agent who learned domain patterns in project X should be able to draw on that knowledge in project Y. Fan-out approach: query all (or specified) project collections in parallel, merge results by similarity score. Simpler than agent-scoped collections because agents don't need to decide at storage time whether knowledge is "project-specific" or "portable." Could add an optional `projects` parameter to `search_memories` (list of project names, or `"*"` for all).

## From spike 3 code reviews

- ~~`updated_at` inconsistency~~ — fixed in spike 4: search/browse/expand all return `updated_at`
- ~~EventBus thread safety~~ — fixed in spike 4: `threading.Lock` on subscribe/unsubscribe/push
- ~~SSE slow client handling~~ — fixed in spike 4: `q.get(timeout=30)` with keepalive loop
- ~~HTMX SSE trigger redundancy~~ — fixed in spike 4: simplified to `hx-trigger` only
- ~~`_annal_executable()` fallback breaks launchd~~ — fixed in spike 4: returns list
- ~~Test gaps~~ — fixed in spike 4: added nonexistent update, no-op update, install idempotency, executable return type, heading depth tests
- `annal serve` subcommand may be dead weight — existing service files and scripts use bare `annal --transport ...`. The `serve` subcommand adds argparse complexity for no current consumers.

## Future considerations (not for next spike)

- pgvector migration path — if ChromaDB becomes a bottleneck at scale, the MemoryStore interface is clean enough to swap backends. Don't build this until it's actually needed.
- Knowledge graph / entity linking — connecting memories by entities (people, systems, decisions) rather than just vector proximity. Significant complexity, only worth it if retrieval quality plateaus.
- Memory dashboard — web UI for reviewing and managing what agents are learning. Browse memories by project/agent/tag, search, view similarity clusters, delete noise, and spot patterns in what's being stored. Primary value is human oversight of agent knowledge — seeing what they're actually retaining and correcting course when needed. Could be a lightweight local server (Flask/FastAPI + HTMX or similar) served alongside the MCP daemon.
