import pytest
from annal.store import MemoryStore


@pytest.fixture
def store(tmp_data_dir):
    return MemoryStore(data_dir=tmp_data_dir, project="testproject")


def test_store_and_retrieve_memory(store):
    mem_id = store.store(
        content="The checkout flow goes through EnrolmentStoreController",
        tags=["billing", "checkout"],
        source="session observation",
    )
    assert mem_id is not None

    results = store.search("checkout flow", limit=1)
    assert len(results) == 1
    assert "EnrolmentStoreController" in results[0]["content"]
    assert results[0]["tags"] == ["billing", "checkout"]


def test_search_with_tag_filter(store):
    store.store(content="Billing uses Stripe", tags=["billing"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("uses", tags=["billing"], limit=5)
    assert len(results) == 1
    assert "Stripe" in results[0]["content"]


def test_delete_memory(store):
    mem_id = store.store(content="Temporary note", tags=["temp"])
    store.delete(mem_id)

    results = store.search("Temporary note", limit=5)
    assert len(results) == 0


def test_list_topics(store):
    store.store(content="Billing info", tags=["billing", "stripe"])
    store.store(content="Frontend info", tags=["frontend", "billing"])

    topics = store.list_topics()
    assert topics["billing"] == 2
    assert topics["stripe"] == 1
    assert topics["frontend"] == 1


def test_search_returns_similarity_score(store):
    store.store(content="The sky is blue", tags=["nature"])
    results = store.search("blue sky", limit=1)
    assert "score" in results[0]
    assert isinstance(results[0]["score"], float)


def test_store_with_source(store):
    store.store(content="Found in AGENT.md", tags=["docs"], source="AGENT.md > Overview")
    results = store.search("AGENT.md", limit=1)
    assert results[0]["source"] == "AGENT.md > Overview"


def test_search_empty_collection(store):
    results = store.search("anything", limit=5)
    assert results == []


def test_get_by_ids(store):
    id1 = store.store(content="First memory", tags=["a"])
    id2 = store.store(content="Second memory", tags=["b"])
    store.store(content="Third memory", tags=["c"])

    results = store.get_by_ids([id1, id2])
    assert len(results) == 2
    ids_returned = {r["id"] for r in results}
    assert ids_returned == {id1, id2}
    for r in results:
        assert "content" in r
        assert "tags" in r
        assert "created_at" in r


def test_get_by_ids_empty_list(store):
    results = store.get_by_ids([])
    assert results == []


@pytest.fixture
def store_with_data(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="dashboard_test")
    store.store("Agent memory about billing", tags=["billing"], source="session observation")
    store.store("Agent memory about auth", tags=["auth", "decision"], source="design review")
    store.store("# README\nProject docs here", tags=["indexed", "docs"], source="file:/tmp/project/README.md", chunk_type="file-indexed")
    store.store("Config content", tags=["indexed", "agent-config"], source="file:/tmp/project/CLAUDE.md", chunk_type="file-indexed")
    return store


def test_browse_returns_paginated_results(store_with_data):
    store = store_with_data
    results, total = store.browse(offset=0, limit=2)
    assert len(results) == 2
    assert total == 4
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
    assert total == 2
    for r in results:
        assert r["chunk_type"] == "file-indexed"


def test_browse_filters_by_source_prefix(store_with_data):
    store = store_with_data
    results, total = store.browse(source_prefix="file:/tmp")
    assert total == 2
    for r in results:
        assert r["source"].startswith("file:/tmp")


def test_browse_filters_by_tags(store_with_data):
    store = store_with_data
    results, total = store.browse(tags=["billing"])
    assert total == 1
    assert results[0]["tags"] == ["billing"]


def test_browse_empty_collection(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="empty_browse")
    results, total = store.browse()
    assert results == []
    assert total == 0


def test_stats_returns_breakdown(store_with_data):
    store = store_with_data
    stats = store.stats()
    assert stats["total"] == 4
    assert stats["by_type"]["agent-memory"] == 2
    assert stats["by_type"]["file-indexed"] == 2
    assert stats["by_tag"]["billing"] == 1
    assert stats["by_tag"]["indexed"] == 2


def test_update_memory_content(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="update_test")
    mem_id = store.store(content="Original content", tags=["test"])

    store.update(mem_id, content="Updated content")

    results = store.get_by_ids([mem_id])
    assert len(results) == 1
    assert results[0]["content"] == "Updated content"
    assert results[0]["tags"] == ["test"]  # tags unchanged
    assert results[0]["updated_at"] != ""


def test_update_memory_tags(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="update_test")
    mem_id = store.store(content="Some content", tags=["old-tag"])

    store.update(mem_id, tags=["new-tag", "extra"])

    results = store.get_by_ids([mem_id])
    assert results[0]["tags"] == ["new-tag", "extra"]
    assert results[0]["content"] == "Some content"  # content unchanged


def test_search_returns_updated_at(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="updated_at_search")
    mem_id = store.store(content="Will be updated", tags=["test"])
    store.update(mem_id, content="Updated content")

    results = store.search("Updated content", limit=1)
    assert len(results) == 1
    assert "updated_at" in results[0]
    assert results[0]["updated_at"] != ""


def test_browse_returns_updated_at(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="updated_at_browse")
    mem_id = store.store(content="Will be updated", tags=["test"])
    store.update(mem_id, content="Updated content")

    results, total = store.browse()
    assert total == 1
    assert "updated_at" in results[0]
    assert results[0]["updated_at"] != ""


def test_update_nonexistent_memory_raises(tmp_data_dir):
    store = MemoryStore(data_dir=tmp_data_dir, project="update_missing")
    with pytest.raises(ValueError, match="not found"):
        store.update("nonexistent-id", content="Should fail")


def test_search_with_after_filter(tmp_data_dir):
    from datetime import datetime, timezone, timedelta
    store = MemoryStore(data_dir=tmp_data_dir, project="temporal")

    store.store(content="Old decision about auth", tags=["decision"])
    store.store(content="New decision about billing", tags=["decision"])

    # After tomorrow — should find nothing
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    results = store.search("decision", after=tomorrow)
    assert len(results) == 0

    # After yesterday — should find both
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    results = store.search("decision", after=yesterday)
    assert len(results) == 2


def test_search_with_before_filter(tmp_data_dir):
    from datetime import datetime, timezone, timedelta
    store = MemoryStore(data_dir=tmp_data_dir, project="temporal2")

    store.store(content="Some memory", tags=["test"])

    # Before yesterday — should find nothing
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    results = store.search("memory", before=yesterday)
    assert len(results) == 0

    # Before tomorrow — should find it
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    results = store.search("memory", before=tomorrow)
    assert len(results) == 1


def test_search_with_after_and_before(tmp_data_dir):
    from datetime import datetime, timezone, timedelta
    store = MemoryStore(data_dir=tmp_data_dir, project="temporal3")

    store.store(content="Memory in range", tags=["test"])

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    results = store.search("Memory", after=yesterday, before=tomorrow)
    assert len(results) == 1


def test_browse_offset_limit_pages_correctly(tmp_data_dir):
    """browse should return correct pages using offset and limit."""
    store = MemoryStore(data_dir=tmp_data_dir, project="paginate")
    for i in range(10):
        store.store(content=f"Memory number {i}", tags=["test"])

    page1, total = store.browse(offset=0, limit=3)
    assert len(page1) == 3
    assert total == 10

    page2, total = store.browse(offset=3, limit=3)
    assert len(page2) == 3
    assert total == 10

    # Pages should have different items
    ids1 = {r["id"] for r in page1}
    ids2 = {r["id"] for r in page2}
    assert ids1.isdisjoint(ids2)


def test_search_before_date_only_includes_full_day(tmp_data_dir):
    """before='2026-02-21' should include memories created on 2026-02-21."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    store = MemoryStore(data_dir=tmp_data_dir, project="date_edge")
    # Store a memory with a known timestamp mid-day
    with patch("annal.store.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 21, 14, 30, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        store.store(content="Created on Feb 21 afternoon", tags=["test"])

    # before='2026-02-21' (date only) should include it
    results = store.search("Feb 21", before="2026-02-21")
    assert len(results) == 1

    # after='2026-02-21' (date only) should also include it
    results = store.search("Feb 21", after="2026-02-21")
    assert len(results) == 1


def test_search_rejects_invalid_date_format(tmp_data_dir):
    """Non-ISO-8601 date strings should not silently produce wrong results."""
    store = MemoryStore(data_dir=tmp_data_dir, project="date_validate")
    store.store(content="Some memory", tags=["test"])

    # These should return empty results (invalid date = no valid filter = return nothing)
    results = store.search("memory", after="yesterday")
    assert len(results) == 0

    results = store.search("memory", before="not-a-date")
    assert len(results) == 0


def test_search_json_empty_results(tmp_data_dir):
    """search with no results returns empty list."""
    store = MemoryStore(data_dir=tmp_data_dir, project="json_empty")
    # Don't store anything — collection is empty
    results = store.search("anything", limit=5)
    assert results == []


def test_search_combined_tags_and_temporal(tmp_data_dir):
    """Tags and temporal filters should compose correctly."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    store = MemoryStore(data_dir=tmp_data_dir, project="combined")

    # Store memories with different tags and simulated timestamps
    with patch("annal.store.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 15, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        store.store(content="Old billing decision", tags=["billing", "decision"])

    with patch("annal.store.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 15, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        store.store(content="New billing decision", tags=["billing", "decision"])

    with patch("annal.store.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 2, 15, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        store.store(content="New auth pattern", tags=["auth", "pattern"])

    # Tags=billing AND after=Feb 1 should return only the new billing decision
    results = store.search("decision", tags=["billing"], after="2026-02-01")
    assert len(results) == 1
    assert "New billing" in results[0]["content"]


def test_search_overfetch_with_tag_filter(tmp_data_dir):
    """With many memories, tag filtering should still return correct results."""
    store = MemoryStore(data_dir=tmp_data_dir, project="overfetch")

    # Store 15 memories with "noise" tag and 3 with "signal" tag
    # Total = 18, overfetch = max(5*3, 20) = 20, so all should be retrieved
    for i in range(15):
        store.store(content=f"Noise memory about topic {i}", tags=["noise"])
    for i in range(3):
        store.store(content=f"Signal memory about finding {i}", tags=["signal"])

    results = store.search("memory", tags=["signal"], limit=5)
    assert len(results) == 3
    assert all("Signal" in r["content"] for r in results)


def test_fuzzy_tag_matching(tmp_data_dir):
    """Searching with tags=['auth'] should find memories tagged 'authentication'."""
    store = MemoryStore(data_dir=tmp_data_dir, project="fuzzy_tags")
    store.store(content="Auth decision about JWT tokens", tags=["authentication", "decision"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("decision", tags=["auth"], limit=5)
    assert len(results) == 1
    assert "JWT" in results[0]["content"]


def test_fuzzy_tag_no_false_positives(tmp_data_dir):
    """Fuzzy matching should not match unrelated tags."""
    store = MemoryStore(data_dir=tmp_data_dir, project="fuzzy_strict")
    store.store(content="Caching layer uses Redis", tags=["caching", "infrastructure"])
    store.store(content="Auth uses OAuth", tags=["authentication"])

    # 'auth' should match 'authentication' but not 'caching'
    results = store.search("uses", tags=["auth"], limit=5)
    assert len(results) == 1
    assert "OAuth" in results[0]["content"]


def test_fuzzy_tag_exact_still_works(tmp_data_dir):
    """Exact tag matches should still work."""
    store = MemoryStore(data_dir=tmp_data_dir, project="fuzzy_exact")
    store.store(content="Billing uses Stripe", tags=["billing"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("uses", tags=["billing"], limit=5)
    assert len(results) == 1
    assert "Stripe" in results[0]["content"]


def test_fuzzy_tag_in_browse(tmp_data_dir):
    """browse() with tags should also use fuzzy matching."""
    store = MemoryStore(data_dir=tmp_data_dir, project="fuzzy_browse")
    store.store(content="Auth decision", tags=["authentication"])
    store.store(content="Frontend stuff", tags=["frontend"])

    results, total = store.browse(tags=["auth"])
    assert total == 1
    assert "Auth" in results[0]["content"]


def test_search_across_projects(tmp_data_dir):
    """Searching across multiple projects returns results from each."""
    store_a = MemoryStore(data_dir=tmp_data_dir, project="project_a")
    store_b = MemoryStore(data_dir=tmp_data_dir, project="project_b")

    store_a.store(content="Auth uses JWT in project A", tags=["auth"])
    store_b.store(content="Auth uses OAuth in project B", tags=["auth"])

    # Search each individually
    results_a = store_a.search("auth", limit=5)
    results_b = store_b.search("auth", limit=5)
    assert len(results_a) == 1
    assert len(results_b) == 1
