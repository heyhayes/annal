# Annal Memory Dashboard — Design

## Problem

Agents index files from watched directories and store memories via tool calls, but there's no way to see what they've learned or clean up mistakes. Field testing on classmanager showed 32,710 vendor chunks drowning out real memories — a problem that would have been caught immediately with visibility into the store.

## Solution

A web dashboard served from the same Annal process, providing browse, search, and bulk-delete capabilities over the memory store. Built with HTMX + Jinja2 for a zero-build-step, lightweight frontend.

## Architecture

The dashboard is a Starlette router mounted on the existing MCP server. It shares the `StorePool` and `AnnalConfig` instances — no separate process, no ChromaDB concurrency issues.

### Package structure

```
src/annal/dashboard/
├── __init__.py        # create_dashboard_app() factory
├── routes.py          # Starlette route handlers
├── templates/
│   ├── base.html      # Layout with nav, CSS, HTMX
│   ├── index.html     # Stats overview
│   └── memories.html  # Browse/search view
└── static/
    └── style.css      # Dashboard styles
```

### Server integration

In `server.py`, after creating the FastMCP instance, create the dashboard Starlette app and mount it. For stdio transport, start a background `uvicorn` server so the dashboard is accessible at `http://localhost:{port}` even while MCP communicates over stdin/stdout. For streamable-http transport, mount on the same ASGI app.

### Routes

```
GET  /                              → Stats overview (landing page)
GET  /memories?project&tags&type&source&page  → Paginated browse with filters
POST /search                        → Semantic search (HTMX fragment response)
DELETE /memories/{id}               → Delete single memory
POST /memories/bulk-delete          → Bulk delete by selected IDs
POST /memories/bulk-delete-filter   → Bulk delete all matching current filter
```

## Store layer

Add methods to `MemoryStore` to support dashboard queries:

- `browse(offset, limit, chunk_type, source_prefix)` — paginated retrieval with optional filters. Uses ChromaDB `get()` with `where` clauses.
- `stats()` — returns total count, chunk type breakdown, tag distribution. Built on `_iter_metadata()`.

## UI Design

### Landing page (`/`)

Per-project stats cards showing: total memory count, file-indexed vs agent-memory breakdown, top tags. Each card links to the browse view for that project.

### Browse/search view (`/memories`)

Filters bar across the top:
- Project selector (dropdown)
- Tag filter (multi-select)
- Chunk type toggle (agent-memory / file-indexed / all)
- Source prefix text input

Results table with columns: checkbox, content (truncated ~150 chars), source, tags, chunk type, created date.

Bulk actions bar: "Delete selected" and "Delete all matching filter" with confirmation modal.

Semantic search box above the table. When used, replaces filter-based results with similarity-ranked search results.

Pagination at the bottom (page size ~50).

### Aesthetic

Dark theme, monospace-forward, IDE-inspired. This is a developer tool — prioritize data density and readability over decoration. Use CSS variables for theming.

## Dependencies

Add `jinja2` to project dependencies. HTMX loaded from a vendored file or CDN link in the base template.

## What this doesn't include

- Memory editing (update content/tags) — add later if needed
- Similarity clustering visualization — future enhancement
- Authentication — this is a local dev tool
