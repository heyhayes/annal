"""Dashboard route handlers."""

from __future__ import annotations

import math
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from annal.config import AnnalConfig
from annal.pool import StorePool

TEMPLATES_DIR = Path(__file__).parent / "templates"

PAGE_SIZE = 50


def create_routes(pool: StorePool, config: AnnalConfig) -> list[Route]:
    """Create dashboard route list with access to the store pool and config."""
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    async def index(request: Request) -> Response:
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
            })
        return templates.TemplateResponse(request, "index.html", {
            "project_stats": project_stats,
        })

    def _parse_memory_params(request: Request) -> dict:
        """Extract common filter/pagination params from a request."""
        params = request.query_params
        project = params.get("project", "")
        chunk_type = params.get("type", "")
        source_prefix = params.get("source", "")
        tags_raw = params.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        page = int(params.get("page", "1"))
        q = params.get("q", "")
        return {
            "project": project,
            "chunk_type": chunk_type or None,
            "source_prefix": source_prefix or None,
            "tags": tags or None,
            "page": page,
            "q": q,
        }

    def _fetch_memories(pool: StorePool, params: dict) -> dict:
        """Fetch memories using either search or browse, return template context."""
        project = params["project"]
        store = pool.get_store(project)
        page = params["page"]
        offset = (page - 1) * PAGE_SIZE

        if params["q"]:
            # Search mode: semantic search, then apply filters client-side
            results = store.search(
                query=params["q"],
                limit=PAGE_SIZE,
                tags=params["tags"],
            )
            total = len(results)
            memories = results
            total_pages = 1  # search doesn't paginate
        else:
            memories, total = store.browse(
                offset=offset,
                limit=PAGE_SIZE,
                chunk_type=params["chunk_type"],
                source_prefix=params["source_prefix"],
                tags=params["tags"],
            )
            total_pages = max(1, math.ceil(total / PAGE_SIZE))

        return {
            "memories": memories,
            "project": project,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "chunk_type": params["chunk_type"] or "",
            "source": params["source_prefix"] or "",
            "tags": ",".join(params["tags"]) if params["tags"] else "",
            "q": params["q"],
        }

    async def memories(request: Request) -> Response:
        """Full memories browse/search page."""
        params = _parse_memory_params(request)
        if not params["project"]:
            return HTMLResponse("Missing project parameter", status_code=400)
        ctx = _fetch_memories(pool, params)
        return templates.TemplateResponse(request, "memories.html", ctx)

    async def memories_table(request: Request) -> Response:
        """HTMX partial: just the table body rows."""
        params = _parse_memory_params(request)
        if not params["project"]:
            return HTMLResponse("Missing project parameter", status_code=400)
        ctx = _fetch_memories(pool, params)
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
        for mem_id in ids_raw.split(","):
            mem_id = mem_id.strip()
            if mem_id:
                store.delete(mem_id)

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
        project = form.get("project", "")
        query = form.get("q", "")
        if not project or not query:
            return HTMLResponse("Missing project or query", status_code=400)

        limit = int(form.get("limit", str(PAGE_SIZE)))
        store = pool.get_store(project)
        results = store.search(query=query, limit=limit)

        ctx = {
            "memories": results,
            "project": project,
            "page": 1,
            "total_pages": 1,
            "total": len(results),
            "chunk_type": "",
            "source": "",
            "tags": "",
            "q": query,
        }
        return templates.TemplateResponse(request, "_table.html", ctx)

    return [
        Route("/", index),
        Route("/memories", memories),
        Route("/memories/table", memories_table),
        Route("/memories/bulk-delete", bulk_delete, methods=["POST"]),
        Route("/memories/{memory_id}", delete_memory, methods=["DELETE"]),
        Route("/search", search, methods=["POST"]),
    ]
