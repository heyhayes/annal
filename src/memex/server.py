"""Memex MCP server — semantic memory for AI agent teams."""

from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from memex.config import MemexConfig, DEFAULT_CONFIG_PATH
from memex.store import MemoryStore
from memex.watcher import FileWatcher

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


def create_server(
    project: str | None = None,
    config_path: str = DEFAULT_CONFIG_PATH,
) -> FastMCP:
    """Create and configure the Memex MCP server."""
    project = project or os.environ.get("MEMEX_PROJECT", "default")
    config = MemexConfig.load(config_path)

    mcp = FastMCP("memex")

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
        return f"Project '{project_name}' initialized. Restart the server with MEMEX_PROJECT={project_name} to use it."

    @mcp.tool()
    def index_files() -> str:
        """Manually trigger re-indexing of all watched files for the current project."""
        store = get_store()
        if project not in config.projects:
            return f"Project '{project}' has no watch paths configured. Use init_project first."

        proj_config = config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        count = watcher.reconcile()
        return f"Re-indexed {count} files."

    return mcp


def main() -> None:
    """Entry point for running the server."""
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
