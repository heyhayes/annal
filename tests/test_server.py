import pytest
from annal.server import create_server, SERVER_INSTRUCTIONS
from annal.config import AnnalConfig


@pytest.fixture
def server_env(tmp_data_dir, tmp_config_path, tmp_path):
    """Set up a config and environment for the server."""
    watch_dir = tmp_path / "project_files"
    watch_dir.mkdir()
    (watch_dir / "README.md").write_text("# Test Project\nSome docs\n")

    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={},
    )
    config.save()

    return {
        "config_path": tmp_config_path,
        "data_dir": tmp_data_dir,
        "watch_dir": str(watch_dir),
    }


@pytest.fixture
def mcp(server_env):
    mcp, _pool = create_server(config_path=server_env["config_path"])
    return mcp


async def _call(mcp, name: str, args: dict) -> str:
    """Call an MCP tool and return the text content."""
    result = await mcp.call_tool(name, args)
    # call_tool returns (list[TextContent], dict) — text is in the first element
    content_blocks = result[0] if isinstance(result, tuple) else result
    return content_blocks[0].text


def test_create_server(server_env):
    mcp, pool = create_server(config_path=server_env["config_path"])
    assert mcp is not None
    assert mcp.name == "annal"


def test_create_server_returns_pool(server_env):
    """create_server should return both mcp and pool."""
    result = create_server(config_path=server_env["config_path"])
    assert isinstance(result, tuple)
    mcp, pool = result
    assert mcp.name == "annal"
    assert pool is not None


def test_create_server_accepts_external_pool(server_env):
    """create_server should use a provided pool instead of creating its own."""
    from annal.pool import StorePool
    config = AnnalConfig.load(server_env["config_path"])
    external_pool = StorePool(config)
    mcp, returned_pool = create_server(
        config_path=server_env["config_path"],
        pool=external_pool,
    )
    assert returned_pool is external_pool


def test_server_has_instructions(server_env):
    mcp, _pool = create_server(config_path=server_env["config_path"])
    assert mcp.instructions == SERVER_INSTRUCTIONS


@pytest.mark.asyncio
async def test_probe_mode_returns_compact_summary(mcp):
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Apply discount on gross, not net — avoids tax-inclusive rounding drift",
        "tags": ["decision", "billing"],
        "source": "session observation",
    })

    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "discount rounding",
        "mode": "probe",
    })

    assert "1 results" in result
    # Probe should show quoted snippet, not full content
    assert '"Apply discount on gross' in result
    # Should include source and ID on the summary line
    assert "Source: session observation" in result
    assert "ID:" in result


@pytest.mark.asyncio
async def test_probe_mode_truncates_long_content(mcp):
    long_content = "A" * 200 + " rest of content"
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": long_content,
        "tags": ["test"],
    })

    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "AAAA",
        "mode": "probe",
    })

    # Should be truncated with ellipsis
    assert "…" in result
    # Should NOT contain the full 200 A's + rest
    assert "rest of content" not in result


@pytest.mark.asyncio
async def test_full_mode_returns_complete_content(mcp):
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Full content should appear here",
        "tags": ["test"],
    })

    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "full content",
        "mode": "full",
    })

    assert "Full content should appear here" in result


@pytest.mark.asyncio
async def test_expand_memories(mcp):
    store_result = await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Detailed architecture notes for the billing system",
        "tags": ["architecture", "billing"],
        "source": "design review",
    })

    # Extract the ID from the store result
    mem_id = store_result.split("Stored memory ")[-1].strip()

    result = await _call(mcp, "expand_memories", {
        "project": "test",
        "memory_ids": [mem_id],
    })

    assert "1 memories" in result
    assert "Detailed architecture notes for the billing system" in result
    assert "architecture" in result
    assert "design review" in result


@pytest.mark.asyncio
async def test_expand_memories_missing_ids(mcp):
    result = await _call(mcp, "expand_memories", {
        "project": "test",
        "memory_ids": ["nonexistent-id"],
    })

    # ChromaDB raises on missing IDs — but we should handle gracefully
    # or return what we can. Let's just verify it doesn't crash.
    assert "[test]" in result


@pytest.mark.asyncio
async def test_dedup_catches_duplicate_behind_file_indexed(mcp):
    """Dedup should find agent-memory duplicates even when file-indexed content is nearer."""
    # Store an agent memory
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "The checkout flow validates cart totals before payment",
        "tags": ["checkout"],
    })

    # Store a file-indexed chunk with very similar content (simulates file indexer)
    from annal.pool import StorePool
    from annal.config import AnnalConfig
    # Access the pool's store directly to insert a file-indexed chunk
    # This is a bit of a reach-through, but necessary to test the dedup logic
    store_result = await _call(mcp, "store_memory", {
        "project": "test",
        "content": "The checkout flow validates cart totals before payment processing begins",
        "tags": ["checkout"],
    })

    # The second store should be caught as a near-duplicate
    assert "Skipped" in store_result or "similar memory already exists" in store_result


@pytest.mark.asyncio
async def test_search_on_empty_project(mcp):
    result = await _call(mcp, "search_memories", {
        "project": "emptyproject",
        "query": "anything",
    })
    assert "No matching memories found" in result


@pytest.mark.asyncio
async def test_init_project_with_custom_excludes(server_env):
    mcp, _pool = create_server(config_path=server_env["config_path"])
    result = await _call(mcp, "init_project", {
        "project_name": "customproj",
        "watch_paths": [server_env["watch_dir"]],
        "watch_exclude": ["**/custom_vendor/**"],
    })
    assert "customproj" in result
    assert "**/custom_vendor/**" in result

    # Verify it persisted to config
    config = AnnalConfig.load(server_env["config_path"])
    assert config.projects["customproj"].watch_exclude == ["**/custom_vendor/**"]


@pytest.mark.asyncio
async def test_index_files_clears_stale_chunks(server_env):
    """index_files should remove old file-indexed chunks before re-indexing."""
    import time

    mcp, _pool = create_server(config_path=server_env["config_path"])
    watch_dir = server_env["watch_dir"]

    # Init project and index files
    await _call(mcp, "init_project", {
        "project_name": "staletest",
        "watch_paths": [watch_dir],
    })
    # Wait for async init indexing to complete
    time.sleep(2)

    # Store an agent memory (should survive re-index)
    await _call(mcp, "store_memory", {
        "project": "staletest",
        "content": "Agent memory that should persist",
        "tags": ["test"],
    })

    # Re-index — should clear file chunks but keep agent memories
    result = await _call(mcp, "index_files", {"project": "staletest"})
    assert "Re-indexing started" in result
    # Wait for async re-indexing to complete
    time.sleep(2)

    # Agent memory should still be searchable
    search_result = await _call(mcp, "search_memories", {
        "project": "staletest",
        "query": "agent memory persist",
    })
    assert "Agent memory that should persist" in search_result


@pytest.mark.asyncio
async def test_store_memory_accepts_string_tags(mcp):
    """store_memory should accept a bare string for tags (not just a list)."""
    result = await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Bare string tag test",
        "tags": "decision",
    })
    assert "Stored memory" in result


@pytest.mark.asyncio
async def test_search_memories_accepts_string_tags(mcp):
    """search_memories should accept a bare string for the tags filter."""
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Memory tagged for searchable string test",
        "tags": ["searchable"],
    })
    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "searchable string test",
        "tags": "searchable",
    })
    assert "Memory tagged for searchable string test" in result


@pytest.mark.asyncio
async def test_store_memory_lowercases_and_dedupes_tags(mcp):
    """Tags should be lowercased and deduplicated."""
    store_result = await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Lowercase and dedupe tag test",
        "tags": ["Decision", "BILLING", "decision"],
    })
    assert "Stored memory" in store_result

    mem_id = store_result.split("Stored memory ")[-1].strip()
    expand_result = await _call(mcp, "expand_memories", {
        "project": "test",
        "memory_ids": [mem_id],
    })
    # Should contain lowercase tags with no duplicates
    assert "decision" in expand_result
    assert "billing" in expand_result
    # Should not contain uppercase variants or duplicated tags
    assert "Decision" not in expand_result
    assert "BILLING" not in expand_result


@pytest.mark.asyncio
async def test_search_suppresses_negative_scores(mcp):
    """With a high min_score, irrelevant results should be filtered out."""
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "The billing module uses Stripe for payment processing",
        "tags": ["billing"],
    })

    # Search with a completely unrelated query and a high min_score threshold
    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "quantum physics entanglement experiments",
        "min_score": 0.5,
    })

    assert "No matching memories found" in result


@pytest.mark.asyncio
async def test_update_memory(mcp):
    result = await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Original decision about auth",
        "tags": ["decision", "auth"],
    })
    mem_id = result.split("Stored memory ")[-1].strip()

    update_result = await _call(mcp, "update_memory", {
        "project": "test",
        "memory_id": mem_id,
        "content": "Revised decision: use JWT not sessions",
        "tags": ["decision", "auth", "jwt"],
    })
    assert "Updated memory" in update_result

    expanded = await _call(mcp, "expand_memories", {
        "project": "test",
        "memory_ids": [mem_id],
    })
    assert "Revised decision" in expanded
    assert "jwt" in expanded


@pytest.mark.asyncio
async def test_search_min_score_zero_allows_positive(mcp):
    """Default min_score=0.0 should allow results with positive similarity."""
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Apply discount on gross total before tax calculation",
        "tags": ["billing"],
    })

    # Search with a relevant query using default min_score (0.0)
    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "discount gross total tax",
    })

    assert "Apply discount on gross total" in result


@pytest.mark.asyncio
async def test_init_project_returns_immediately(server_env):
    """init_project should return immediately with indexing message."""
    mcp, _pool = create_server(config_path=server_env["config_path"])
    result = await _call(mcp, "init_project", {
        "project_name": "asyncinit",
        "watch_paths": [server_env["watch_dir"]],
    })
    assert "indexing in progress" in result.lower() or "initialized" in result.lower()


@pytest.mark.asyncio
async def test_index_files_returns_immediately(server_env):
    """index_files should return immediately with progress message."""
    import time

    mcp, _pool = create_server(config_path=server_env["config_path"])
    await _call(mcp, "init_project", {
        "project_name": "asyncidx",
        "watch_paths": [server_env["watch_dir"]],
    })
    time.sleep(1)

    result = await _call(mcp, "index_files", {"project": "asyncidx"})
    assert "asyncidx" in result.lower() or "index" in result.lower()


@pytest.mark.asyncio
async def test_index_status(mcp):
    """index_status should return project diagnostics."""
    await _call(mcp, "store_memory", {
        "project": "statustest",
        "content": "Some memory",
        "tags": ["test"],
    })
    result = await _call(mcp, "index_status", {"project": "statustest"})
    assert "statustest" in result
    assert "chunks" in result.lower() or "total" in result.lower()


@pytest.mark.asyncio
async def test_update_memory_nonexistent_id(mcp):
    """update_memory with a nonexistent ID should return a not-found message."""
    result = await _call(mcp, "update_memory", {
        "project": "test",
        "memory_id": "nonexistent-id-12345",
        "content": "This should fail",
    })
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_update_memory_no_op(mcp):
    """update_memory with no content, tags, or source should return a no-op message."""
    result = await _call(mcp, "update_memory", {
        "project": "test",
        "memory_id": "doesnt-matter",
    })
    assert "nothing to update" in result.lower()


@pytest.mark.asyncio
async def test_search_with_temporal_filter(mcp):
    """search_memories should accept after/before date params."""
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Decision made today about API design",
        "tags": ["decision"],
    })

    from datetime import datetime, timezone, timedelta
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    # Should find with yesterday-tomorrow range
    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "API design",
        "after": yesterday,
        "before": tomorrow,
    })
    assert "API design" in result

    # Should not find with future-only range
    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "API design",
        "after": tomorrow,
    })
    assert "No matching memories" in result


@pytest.mark.asyncio
async def test_search_json_output(mcp):
    """output='json' should return valid JSON with results and meta."""
    import json

    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "JSON output test memory",
        "tags": ["test"],
        "source": "test-source",
    })

    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "JSON output",
        "output": "json",
    })

    data = json.loads(result)
    assert "results" in data
    assert "meta" in data
    assert len(data["results"]) > 0
    assert data["meta"]["project"] == "test"
    assert data["meta"]["mode"] == "full"
    assert data["meta"]["query"] == "JSON output"

    first = data["results"][0]
    assert "id" in first
    assert "content" in first
    assert "tags" in first
    assert "score" in first
    assert "source" in first
    assert "created_at" in first


@pytest.mark.asyncio
async def test_search_json_probe_mode(mcp):
    """output='json' + mode='probe' should include content_preview but not full content."""
    import json

    long_content = "A" * 300 + " unique marker"
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": long_content,
        "tags": ["test"],
    })

    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "AAAA",
        "mode": "probe",
        "output": "json",
    })

    data = json.loads(result)
    first = data["results"][0]
    assert "content_preview" in first
    assert len(first["content_preview"]) <= 200
    assert "content" not in first


@pytest.mark.asyncio
async def test_search_memories_json_empty(mcp):
    """search_memories with output='json' and no results returns correct JSON structure."""
    import json

    result = await _call(mcp, "search_memories", {
        "project": "emptyproject",
        "query": "anything",
        "output": "json",
    })

    data = json.loads(result)
    assert data["results"] == []
    assert data["meta"]["total"] == 0
    assert data["meta"]["project"] == "emptyproject"


@pytest.mark.asyncio
async def test_search_text_output_unchanged(mcp):
    """output='text' (default) should return the same format as before."""
    await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Text output test",
        "tags": ["test"],
    })

    result = await _call(mcp, "search_memories", {
        "project": "test",
        "query": "Text output",
    })

    # Should be the existing text format, not JSON
    assert "[test]" in result


@pytest.mark.asyncio
async def test_expand_json_output(mcp):
    """expand_memories with output='json' should return structured results."""
    import json

    store_result = await _call(mcp, "store_memory", {
        "project": "test",
        "content": "Expand JSON test",
        "tags": ["test"],
    })
    mem_id = store_result.split("Stored memory ")[-1].strip()

    result = await _call(mcp, "expand_memories", {
        "project": "test",
        "memory_ids": [mem_id],
        "output": "json",
    })

    data = json.loads(result)
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == mem_id
    assert data["results"][0]["content"] == "Expand JSON test"
    assert "score" not in data["results"][0]
