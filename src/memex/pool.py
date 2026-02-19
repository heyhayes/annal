"""Multi-project store and watcher pool for Memex daemon mode."""

from __future__ import annotations

import logging

from memex.config import MemexConfig
from memex.store import MemoryStore
from memex.watcher import FileWatcher

logger = logging.getLogger(__name__)


class StorePool:
    """Manages MemoryStore and FileWatcher instances per project."""

    def __init__(self, config: MemexConfig) -> None:
        self._config = config
        self._stores: dict[str, MemoryStore] = {}
        self._watchers: dict[str, FileWatcher] = {}

    def get_store(self, project: str) -> MemoryStore:
        """Get or create a MemoryStore for the given project."""
        if project not in self._stores:
            logger.info("Creating store for project '%s'", project)
            self._stores[project] = MemoryStore(
                data_dir=self._config.data_dir, project=project
            )
        return self._stores[project]

    def reconcile_project(self, project: str) -> int:
        """Reconcile file indexes for a project. Returns number of files indexed."""
        if project not in self._config.projects:
            return 0
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        count = watcher.reconcile()
        logger.info("Reconciled %d files for project '%s'", count, project)
        return count

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
