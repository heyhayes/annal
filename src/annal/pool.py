"""Multi-project store and watcher pool for Annal daemon mode."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

from annal.config import AnnalConfig
from annal.store import MemoryStore
from annal.watcher import FileWatcher

logger = logging.getLogger(__name__)


class StorePool:
    """Manages MemoryStore and FileWatcher instances per project."""

    def __init__(self, config: AnnalConfig) -> None:
        self._config = config
        self._stores: dict[str, MemoryStore] = {}
        self._watchers: dict[str, FileWatcher] = {}
        self._lock = threading.Lock()
        self._index_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last_reconcile: dict[str, dict] = {}

    def get_store(self, project: str) -> MemoryStore:
        """Get or create a MemoryStore for the given project."""
        with self._lock:
            if project not in self._stores:
                logger.info("Creating store for project '%s'", project)
                self._stores[project] = MemoryStore(
                    data_dir=self._config.data_dir, project=project
                )
                # Auto-register unknown projects in config so they're discoverable
                if project not in self._config.projects:
                    self._config.add_project(project)
                    self._config.save()
                    logger.info("Auto-registered project '%s' in config", project)
            return self._stores[project]

    def reconcile_project(self, project: str) -> int:
        """Reconcile file indexes for a project. Returns number of files indexed."""
        if project not in self._config.projects:
            return 0
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        count = watcher.reconcile()
        self._last_reconcile[project] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_count": count,
        }
        logger.info("Reconciled %d files for project '%s'", count, project)
        return count

    def reconcile_project_async(
        self,
        project: str,
        on_progress: Callable[[int], None] | None = None,
        on_complete: Callable[[int], None] | None = None,
        clear_first: bool = False,
    ) -> None:
        """Kick off reconciliation on a background thread. Returns immediately."""
        def _run() -> None:
            lock = self._index_locks[project]
            if not lock.acquire(blocking=False):
                logger.info("Indexing already in progress for '%s', waiting", project)
                lock.acquire()
            try:
                if project not in self._config.projects:
                    return
                store = self.get_store(project)
                if clear_first:
                    store.delete_by_source("file:")
                proj_config = self._config.projects[project]
                watcher = FileWatcher(store=store, project_config=proj_config)
                count = watcher.reconcile(progress_callback=on_progress)
                self._last_reconcile[project] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "file_count": count,
                }
                logger.info("Reconciled %d files for project '%s'", count, project)
                if on_complete:
                    on_complete(count)
            finally:
                lock.release()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def is_indexing(self, project: str) -> bool:
        """Check if a project is currently being indexed."""
        lock = self._index_locks[project]
        acquired = lock.acquire(blocking=False)
        if acquired:
            lock.release()
            return False
        return True

    def get_last_reconcile(self, project: str) -> dict | None:
        """Get the last reconcile info for a project."""
        return self._last_reconcile.get(project)

    def start_watcher(self, project: str) -> None:
        """Start a file watcher for the given project."""
        if project not in self._config.projects:
            return
        if project in self._watchers:
            return
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        watcher.start()
        self._watchers[project] = watcher
        logger.info("File watcher started for project '%s'", project)

    def shutdown(self) -> None:
        """Stop all active file watchers."""
        for project, watcher in self._watchers.items():
            logger.info("Stopping watcher for project '%s'", project)
            watcher.stop()
        self._watchers.clear()
