# Annal

*A tool built by tools, for tools.*

> Early stage — this project is under active development and not yet ready for production use. APIs, config formats, and storage schemas may change without notice. If you're curious, feel free to explore and open issues, but expect rough edges.

Semantic memory server for AI agent teams. Stores, searches, and retrieves knowledge across sessions using ChromaDB with local ONNX embeddings, exposed as an MCP server.

Designed for multi-agent workflows where analysts, architects, developers, and reviewers need shared institutional memory — decisions made months ago surface automatically when relevant, preventing contradictions and preserving context that no single session can hold.

## How it works

Annal runs as a persistent MCP server (stdio or HTTP) and provides tools for storing, searching, updating, and managing memories. Memories are embedded locally using all-MiniLM-L6-v2 (ONNX) and stored in ChromaDB, namespaced per project.

File indexing is optional. Point Annal at directories to watch and it will chunk markdown files by heading, track modification times for incremental re-indexing, and keep the store current via watchdog filesystem events. For large repos, file watching can be disabled per-project — agents trigger re-indexing on demand via `index_files`.

Indexing is non-blocking. `init_project` and `index_files` return immediately while reconciliation runs in the background. Agents poll `index_status` to track progress, which shows elapsed time and chunk counts.

Agent memories and file-indexed content coexist in the same search space but are distinguished by tags (`memory`, `decision`, `pattern`, `bug`, `indexed`, etc.), so agents can search everything or filter to just what they need.

A web dashboard (HTMX + Jinja2) runs alongside the server, providing a browser-based view of memories with search, browsing, bulk delete, and live SSE updates when memories are stored or indexing is in progress.

## Quick start

```bash
pip install annal

# One-shot setup: creates service, configures MCP clients, starts the daemon
annal install
```

Or from source:

```bash
git clone https://github.com/heyhayes/annal.git
cd annal
pip install -e ".[dev]"

# Run in stdio mode (single session)
annal

# Run as HTTP daemon (shared across sessions)
annal --transport streamable-http
```

`annal install` detects your OS and sets up the appropriate service (systemd on Linux, launchd on macOS, scheduled task on Windows). It also writes MCP client configs for Claude Code, Codex, and Gemini CLI.

## MCP client integration

### Claude Code

Add to `~/.mcp.json` for stdio mode:

```json
{
  "mcpServers": {
    "annal": {
      "command": "/path/to/annal/.venv/bin/annal"
    }
  }
}
```

For HTTP daemon mode (recommended when running multiple concurrent sessions):

```json
{
  "mcpServers": {
    "annal": {
      "type": "http",
      "url": "http://localhost:9200/mcp"
    }
  }
}
```

### Codex / Gemini CLI

`annal install` writes the appropriate config files automatically. See `annal install` output for paths.

## Agent configuration

For agents to actually use Annal, they need instructions that explain why it matters, not just how to call it. Add one of these snippets to your `CLAUDE.md`, `AGENT.md`, or equivalent agent instructions file.

### Recommended snippet

```xml
<annal_semantic_memory>
You have persistent semantic memory via Annal (mcp__annal__* tools). Memories survive across
sessions and are searchable by meaning. This is your long-term memory — MEMORY.md is a cheat
sheet, Annal is deep storage.

Why this matters: every session starts blank. Without Annal, you repeat investigations,
rediscover patterns, and miss prior decisions. With it, you inherit your past self's
understanding of the codebase.

When to search (use mode="probe" to scan, then expand_memories for details):
- Session start: load context for the current task area
- Unfamiliar code: before diving into a module you haven't seen this session
- "What happened" questions: anything about recent work, prior decisions, project state
- Before architectural changes: check for prior decisions in the same domain
- Familiar-feeling bugs: search for prior root causes

When to store (tag with type + domain, e.g. tags=["decision", "auth"]):
- Bug root causes and the fix that worked
- Architectural decisions and their rationale
- Codebase patterns that took effort to discover
- User preferences for workflow, tools, style
- Key file paths and module responsibilities in unfamiliar codebases

After completing a task, before moving on, always ask: what did I learn that I'd want to know
next time? If you discovered a root cause, mapped unfamiliar architecture, or found a pattern
that took effort — store it. This is the single most important habit for cross-session value.

Project name: use the basename of the current working directory.
</annal_semantic_memory>
```

### Minimal snippet

If you prefer something shorter:

```xml
<annal_semantic_memory>
You have persistent semantic memory via Annal (mcp__annal__* tools). Unlike MEMORY.md which
resets with context, Annal memories survive across sessions and are searchable by meaning.

This matters because you lose all context when a session ends. Annal is how you recover it.
Search before starting work — your past self may have already mapped the architecture,
debugged this module, or recorded a decision that saves you from repeating the investigation.

Search: at session start, when touching unfamiliar code, when the user asks "what did we
decide about X", and before proposing architectural changes. Use mode="probe" to scan cheaply.

Store: bug root causes, architectural decisions, codebase patterns, surprising discoveries —
anything you'd want to know if you started a fresh session tomorrow. Tag with a type
(decision, bug, pattern, memory) plus domain tags. After completing a task, always ask: what
did I learn? Store it before moving on.

Project name: use the basename of the current working directory.
</annal_semantic_memory>
```

## Project setup

On first use, call `init_project` with watch paths for file indexing, or just start storing memories — unknown projects are auto-registered in the config.

```
init_project(project_name="myapp", watch_paths=["/home/user/projects/myapp"])
```

Every tool takes a `project` parameter. Use the directory name of the codebase you're working in (e.g. "myapp", "annal").

## Tools

`store_memory` — Store knowledge with tags and source attribution. Near-duplicates (>95% similarity) are automatically skipped.

`search_memories` — Natural language search with optional tag filtering and similarity scores. Supports `mode="probe"` for compact summaries (saves context window) and `mode="full"` for complete content. Optional `min_score` filter suppresses low-relevance noise. Tags use fuzzy matching (semantic similarity) so `tags=["auth"]` finds memories tagged `authentication`. Optional `projects` parameter enables cross-project search.

`expand_memories` — Retrieve full content for specific memory IDs. Use after a probe search to fetch details for relevant results.

`update_memory` — Revise content, tags, or source on an existing memory without losing its ID or creation timestamp. Tracks `updated_at` alongside the original.

`delete_memory` — Remove a specific memory by ID.

`list_topics` — Show all tags and their frequency counts.

`init_project` — Register a project with watch paths, patterns, and exclusions for file indexing. Indexing starts in the background and returns immediately.

`index_files` — Full re-index: clears all file-indexed chunks and re-indexes from scratch. Use after changing exclude patterns to remove stale chunks.

`index_status` — Per-project diagnostics: total chunks, file-indexed vs agent memory counts, indexing state with elapsed time, and last reconcile timestamp.

## Configuration

`~/.annal/config.yaml`:

```yaml
data_dir: ~/.annal/data
port: 9200
projects:
  myapp:
    watch_paths:
      - /home/user/projects/myapp
    watch_patterns:
      - "**/*.md"
      - "**/*.yaml"
      - "**/*.toml"
      - "**/*.json"
    watch_exclude:
      - "**/node_modules/**"
      - "**/vendor/**"
      - "**/.git/**"
      - "**/.venv/**"
      - "**/__pycache__/**"
      - "**/dist/**"
      - "**/build/**"
  large-repo:
    watch: false          # disable file watching, use index_files on demand
    watch_paths:
      - /home/user/projects/large-repo
```

## Running as a daemon

The recommended approach is `annal install`, which sets up the service for your OS automatically.

For manual setup, use the service scripts in `contrib/`:

### Linux (systemd)

```bash
cp contrib/annal.service ~/.config/systemd/user/
# Edit ExecStart path, then:
systemctl --user daemon-reload
systemctl --user enable --now annal
```

### macOS (launchd)

```bash
cp contrib/com.annal.server.plist ~/Library/LaunchAgents/
# Edit the ProgramArguments path, then:
launchctl load ~/Library/LaunchAgents/com.annal.server.plist
```

### Windows (scheduled task)

```powershell
.\contrib\annal-service.ps1 -Action install -AnnalPath "C:\path\to\annal\.venv\Scripts\annal.exe"
Start-ScheduledTask -TaskName "Annal MCP Server"
```

## Dashboard

When running as an HTTP daemon, the dashboard is available at `http://localhost:9200`. It provides:

- Memory browsing with pagination and filters (by type, source, tags)
- Full-text search across memories
- Expandable content previews
- Bulk delete by filter
- Live SSE updates when memories are stored, deleted, or indexing is in progress

Disable with `--no-dashboard` if not needed.

## Roadmap

### 0.1.0 — Foundation (shipped)
Core memory store, semantic search, file indexing, MCP server, web dashboard, one-shot install.

### 0.2.0 — Operational Readiness (shipped)
Async indexing, thread safety, index_status diagnostics, mtime cache performance, optional file watching.

### 0.3.0 — Search & Retrieval (shipped)
Temporal filtering, structured JSON output, heading context in embeddings.

### 0.4.0 — Bug Sweep + Features (shipped)
Six bug fixes (date filter, dual config, startup lock, pool lock safety, browse pagination, config I/O under lock). Fuzzy tag matching via ONNX embeddings. Cross-project search with fan-out and score-based merge.

### 0.5.0 — Stress-Test Bug Sweep (shipped)
Seven fixes from stress testing: min_score no longer masks fuzzy tag matches, cross-project search always includes primary project, empty parent heading chunks skipped, invalid dates raise errors instead of silently returning empty, dedup checks all agent-memory candidates, daemon threads joined on shutdown, fuzzy tag threshold lowered to 0.72.

### Future
Memory relationships and supersession. Proactive context injection. Hybrid search (vector + full-text). CLI subcommands. Import/export.

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

Tests cover store operations, search, indexing, file watching, dashboard routes, SSE events, and CLI installation.

## License

MIT — see [LICENSE](LICENSE).
