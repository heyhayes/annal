# Annal Memory Dashboard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a web dashboard for browsing, searching, and managing agent memories, served from the existing Annal MCP server process.

**Architecture:** Starlette dashboard app started on a background thread (using the configured port for stdio transport, port+1 for streamable-http). Shares `StorePool` and `AnnalConfig` in-process. HTMX for interactivity, Jinja2 for templates, single CSS file for styling.

**Tech Stack:** Starlette, Jinja2, HTMX (vendored), uvicorn (already a transitive dep via mcp)

---

### Task 1: Add jinja2 dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add jinja2 to dependencies**

In `pyproject.toml`, add `"jinja2>=3.1"` to the `dependencies` list.

**Step 2: Install updated deps**

Run: `pip install -e ".[dev]" --break-system-packages`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add jinja2 dependency for dashboard"
```

---

### Task 2: Add browse() and stats() to MemoryStore (TDD)

**Files:**
- Modify: `src/annal/store.py`
- Modify: `tests/test_store.py`

**Step 1: Write failing tests**

```python
def test_browse_returns_paginated_results(store_with_data):
    store = store_with_data
    results, total = store.browse(offset=0, limit=2)
    assert len(results) == 2
    assert total >= 3
    # Each result should have expected fields
    r = results[0]
    assert "id" in r
    assert "content" in r
    assert "tags" in r
    assert "source" in r
    assert "chunk_type" in r
    assert "created_at" in r


def test_browse_filters_by_chunk_type(store_with_data):
    store = store_with_data
    results, total = store.browse(chunk_type="file-indexed")
    # Only file-indexed chunks should be returned
    for r in results:
        assert r["chunk_type"] == "file-indexed"


def test_browse_filters_by_source_prefix(store_with_data):
    store = store_with_data
    results, _ = store.browse(source_prefix="file:/tmp")
    for r in results:
        assert r["source"].startswith("file:/tmp")


def test_stats_returns_breakdown(store_with_data):
    store = store_with_data
    stats = store.stats()
    assert "total" in stats
    assert "by_type" in stats
    assert "by_tag" in stats
    assert stats["total"] >= 3
    assert isinstance(stats["by_type"], dict)
    assert isinstance(stats["by_tag"], dict)
```

The `store_with_data` fixture needs to set up a store with a mix of agent-memory and file-indexed chunks. Add it to `tests/test_store.py`:

```python
@pytest.fixture
def store_with_data(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="dashboard_test")
    store.store("Agent memory about billing", tags=["billing"], source="session observation")
    store.store("Agent memory about auth", tags=["auth", "decision"], source="design review")
    store.store("# README\nProject docs here", tags=["indexed", "docs"], source="file:/tmp/project/README.md", chunk_type="file-indexed")
    store.store("Config content", tags=["indexed", "agent-config"], source="file:/tmp/project/CLAUDE.md", chunk_type="file-indexed")
    return store
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py::test_browse_returns_paginated_results tests/test_store.py::test_stats_returns_breakdown -v`
Expected: FAIL — `MemoryStore` has no `browse` or `stats` method

**Step 3: Implement browse() and stats()**

Add to `MemoryStore` in `src/annal/store.py`:

```python
def browse(
    self,
    offset: int = 0,
    limit: int = 50,
    chunk_type: str | None = None,
    source_prefix: str | None = None,
    tags: list[str] | None = None,
) -> tuple[list[dict], int]:
    """Paginated retrieval with optional filters. Returns (results, total_matching)."""
    total = self._collection.count()
    if total == 0:
        return [], 0

    # Fetch with chunk_type where clause if provided
    kwargs: dict = {"include": ["documents", "metadatas"], "limit": total}
    if chunk_type:
        kwargs["where"] = {"chunk_type": chunk_type}

    batch = self._collection.get(**kwargs)

    memories = []
    for i, doc_id in enumerate(batch["ids"]):
        meta = batch["metadatas"][i]
        source = meta.get("source", "")
        mem_tags = json.loads(meta.get("tags", "[]"))

        if source_prefix and not source.startswith(source_prefix):
            continue
        if tags and not any(t in mem_tags for t in tags):
            continue

        memories.append({
            "id": doc_id,
            "content": batch["documents"][i],
            "tags": mem_tags,
            "source": source,
            "chunk_type": meta.get("chunk_type", ""),
            "created_at": meta.get("created_at", ""),
        })

    filtered_total = len(memories)
    page = memories[offset:offset + limit]
    return page, filtered_total


def stats(self) -> dict:
    """Return collection statistics: total count, type breakdown, tag distribution."""
    type_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    total = 0

    for _, meta in self._iter_metadata():
        total += 1
        chunk_type = meta.get("chunk_type", "unknown")
        type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
        for tag in json.loads(meta.get("tags", "[]")):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {"total": total, "by_type": type_counts, "by_tag": tag_counts}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/annal/store.py tests/test_store.py
git commit -m "feat: add browse() and stats() to MemoryStore for dashboard"
```

---

### Task 3: Create dashboard package structure

**Files:**
- Create: `src/annal/dashboard/__init__.py`
- Create: `src/annal/dashboard/routes.py`
- Create: `src/annal/dashboard/templates/base.html`
- Create: `src/annal/dashboard/templates/index.html`
- Create: `src/annal/dashboard/templates/memories.html`
- Create: `src/annal/dashboard/static/style.css`

**Step 1: Create `__init__.py` with app factory**

```python
"""Annal memory dashboard — web UI for browsing and managing agent memories."""

from __future__ import annotations

from pathlib import Path
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from annal.dashboard.routes import create_routes

PACKAGE_DIR = Path(__file__).parent


def create_dashboard_app(pool, config) -> Starlette:
    """Create the dashboard Starlette application."""
    routes = create_routes(pool, config)
    routes.append(
        Mount("/static", app=StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    )
    return Starlette(routes=routes)
```

**Step 2: Create `routes.py` with route handlers**

Create `src/annal/dashboard/routes.py`. This file has all the request handlers. It receives `pool` and `config` via a factory function, creates Jinja2Templates, and returns a list of Route objects.

Route handlers:
- `index` — GET `/` — renders stats overview per project
- `memories` — GET `/memories` — renders browse view with filters
- `memories_table` — GET `/memories/table` — HTMX partial, returns just the table rows
- `search` — POST `/search` — semantic search, returns HTMX table fragment
- `delete_memory` — DELETE `/memories/{id}` — delete single, returns empty (HTMX removes row)
- `bulk_delete` — POST `/memories/bulk-delete` — delete selected IDs, returns updated table
- `bulk_delete_filter` — POST `/memories/bulk-delete-filter` — delete all matching current filter

The route handlers use `pool.get_store(project)` to access the store, then call `browse()`, `stats()`, `search()`, or `delete()`.

**Step 3: Create templates**

`base.html` — Page layout with nav bar (link to home, project links), HTMX script tag (CDN: `https://unpkg.com/htmx.org@2.0.4`), link to `/static/style.css`. Dark theme.

`index.html` — Extends base. Shows a card per project from `config.projects`. Each card shows stats (total memories, file-indexed count, agent-memory count, top 10 tags). Card links to `/memories?project={name}`.

`memories.html` — Extends base. Filter bar at top: project dropdown, chunk type select, source prefix input, tag filter input. Below: search box. Table of memories with checkboxes. Bulk action buttons. Pagination. The table body has `id="memory-table"` for HTMX swapping. Filter changes trigger `hx-get="/memories/table?..."` targeting `#memory-table`.

**Step 4: Create `static/style.css`**

Dark theme, monospace-forward. CSS variables for colors. Use the frontend-design skill for the actual implementation to get a distinctive aesthetic. Key characteristics: dark background (#0d1117 family), accent color, high data density, readable table rows, tag pills.

**Step 5: Commit**

```bash
git add src/annal/dashboard/
git commit -m "feat: dashboard package with routes, templates, and static assets"
```

---

### Task 4: Wire dashboard into server.py

**Files:**
- Modify: `src/annal/server.py`

**Step 1: Add dashboard startup to create_server()**

After creating the `pool` and starting the reconciliation thread, create the dashboard app and start it on a background thread:

```python
import uvicorn
from annal.dashboard import create_dashboard_app

# ... existing code ...

# Start dashboard on background thread
dashboard_app = create_dashboard_app(pool, config)

def _start_dashboard() -> None:
    dashboard_port = config.port  # In stdio mode, the MCP port is unused
    uv_config = uvicorn.Config(
        dashboard_app,
        host="127.0.0.1",
        port=dashboard_port,
        log_level="warning",
    )
    server = uvicorn.Server(uv_config)
    server.run()

dashboard_thread = threading.Thread(target=_start_dashboard, daemon=True)
dashboard_thread.start()
logger.info("Dashboard available at http://127.0.0.1:%d", config.port)
```

Note: the dashboard uses the configured port (default 9200). In stdio mode this is fine since MCP uses stdin/stdout. For streamable-http mode, the MCP server would use this port, so dashboard would need port+1 — but that's an edge case to handle later if needed. The common case (Claude Code → stdio) works immediately.

**Step 2: Verify manually**

Run: `python -m annal.server --transport stdio` and check `http://localhost:9200` in a browser.

**Step 3: Commit**

```bash
git add src/annal/server.py
git commit -m "feat: start dashboard on background thread alongside MCP server"
```

---

### Task 5: Test route handlers

**Files:**
- Create: `tests/test_dashboard.py`

**Step 1: Write tests using Starlette TestClient**

```python
import pytest
from starlette.testclient import TestClient
from annal.config import AnnalConfig, ProjectConfig
from annal.pool import StorePool
from annal.dashboard import create_dashboard_app


@pytest.fixture
def dashboard_client(tmp_data_dir, tmp_config_path):
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={"testproj": ProjectConfig()},
    )
    config.save()
    pool = StorePool(config)
    # Seed some data
    store = pool.get_store("testproj")
    store.store("Billing decision about rounding", tags=["decision", "billing"], source="session")
    store.store("File content from README", tags=["indexed", "docs"], source="file:/tmp/README.md", chunk_type="file-indexed")
    app = create_dashboard_app(pool, config)
    return TestClient(app)


def test_index_page(dashboard_client):
    resp = dashboard_client.get("/")
    assert resp.status_code == 200
    assert "testproj" in resp.text


def test_memories_page(dashboard_client):
    resp = dashboard_client.get("/memories?project=testproj")
    assert resp.status_code == 200
    assert "Billing decision" in resp.text


def test_memories_table_htmx(dashboard_client):
    resp = dashboard_client.get("/memories/table?project=testproj&type=file-indexed")
    assert resp.status_code == 200
    assert "File content from README" in resp.text
    assert "Billing decision" not in resp.text


def test_delete_memory(dashboard_client):
    # Get a memory ID from the browse results
    resp = dashboard_client.get("/memories/table?project=testproj")
    # Delete via the API
    # (extract ID from response or use store directly)
    pool_store = ...  # access via fixture
    # This test needs refinement during implementation


def test_search(dashboard_client):
    resp = dashboard_client.post("/search", data={"project": "testproj", "query": "billing rounding"})
    assert resp.status_code == 200
    assert "Billing decision" in resp.text
```

**Step 2: Run tests**

Run: `pytest tests/test_dashboard.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test: dashboard route handler tests"
```

---

### Task 6: Full test suite + polish

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

**Step 2: Manual verification**

Start the server, open the dashboard, verify:
- Stats page shows project cards
- Browse page shows memories with working filters
- Search returns ranked results
- Delete removes individual memories
- Bulk delete works

**Step 3: Final commit if any polish needed**

---

## Implementation Notes

- HTMX is loaded from CDN (`unpkg.com/htmx.org@2.0.4`). Could vendor it later if offline usage matters.
- The `browse()` method fetches all matching chunks then slices for pagination. This is fine for stores under ~100K entries. If performance becomes an issue, add ChromaDB-level pagination with `where` + `offset`.
- Delete operations go through `store.delete(id)` — same method the MCP `delete_memory` tool uses.
- No authentication. This is a local dev tool on localhost.
