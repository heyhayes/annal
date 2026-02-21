"""File watcher with startup reconciliation for Annal."""

from __future__ import annotations

import fnmatch
import logging
import os
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
from watchdog.observers import Observer

from annal.config import ProjectConfig
from annal.indexer import index_file
from annal.store import MemoryStore

logger = logging.getLogger(__name__)


def matches_patterns(
    rel_path: str, patterns: list[str], excludes: list[str]
) -> bool:
    """Check if a relative path matches watch patterns and isn't excluded."""
    rel_path = rel_path.replace(os.sep, "/")

    for exclude in excludes:
        if _glob_match(rel_path, exclude):
            return False

    for pattern in patterns:
        if _glob_match(rel_path, pattern):
            return True

    return False


def _glob_match(rel_path: str, pattern: str) -> bool:
    """Match a relative path against a glob pattern with ** support."""
    # For patterns like **/*.md, match at any depth including root
    if pattern.startswith("**/"):
        suffix = pattern[3:]  # e.g. "*.md"
        # Match the full path or just the filename
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, suffix):
            return True
        # Also match any sub-path
        parts = rel_path.split("/")
        for i in range(len(parts)):
            sub = "/".join(parts[i:])
            if fnmatch.fnmatch(sub, suffix):
                return True
        return False

    # For patterns like node_modules/**, check if path starts with the prefix
    if pattern.endswith("/**"):
        prefix = pattern[:-3]  # e.g. "node_modules"
        return rel_path == prefix or rel_path.startswith(prefix + "/")

    return fnmatch.fnmatch(rel_path, pattern)


class _IndexHandler(FileSystemEventHandler):
    """Watchdog handler that re-indexes files on change."""

    def __init__(
        self, store: MemoryStore, project_config: ProjectConfig, watch_root: str
    ) -> None:
        self._store = store
        self._config = project_config
        self._watch_root = watch_root

    def _should_index(self, path: str) -> bool:
        rel = os.path.relpath(path, self._watch_root)
        return matches_patterns(rel, self._config.watch_patterns, self._config.watch_exclude)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory and self._should_index(event.src_path):
            try:
                logger.info("File modified, re-indexing: %s", event.src_path)
                index_file(self._store, event.src_path)
            except Exception:
                logger.exception("Failed to index modified file: %s", event.src_path)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory and self._should_index(event.src_path):
            try:
                logger.info("File created, indexing: %s", event.src_path)
                index_file(self._store, event.src_path)
            except Exception:
                logger.exception("Failed to index created file: %s", event.src_path)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory and self._should_index(event.src_path):
            try:
                logger.info("File deleted, removing from store: %s", event.src_path)
                self._store.delete_by_source(f"file:{event.src_path}")
            except Exception:
                logger.exception("Failed to remove deleted file: %s", event.src_path)


class FileWatcher:
    def __init__(self, store: MemoryStore, project_config: ProjectConfig) -> None:
        self._store = store
        self._config = project_config
        self._observer: Observer | None = None

    def reconcile(self, progress_callback: Callable[[int], None] | None = None) -> int:
        """Scan all watch paths and index new or changed files. Returns file count."""
        total = 0
        skipped = 0
        for watch_path in self._config.watch_paths:
            root = Path(watch_path)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_dir():
                    continue
                try:
                    rel = str(path.relative_to(root))
                    if not matches_patterns(rel, self._config.watch_patterns, self._config.watch_exclude):
                        continue

                    file_path = str(path)
                    current_mtime = path.stat().st_mtime
                    stored_mtime = self._store.get_file_mtime(f"file:{file_path}")

                    if stored_mtime is not None and abs(stored_mtime - current_mtime) < 0.5:
                        skipped += 1
                        continue

                    index_file(self._store, file_path, file_mtime=current_mtime)
                    total += 1
                    if progress_callback and total % 50 == 0:
                        progress_callback(total)
                except Exception:
                    logger.exception("Failed to reconcile file: %s", path)

        if skipped:
            logger.info("Skipped %d unchanged files", skipped)
        return total

    def start(self) -> None:
        """Start watching for file changes."""
        self._observer = Observer()
        for watch_path in self._config.watch_paths:
            if not Path(watch_path).exists():
                continue
            handler = _IndexHandler(self._store, self._config, watch_path)
            self._observer.schedule(handler, watch_path, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
