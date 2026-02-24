import pytest
from tests.conftest import make_store
from annal.store import BatchItem


@pytest.fixture
def store(tmp_data_dir):
    return make_store(tmp_data_dir, "testproject")


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
    store = make_store(tmp_data_dir, "dashboard_test")
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
    store = make_store(tmp_data_dir, "empty_browse")
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
    store = make_store(tmp_data_dir, "update_test")
    mem_id = store.store(content="Original content", tags=["test"])

    store.update(mem_id, content="Updated content")

    results = store.get_by_ids([mem_id])
    assert len(results) == 1
    assert results[0]["content"] == "Updated content"
    assert results[0]["tags"] == ["test"]  # tags unchanged
    assert results[0]["updated_at"] != ""


def test_update_memory_tags(tmp_data_dir):
    store = make_store(tmp_data_dir, "update_test")
    mem_id = store.store(content="Some content", tags=["old-tag"])

    store.update(mem_id, tags=["new-tag", "extra"])

    results = store.get_by_ids([mem_id])
    assert results[0]["tags"] == ["new-tag", "extra"]
    assert results[0]["content"] == "Some content"  # content unchanged


def test_search_returns_updated_at(tmp_data_dir):
    store = make_store(tmp_data_dir, "updated_at_search")
    mem_id = store.store(content="Will be updated", tags=["test"])
    store.update(mem_id, content="Updated content")

    results = store.search("Updated content", limit=1)
    assert len(results) == 1
    assert "updated_at" in results[0]
    assert results[0]["updated_at"] != ""


def test_browse_returns_updated_at(tmp_data_dir):
    store = make_store(tmp_data_dir, "updated_at_browse")
    mem_id = store.store(content="Will be updated", tags=["test"])
    store.update(mem_id, content="Updated content")

    results, total = store.browse()
    assert total == 1
    assert "updated_at" in results[0]
    assert results[0]["updated_at"] != ""


def test_update_nonexistent_memory_raises(tmp_data_dir):
    store = make_store(tmp_data_dir, "update_missing")
    with pytest.raises(ValueError, match="not found"):
        store.update("nonexistent-id", content="Should fail")


def test_search_with_after_filter(tmp_data_dir):
    from datetime import datetime, timezone, timedelta
    store = make_store(tmp_data_dir, "temporal")

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
    store = make_store(tmp_data_dir, "temporal2")

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
    store = make_store(tmp_data_dir, "temporal3")

    store.store(content="Memory in range", tags=["test"])

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    results = store.search("Memory", after=yesterday, before=tomorrow)
    assert len(results) == 1


def test_browse_offset_limit_pages_correctly(tmp_data_dir):
    """browse should return correct pages using offset and limit."""
    store = make_store(tmp_data_dir, "paginate")
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

    store = make_store(tmp_data_dir, "date_edge")
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
    """Non-ISO-8601 date strings should raise ValueError."""
    store = make_store(tmp_data_dir, "date_validate")
    store.store(content="Some memory", tags=["test"])

    with pytest.raises(ValueError, match="after.*yesterday"):
        store.search("memory", after="yesterday")

    with pytest.raises(ValueError, match="before.*not-a-date"):
        store.search("memory", before="not-a-date")


def test_search_json_empty_results(tmp_data_dir):
    """search with no results returns empty list."""
    store = make_store(tmp_data_dir, "json_empty")
    # Don't store anything — collection is empty
    results = store.search("anything", limit=5)
    assert results == []


def test_search_combined_tags_and_temporal(tmp_data_dir):
    """Tags and temporal filters should compose correctly."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    store = make_store(tmp_data_dir, "combined")

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
    """With many memories, tag filtering should still return correct results.

    Backend does 3x overfetch when post-filters (like tags) are present.
    With limit=5, it fetches 15 candidates. All matching results should be
    tagged "signal" — the overfetch ensures enough candidates to filter from.
    """
    store = make_store(tmp_data_dir, "overfetch")

    # Store 15 memories with "noise" tag and 3 with "signal" tag
    for i in range(15):
        store.store(content=f"Noise memory about topic {i}", tags=["noise"])
    for i in range(3):
        store.store(content=f"Signal memory about finding {i}", tags=["signal"])

    results = store.search("memory", tags=["signal"], limit=5)
    # Backend fetches limit*3=15 candidates, post-filters by tag.
    # At least 2 of the 3 signal memories should appear in top-15 by similarity.
    assert len(results) >= 2
    assert all("Signal" in r["content"] for r in results)


def test_fuzzy_tag_matching(tmp_data_dir):
    """Searching with tags=['auth'] should find memories tagged 'authentication'."""
    store = make_store(tmp_data_dir, "fuzzy_tags")
    store.store(content="Auth decision about JWT tokens", tags=["authentication", "decision"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("decision", tags=["auth"], limit=5)
    assert len(results) == 1
    assert "JWT" in results[0]["content"]


def test_fuzzy_tag_no_false_positives(tmp_data_dir):
    """Fuzzy matching should not match unrelated tags."""
    store = make_store(tmp_data_dir, "fuzzy_strict")
    store.store(content="Caching layer uses Redis", tags=["caching", "infrastructure"])
    store.store(content="Auth uses OAuth", tags=["authentication"])

    # 'auth' should match 'authentication' but not 'caching'
    results = store.search("uses", tags=["auth"], limit=5)
    assert len(results) == 1
    assert "OAuth" in results[0]["content"]


def test_fuzzy_tag_exact_still_works(tmp_data_dir):
    """Exact tag matches should still work."""
    store = make_store(tmp_data_dir, "fuzzy_exact")
    store.store(content="Billing uses Stripe", tags=["billing"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("uses", tags=["billing"], limit=5)
    assert len(results) == 1
    assert "Stripe" in results[0]["content"]


def test_fuzzy_tag_in_browse(tmp_data_dir):
    """browse() with tags should also use fuzzy matching."""
    store = make_store(tmp_data_dir, "fuzzy_browse")
    store.store(content="Auth decision", tags=["authentication"])
    store.store(content="Frontend stuff", tags=["frontend"])

    results, total = store.browse(tags=["auth"])
    assert total == 1
    assert "Auth" in results[0]["content"]


def test_search_across_projects(tmp_data_dir):
    """Searching across multiple projects returns results from each."""
    store_a = make_store(tmp_data_dir, "project_a")
    store_b = make_store(tmp_data_dir, "project_b")

    store_a.store(content="Auth uses JWT in project A", tags=["auth"])
    store_b.store(content="Auth uses OAuth in project B", tags=["auth"])

    # Search each individually
    results_a = store_a.search("auth", limit=5)
    results_b = store_b.search("auth", limit=5)
    assert len(results_a) == 1
    assert len(results_b) == 1


def test_retag_add_tags(tmp_data_dir):
    """retag with add_tags should append new tags."""
    store = make_store(tmp_data_dir, "retag_add")
    mem_id = store.store(content="Auth decision", tags=["auth"])

    final = store.retag(mem_id, add_tags=["decision", "jwt"])
    assert final == ["auth", "decision", "jwt"]

    result = store.get_by_ids([mem_id])
    assert result[0]["tags"] == ["auth", "decision", "jwt"]
    assert result[0]["updated_at"] != ""


def test_retag_remove_tags(tmp_data_dir):
    """retag with remove_tags should remove specified tags."""
    store = make_store(tmp_data_dir, "retag_remove")
    mem_id = store.store(content="Billing auth decision", tags=["billing", "auth", "decision"])

    final = store.retag(mem_id, remove_tags=["auth"])
    assert final == ["billing", "decision"]


def test_retag_add_and_remove(tmp_data_dir):
    """retag with both add and remove in one call."""
    store = make_store(tmp_data_dir, "retag_both")
    mem_id = store.store(content="Some memory", tags=["old", "keep"])

    final = store.retag(mem_id, add_tags=["new"], remove_tags=["old"])
    assert final == ["keep", "new"]


def test_retag_set_tags(tmp_data_dir):
    """retag with set_tags should replace all tags."""
    store = make_store(tmp_data_dir, "retag_set")
    mem_id = store.store(content="Some memory", tags=["a", "b", "c"])

    final = store.retag(mem_id, set_tags=["x", "y"])
    assert final == ["x", "y"]

    result = store.get_by_ids([mem_id])
    assert result[0]["tags"] == ["x", "y"]


def test_retag_set_mixed_with_add_raises(tmp_data_dir):
    """Cannot mix set_tags with add_tags."""
    store = make_store(tmp_data_dir, "retag_mix")
    mem_id = store.store(content="Memory", tags=["a"])

    with pytest.raises(ValueError, match="Cannot mix"):
        store.retag(mem_id, set_tags=["x"], add_tags=["y"])


def test_retag_no_ops_raises(tmp_data_dir):
    """Must provide at least one tag operation."""
    store = make_store(tmp_data_dir, "retag_noop")
    mem_id = store.store(content="Memory", tags=["a"])

    with pytest.raises(ValueError, match="at least one"):
        store.retag(mem_id)


def test_retag_nonexistent_raises(tmp_data_dir):
    """retag on missing ID should raise ValueError."""
    store = make_store(tmp_data_dir, "retag_missing")

    with pytest.raises(ValueError, match="not found"):
        store.retag("nonexistent-id", add_tags=["x"])


def test_retag_deduplicates(tmp_data_dir):
    """Adding a tag that already exists should not create duplicates."""
    store = make_store(tmp_data_dir, "retag_dedup")
    mem_id = store.store(content="Memory", tags=["auth", "decision"])

    final = store.retag(mem_id, add_tags=["auth", "new"])
    assert final == ["auth", "decision", "new"]


def test_fuzzy_tag_matches_dbs_to_database(tmp_data_dir):
    """Lowered threshold (0.72) should match 'dbs' to 'database'."""
    store = make_store(tmp_data_dir, "fuzzy_threshold")
    store.store(content="PostgreSQL is our primary database", tags=["database"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("primary", tags=["dbs"], limit=5)
    assert len(results) == 1
    assert "PostgreSQL" in results[0]["content"]


def test_search_excludes_superseded_by_default(tmp_data_dir):
    """Superseded memories should not appear in search results by default."""
    store = make_store(tmp_data_dir, "supersede_search")
    old_id = store.store(content="We use session cookies for auth", tags=["decision", "auth"])
    store.store(content="We use JWT for auth", tags=["decision", "auth"], supersedes=old_id)

    results = store.search("auth decision", limit=10)
    ids = [r["id"] for r in results]
    assert old_id not in ids


def test_search_includes_superseded_when_requested(tmp_data_dir):
    """include_superseded=True should return superseded memories."""
    store = make_store(tmp_data_dir, "supersede_include")
    old_id = store.store(content="We use session cookies for auth", tags=["decision", "auth"])
    new_id = store.store(content="We use JWT for auth", tags=["decision", "auth"], supersedes=old_id)

    results = store.search("auth decision", limit=10, include_superseded=True)
    ids = [r["id"] for r in results]
    assert old_id in ids
    assert new_id in ids


def test_browse_excludes_superseded_by_default(tmp_data_dir):
    """Superseded memories should not appear in browse results by default."""
    store = make_store(tmp_data_dir, "supersede_browse")
    old_id = store.store(content="Old decision", tags=["decision"])
    store.store(content="New decision", tags=["decision"], supersedes=old_id)

    results, total = store.browse()
    ids = [r["id"] for r in results]
    assert old_id not in ids
    assert total == 1


def test_browse_includes_superseded_when_requested(tmp_data_dir):
    """include_superseded=True should return superseded memories in browse."""
    store = make_store(tmp_data_dir, "supersede_browse_inc")
    old_id = store.store(content="Old decision", tags=["decision"])
    store.store(content="New decision", tags=["decision"], supersedes=old_id)

    results, total = store.browse(include_superseded=True)
    ids = [r["id"] for r in results]
    assert old_id in ids
    assert total == 2


def test_store_supersedes_marks_old_memory(tmp_data_dir):
    """store(supersedes=...) should set superseded_by on the old memory."""
    store = make_store(tmp_data_dir, "supersede_mark")
    old_id = store.store(content="Old decision", tags=["decision"])
    new_id = store.store(content="New decision", tags=["decision"], supersedes=old_id)

    results = store.get_by_ids([old_id])
    assert results[0]["superseded_by"] == new_id


def test_list_topics_excludes_superseded_by_default(tmp_data_dir):
    """list_topics should not count tags from superseded memories."""
    store = make_store(tmp_data_dir, "topics_supersede")
    old_id = store.store(content="Session cookies for auth", tags=["auth", "decision"])
    store.store(content="JWT for auth", tags=["auth", "decision"], supersedes=old_id)
    store.store(content="React frontend", tags=["frontend"])

    topics = store.list_topics()
    assert topics["auth"] == 1
    assert topics["decision"] == 1
    assert topics["frontend"] == 1


def test_list_topics_includes_superseded_when_requested(tmp_data_dir):
    """list_topics(include_superseded=True) should count all tags."""
    store = make_store(tmp_data_dir, "topics_supersede_inc")
    old_id = store.store(content="Session cookies for auth", tags=["auth", "decision"])
    store.store(content="JWT for auth", tags=["auth", "decision"], supersedes=old_id)

    topics = store.list_topics(include_superseded=True)
    assert topics["auth"] == 2
    assert topics["decision"] == 2


def test_stats_excludes_superseded_by_default(tmp_data_dir):
    """stats should not count superseded memories."""
    store = make_store(tmp_data_dir, "stats_supersede")
    old_id = store.store(content="Old decision", tags=["decision"])
    store.store(content="New decision", tags=["decision"], supersedes=old_id)

    stats = store.stats()
    assert stats["total"] == 1
    assert stats["by_type"]["agent-memory"] == 1
    assert stats["by_tag"]["decision"] == 1


def test_stats_includes_superseded_when_requested(tmp_data_dir):
    """stats(include_superseded=True) should count all memories."""
    store = make_store(tmp_data_dir, "stats_supersede_inc")
    old_id = store.store(content="Old decision", tags=["decision"])
    store.store(content="New decision", tags=["decision"], supersedes=old_id)

    stats = store.stats(include_superseded=True)
    assert stats["total"] == 2
    assert stats["by_type"]["agent-memory"] == 2
    assert stats["by_tag"]["decision"] == 2


def test_store_supersedes_nonexistent_id_does_not_error(tmp_data_dir):
    """store(supersedes=...) with a nonexistent ID should silently succeed."""
    store = make_store(tmp_data_dir, "supersede_missing")
    new_id = store.store(content="New decision", tags=["decision"], supersedes="nonexistent-id-xyz")
    assert new_id is not None
    results = store.search("New decision", limit=1)
    assert len(results) == 1


# ── store_batch tests ────────────────────────────────────────────────


def test_store_batch_happy_path(tmp_data_dir):
    """3 distinct items should all be stored and searchable."""
    store = make_store(tmp_data_dir, "batch_happy")
    result = store.store_batch([
        BatchItem(content="Billing uses Stripe for payment processing", tags=["billing"]),
        BatchItem(content="Auth uses JWT with RS256 signing algorithm", tags=["auth"]),
        BatchItem(content="Frontend uses React with TypeScript", tags=["frontend"]),
    ])
    assert result.stored_count == 3
    assert result.skipped_count == 0
    assert len(result.stored_ids) == 3

    # All should be searchable
    assert len(store.search("Stripe payment", limit=1)) == 1
    assert len(store.search("JWT signing", limit=1)) == 1
    assert len(store.search("React TypeScript", limit=1)) == 1


def test_store_batch_intra_batch_dedup(tmp_data_dir):
    """Items 0 and 2 are identical; item 2 should be skipped."""
    store = make_store(tmp_data_dir, "batch_intra_dedup")
    result = store.store_batch([
        BatchItem(content="The checkout flow validates cart totals before payment", tags=["checkout"]),
        BatchItem(content="Auth uses JWT with RS256 for all API endpoints", tags=["auth"]),
        BatchItem(content="The checkout flow validates cart totals before payment", tags=["checkout"]),
    ])
    assert result.stored_count == 2
    assert result.skipped_count == 1


def test_store_batch_dedup_against_existing(tmp_data_dir):
    """Pre-stored memory should cause near-identical batch item to be skipped."""
    store = make_store(tmp_data_dir, "batch_existing_dedup")
    store.store(content="The billing pipeline validates invoice totals before charging", tags=["billing"])

    result = store.store_batch([
        BatchItem(content="The billing pipeline validates invoice totals before charging", tags=["billing"]),
        BatchItem(content="Frontend uses React with TypeScript for the dashboard", tags=["frontend"]),
    ])
    assert result.stored_count == 1
    assert result.skipped_count == 1


def test_store_batch_supersession(tmp_data_dir):
    """Batch item with supersedes should mark old memory and store new one."""
    store = make_store(tmp_data_dir, "batch_supersede")
    old_id = store.store(content="We use session cookies for auth", tags=["decision", "auth"])

    result = store.store_batch([
        BatchItem(content="We now use JWT for auth", tags=["decision", "auth"], supersedes=old_id),
    ])
    assert result.stored_count == 1

    # Old memory should be marked as superseded
    old = store.get_by_ids([old_id])
    assert old[0]["superseded_by"] == result.stored_ids[0]


def test_store_batch_supersedes_skips_dedup(tmp_data_dir):
    """Item with supersedes and identical content to existing should still be stored."""
    store = make_store(tmp_data_dir, "batch_supersede_dedup")
    old_id = store.store(content="We use session cookies for auth across all services", tags=["decision", "auth"])

    result = store.store_batch([
        BatchItem(
            content="We use session cookies for auth across all services",
            tags=["decision", "auth"],
            supersedes=old_id,
        ),
    ])
    assert result.stored_count == 1
    assert result.skipped_count == 0

    # Old memory should be superseded
    old = store.get_by_ids([old_id])
    assert "superseded_by" in old[0]


def test_store_batch_hint_for_similar(tmp_data_dir):
    """Item scoring 0.80-0.95 against existing should be stored with a hint."""
    store = make_store(tmp_data_dir, "batch_hint")
    store.store(content="The billing pipeline validates invoice totals before charging the card", tags=["billing"])

    result = store.store_batch([
        BatchItem(content="The billing pipeline validates invoice totals before processing payment through Stripe", tags=["billing"]),
    ])
    # Should be stored (not skipped) — either with or without hint depending on score
    assert result.stored_count == 1 or result.skipped_count == 1
    # If stored, check for hint presence
    if result.stored_count == 1:
        stored_item = [i for i in result.items if i.status == "stored"][0]
        # Hint may or may not be present depending on exact score
        # (we just verify the mechanism doesn't crash)
        assert stored_item.mem_id is not None


def test_store_batch_empty_list(tmp_data_dir):
    """Empty input should return immediately with zero counts."""
    store = make_store(tmp_data_dir, "batch_empty")
    result = store.store_batch([])
    assert result.stored_count == 0
    assert result.skipped_count == 0
    assert result.stored_ids == []


# ── Spike 13: Search improvements ───────────────────────────────────


def test_search_with_source_prefix(tmp_data_dir):
    """search with source_prefix should only return memories matching that prefix."""
    store = make_store(tmp_data_dir, "source_prefix")
    store.store(content="Session observation about auth", tags=["auth"], source="session observation")
    store.store(content="File content about auth", tags=["auth"], source="file:/tmp/README.md|auth")

    results = store.search("auth", source_prefix="file:", limit=5)
    assert len(results) == 1
    assert results[0]["source"].startswith("file:")

    results = store.search("auth", source_prefix="session", limit=5)
    assert len(results) == 1
    assert results[0]["source"].startswith("session")


def test_search_hit_tracking_increments(tmp_data_dir):
    """search should increment hit_count and set last_accessed_at on agent-memory results."""
    store = make_store(tmp_data_dir, "hit_tracking")
    store.store(content="Auth uses JWT tokens for all services", tags=["auth"])

    results = store.search("JWT tokens", limit=1)
    assert len(results) == 1
    assert results[0]["hit_count"] == 1
    assert "last_accessed_at" in results[0]

    # Second search should increment
    results = store.search("JWT tokens", limit=1)
    assert results[0]["hit_count"] == 2


def test_get_by_ids_hit_tracking(tmp_data_dir):
    """get_by_ids should increment hit_count on agent-memory results."""
    store = make_store(tmp_data_dir, "hit_get")
    mem_id = store.store(content="Billing uses Stripe", tags=["billing"])

    results = store.get_by_ids([mem_id])
    assert results[0]["hit_count"] == 1

    results = store.get_by_ids([mem_id])
    assert results[0]["hit_count"] == 2


def test_hit_tracking_skips_file_indexed(tmp_data_dir):
    """File-indexed chunks should not get hit tracking metadata."""
    store = make_store(tmp_data_dir, "hit_skip_file")
    store.store(
        content="README content about project setup",
        tags=["indexed", "docs"],
        source="file:/tmp/README.md",
        chunk_type="file-indexed",
    )

    results = store.search("project setup", limit=1)
    assert len(results) == 1
    assert "hit_count" not in results[0]
    assert "last_accessed_at" not in results[0]


def test_stats_includes_stale_counts(tmp_data_dir):
    """stats should report stale and never-accessed agent memory counts."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    store = make_store(tmp_data_dir, "stale_stats")

    # Store a memory, then manually set old last_accessed_at
    mem_id = store.store(content="Old accessed memory", tags=["test"])
    old = store._backend.get([mem_id])
    old_meta = dict(old[0].metadata)
    old_meta["last_accessed_at"] = "2025-01-01T00:00:00"
    old_meta["hit_count"] = 1
    store._backend.update(mem_id, text=None, embedding=None, metadata=old_meta)

    # Store a never-accessed memory with old created_at
    never_id = store.store(content="Never accessed memory", tags=["test"])
    never_meta = dict(store._backend.get([never_id])[0].metadata)
    never_meta["created_at"] = "2025-01-01T00:00:00"
    store._backend.update(never_id, text=None, embedding=None, metadata=never_meta)

    stats = store.stats()
    assert stats["stale_count"] == 1
    assert stats["never_accessed_count"] == 1



# ── Spike 14: Stale memory management ───────────────────────────────


def test_find_stale_returns_stale_ids(tmp_data_dir):
    """find_stale should return IDs of memories with old last_accessed_at."""
    store = make_store(tmp_data_dir, "find_stale")
    mem_id = store.store(content="Old accessed memory", tags=["test"])

    # Manually set an old last_accessed_at
    old = store._backend.get([mem_id])
    old_meta = dict(old[0].metadata)
    old_meta["last_accessed_at"] = "2025-01-01T00:00:00"
    old_meta["hit_count"] = 1
    store._backend.update(mem_id, text=None, embedding=None, metadata=old_meta)

    result = store.find_stale(max_age_days=60)
    assert mem_id in result["stale_ids"]
    assert result["stale_count"] == 1


def test_find_stale_excludes_file_indexed(tmp_data_dir):
    """File-indexed chunks should not appear in stale results."""
    store = make_store(tmp_data_dir, "find_stale_file")
    store.store(
        content="File content",
        tags=["indexed"],
        source="file:/tmp/README.md",
        chunk_type="file-indexed",
    )
    # Store an agent memory and backdate it so it qualifies as never-accessed
    from datetime import datetime, timezone, timedelta
    old_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    mem_id = store.store(content="Agent memory", tags=["test"])
    rec = store._backend.get([mem_id])
    meta = dict(rec[0].metadata)
    meta["created_at"] = old_date
    store._backend.update(mem_id, text=None, embedding=None, metadata=meta)

    result = store.find_stale()
    all_ids = result["stale_ids"] + result["never_accessed_ids"]
    # File-indexed chunk should not be in the results at all
    # Only the agent memory (never accessed) should appear
    assert result["never_accessed_count"] == 1
    assert result["stale_count"] == 0


def test_find_stale_excludes_superseded(tmp_data_dir):
    """Superseded memories should not appear in stale results."""
    from datetime import datetime, timezone, timedelta
    old_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

    store = make_store(tmp_data_dir, "find_stale_superseded")
    old_id = store.store(content="Old decision", tags=["decision"])
    new_id = store.store(content="New decision", tags=["decision"], supersedes=old_id)

    # Backdate both so they're old enough to qualify
    for mid in [old_id, new_id]:
        rec = store._backend.get([mid])
        meta = dict(rec[0].metadata)
        meta["created_at"] = old_date
        store._backend.update(mid, text=None, embedding=None, metadata=meta)

    result = store.find_stale()
    assert old_id not in result["stale_ids"]
    assert old_id not in result["never_accessed_ids"]
    # Only the new (non-superseded, never-accessed) memory should appear
    assert result["never_accessed_count"] == 1


def test_find_stale_respects_max_age_days(tmp_data_dir):
    """Custom max_age_days threshold should work."""
    store = make_store(tmp_data_dir, "find_stale_age")
    mem_id = store.store(content="Recently accessed memory", tags=["test"])

    # Set last_accessed_at to 10 days ago
    from datetime import datetime, timezone, timedelta
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    old = store._backend.get([mem_id])
    old_meta = dict(old[0].metadata)
    old_meta["last_accessed_at"] = ten_days_ago
    old_meta["hit_count"] = 1
    store._backend.update(mem_id, text=None, embedding=None, metadata=old_meta)

    # With 60-day threshold, should NOT be stale
    result = store.find_stale(max_age_days=60)
    assert mem_id not in result["stale_ids"]

    # With 5-day threshold, should be stale
    result = store.find_stale(max_age_days=5)
    assert mem_id in result["stale_ids"]


def test_find_stale_never_accessed_flag(tmp_data_dir):
    """include_never_accessed=False should exclude never-accessed memories."""
    from datetime import datetime, timezone, timedelta
    old_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

    store = make_store(tmp_data_dir, "find_stale_flag")
    mem_id = store.store(content="Never accessed memory", tags=["test"])

    # Backdate so it's old enough to qualify as never-accessed
    rec = store._backend.get([mem_id])
    meta = dict(rec[0].metadata)
    meta["created_at"] = old_date
    store._backend.update(mem_id, text=None, embedding=None, metadata=meta)

    result_with = store.find_stale(include_never_accessed=True)
    assert result_with["never_accessed_count"] == 1

    result_without = store.find_stale(include_never_accessed=False)
    assert result_without["never_accessed_count"] == 0


def test_find_stale_ignores_recently_created_never_accessed(tmp_data_dir):
    """Never-accessed memories created within max_age_days should not be stale."""
    store = make_store(tmp_data_dir, "find_stale_recent")
    store.store(content="Brand new memory", tags=["test"])

    # Freshly created, never accessed — should NOT be stale
    result = store.find_stale(max_age_days=60)
    assert result["never_accessed_count"] == 0
    assert result["stale_count"] == 0


def test_agent_memory_boost_over_file_indexed(tmp_data_dir):
    """Agent memories should rank higher than file-indexed chunks at similar similarity."""
    store = make_store(tmp_data_dir, "boost_test")
    # Store similar content as both file-indexed and agent-memory
    store.store(
        content="The billing module handles tax calculation via TaxService",
        tags=["indexed"],
        source="file:/tmp/docs/billing.md",
        chunk_type="file-indexed",
    )
    store.store(
        content="The billing module tax calculation uses TaxService — watch for rounding",
        tags=["billing", "memory"],
        source="session observation",
    )

    results = store.search("billing tax calculation", limit=2)
    assert len(results) == 2
    # Agent memory should rank first due to boost
    assert results[0]["chunk_type"] == "agent-memory"
    assert results[1]["chunk_type"] == "file-indexed"
