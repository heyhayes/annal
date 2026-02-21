import os
import pytest
from annal.config import AnnalConfig
from tests.conftest import make_store
from annal.watcher import FileWatcher


def test_full_workflow(tmp_data_dir, tmp_config_path, tmp_path):
    """Test the complete flow: config -> index files -> store memories -> search."""
    # 1. Create project files
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "CLAUDE.md").write_text(
        "# Project Rules\n\nAlways use TypeScript.\n\n"
        "## Testing\n\nRun tests with `npm test`.\n"
    )
    (project_dir / "AGENT.md").write_text(
        "# Agent Config\n\nBackend is PHP Laravel.\nFrontend is React.\n"
    )

    # 2. Create config
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={},
    )
    config.add_project("myproject", watch_paths=[str(project_dir)])
    config.save()

    # 3. Create store and reconcile
    store = make_store(tmp_data_dir,"myproject")
    proj_config = config.get_project("myproject")
    watcher = FileWatcher(store=store, project_config=proj_config)
    file_count = watcher.reconcile()
    assert file_count == 2  # CLAUDE.md + AGENT.md

    # 4. Search indexed content
    results = store.search("how to run tests", limit=3)
    assert len(results) > 0
    assert any("npm test" in r["content"] for r in results)

    # 5. Store an agent memory
    store.store(
        content="The pricing calculation has a timezone bug in CalculateSeasonPrice",
        tags=["billing", "bugs"],
        source="debugging session",
    )

    # 6. Search combines file-indexed and agent memories
    results = store.search("pricing calculation", limit=5)
    assert any("timezone bug" in r["content"] for r in results)

    # 7. Topic listing includes both sources
    topics = store.list_topics()
    assert "billing" in topics
    assert "indexed" in topics  # from file indexing
