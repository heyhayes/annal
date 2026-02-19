# Memex — Semantic Memory MCP Server

## What This Is

A standalone Python MCP server that provides semantic memory storage and retrieval for AI agent teams. Uses ChromaDB with local ONNX embeddings. Project-agnostic — designed to work across any codebase.

## Project Structure

```
memex/
├── src/memex/          # Package source
│   ├── __init__.py
│   ├── server.py       # MCP server entry point (FastMCP)
│   ├── config.py       # YAML config management
│   ├── store.py        # ChromaDB wrapper
│   ├── indexer.py       # File chunking (markdown by headings, config as single chunks)
│   └── watcher.py      # File watcher (watchdog + startup reconciliation)
├── tests/              # pytest tests
├── docs/plans/         # Design doc and implementation plan
└── pyproject.toml      # Project config (hatchling build)
```

## Commands

```bash
# Install (editable with dev deps)
pip install -e ".[dev]"

# Run tests
pytest -v

# Run single test file
pytest tests/test_store.py -v

# Run the server (stdio mode)
python -m memex.server
```

## Tech Stack

- Python 3.12, FastMCP (mcp SDK), ChromaDB (ONNX default embeddings), watchdog, PyYAML, pytest

## Code Standards

- Type hints on all function signatures
- Docstrings on public functions
- Tests for every module (TDD — write tests first)
- No print() to stdout (breaks MCP stdio transport) — use logging to stderr

## Architecture Notes

- ChromaDB PersistentClient stores data at `~/.memex/data` by default
- Collections namespaced by project: `memex_{project_name}`
- Tags stored as JSON strings in ChromaDB metadata (ChromaDB doesn't natively support list metadata)
- File-indexed chunks use `source: file:{path}|{heading}` format for identification
- Tag filtering is post-query (search over-fetches then filters) due to ChromaDB metadata limitations
- Lazy store initialization — created on first tool call, not at server startup

## Implementation Plan

See `docs/plans/2026-02-19-memex-implementation.md` for the full task-by-task plan.
