# Memex

A semantic memory MCP server for AI agent teams. Stores and retrieves knowledge using ChromaDB with local ONNX embeddings. Indexes markdown and config files automatically, and provides natural language search across both file-indexed content and agent-stored memories.

## Install

```bash
pip install -e ".[dev]"
```

## Config

Create `~/.memex/config.yaml`:

```yaml
data_dir: ~/.memex/data

projects:
  myproject:
    watch_paths:
      - /path/to/your/project
    watch_patterns:
      - "**/*.md"
      - "**/*.yaml"
      - "**/*.toml"
      - "**/*.json"
    watch_exclude:
      - "node_modules/**"
      - "vendor/**"
      - ".git/**"
```

## Claude Code Integration

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "memex": {
      "command": "/path/to/memex/.venv/bin/python",
      "args": ["-m", "memex.server"],
      "env": {
        "MEMEX_PROJECT": "myproject"
      }
    }
  }
}
```

## Tools

The server exposes 6 MCP tools:

`store_memory` — Store a piece of knowledge with tags and source attribution.
`search_memories` — Natural language search across all memories, with optional tag filtering.
`delete_memory` — Remove a specific memory by ID.
`list_topics` — Show all tags and their frequency counts.
`init_project` — Register a new project in the config with watch paths.
`index_files` — Manually re-index all watched files for the current project.

## Running Tests

```bash
pytest -v
```
