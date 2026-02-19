# Annal

Semantic memory server for AI agent teams. Stores, searches, and retrieves knowledge across sessions using ChromaDB with local ONNX embeddings, exposed as an MCP server.

Designed for multi-agent workflows where analysts, architects, developers, and reviewers need shared institutional memory — decisions made months ago surface automatically when relevant, preventing contradictions and preserving context that no single session can hold.

## How it works

Annal runs as a persistent MCP server (stdio or HTTP) and provides five core operations: store a memory, search memories by natural language, delete a memory, list topics, and initialize a project. Memories are embedded locally using all-MiniLM-L6-v2 (ONNX) and stored in ChromaDB, namespaced per project.

File indexing is optional. Point Annal at directories to watch and it will chunk markdown files by heading, track modification times for incremental re-indexing, and keep the store current via watchdog filesystem events.

Agent memories and file-indexed content coexist in the same search space but are distinguished by tags (`memory`, `decision`, `pattern`, `bug`, `indexed`, etc.), so agents can search everything or filter to just what they need.

## Quick start

```bash
git clone https://github.com/yourusername/annal.git
cd annal
pip install -e ".[dev]"

# Run in stdio mode (single session)
annal

# Run as HTTP daemon (shared across sessions)
annal --transport streamable-http
```

## Claude Code integration

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

## Project setup

On first use, either call the `init_project` tool with watch paths for file indexing, or just start storing memories — unknown projects are auto-registered in the config.

```
init_project(project_name="myapp", watch_paths=["/home/user/projects/myapp"])
```

Every tool takes a `project` parameter. Use the directory name of the codebase you're working in (e.g. "myapp", "annal").

## Tools

`store_memory` — Store knowledge with tags and source attribution. Near-duplicates (>95% similarity) are automatically skipped.

`search_memories` — Natural language search across all memories, with optional tag filtering. Returns similarity scores and memory IDs.

`delete_memory` — Remove a specific memory by ID.

`list_topics` — Show all tags and their frequency counts.

`init_project` — Register a project with watch paths for file indexing.

`index_files` — Manually re-index all watched files for a project.

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
      - "node_modules/**"
      - ".git/**"
      - ".venv/**"
```

## Running as a systemd service

For always-on daemon mode:

```bash
cp contrib/annal.service ~/.config/systemd/user/
# Edit ExecStart path to match your install, then:
systemctl --user daemon-reload
systemctl --user enable --now annal
```

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

## License

MIT — see [LICENSE](LICENSE).
