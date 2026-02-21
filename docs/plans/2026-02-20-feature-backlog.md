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

## Shipped (spike 6 — 2026-02-21)

- ~~`annal install` writes CLAUDE.md instructions and post-commit hook~~ — install enhancements from spike 5 uncommitted work
- ~~`before` date filter loses last day~~ — normalize date-only inputs (`T23:59:59`/`T00:00:00`)
- ~~Dual `AnnalConfig`~~ — `create_server()` accepts optional `config` param, shares instance with `main()`
- ~~`_startup_reconcile` skips index lock~~ — switched to `reconcile_project_async` which acquires lock
- ~~`_index_started` / `_last_reconcile` reads without locks~~ — all reads/writes now protected by `self._lock`
- ~~`config.save()` under `_lock`~~ — moved save outside lock, I/O no longer blocks pool
- ~~`browse()` loads entire collection~~ — fast path uses ChromaDB `offset`/`limit` for unfiltered queries
- ~~Invalid date format validation~~ — ISO 8601 regex, return empty on invalid input
- ~~Test coverage gaps~~ — combined filters, overfetch, heading path, concurrent lock, empty JSON
- ~~Fuzzy tag matching~~ — semantic similarity expands tag filters via ONNX embeddings (0.75 threshold)
- ~~Cross-project search~~ — `projects` param on `search_memories` fans out across collections, merges by score

## Shipped (spike 6.1 — 2026-02-21)

- ~~`projects=["*"]` wildcard list form~~ — `projects == "*"` check didn't match `["*"]` (list), causing literal `annal_*` collection name error. Added `or projects == ["*"]` check. Published as 0.4.1.

## Shipped (spike 7 — 2026-02-21)

- ~~`min_score` masks fuzzy tag matches~~ — skip `min_score` filtering when tag filters are provided. Content similarity is noise when fuzzy tag match is the real signal. P1.
- ~~Cross-project `projects` param excludes primary~~ — always include primary project in search set when `projects` is provided. P1.
- ~~Empty parent heading chunks~~ — skip headings with no body text (only sub-headings). P1.
- ~~Invalid date returns empty silently~~ — raise `ValueError` on invalid dates, return descriptive error message. Validate before empty-collection check. P1.
- ~~Dedup check bypassed by file-indexed chunks~~ — increased limit from 5 to 10, removed early break so all agent-memory candidates are checked. P2.
- ~~Daemon threads not joined on shutdown~~ — track reconciliation threads, join in `shutdown()` with configurable timeout. P2.
- ~~Fuzzy tag threshold lowered to 0.72~~ — rescues "dbs"→"database" and "CI"→"ci-cd" with zero false positives. P2.

## Shipped (spike 8 — 2026-02-21)

- ~~Vector backend abstraction~~ — `VectorBackend` protocol (7 methods), `Embedder` protocol, `OnnxEmbedder` implementation. `MemoryStore` refactored to delegate to backend + embedder.
- ~~ChromaBackend extraction~~ — existing ChromaDB logic extracted behind the `VectorBackend` protocol. Post-query filtering for tags/prefix/dates, JSON tag roundtrip.
- ~~QdrantBackend~~ — full implementation with server-side tag filtering (MatchAny), deterministic UUID IDs (uuid5), cursor-based scroll for scan, post-query prefix/date filtering.
- ~~Hybrid search (BM25 + vector fusion)~~ — Qdrant collections with BM25 sparse vectors + dense vectors. Queries use Reciprocal Rank Fusion (RRF) via Prefetch stages. Transparent to MemoryStore — `query_text` flows through for the BM25 leg.
- ~~Config-driven backend selection~~ — `storage:` section in config.yaml selects backend (`chromadb` or `qdrant`) with per-backend config (path, url, hybrid flag).
- ~~Migration CLI~~ — `annal migrate --from chromadb --to qdrant --project <name>` scans source, re-embeds in batches of 100, inserts into destination.

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

- ~~Fuzzy tag matching~~ — shipped in spike 6: semantic similarity expands tag filters via ONNX embeddings
- Type tag validation on store — the type tags (`memory`, `decision`, `pattern`, `bug`, `spec`, `preference`) are a fixed vocabulary. Soft-reject unknown type tags at store time with a suggestion ("did you mean `decision`?") to prevent drift. Domain tags remain free-form. P3.
- ~~Hybrid search~~ — shipped in spike 8: BM25 + vector fusion via Qdrant RRF
- [field] Tune the dedup threshold — currently 0.95 cosine similarity. Might be too aggressive (rejecting distinct memories) or too loose (allowing near-duplicates). Needs real-world data to calibrate.
- [field] Evaluate retrieval quality — are agents finding what they need? Track cases where relevant memories aren't surfacing and identify patterns. *Spike 7 stress test scored 3.4/5 average across 10 MCP SDK onboarding queries. Auth and error handling were 5/5, project structure 1/5 (info not in docs). Main gaps: empty parent heading chunks and enumeration queries needing higher limits.*

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

- ~~Migration tooling~~ — shipped in spike 8: `annal migrate --from chromadb --to qdrant --project <name>`
- Memory pinning / weight — not all memories are equal. An architectural decision should outrank a casual session observation. A `priority` metadata field (`normal`, `important`, `critical`) that boosts search scores would let agents surface high-value memories first. Could be set on store or promoted after the fact with a `pin_memory` tool.
- Stale memory detection — surface memories that haven't matched any search in a long time or were stored many sessions ago. A `stale_memories(project, older_than_days)` tool would help agents curate the store. Needs a `last_accessed_at` field updated on search hits.
- Memory supersession — a lightweight `supersede(old_id, new_id)` that marks an old memory as replaced without deleting it. Simpler than full knowledge graph linking but solves the key problem: agents can follow the chain to find the latest version of a decision. Could be as simple as a `superseded_by` metadata field that search results flag.
- Memory expiry / cleanup — should old memories decay? Or should there be a manual cleanup tool? As the store grows, retrieval quality may degrade from noise.
- [field] Backup and restore — is ChromaDB's file-based storage easy to back up? Can you just tar ~/.annal/data?

## Architecture

- ~~Concurrent write safety~~ — resolved by Qdrant backend (native concurrent access). ChromaDB still limited to single-process access.
- [field] Memory isolation between agents — the tag conventions (agent:role-name) provide soft isolation. Is that sufficient or do agents pollute each other's search results?
- ~~Store pool thread safety~~ — fixed in spike 4: `threading.Lock` on `_stores` dict
- Reconcile creates throwaway FileWatcher — `pool.reconcile_project` instantiates a full FileWatcher just to call `.reconcile()`, then discards it. `start_watcher` then creates another one. The reconcile logic could be a standalone function or live on the pool directly.
- ~~Cross-project search~~ — shipped in spike 6: `projects` param on `search_memories` fans out across collections

## From spike 3 code reviews

- ~~`updated_at` inconsistency~~ — fixed in spike 4: search/browse/expand all return `updated_at`
- ~~EventBus thread safety~~ — fixed in spike 4: `threading.Lock` on subscribe/unsubscribe/push
- ~~SSE slow client handling~~ — fixed in spike 4: `q.get(timeout=30)` with keepalive loop
- ~~HTMX SSE trigger redundancy~~ — fixed in spike 4: simplified to `hx-trigger` only
- ~~`_annal_executable()` fallback breaks launchd~~ — fixed in spike 4: returns list
- ~~Test gaps~~ — fixed in spike 4: added nonexistent update, no-op update, install idempotency, executable return type, heading depth tests
- `annal serve` subcommand may be dead weight — existing service files and scripts use bare `annal --transport ...`. The `serve` subcommand adds argparse complexity for no current consumers.

## Future considerations (not for next spike)

- ~~pgvector migration path~~ — superseded by spike 8: VectorBackend protocol makes adding new backends straightforward. Qdrant already available as an alternative.
- Knowledge graph / entity linking — connecting memories by entities (people, systems, decisions) rather than just vector proximity. Significant complexity, only worth it if retrieval quality plateaus.
- Memory dashboard — web UI for reviewing and managing what agents are learning. Browse memories by project/agent/tag, search, view similarity clusters, delete noise, and spot patterns in what's being stored. Primary value is human oversight of agent knowledge — seeing what they're actually retaining and correcting course when needed. Could be a lightweight local server (Flask/FastAPI + HTMX or similar) served alongside the MCP daemon.
