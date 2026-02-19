"""Memex MCP server — semantic memory for AI agent teams."""

from __future__ import annotations

import atexit
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from memex.config import MemexConfig, DEFAULT_CONFIG_PATH
from memex.store import MemoryStore
from memex.watcher import FileWatcher

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


SERVER_INSTRUCTIONS = """\
Memex is your persistent semantic memory. Memories you store survive across sessions.

## Automatic project detection
The current project is derived from the working directory name unless overridden
via the MEMEX_PROJECT environment variable. You can check which project is active
by looking at the project name in tool responses.

## First-time setup
If the current project has no watch paths configured, use `init_project` to set it up.
Pass the project name and a list of directory paths to watch for file indexing.
For example: init_project("myapp", ["/home/user/projects/myapp"])

## When to store memories
Store memories when you encounter information worth preserving across sessions:
- Architectural decisions and their rationale
- Bug fixes and their root causes
- User preferences for workflow, style, or tooling
- Important patterns or conventions in the codebase
- Domain knowledge that took effort to discover

## Searching
Use search_memories with natural language — it uses semantic similarity, not keyword
matching. Filter by tags to narrow results when the memory store grows large.

## Tag conventions

Tags serve two purposes: classifying what a memory is about (domain tags) and
controlling who stored it and how to retrieve it (system tags).

### Memory type tags — use these when storing memories

- `memory` — session observations, discoveries, things learned while working
- `decision` — architectural or design decisions and their rationale
- `preference` — user preferences for workflow, tooling, or communication style
- `pattern` — recurring codebase patterns, conventions, or idioms
- `bug` — bug discoveries, root causes, and fixes
- `spec` — specifications, requirements, or design constraints

Combine type tags with domain tags for the subject area, e.g.:
  tags: ["decision", "billing", "auth"]
  tags: ["bug", "checkout", "timezone"]

### Agent identity tags — namespace with `agent:`

When storing memories, include your agent identity tag so memories can be
filtered by who stored them. Format: `agent:<role>`.

Examples: `agent:code-reviewer`, `agent:planner`, `agent:debugger`

This lets agents retrieve their own prior context:
  search_memories(query="...", tags=["agent:code-reviewer"])

### System tags — applied automatically to file-indexed content

These are set by the file indexer, not by agents:
- `indexed` — all file-indexed chunks
- `agent-config` — chunks from CLAUDE.md, AGENT.md, or similar agent config files
- `docs` — chunks from README files

To search only agent-stored memories (excluding file-indexed content), filter
by any memory type tag. To search only file-indexed content, use `indexed`.

## Decision verification

Before accepting, proposing, or implementing a design decision, search memex
for prior decisions in the same domain. Use the `decision` tag combined with
relevant domain tags:
  search_memories(query="<describe the decision area>", tags=["decision"])

If a prior decision contradicts what is currently being proposed, surface it
explicitly. Explain what was previously decided, why, and ask whether the new
direction is intentional or an oversight. Do not silently override prior
decisions — treat them as constraints until the user explicitly revises them.

This applies at every stage of a workflow: analysis, architecture, development,
review, and QA. Each role should verify against prior decisions before proceeding.
"""


def create_server(
    project: str | None = None,
    config_path: str = DEFAULT_CONFIG_PATH,
) -> FastMCP:
    """Create and configure the Memex MCP server."""
    project = project or os.environ.get(
        "MEMEX_PROJECT", os.path.basename(os.getcwd())
    )
    config = MemexConfig.load(config_path)

    mcp = FastMCP("memex", instructions=SERVER_INSTRUCTIONS)

    # Lazy-init store — created on first tool call so the server starts fast
    _store: MemoryStore | None = None
    _watcher: FileWatcher | None = None

    def get_store() -> MemoryStore:
        nonlocal _store, _watcher
        if _store is None:
            _store = MemoryStore(data_dir=config.data_dir, project=project)

            # If the project exists in config, reconcile and start watching
            if project in config.projects:
                proj_config = config.projects[project]
                _watcher = FileWatcher(store=_store, project_config=proj_config)
                logger.info("Reconciling files for project '%s'...", project)
                count = _watcher.reconcile()
                logger.info("Indexed %d files", count)
                _watcher.start()
                logger.info("File watcher started")
                atexit.register(_watcher.stop)

        return _store

    @mcp.tool()
    def store_memory(content: str, tags: list[str], source: str = "") -> str:
        """Store a piece of knowledge in the project's memory.

        Args:
            content: The knowledge to store
            tags: Domain labels like ["billing", "checkout", "pricing"]
            source: Where this knowledge came from (file path, "session observation", etc.)
        """
        store = get_store()
        mem_id = store.store(content=content, tags=tags, source=source)
        return f"Stored memory {mem_id}"

    @mcp.tool()
    def search_memories(query: str, tags: list[str] | None = None, limit: int = 5) -> str:
        """Search project memories using natural language.

        Args:
            query: Natural language search query
            tags: Optional tag filter — only return memories with at least one of these tags
            limit: Maximum number of results (default 5)
        """
        store = get_store()
        results = store.search(query=query, tags=tags, limit=limit)
        if not results:
            return "No matching memories found."

        lines = []
        for r in results:
            lines.append(
                f"[{r['score']:.2f}] ({', '.join(r['tags'])}) {r['content']}"
                + (f"\n  Source: {r['source']}" if r['source'] else "")
            )
        return "\n\n".join(lines)

    @mcp.tool()
    def delete_memory(memory_id: str) -> str:
        """Delete a specific memory by its ID.

        Args:
            memory_id: The ID of the memory to delete
        """
        store = get_store()
        store.delete(memory_id)
        return f"Deleted memory {memory_id}"

    @mcp.tool()
    def list_topics() -> str:
        """List all knowledge domains (tags) in the project with their counts."""
        store = get_store()
        topics = store.list_topics()
        if not topics:
            return "No topics found. The memory store is empty."

        lines = [f"  {tag}: {count} memories" for tag, count in sorted(topics.items(), key=lambda x: -x[1])]
        return "Topics:\n" + "\n".join(lines)

    @mcp.tool()
    def init_project(project_name: str, watch_paths: list[str] | None = None) -> str:
        """Initialize a new project in the Memex config.

        Args:
            project_name: Name for the project (used as the collection namespace)
            watch_paths: Optional list of directory paths to watch for file changes
        """
        config.add_project(project_name, watch_paths=watch_paths)
        config.save()
        return f"Project '{project_name}' initialized with watch paths: {watch_paths or []}. It will activate automatically when you work in a directory named '{project_name}'."

    @mcp.tool()
    def index_files() -> str:
        """Manually trigger re-indexing of all watched files for the current project."""
        get_store()
        if project not in config.projects:
            return f"Project '{project}' has no watch paths configured. Use init_project first."

        if _watcher:
            count = _watcher.reconcile()
        else:
            proj_config = config.projects[project]
            watcher = FileWatcher(store=_store, project_config=proj_config)
            count = watcher.reconcile()
        return f"Re-indexed {count} files."

    return mcp


def main() -> None:
    """Entry point for running the server."""
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
