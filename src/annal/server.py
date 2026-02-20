"""Annal MCP server — semantic memory for AI agent teams."""

from __future__ import annotations

import atexit
import logging
import sys
import threading

from mcp.server.fastmcp import FastMCP

from annal.config import AnnalConfig, DEFAULT_CONFIG_PATH
from annal.pool import StorePool

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


def _normalize_tags(tags: list[str] | str | None) -> list[str] | None:
    """Normalize tags input: accept string or list, lowercase, strip, deduplicate."""
    if tags is None:
        return None
    if isinstance(tags, str):
        tags = [tags]
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


SERVER_INSTRUCTIONS = """\
Annal is your persistent semantic memory. Memories you store survive across sessions.

## Project parameter
Every tool requires a `project` parameter. Pass the project name that matches
your current working context. The project name is typically the directory name
of the codebase you're working in (e.g. "classmanager", "annal").

If you're unsure which project to use, check your CLAUDE.md or environment
for an ANNAL_PROJECT reference, or use the directory name of the current codebase.

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

## When to search
Search annal at these moments — prefer probe mode to keep context lean:
- Session start: load context for the current project and task area
- Questions about prior work: "what did we decide about X?", "have we seen this before?"
- Before proposing architectural changes: check for prior decisions in the same domain
- When a bug feels familiar: search for prior root causes and fixes
- Before starting a new feature: look for related specs, patterns, or preferences

## Searching
Use search_memories with natural language — it uses semantic similarity, not keyword
matching. Use mode="probe" to scan results cheaply, then expand_memories for details.
Filter by tags to narrow results when the memory store grows large.

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

Before accepting, proposing, or implementing a design decision, search annal
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
    """Create and configure the Annal MCP server."""
    config = AnnalConfig.load(config_path)

    mcp = FastMCP(
        "annal",
        instructions=SERVER_INSTRUCTIONS,
        host="127.0.0.1",
        port=config.port,
    )

    pool = StorePool(config)

    # Reconcile and start watchers in a background thread so the HTTP
    # server can start accepting connections immediately
    def _startup_reconcile() -> None:
        for project_name in config.projects:
            logger.info("Reconciling project '%s'...", project_name)
            pool.reconcile_project(project_name)
            pool.start_watcher(project_name)
        logger.info("Startup reconciliation complete")

    threading.Thread(target=_startup_reconcile, daemon=True).start()

    atexit.register(pool.shutdown)

    @mcp.tool()
    def store_memory(project: str, content: str, tags: list[str] | str, source: str = "") -> str:
        """Store a piece of knowledge in a project's memory.

        Args:
            project: Project name (e.g. "classmanager", "annal")
            content: The knowledge to store
            tags: Domain labels like ["billing", "checkout", "pricing"]
            source: Where this knowledge came from (file path, "session observation", etc.)
        """
        tags = _normalize_tags(tags)
        store = pool.get_store(project)

        # Check for near-duplicate before storing — over-fetch so file-indexed
        # chunks at the top don't hide a real agent-memory duplicate further down
        existing = store.search(query=content, limit=5)
        for candidate in existing:
            if candidate["chunk_type"] != "agent-memory":
                continue
            if candidate["score"] > 0.95:
                return (
                    f"[{project}] Skipped — similar memory already exists "
                    f"(score: {candidate['score']:.2f}, ID: {candidate['id']})"
                )
            break  # first agent-memory was below threshold, no need to check worse ones

        mem_id = store.store(content=content, tags=tags, source=source)
        return f"[{project}] Stored memory {mem_id}"

    @mcp.tool()
    def search_memories(
        project: str,
        query: str,
        tags: list[str] | str | None = None,
        limit: int = 5,
        mode: str = "full",
    ) -> str:
        """Search project memories using natural language.

        Args:
            project: Project name to search in
            query: Natural language search query
            tags: Optional tag filter — only return memories with at least one of these tags
            limit: Maximum number of results (default 5)
            mode: "full" (default) returns complete content; "probe" returns compact
                  summaries — use probe to scan relevance, then expand_memories for details
        """
        tags = _normalize_tags(tags)
        store = pool.get_store(project)
        results = store.search(query=query, tags=tags, limit=limit)
        if not results:
            return f"[{project}] No matching memories found."

        lines = []
        for r in results:
            if mode == "probe":
                # Truncate to first newline or ~150 chars, whichever is shorter
                content = r["content"]
                first_line = content.split("\n", 1)[0]
                snippet = first_line[:150]
                if len(first_line) > 150:
                    snippet += "…"
                # Extract date portion from ISO created_at
                date = r["created_at"][:10] if r["created_at"] else "unknown"
                source_label = r["source"] or "session observation"
                lines.append(
                    f'[{r["score"]:.2f}] ({", ".join(r["tags"])}) "{snippet}"'
                    f"\n  Source: {source_label} | {date} | ID: {r['id']}"
                )
            else:
                lines.append(
                    f"[{r['score']:.2f}] ({', '.join(r['tags'])}) {r['content']}"
                    + (f"\n  Source: {r['source']}" if r["source"] else "")
                    + f"\n  ID: {r['id']}"
                )
        return f"[{project}] {len(results)} results:\n\n" + "\n\n".join(lines)

    @mcp.tool()
    def expand_memories(project: str, memory_ids: list[str]) -> str:
        """Retrieve full content for specific memories by ID.

        Use after a probe-mode search to fetch details for relevant results.

        Args:
            project: Project name the memories belong to
            memory_ids: List of memory IDs to expand
        """
        store = pool.get_store(project)
        results = store.get_by_ids(memory_ids)
        if not results:
            return f"[{project}] No memories found for the given IDs."

        lines = []
        for r in results:
            lines.append(
                f"({', '.join(r['tags'])}) {r['content']}"
                + (f"\n  Source: {r['source']}" if r["source"] else "")
                + f"\n  ID: {r['id']}"
            )
        return f"[{project}] {len(results)} memories:\n\n" + "\n\n".join(lines)

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
    def init_project(
        project_name: str,
        watch_paths: list[str] | None = None,
        watch_patterns: list[str] | None = None,
        watch_exclude: list[str] | None = None,
    ) -> str:
        """Initialize a new project in the Annal config.

        Args:
            project_name: Name for the project (used as the collection namespace)
            watch_paths: Optional list of directory paths to watch for file changes
            watch_patterns: Optional glob patterns for files to index (default: markdown, yaml, toml, json).
                            Replaces defaults entirely when provided.
            watch_exclude: Optional glob patterns for paths to exclude (default: node_modules, vendor,
                           .git, .venv, __pycache__, dist, build — matched at any depth).
                           Replaces defaults entirely when provided.
        """
        config.add_project(
            project_name,
            watch_paths=watch_paths,
            watch_patterns=watch_patterns,
            watch_exclude=watch_exclude,
        )
        config.save()
        if watch_paths:
            pool.reconcile_project(project_name)
            pool.start_watcher(project_name)
        proj = config.projects[project_name]
        return (
            f"Project '{project_name}' initialized with "
            f"watch paths: {proj.watch_paths}, "
            f"patterns: {proj.watch_patterns}, "
            f"excludes: {proj.watch_exclude}."
        )

    @mcp.tool()
    def index_files(project: str) -> str:
        """Full re-index: clears all file-indexed chunks, then re-indexes from scratch.

        Use after changing watch_exclude or watch_patterns to remove stale chunks
        from previously-included paths (e.g. vendor directories).

        Args:
            project: Project name to re-index
        """
        if project not in config.projects:
            return f"[{project}] No watch paths configured. Use init_project first."

        store = pool.get_store(project)
        store.delete_by_source("file:")
        count = pool.reconcile_project(project)
        return f"[{project}] Cleared old file chunks and re-indexed {count} files."

    return mcp


def _start_dashboard(pool: StorePool, config: AnnalConfig, port: int) -> None:
    """Start the dashboard web server on a background thread."""
    import asyncio

    import uvicorn

    from annal.dashboard import create_dashboard_app

    app = create_dashboard_app(pool, config)
    uv_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(uv_config)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("Dashboard available at http://127.0.0.1:%d", port)


def main() -> None:
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Annal MCP server")
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
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable the dashboard web server",
    )
    args = parser.parse_args()

    config = AnnalConfig.load(args.config)
    mcp = create_server(config_path=args.config)

    if not args.no_dashboard:
        pool = StorePool(config)
        # In stdio mode the MCP port is free; in HTTP mode use port+1
        dashboard_port = config.port if args.transport == "stdio" else config.port + 1
        _start_dashboard(pool, config, port=dashboard_port)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
