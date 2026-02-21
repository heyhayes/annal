import os
import time
import pytest
from pathlib import Path
from annal.watcher import FileWatcher, matches_patterns
from tests.conftest import make_store
from annal.config import ProjectConfig


def test_matches_patterns():
    assert matches_patterns("docs/README.md", ["**/*.md"], []) is True
    assert matches_patterns("docs/README.md", ["**/*.yaml"], []) is False
    assert matches_patterns("node_modules/pkg/README.md", ["**/*.md"], ["node_modules/**"]) is False
    assert matches_patterns("src/config.yaml", ["**/*.yaml", "**/*.md"], []) is True


def test_matches_patterns_excludes_nested_vendor():
    """Depth-independent excludes should match vendor dirs at any nesting level."""
    excludes = ["**/node_modules/**", "**/vendor/**"]
    patterns = ["**/*.md", "**/*.json"]

    # Top-level — still excluded
    assert matches_patterns("node_modules/pkg/README.md", patterns, excludes) is False
    assert matches_patterns("vendor/lib/config.json", patterns, excludes) is False

    # Nested — the whole point of this fix
    assert matches_patterns("backend/src/vendor/lib/README.md", patterns, excludes) is False
    assert matches_patterns("frontend/node_modules/react/package.json", patterns, excludes) is False

    # Non-vendor paths should still match
    assert matches_patterns("backend/src/README.md", patterns, excludes) is True
    assert matches_patterns("docs/config.json", patterns, excludes) is True


def test_reconcile_indexes_new_files(tmp_data_dir, tmp_path):
    # Create a markdown file
    md_file = tmp_path / "test.md"
    md_file.write_text("# Hello\nWorld\n")

    store = make_store(tmp_data_dir,"testproject")
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
    (excluded / "README.md").write_text("# Ignored\nThis lives in node_modules.\n")

    # And a non-excluded file
    (tmp_path / "docs.md").write_text("# Docs\nThis should be indexed.\n")

    store = make_store(tmp_data_dir,"testproject")
    project_config = ProjectConfig(
        watch_paths=[str(tmp_path)],
        watch_patterns=["**/*.md"],
        watch_exclude=["node_modules/**"],
    )

    watcher = FileWatcher(store=store, project_config=project_config)
    watcher.reconcile()

    assert store.count() == 1


def test_reconcile_survives_unreadable_file(tmp_data_dir, tmp_path):
    """reconcile() should log and skip files it cannot read, not crash."""
    good = tmp_path / "good.md"
    good.write_text("# Good file\nThis should be indexed.\n")

    bad = tmp_path / "bad.md"
    bad.write_text("# Unreadable\n")
    bad.chmod(0o000)

    store = make_store(tmp_data_dir,"testproject")
    project_config = ProjectConfig(
        watch_paths=[str(tmp_path)],
        watch_patterns=["**/*.md"],
    )

    watcher = FileWatcher(store=store, project_config=project_config)
    try:
        count = watcher.reconcile()
        assert count >= 1, "Good file should still be indexed"
    finally:
        # Restore permissions so tmp_path cleanup works
        bad.chmod(0o644)
