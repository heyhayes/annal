"""Annal MCP server — semantic memory for AI agent teams."""

from __future__ import annotations

import atexit
import json
import logging
import sys
import threading
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from annal.config import AnnalConfig, DEFAULT_CONFIG_PATH
from annal.events import event_bus, Event
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
Search annal at these moments — prefer summary mode for most searches:
- Session start: load context for the current project and task area
- Questions about prior work: "what did we decide about X?", "have we seen this before?"
- Before proposing architectural changes: check for prior decisions in the same domain
- When a bug feels familiar: search for prior root causes and fixes
- Before starting a new feature: look for related specs, patterns, or preferences

## Search modes
- `mode="summary"` (recommended): returns first 200 chars of content with full metadata.
  Enough to judge relevance without a follow-up call. Use this for most searches.
- `mode="probe"`: compact one-line summaries with scores. Use when scanning large result
  sets and context window is tight. Follow up with `expand_memories` for details.
- `mode="full"`: complete content. Use when you already know you need the full text.

## Searching
Use search_memories with natural language — it uses semantic similarity, not keyword
matching. Use mode="probe" to scan results cheaply, then expand_memories for details.
Filter by tags to narrow results when the memory store grows large.

## Temporal filtering
Scope searches by date using `after` and `before` (ISO 8601 dates):
  search_memories(query="auth decision", after="2026-02-01", before="2026-02-28")

## Cross-project search
Search across multiple projects to find knowledge from other codebases:
  search_memories(query="auth decision", project="current", projects=["other_project"])
Use projects="*" to search all configured projects at once. Results are merged
by relevance score. Each result includes the source project name.

## Structured output
For programmatic access, use output="json" to get structured results:
  search_memories(query="...", output="json")
Returns {"results": [...], "meta": {...}} instead of formatted text.
Also available on expand_memories(memory_ids=[...], output="json").

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

### Retagging memories

Use `retag_memory` to fix or refine tags after storage without changing content.
Supports `add_tags`, `remove_tags` (incremental), or `set_tags` (full replace).
  retag_memory(project="myapp", memory_id="...", add_tags=["billing"], remove_tags=["misc"])

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
    pool: StorePool | None = None,
    config: AnnalConfig | None = None,
) -> tuple[FastMCP, StorePool]:
    """Create and configure the Annal MCP server."""
    if config is None:
        config = AnnalConfig.load(config_path)

    mcp = FastMCP(
        "annal",
        instructions=SERVER_INSTRUCTIONS,
        host="127.0.0.1",
        port=config.port,
    )

    if pool is None:
        pool = StorePool(config)

    # Reconcile and start watchers in a background thread so the HTTP
    # server can start accepting connections immediately
    def _startup_reconcile() -> None:
        for project_name in config.projects:
            try:
                logger.info("Reconciling project '%s'...", project_name)
                event_bus.push(Event(type="index_started", project=project_name))

                def _make_complete_callback(pname: str):
                    def on_complete(count: int) -> None:
                        event_bus.push(Event(type="index_complete", project=pname, detail=f"{count} files"))
                        pool.start_watcher(pname)
                    return on_complete

                pool.reconcile_project_async(
                    project_name,
                    on_complete=_make_complete_callback(project_name),
                )
            except Exception:
                logger.exception("Startup reconciliation failed for project '%s'", project_name)
                event_bus.push(Event(type="index_failed", project=project_name, detail="startup reconciliation failed"))
        logger.info("Startup reconciliation dispatched")

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
        existing = store.search(query=content, limit=10)
        for candidate in existing:
            if candidate["chunk_type"] != "agent-memory":
                continue
            if candidate["score"] > 0.95:
                return (
                    f"[{project}] Skipped — similar memory already exists "
                    f"(score: {candidate['score']:.2f}, ID: {candidate['id']})"
                )

        mem_id = store.store(content=content, tags=tags, source=source)
        event_bus.push(Event(type="memory_stored", project=project, detail=mem_id))
        return f"[{project}] Stored memory {mem_id}"

    @mcp.tool()
    def search_memories(
        project: str,
        query: str,
        tags: list[str] | str | None = None,
        limit: int = 5,
        mode: str = "summary",
        min_score: float = 0.0,
        after: str | None = None,
        before: str | None = None,
        output: str = "text",
        projects: list[str] | str | None = None,
    ) -> str:
        """Search project memories using natural language.

        Args:
            project: Project name to search in
            query: Natural language search query
            tags: Optional tag filter — only return memories with at least one of these tags
            limit: Maximum number of results (default 5)
            mode: "summary" (default) returns first 200 chars with full metadata — enough
                  to judge relevance without expanding; "full" returns complete content;
                  "probe" returns compact one-line summaries for scanning large result sets
            min_score: Minimum similarity score to include (default 0.0, suppresses negative scores)
            after: Optional ISO 8601 date — only return memories created after this date
            before: Optional ISO 8601 date — only return memories created before this date
            output: "text" (default) for formatted text, "json" for structured JSON
            projects: Optional list of project names to search across, or "*" for all
                      configured projects. Results are merged by score. Each result includes
                      a project field. When omitted, searches only the primary project.
        """

        tags = _normalize_tags(tags)

        # Determine project list for search
        # Normalize: ["*"] and "*" both mean "all projects"
        if projects == "*" or projects == ["*"]:
            search_projects = list(config.projects.keys())
            if project not in search_projects:
                search_projects.append(project)
        elif projects:
            search_projects = list(projects) if isinstance(projects, list) else [projects]
            if project not in search_projects:
                search_projects.insert(0, project)
        else:
            search_projects = [project]

        # Fan-out search across projects
        all_results = []
        for proj_name in search_projects:
            store = pool.get_store(proj_name)
            try:
                proj_results = store.search(query=query, tags=tags, limit=limit, after=after, before=before)
            except ValueError as e:
                return f"[{project}] Error: {e}"
            for r in proj_results:
                r["project"] = proj_name
            all_results.extend(proj_results)

        # Merge by score, take top limit
        all_results.sort(key=lambda r: r["score"], reverse=True)
        results = all_results[:limit]

        is_cross_project = len(search_projects) > 1

        empty_meta = {"query": query, "mode": mode, "project": project, "total": 0, "returned": 0}
        if is_cross_project:
            empty_meta["projects_searched"] = search_projects
        empty_json = json.dumps({"results": [], "meta": empty_meta})

        if not results:
            return empty_json if output == "json" else f"[{project}] No matching memories found."

        if not tags:
            results = [r for r in results if r["score"] >= min_score]
        if not results:
            return empty_json if output == "json" else f"[{project}] No matching memories found."

        if output == "json":
            json_results = []
            for r in results:
                entry = {
                    "id": r["id"],
                    "tags": r["tags"],
                    "score": round(r["score"], 4),
                    "source": r["source"],
                    "created_at": r["created_at"],
                    "updated_at": r.get("updated_at", ""),
                }
                if is_cross_project:
                    entry["project"] = r["project"]
                if mode in ("probe", "summary"):
                    entry["content_preview"] = r["content"][:200]
                else:
                    entry["content"] = r["content"]
                json_results.append(entry)
            meta = {
                "query": query,
                "mode": mode,
                "project": project,
                "total": len(results),
                "returned": len(results),
            }
            if is_cross_project:
                meta["projects_searched"] = search_projects
            return json.dumps({"results": json_results, "meta": meta})

        lines = []
        for r in results:
            proj_label = f"({r['project']}) " if is_cross_project else ""
            if mode == "probe":
                content = r["content"]
                first_line = content.split("\n", 1)[0]
                snippet = first_line[:150]
                if len(first_line) > 150:
                    snippet += "…"
                date = (r.get("updated_at") or r["created_at"] or "")[:10] or "unknown"
                source_label = r["source"] or "session observation"
                lines.append(
                    f'{proj_label}[{r["score"]:.2f}] ({", ".join(r["tags"])}) "{snippet}"'
                    f"\n  Source: {source_label} | {date} | ID: {r['id']}"
                )
            elif mode == "summary":
                content = r["content"]
                preview = content[:200]
                if len(content) > 200:
                    preview += "…"
                date = (r.get("updated_at") or r["created_at"] or "")[:10] or "unknown"
                source_label = r["source"] or "session observation"
                entry = f'{proj_label}[{r["score"]:.2f}] ({", ".join(r["tags"])}) {preview}'
                entry += f"\n  Source: {source_label} | {date} | ID: {r['id']}"
                lines.append(entry)
            else:
                entry = f"{proj_label}[{r['score']:.2f}] ({', '.join(r['tags'])}) {r['content']}"
                if r["source"]:
                    entry += f"\n  Source: {r['source']}"
                if r.get("updated_at"):
                    entry += f"\n  Updated: {r['updated_at']}"
                entry += f"\n  ID: {r['id']}"
                lines.append(entry)
        return f"[{project}] {len(results)} results:\n\n" + "\n\n".join(lines)

    @mcp.tool()
    def expand_memories(project: str, memory_ids: list[str], output: str = "text") -> str:
        """Retrieve full content for specific memories by ID.

        Use after a probe-mode search to fetch details for relevant results.

        Args:
            project: Project name the memories belong to
            memory_ids: List of memory IDs to expand
            output: "text" (default) for formatted text, "json" for structured JSON
        """

        store = pool.get_store(project)
        results = store.get_by_ids(memory_ids)
        if not results:
            if output == "json":
                return json.dumps({"results": []})
            return f"[{project}] No memories found for the given IDs."

        if output == "json":
            json_results = []
            for r in results:
                json_results.append({
                    "id": r["id"],
                    "content": r["content"],
                    "tags": r["tags"],
                    "source": r["source"],
                    "created_at": r["created_at"],
                    "updated_at": r.get("updated_at", ""),
                })
            return json.dumps({"results": json_results})

        lines = []
        for r in results:
            entry = f"({', '.join(r['tags'])}) {r['content']}"
            if r["source"]:
                entry += f"\n  Source: {r['source']}"
            if r.get("updated_at"):
                entry += f"\n  Updated: {r['updated_at']}"
            entry += f"\n  ID: {r['id']}"
            lines.append(entry)
        return f"[{project}] {len(results)} memories:\n\n" + "\n\n".join(lines)

    @mcp.tool()
    def delete_memory(project: str, memory_id: str) -> str:
        """Delete a specific memory by its ID.

        Args:
            project: Project name the memory belongs to
            memory_id: The ID of the memory to delete
        """
        store = pool.get_store(project)
        if not store.get_by_ids([memory_id]):
            return f"[{project}] Memory {memory_id} not found."
        store.delete(memory_id)
        event_bus.push(Event(type="memory_deleted", project=project, detail=memory_id))
        return f"[{project}] Deleted memory {memory_id}"

    @mcp.tool()
    def update_memory(
        project: str,
        memory_id: str,
        content: str | None = None,
        tags: list[str] | str | None = None,
        source: str | None = None,
    ) -> str:
        """Update an existing memory's content, tags, or source without losing its ID.

        Args:
            project: Project name the memory belongs to
            memory_id: The ID of the memory to update
            content: New content (omit to keep existing)
            tags: New tags (omit to keep existing)
            source: New source (omit to keep existing)
        """
        if content is None and tags is None and source is None:
            return f"[{project}] Nothing to update — provide content, tags, or source."
        store = pool.get_store(project)
        normalized_tags = _normalize_tags(tags) if tags is not None else None
        try:
            store.update(memory_id, content=content, tags=normalized_tags, source=source)
        except ValueError:
            return f"[{project}] Memory {memory_id} not found."
        event_bus.push(Event(type="memory_updated", project=project, detail=memory_id))
        return f"[{project}] Updated memory {memory_id}"

    @mcp.tool()
    def retag_memory(
        project: str,
        memory_id: str,
        add_tags: list[str] | str | None = None,
        remove_tags: list[str] | str | None = None,
        set_tags: list[str] | str | None = None,
    ) -> str:
        """Modify tags on an existing memory without changing its content.

        Use add_tags/remove_tags for incremental edits, or set_tags to replace
        all tags at once. Cannot mix set_tags with add/remove.

        Args:
            project: Project name the memory belongs to
            memory_id: The ID of the memory to retag
            add_tags: Tags to add (str or list)
            remove_tags: Tags to remove (str or list)
            set_tags: Replace all tags with these (str or list)
        """
        add = _normalize_tags(add_tags)
        remove = _normalize_tags(remove_tags)
        replace = _normalize_tags(set_tags)
        store = pool.get_store(project)
        try:
            final = store.retag(
                memory_id,
                add_tags=add,
                remove_tags=remove,
                set_tags=replace,
            )
        except ValueError as e:
            return f"[{project}] Error: {e}"
        event_bus.push(Event(type="memory_updated", project=project, detail=memory_id))
        return f"[{project}] Retagged memory {memory_id} → [{', '.join(final)}]"

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
        proj = config.projects[project_name]
        if watch_paths:
            def on_progress(count: int) -> None:
                event_bus.push(Event(type="index_progress", project=project_name, detail=f"{count} files"))

            def on_complete(count: int) -> None:
                pool.start_watcher(project_name)
                event_bus.push(Event(type="index_complete", project=project_name, detail=f"{count} files"))

            event_bus.push(Event(type="index_started", project=project_name))
            pool.reconcile_project_async(
                project_name,
                on_progress=on_progress,
                on_complete=on_complete,
            )
            return (
                f"Project '{project_name}' initialized. "
                f"Indexing in progress — use index_status to check progress. "
                f"Patterns: {proj.watch_patterns}, excludes: {proj.watch_exclude}."
            )
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

        if pool.is_indexing(project):
            return f"[{project}] Indexing already in progress. Use index_status to check progress."

        def on_progress(count: int) -> None:
            event_bus.push(Event(type="index_progress", project=project, detail=f"{count} files"))

        def on_complete(count: int) -> None:
            event_bus.push(Event(type="index_complete", project=project, detail=f"{count} files"))

        event_bus.push(Event(type="index_started", project=project))
        pool.reconcile_project_async(
            project,
            on_progress=on_progress,
            on_complete=on_complete,
            clear_first=True,
        )
        return f"[{project}] Re-indexing started in background. Use index_status to check progress."

    @mcp.tool()
    def index_status(project: str) -> str:
        """Check indexing status and collection diagnostics for a project.

        Args:
            project: Project name to check
        """
        store = pool.get_store(project)
        total = store.count()
        stats = store.stats()
        indexing = pool.is_indexing(project)
        last = pool.get_last_reconcile(project)

        lines = [f"[{project}] Status:"]
        if indexing:
            started = pool.get_index_started(project)
            if started:
                elapsed = datetime.now(timezone.utc) - started
                mins, secs = divmod(int(elapsed.total_seconds()), 60)
                lines.append(f"  Indexing: IN PROGRESS (running for {mins}m {secs}s)")
            else:
                lines.append("  Indexing: IN PROGRESS")
        else:
            lines.append("  Indexing: idle")
        lines.append(f"  Total chunks: {total}")
        lines.append(f"  File-indexed: {stats['by_type'].get('file-indexed', 0)}")
        lines.append(f"  Agent memories: {stats['by_type'].get('agent-memory', 0)}")
        if last:
            lines.append(f"  Last reconcile: {last['timestamp']} ({last['file_count']} files)")
        else:
            lines.append("  Last reconcile: never")
        return "\n".join(lines)

    return mcp, pool


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


def _add_serve_args(parser: "argparse.ArgumentParser") -> None:
    """Add --transport, --config, --no-dashboard flags to a parser."""
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


def _make_backend(name: str, config: AnnalConfig, collection: str, dimension: int):
    """Create a backend instance by name using config settings."""
    backend_config = config.storage.backends.get(name, {})
    if name == "chromadb":
        from annal.backends.chromadb import ChromaBackend
        path = backend_config.get("path", config.data_dir)
        return ChromaBackend(path=path, collection_name=collection, dimension=dimension)
    if name == "qdrant":
        from annal.backends.qdrant import QdrantBackend
        url = backend_config.get("url", "http://localhost:6333")
        hybrid = backend_config.get("hybrid", True)
        return QdrantBackend(url=url, collection_name=collection, dimension=dimension, hybrid=hybrid)
    raise ValueError(f"Unknown backend: {name}")


def _run_export(config: AnnalConfig, project: str) -> None:
    """Export all memories for a project to JSONL on stdout."""
    from annal.embedder import OnnxEmbedder

    embedder = OnnxEmbedder()
    collection = f"annal_{project}"
    backend = _make_backend(config.storage.backend, config, collection, embedder.dimension)

    batch_size = 500
    offset = 0
    count = 0
    while True:
        results, total = backend.scan(offset=offset, limit=batch_size)
        if not results:
            break
        for r in results:
            record = {"id": r.id, "text": r.text, "metadata": r.metadata}
            sys.stdout.write(json.dumps(record) + "\n")
            count += 1
        offset += len(results)
        sys.stderr.write(f"\rExported {count}/{total} records")
    sys.stderr.write(f"\rExported {count} records total\n")


def _run_import(config: AnnalConfig, project: str, filepath: str) -> None:
    """Import memories from a JSONL file into a project."""
    from annal.embedder import OnnxEmbedder

    embedder = OnnxEmbedder()
    collection = f"annal_{project}"
    backend = _make_backend(config.storage.backend, config, collection, embedder.dimension)

    batch_texts: list[str] = []
    batch_records: list[dict] = []
    count = 0

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            batch_texts.append(record["text"])
            batch_records.append(record)

            if len(batch_texts) >= 100:
                _import_batch(backend, embedder, batch_records, batch_texts)
                count += len(batch_texts)
                sys.stderr.write(f"\rImported {count} records")
                batch_texts.clear()
                batch_records.clear()

    if batch_texts:
        _import_batch(backend, embedder, batch_records, batch_texts)
        count += len(batch_texts)

    sys.stderr.write(f"\rImported {count} records total\n")


def _import_batch(backend, embedder, records: list[dict], texts: list[str]) -> None:
    """Embed and insert a batch of records."""
    embeddings = embedder.embed_batch(texts)
    for record, embedding in zip(records, embeddings):
        backend.insert(record["id"], record["text"], embedding, record["metadata"])


def main() -> None:
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Annal semantic memory server")
    # Add serve flags to top-level parser for backward compat (bare `annal --transport ...`)
    _add_serve_args(parser)

    subparsers = parser.add_subparsers(dest="command")

    # serve subcommand (also works with no subcommand)
    serve_parser = subparsers.add_parser("serve", help="Run the MCP server")
    _add_serve_args(serve_parser)

    # install subcommand
    subparsers.add_parser("install", help="Install Annal service and configure MCP clients")

    # uninstall subcommand
    subparsers.add_parser("uninstall", help="Remove Annal service and MCP client configs")

    # migrate subcommand
    migrate_parser = subparsers.add_parser("migrate", help="Migrate data between backends")
    migrate_parser.add_argument("--from", dest="from_backend", required=True, help="Source backend (chromadb or qdrant)")
    migrate_parser.add_argument("--to", dest="to_backend", required=True, help="Destination backend (chromadb or qdrant)")
    migrate_parser.add_argument("--project", required=True, help="Project to migrate")
    migrate_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")

    # export subcommand
    export_parser = subparsers.add_parser("export", help="Export project memories to JSONL (stdout)")
    export_parser.add_argument("--project", required=True, help="Project to export")
    export_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")

    # import subcommand
    import_parser = subparsers.add_parser("import", help="Import memories from JSONL file")
    import_parser.add_argument("--project", required=True, help="Project to import into")
    import_parser.add_argument("file", help="Path to JSONL file")
    import_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config file")

    args = parser.parse_args()

    if args.command == "install":
        from annal.cli import install
        print(install())
        return

    if args.command == "uninstall":
        from annal.cli import uninstall
        print(uninstall())
        return

    if args.command == "migrate":
        from annal.embedder import OnnxEmbedder
        from annal.migrate import migrate

        config = AnnalConfig.load(args.config)
        embedder = OnnxEmbedder()
        collection = f"annal_{args.project}"

        src = _make_backend(args.from_backend, config, collection, embedder.dimension)
        dst = _make_backend(args.to_backend, config, collection, embedder.dimension)
        count = migrate(src, dst, embedder)
        print(f"Migrated {count} documents from {args.from_backend} to {args.to_backend}")
        return

    if args.command == "export":
        config = AnnalConfig.load(args.config)
        _run_export(config, args.project)
        return

    if args.command == "import":
        config = AnnalConfig.load(args.config)
        _run_import(config, args.project, args.file)
        return

    # Default: serve (handles both `annal serve` and bare `annal` with old flags)
    transport = getattr(args, "transport", "stdio")
    config_path = getattr(args, "config", DEFAULT_CONFIG_PATH)
    no_dashboard = getattr(args, "no_dashboard", False)

    config = AnnalConfig.load(config_path)
    pool = StorePool(config)
    mcp, _ = create_server(config_path=config_path, pool=pool, config=config)

    if not no_dashboard:
        # In stdio mode the MCP port is free; in HTTP mode use port+1
        dashboard_port = config.port if transport == "stdio" else config.port + 1
        _start_dashboard(pool, config, port=dashboard_port)

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
