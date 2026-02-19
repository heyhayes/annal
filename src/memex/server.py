"""Memex MCP server — semantic memory for AI agent teams."""

from __future__ import annotations

import atexit
import logging
import sys

from mcp.server.fastmcp import FastMCP

from memex.config import MemexConfig, DEFAULT_CONFIG_PATH
from memex.pool import StorePool

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


SERVER_INSTRUCTIONS = """\
Memex is your persistent semantic memory. Memories you store survive across sessions.

## Project parameter
Every tool requires a `project` parameter. Pass the project name that matches
your current working context. The project name is typically the directory name
of the codebase you're working in (e.g. "classmanager", "memex").

If you're unsure which project to use, check your CLAUDE.md or environment
for a MEMEX_PROJECT reference, or use the directory name of the current codebase.

## First-time setup
If the current project has no watch paths configured, use `init_project` to set it up.
Pass the project name and a list of directory paths to watch for file indexing.
For example: init_project(project_name="myapp", watch_paths=["/home/user/projects/myapp"])

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
    config_path: str = DEFAULT_CONFIG_PATH,
) -> FastMCP:
    """Create and configure the Memex MCP server."""
    config = MemexConfig.load(config_path)

    mcp = FastMCP(
        "memex",
        instructions=SERVER_INSTRUCTIONS,
        host="127.0.0.1",
        port=config.port,
    )

    pool = StorePool(config)

    # Reconcile and start watchers for all configured projects
    for project_name in config.projects:
        pool.reconcile_project(project_name)
        pool.start_watcher(project_name)

    atexit.register(pool.shutdown)

    @mcp.tool()
    def store_memory(project: str, content: str, tags: list[str], source: str = "") -> str:
        """Store a piece of knowledge in a project's memory.

        Args:
            project: Project name (e.g. "classmanager", "memex")
            content: The knowledge to store
            tags: Domain labels like ["billing", "checkout", "pricing"]
            source: Where this knowledge came from (file path, "session observation", etc.)
        """
        store = pool.get_store(project)
        mem_id = store.store(content=content, tags=tags, source=source)
        return f"[{project}] Stored memory {mem_id}"

    @mcp.tool()
    def search_memories(project: str, query: str, tags: list[str] | None = None, limit: int = 5) -> str:
        """Search project memories using natural language.

        Args:
            project: Project name to search in
            query: Natural language search query
            tags: Optional tag filter — only return memories with at least one of these tags
            limit: Maximum number of results (default 5)
        """
        store = pool.get_store(project)
        results = store.search(query=query, tags=tags, limit=limit)
        if not results:
            return f"[{project}] No matching memories found."

        lines = []
        for r in results:
            lines.append(
                f"[{r['score']:.2f}] ({', '.join(r['tags'])}) {r['content']}"
                + (f"\n  Source: {r['source']}" if r['source'] else "")
            )
        return f"[{project}] {len(results)} results:\n\n" + "\n\n".join(lines)

    @mcp.tool()
    def delete_memory(project: str, memory_id: str) -> str:
        """Delete a specific memory by its ID.

        Args:
            project: Project name the memory belongs to
            memory_id: The ID of the memory to delete
        """
        store = pool.get_store(project)
        store.delete(memory_id)
        return f"[{project}] Deleted memory {memory_id}"

    @mcp.tool()
    def list_topics(project: str) -> str:
        """List all knowledge domains (tags) in a project with their counts.

        Args:
            project: Project name to list topics for
        """
        store = pool.get_store(project)
        topics = store.list_topics()
        if not topics:
            return f"[{project}] No topics found. The memory store is empty."

        lines = [f"  {tag}: {count} memories" for tag, count in sorted(topics.items(), key=lambda x: -x[1])]
        return f"[{project}] Topics:\n" + "\n".join(lines)

    @mcp.tool()
    def init_project(project_name: str, watch_paths: list[str] | None = None) -> str:
        """Initialize a new project in the Memex config.

        Args:
            project_name: Name for the project (used as the collection namespace)
            watch_paths: Optional list of directory paths to watch for file changes
        """
        config.add_project(project_name, watch_paths=watch_paths)
        config.save()
        if watch_paths:
            pool.reconcile_project(project_name)
            pool.start_watcher(project_name)
        return f"Project '{project_name}' initialized with watch paths: {watch_paths or []}."

    @mcp.tool()
    def index_files(project: str) -> str:
        """Manually trigger re-indexing of all watched files for a project.

        Args:
            project: Project name to re-index
        """
        if project not in config.projects:
            return f"[{project}] No watch paths configured. Use init_project first."

        count = pool.reconcile_project(project)
        return f"[{project}] Re-indexed {count} files."

    return mcp


def main() -> None:
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Memex MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to config file",
    )
    args = parser.parse_args()

    mcp = create_server(config_path=args.config)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
