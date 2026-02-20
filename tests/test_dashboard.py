import pytest
from starlette.testclient import TestClient

from annal.config import AnnalConfig, ProjectConfig
from annal.dashboard import create_dashboard_app
from annal.events import event_bus, Event
from annal.pool import StorePool


@pytest.fixture
def dashboard_client(tmp_data_dir, tmp_config_path):
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={"testproj": ProjectConfig()},
    )
    config.save()
    pool = StorePool(config)
    store = pool.get_store("testproj")
    store.store(
        "Billing decision about rounding",
        tags=["decision", "billing"],
        source="session",
    )
    store.store(
        "Auth architecture notes",
        tags=["decision", "auth"],
        source="design review",
    )
    store.store(
        "File content from README",
        tags=["indexed", "docs"],
        source="file:/tmp/README.md",
        chunk_type="file-indexed",
    )
    app = create_dashboard_app(pool, config)
    return TestClient(app)


@pytest.fixture
def empty_dashboard_client(tmp_data_dir, tmp_config_path):
    """Dashboard with no projects configured."""
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={},
    )
    config.save()
    pool = StorePool(config)
    app = create_dashboard_app(pool, config)
    return TestClient(app)


@pytest.fixture
def dashboard_with_pool(tmp_data_dir, tmp_config_path):
    """Return both the TestClient and the StorePool for tests that need store access."""
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={"testproj": ProjectConfig()},
    )
    config.save()
    pool = StorePool(config)
    store = pool.get_store("testproj")
    store.store(
        "Billing decision about rounding",
        tags=["decision", "billing"],
        source="session",
    )
    store.store(
        "Auth architecture notes",
        tags=["decision", "auth"],
        source="design review",
    )
    store.store(
        "File content from README",
        tags=["indexed", "docs"],
        source="file:/tmp/README.md",
        chunk_type="file-indexed",
    )
    app = create_dashboard_app(pool, config)
    return TestClient(app), pool


def test_index_page(dashboard_client):
    response = dashboard_client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "testproj" in html
    # The index page shows total count and per-type counts
    assert "3" in html  # total memories


def test_index_page_no_projects(empty_dashboard_client):
    response = empty_dashboard_client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "No projects configured yet" in html


def test_memories_page(dashboard_client):
    response = dashboard_client.get("/memories?project=testproj")
    assert response.status_code == 200
    html = response.text
    assert "Billing decision about rounding" in html
    assert "Auth architecture notes" in html
    assert "File content from README" in html


def test_memories_page_missing_project(dashboard_client):
    response = dashboard_client.get("/memories")
    assert response.status_code == 400
    assert "Missing project parameter" in response.text


def test_memories_table_filters_by_type(dashboard_client):
    response = dashboard_client.get("/memories/table?project=testproj&type=file-indexed")
    assert response.status_code == 200
    html = response.text
    assert "File content from README" in html
    assert "Billing decision about rounding" not in html
    assert "Auth architecture notes" not in html


def test_memories_table_filters_by_source(dashboard_client):
    response = dashboard_client.get("/memories/table?project=testproj&source=file:/tmp")
    assert response.status_code == 200
    html = response.text
    assert "file:/tmp/README.md" in html
    assert "Billing decision about rounding" not in html


def test_delete_single_memory(dashboard_with_pool):
    client, pool = dashboard_with_pool
    store = pool.get_store("testproj")

    # Get all memories to find an ID to delete
    memories, _ = store.browse()
    target = next(m for m in memories if "Billing" in m["content"])
    target_id = target["id"]

    response = client.request("DELETE", f"/memories/{target_id}?project=testproj")
    assert response.status_code == 200

    # Verify the memory is actually gone from the store
    remaining, total = store.browse()
    remaining_ids = {m["id"] for m in remaining}
    assert target_id not in remaining_ids
    assert total == 2


def test_bulk_delete(dashboard_with_pool):
    client, pool = dashboard_with_pool
    store = pool.get_store("testproj")

    memories, _ = store.browse()
    ids_to_delete = [m["id"] for m in memories[:2]]

    response = client.post(
        "/memories/bulk-delete",
        data={"project": "testproj", "ids": ",".join(ids_to_delete)},
    )
    assert response.status_code == 200

    # Verify the memories are actually gone
    remaining, total = store.browse()
    remaining_ids = {m["id"] for m in remaining}
    for deleted_id in ids_to_delete:
        assert deleted_id not in remaining_ids
    assert total == 1


def test_search(dashboard_with_pool):
    client, pool = dashboard_with_pool

    response = client.post(
        "/search",
        data={"project": "testproj", "q": "billing rounding"},
    )
    assert response.status_code == 200
    html = response.text
    # The search should return results rendered as table rows
    assert "Billing decision about rounding" in html


def test_bulk_delete_filter(dashboard_with_pool):
    """Delete all memories matching a filter (e.g. all file-indexed chunks)."""
    client, pool = dashboard_with_pool
    store = pool.get_store("testproj")

    assert store.count() == 3

    # Delete all file-indexed chunks
    response = client.post(
        "/memories/bulk-delete-filter",
        data={"project": "testproj", "type": "file-indexed"},
    )
    assert response.status_code == 200

    # Only agent-memory chunks should remain
    remaining, total = store.browse()
    assert total == 2
    for m in remaining:
        assert m["chunk_type"] == "agent-memory"


def test_sse_endpoint_streams_events(dashboard_client):
    """The /events SSE endpoint should stream events with correct format."""
    import threading

    import httpx
    import uvicorn

    # Use a real HTTP server to test the SSE endpoint, since the httpx
    # ASGI transport buffers the full response and can't handle infinite streams.
    app = dashboard_client.app

    uv_config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(uv_config)

    server_started = threading.Event()
    original_startup = server.startup

    async def patched_startup(*a, **kw):
        result = await original_startup(*a, **kw)
        server_started.set()
        return result

    server.startup = patched_startup

    def run_server():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    server_started.wait(timeout=5)

    # Find the actual port
    for s in server.servers:
        for sock in s.sockets:
            port = sock.getsockname()[1]
            break

    try:
        with httpx.stream("GET", f"http://127.0.0.1:{port}/events", timeout=5) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            # Push an event so the stream yields data
            event_bus.push(Event(type="memory_stored", project="test", detail="id123"))

            for chunk in response.iter_text():
                assert "event: memory_stored" in chunk
                assert "data: test|id123" in chunk
                break
    finally:
        server.should_exit = True
        t.join(timeout=3)


def test_event_bus_pub_sub():
    """Events pushed to the bus should be received by subscribers."""
    q = event_bus.subscribe()
    event_bus.push(Event(type="memory_stored", project="test", detail="test memory"))
    try:
        received = q.get(timeout=1.0)
        assert received.type == "memory_stored"
        assert received.project == "test"
    finally:
        event_bus.unsubscribe(q)
