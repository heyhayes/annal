# Memex — Semantic Memory Server for AI Agent Teams

## Problem

AI agents working across sessions repeatedly search for the same codebase knowledge. The current memory system (MEMORY.md) is always-on — every session loads everything regardless of relevance. This wastes tokens, introduces noise, and doesn't scale to multiple agents or projects. Agents need selective, contextually relevant knowledge retrieval.

## Solution

A standalone Python MCP server that provides semantic memory storage and retrieval using ChromaDB with local embeddings. Agents store and query knowledge through MCP tools, getting back only what's relevant to their current task. The server is project-agnostic and works across any codebase.

## Architecture

### Core Components

The server has four layers: an MCP tool interface that agents interact with, a retrieval engine combining ChromaDB vector similarity with metadata filtering, a file indexer that watches configured paths and auto-indexes documents, and a config system mapping project names to settings.

### Runtime

Phase 1 runs on-demand via MCP stdio transport — Claude Code spawns the process at session start and kills it when done. Phase 2 adds HTTP/SSE transport for remote access from multiple machines, deployed on a persistent Linux server.

### Embeddings

Uses ChromaDB's default ONNX-based embedding function with the `all-MiniLM-L6-v2` model. Local inference, no API calls, ~100-200MB RAM footprint. Chosen for deployment portability to cheap servers.

### Data Storage

All data lives under a configurable root directory (`~/.memex/data`). ChromaDB collections are namespaced by project name. Each project gets its own isolated collection.

## MCP Tool Interface

### store_memory
Stores a piece of knowledge.
- `content` (string, required) — the knowledge to store
- `tags` (list of strings, required) — domain labels like `["billing", "checkout"]`
- `source` (string, optional) — origin context (file path, "session observation", etc.)
- `project` (string, required) — project name
- Returns: memory ID

### search_memories
Retrieves relevant knowledge.
- `query` (string, required) — natural language search
- `project` (string, required) — project name
- `tags` (list of strings, optional) — filter to specific domains
- `limit` (int, optional, default 5) — max results
- Returns: list of memories with content, tags, source, similarity score, timestamp

### delete_memory
Removes outdated knowledge.
- `id` (string, required) — memory ID

### list_topics
Shows what knowledge domains exist.
- `project` (string, required)
- Returns: unique tags with counts

### init_project
Bootstraps a new project.
- `project` (string, required) — project name
- `watch_paths` (list of strings, optional) — directories to watch
- Creates config entry with sensible defaults

### index_files
Triggers manual re-indexing.
- `project` (string, required)
- Re-indexes all watched paths for the project

## Memory Chunking

### Agent-written memories
Stored as single chunks. Agents naturally produce discrete, well-sized knowledge pieces.

### File-indexed documents (markdown)
Split by heading sections (h1/h2/h3 boundaries). Each section becomes a separate chunk tagged with filename and heading path (e.g., `source: AGENT.md > Backend Structure`). This prevents large documents from producing diluted embeddings.

### Config files (JSON/YAML/TOML)
Stored as single chunks — typically small and semantically cohesive.

### Chunk metadata
Every chunk carries: project, tags, source file path, section heading, chunk type (agent-memory vs file-indexed), and last-modified timestamp.

## File Watcher

Uses Python's `watchdog` library to monitor configured paths during active sessions. On file create/modify/delete, re-indexes the affected file (delete old chunks, re-chunk, embed, store).

On startup, performs a full reconciliation: compares every watched file's modification time against stored chunk timestamps. Re-indexes anything newer, cleans up chunks for deleted files. This handles changes that occurred while the server wasn't running.

### Default watch patterns
```yaml
watch_patterns: ["**/*.md", "**/*.yaml", "**/*.toml", "**/*.json"]
watch_exclude: ["node_modules/**", "vendor/**", ".git/**", "dist/**", "build/**"]
```

## Configuration

Lives at `~/.memex/config.yaml`:

```yaml
data_dir: ~/.memex/data
embedding_model: all-MiniLM-L6-v2

projects:
  classmanager:
    watch_paths:
      - /home/hayes/development/work/classmanager
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

### Claude Code integration

Add to `.claude/settings.json` (per-project or global):

```json
{
  "mcpServers": {
    "memex": {
      "command": "python",
      "args": ["-m", "memex.server"],
      "env": {
        "MEMEX_PROJECT": "classmanager"
      }
    }
  }
}
```

## Design Decisions

- **Project identification**: Explicit project name in config, not derived from paths. Supports worktrees, multiple machines, and remote deployment.
- **Access control**: Open — any agent can read/write any memory in a project. Simplicity over granularity.
- **Knowledge sources**: Pre-seeded file indexing + agent session memories + file-watching with startup reconciliation.
- **Embedding runtime**: ONNX over PyTorch for deployment portability to resource-constrained servers.
- **Transport**: Stdio for Phase 1 (local), HTTP/SSE for Phase 2 (remote multi-machine access).

## Phase 2: Remote Access (Future)

Add HTTP/SSE transport so the server can run on a persistent Linux box and be accessed by agents on any machine. File-watching on the server would require either cloning repos locally or having agents push file contents through the API. The MCP tool interface remains unchanged.
