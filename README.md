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

## Project setup

On first use, call `init_project` with watch paths for file indexing, or just start storing memories — unknown projects are auto-registered in the config.

```
init_project(project_name="myapp", watch_paths=["/home/user/projects/myapp"])
```

Every tool takes a `project` parameter. Use the directory name of the codebase you're working in (e.g. "myapp", "annal").

## Tools

`store_memory` — Store knowledge with tags and source attribution. Near-duplicates (>95% similarity) are automatically skipped.

`search_memories` — Natural language search with optional tag filtering and similarity scores. Supports `mode="probe"` for compact summaries (saves context window) and `mode="full"` for complete content. Optional `min_score` filter suppresses low-relevance noise.

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

### 0.3.0 — Search & Retrieval (next)
Temporal filtering, source/path scoping, cross-project search, bulk operations, structured JSON output.

### Future
Memory relationships and supersession. Proactive context injection. Hybrid search (vector + full-text). Automated git history indexing.

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

Tests cover store operations, search, indexing, file watching, dashboard routes, SSE events, and CLI installation.

## License

MIT — see [LICENSE](LICENSE).
