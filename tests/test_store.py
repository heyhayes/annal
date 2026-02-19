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
