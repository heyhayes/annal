# Annal Feature Backlog

Compiled from the initial spike. Items marked with [field] are things to validate during real-world use before committing to implementation.

## Parked from this session

- `annal --install-service` CLI command — detect OS and generate/install the appropriate service file (systemd, launchd, or Windows scheduled task) automatically instead of requiring manual setup from contrib/

## Retrieval quality

- Hybrid search — combine vector similarity with full-text search (BM25 or similar) for better recall. Vector search misses exact keyword matches; full-text misses semantic similarity. Fusing both (reciprocal rank fusion or similar) would improve retrieval without adding infrastructure.
- [field] Tune the dedup threshold — currently 0.95 cosine similarity. Might be too aggressive (rejecting distinct memories) or too loose (allowing near-duplicates). Needs real-world data to calibrate.
- [field] Evaluate retrieval quality — are agents finding what they need? Track cases where relevant memories aren't surfacing and identify patterns.

## LLM enrichment

- Summarize the "why" from business documents — point a lightweight model at requirements docs, specs, meeting notes and extract intent, constraints, trade-offs. Store enriched summaries alongside raw content so semantic search catches the reasoning, not just the text.
- [field] Figure out where the "why" comes from — code analysis alone won't give you intent. The richest source is agent-user conversations where decisions happen. Consider: should agents be better at recognizing "this is a moment worth recording" rather than enriching after the fact?

## Developer experience

- `.gitignore` for `~/.annal/data` or equivalent — make sure ChromaDB storage doesn't accidentally get committed if someone puts a project inside a repo
- [field] Cross-platform path handling — test on macOS and Windows. File watcher paths, config paths (`~/.annal/`), and `os.path` usage should work across all three OSes.
- [field] Cold start performance — first query loads the ONNX embedding model. Is the delay acceptable? Does it cause MCP timeouts?
- [field] Large repo behavior — what happens with a repo that has thousands of markdown files? Does reconciliation block for too long? Is the mtime check fast enough at scale?

## Data management

- Migration tooling — when config paths or collection naming changes (like the memex → annal rename), provide a way to migrate existing data rather than starting fresh
- Memory expiry / cleanup — should old memories decay? Or should there be a manual cleanup tool? As the store grows, retrieval quality may degrade from noise.
- [field] Backup and restore — is ChromaDB's file-based storage easy to back up? Can you just tar ~/.annal/data?

## Architecture

- [field] Concurrent write safety — multiple agents storing memories simultaneously via the HTTP daemon. Does ChromaDB handle this gracefully or do we need locking?
- [field] Memory isolation between agents — the tag conventions (agent:role-name) provide soft isolation. Is that sufficient or do agents pollute each other's search results?
- Store pool thread safety — the StorePool dict isn't protected by a lock. If two requests hit get_store for a new project simultaneously, could we get a race condition?

## Future considerations (not for next spike)

- pgvector migration path — if ChromaDB becomes a bottleneck at scale, the MemoryStore interface is clean enough to swap backends. Don't build this until it's actually needed.
- Knowledge graph / entity linking — connecting memories by entities (people, systems, decisions) rather than just vector proximity. Significant complexity, only worth it if retrieval quality plateaus.
- Web UI — dashboard for browsing memories, searching, cleaning up. Low priority since the primary interface is MCP tools, but useful for debugging and manual curation.
