import os
import time
import pytest
from pathlib import Path
from annal.watcher import FileWatcher, matches_patterns
from annal.store import MemoryStore
from annal.config import ProjectConfig


def test_matches_patterns():
    assert matches_patterns("docs/README.md", ["**/*.md"], []) is True
    assert matches_patterns("docs/README.md", ["**/*.yaml"], []) is False
    assert matches_patterns("node_modules/pkg/README.md", ["**/*.md"], ["node_modules/**"]) is False
    assert matches_patterns("src/config.yaml", ["**/*.yaml", "**/*.md"], []) is True


def test_reconcile_indexes_new_files(tmp_data_dir, tmp_path):
    # Create a markdown file
    md_file = tmp_path / "test.md"
    md_file.write_text("# Hello\nWorld\n")

    store = MemoryStore(data_dir=tmp_data_dir, project="testproject")
    project_config = ProjectConfig(
        watch_paths=[str(tmp_path)],
        watch_patterns=["**/*.md"],
    )

    watcher = FileWatcher(store=store, project_config=project_config)
    count1 = watcher.reconcile()
    assert count1 == 1

    assert store.count() == 1
    results = store.search("Hello World", limit=1)
    assert len(results) == 1

    # Second reconcile should skip unchanged files
    count2 = watcher.reconcile()
    assert count2 == 0
    assert store.count() == 1


def test_reconcile_skips_excluded_dirs(tmp_data_dir, tmp_path):
    # Create a file in an excluded directory
    excluded = tmp_path / "node_modules" / "pkg"
    excluded.mkdir(parents=True)
    (excluded / "README.md").write_text("# Should be ignored\n")

    # And a non-excluded file
    (tmp_path / "docs.md").write_text("# Should be indexed\n")

    store = MemoryStore(data_dir=tmp_data_dir, project="testproject")
    project_config = ProjectConfig(
        watch_paths=[str(tmp_path)],
        watch_patterns=["**/*.md"],
        watch_exclude=["node_modules/**"],
    )

    watcher = FileWatcher(store=store, project_config=project_config)
    watcher.reconcile()

    assert store.count() == 1
