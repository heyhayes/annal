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
