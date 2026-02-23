"""Dashboard route handlers."""

from __future__ import annotations

import asyncio
import math
import queue
from datetime import datetime, timedelta, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from annal.config import AnnalConfig
from annal.events import event_bus
from annal.pool import StorePool

TEMPLATES_DIR = Path(__file__).parent / "templates"

PAGE_SIZE = 50


def _annotate_stale(memories: list[dict], max_age_days: int = 60) -> None:
    """Mark each memory dict with a 'stale' boolean for template rendering."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    for mem in memories:
        if mem.get("chunk_type") != "agent-memory":
            mem["stale"] = False
            continue
        last = mem.get("last_accessed_at")
        if last is None:
            created = mem.get("created_at", "")
            mem["stale"] = bool(created and created < cutoff)
        else:
            mem["stale"] = last < cutoff


def create_routes(pool: StorePool, config: AnnalConfig) -> list[Route]:
    """Create dashboard route list with access to the store pool and config."""
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    async def dashboard(request: Request) -> Response:
        """System dashboard landing page."""
        total_memories = 0
        total_agent = 0
        total_stale = 0
        non_empty_projects = 0

        for name in sorted(config.projects):
            store = pool.get_store(name)
            stats = store.stats()
            if stats["total"] == 0:
                continue
            non_empty_projects += 1
            total_memories += stats["total"]
            total_agent += stats["by_type"].get("agent-memory", 0)
            total_stale += stats.get("stale_count", 0) + stats.get("never_accessed_count", 0)

        # Check if any project is currently indexing
        indexing = any(pool.is_indexing(name) for name in config.projects)

        recent_events = event_bus.recent(limit=20)

        return templates.TemplateResponse(request, "dashboard.html", {
            "total_memories": total_memories,
            "total_projects": non_empty_projects,
            "total_agent": total_agent,
            "total_stale": total_stale,
            "indexing": indexing,
            "recent_events": recent_events,
        })

    async def projects_page(request: Request) -> Response:
        """Project overview with stats cards."""
        project_stats = []
        for name in sorted(config.projects):
            store = pool.get_store(name)
            stats = store.stats()
            top_tags = sorted(stats["by_tag"].items(), key=lambda x: -x[1])[:10]
            project_stats.append({
                "name": name,
                "total": stats["total"],
                "file_indexed": stats["by_type"].get("file-indexed", 0),
                "agent_memory": stats["by_type"].get("agent-memory", 0),
                "top_tags": top_tags,
                "stale": stats.get("stale_count", 0),
                "never_accessed": stats.get("never_accessed_count", 0),
            })
        return templates.TemplateResponse(request, "index.html", {
            "project_stats": project_stats,
        })

    def _parse_memory_params(request: Request) -> dict:
        """Extract common filter/pagination params from a request."""
        params = request.query_params
        projects = params.get("projects", "")
        project = params.get("project", "")
        chunk_type = params.get("type", "")
        source_prefix = params.get("source", "")
        tags_raw = params.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        try:
            page = int(params.get("page", "1"))
        except (ValueError, TypeError):
            page = 1
        q = params.get("q", "")
        superseded = params.get("superseded", "") == "1"
        stale = params.get("stale", "")
        return {
            "project": project,
            "projects": projects,
            "cross_project": projects == "*",
            "chunk_type": chunk_type or None,
            "source_prefix": source_prefix or None,
            "tags": tags or None,
            "page": page,
            "q": q,
            "include_superseded": superseded,
            "stale": stale,
        }

    def _fetch_memories(pool: StorePool, params: dict) -> dict:
        """Fetch memories using either search or browse, return template context."""
        project = params["project"]
        store = pool.get_store(project)
        page = params["page"]
        offset = (page - 1) * PAGE_SIZE

        if params.get("stale") == "1" and not params["q"]:
            # Stale filter: get all stale IDs, paginate manually
            stale_result = store.find_stale()
            stale_id_set = set(stale_result["stale_ids"])
            never_id_set = set(stale_result["never_accessed_ids"])
            all_ids = stale_result["stale_ids"] + stale_result["never_accessed_ids"]
            total = len(all_ids)
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            page_ids = all_ids[offset:offset + PAGE_SIZE]
            memories = store.get_by_ids(page_ids, track_hits=False) if page_ids else []
            # Annotate from find_stale result directly — get_by_ids updates
            # last_accessed_at as a side effect, so _annotate_stale would
            # see them as freshly accessed and miss them.
            for mem in memories:
                if mem["id"] in never_id_set:
                    mem["stale"] = True
                    mem.pop("last_accessed_at", None)
                elif mem["id"] in stale_id_set:
                    mem["stale"] = True
                else:
                    mem["stale"] = False
        elif params["q"]:
            # Search mode: semantic search, then apply filters client-side
            results = store.search(
                query=params["q"],
                limit=PAGE_SIZE,
                tags=params["tags"],
                include_superseded=params.get("include_superseded", False),
            )
            total = len(results)
            memories = results
            total_pages = 1  # search doesn't paginate
            _annotate_stale(memories)
        else:
            memories, total = store.browse(
                offset=offset,
                limit=PAGE_SIZE,
                chunk_type=params["chunk_type"],
                source_prefix=params["source_prefix"],
                tags=params["tags"],
                include_superseded=params.get("include_superseded", False),
            )
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            _annotate_stale(memories)

        return {
            "memories": memories,
            "project": project,
            "cross_project": False,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "chunk_type": params["chunk_type"] or "",
            "source": params["source_prefix"] or "",
            "tags": ",".join(params["tags"]) if params["tags"] else "",
            "q": params["q"],
            "superseded": "1" if params.get("include_superseded") else "",
            "stale": params.get("stale", ""),
        }

    def _fetch_cross_project(pool: StorePool, params: dict) -> dict:
        """Search across all projects, merge results by score."""
        query = params["q"]
        tags = params["tags"]
        include_superseded = params.get("include_superseded", False)
        all_results = []
        if query:
            for name in sorted(config.projects):
                store = pool.get_store(name)
                results = store.search(query=query, limit=PAGE_SIZE, tags=tags, include_superseded=include_superseded)
                for mem in results:
                    mem["project"] = name
                all_results.extend(results)
            # Sort by distance (lower = more similar) if present, else keep order
            all_results.sort(key=lambda m: m.get("distance", 1.0))
            all_results = all_results[:PAGE_SIZE]
        _annotate_stale(all_results)
        return {
            "memories": all_results,
            "project": "",
            "cross_project": True,
            "page": 1,
            "total_pages": 1,
            "total": len(all_results),
            "chunk_type": "",
            "source": "",
            "tags": ",".join(tags) if tags else "",
            "q": query,
            "superseded": "1" if include_superseded else "",
            "stale": "",
        }

    async def memories(request: Request) -> Response:
        """Full memories browse/search page."""
        params = _parse_memory_params(request)
        if params["cross_project"]:
            ctx = _fetch_cross_project(pool, params)
        elif params["project"]:
            ctx = _fetch_memories(pool, params)
        else:
            return HTMLResponse("Missing project parameter", status_code=400)
        return templates.TemplateResponse(request, "memories.html", ctx)

    async def memories_table(request: Request) -> Response:
        """HTMX partial: just the table body rows."""
        params = _parse_memory_params(request)
        if params["cross_project"]:
            ctx = _fetch_cross_project(pool, params)
        elif params["project"]:
            ctx = _fetch_memories(pool, params)
        else:
            return HTMLResponse("Missing project parameter", status_code=400)
        return templates.TemplateResponse(request, "_table.html", ctx)

    async def delete_memory(request: Request) -> Response:
        """Delete a single memory by ID."""
        memory_id = request.path_params["memory_id"]
        project = request.query_params.get("project", "")
        if not project:
            return HTMLResponse("Missing project parameter", status_code=400)
        store = pool.get_store(project)
        store.delete(memory_id)
        return Response(status_code=200)

    async def bulk_delete(request: Request) -> Response:
        """Delete multiple memories and return updated table partial."""
        form = await request.form()
        project = form.get("project", "")
        ids_raw = form.get("ids", "")
        if not project or not ids_raw:
            return HTMLResponse("Missing project or ids", status_code=400)

        store = pool.get_store(project)
        ids_to_delete = [m.strip() for m in ids_raw.split(",") if m.strip()]
        if ids_to_delete:
            store.delete_many(ids_to_delete)

        # Return updated table using current filter state from form
        tags_raw = form.get("tags", "")
        params = {
            "project": project,
            "chunk_type": form.get("type", "") or None,
            "source_prefix": form.get("source", "") or None,
            "tags": [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None,
            "page": int(form.get("page", "1")),
            "q": form.get("q", ""),
        }
        ctx = _fetch_memories(pool, params)
        return templates.TemplateResponse(request, "_table.html", ctx)

    async def search(request: Request) -> Response:
        """HTMX search: POST with form data, return table partial."""
        form = await request.form()
        projects = form.get("projects", "")
        project = form.get("project", "")
        query = form.get("q", "")
        cross = projects == "*"

        if not cross and (not project or not query):
            return HTMLResponse("Missing project or query", status_code=400)
        if not query:
            return HTMLResponse("Missing query", status_code=400)

        tags_raw = form.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
        include_superseded = form.get("superseded", "") == "1"

        if cross:
            params = {"q": query, "tags": tags, "include_superseded": include_superseded}
            ctx = _fetch_cross_project(pool, params)
        else:
            limit = int(form.get("limit", str(PAGE_SIZE)))
            store = pool.get_store(project)
            results = store.search(query=query, tags=tags, limit=limit, include_superseded=include_superseded)
            _annotate_stale(results)
            ctx = {
                "memories": results,
                "project": project,
                "cross_project": False,
                "page": 1,
                "total_pages": 1,
                "total": len(results),
                "chunk_type": form.get("type", ""),
                "source": form.get("source", ""),
                "tags": tags_raw,
                "q": query,
                "superseded": "1" if include_superseded else "",
                "stale": "",
            }
        return templates.TemplateResponse(request, "_table.html", ctx)

    async def bulk_delete_filter(request: Request) -> Response:
        """Delete ALL memories matching the current filter, then return updated table."""
        form = await request.form()
        project = form.get("project", "")
        if not project:
            return HTMLResponse("Missing project parameter", status_code=400)

        chunk_type = form.get("type", "") or None
        source_prefix = form.get("source", "") or None
        tags_raw = form.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

        store = pool.get_store(project)
        # Fetch all matching IDs (no pagination — get everything)
        collection_size = store.count() or 1
        all_matching, _ = store.browse(
            offset=0, limit=collection_size,
            chunk_type=chunk_type,
            source_prefix=source_prefix,
            tags=tags,
        )
        ids_to_delete = [mem["id"] for mem in all_matching]
        if ids_to_delete:
            store.delete_many(ids_to_delete)

        # Return fresh table at page 1
        params = {
            "project": project,
            "chunk_type": chunk_type,
            "source_prefix": source_prefix,
            "tags": tags,
            "page": 1,
            "q": "",
        }
        ctx = _fetch_memories(pool, params)
        return templates.TemplateResponse(request, "_table.html", ctx)

    async def api_projects(request: Request) -> Response:
        """JSON list of non-empty projects for command palette."""
        projects = []
        for name in sorted(config.projects):
            store = pool.get_store(name)
            stats = store.stats()
            if stats["total"] == 0:
                continue
            projects.append({
                "name": name,
                "total": stats["total"],
                "agent_memory": stats["by_type"].get("agent-memory", 0),
                "file_indexed": stats["by_type"].get("file-indexed", 0),
            })
        return JSONResponse(projects)

    async def events(request: Request) -> Response:
        """SSE endpoint for live dashboard updates."""
        q = event_bus.subscribe()
        loop = asyncio.get_running_loop()

        async def generate():
            try:
                while True:
                    try:
                        event = await loop.run_in_executor(
                            None, lambda: q.get(timeout=30)
                        )
                        safe_project = event.project.replace("\n", " ")
                        safe_detail = event.detail.replace("\n", " ")
                        yield f"event: {event.type}\ndata: {safe_project}|{safe_detail}|{event.created_at}\n\n"
                    except queue.Empty:
                        # Timeout — send keepalive comment
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                event_bus.unsubscribe(q)

        return StreamingResponse(generate(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })

    return [
        Route("/", dashboard),
        Route("/projects", projects_page),
        Route("/api/projects", api_projects),
        Route("/memories", memories),
        Route("/memories/table", memories_table),
        Route("/memories/bulk-delete", bulk_delete, methods=["POST"]),
        Route("/memories/bulk-delete-filter", bulk_delete_filter, methods=["POST"]),
        Route("/memories/{memory_id}", delete_memory, methods=["DELETE"]),
        Route("/search", search, methods=["POST"]),
        Route("/events", events),
    ]
