"""Multi-project store and watcher pool for Annal daemon mode."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from annal.backend import Embedder, OnnxEmbedder, VectorBackend
from annal.config import AnnalConfig
from annal.events import event_bus, Event
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
        self._index_locks: dict[str, threading.Lock] = {}
        self._index_started: dict[str, datetime] = {}
        self._last_reconcile: dict[str, dict] = {}
        self._reconcile_threads: list[threading.Thread] = []
        self._embedder: Embedder | None = None

    def _get_index_lock(self, project: str) -> threading.Lock:
        """Get or create an index lock for a project (thread-safe)."""
        with self._lock:
            if project not in self._index_locks:
                self._index_locks[project] = threading.Lock()
            return self._index_locks[project]

    def _get_embedder(self) -> Embedder:
        """Get the shared embedder instance (created once, reused across stores)."""
        if self._embedder is None:
            self._embedder = OnnxEmbedder()
        return self._embedder

    def _create_backend(self, project: str) -> VectorBackend:
        """Create a vector backend for the given project based on config."""
        storage = self._config.storage
        backend_name = storage.backend
        backend_config = storage.backends.get(backend_name, {})
        collection_name = f"annal_{project}"
        dimension = self._get_embedder().dimension

        if backend_name == "chromadb":
            from annal.backends.chromadb import ChromaBackend
            path = backend_config.get("path", self._config.data_dir)
            return ChromaBackend(path=path, collection_name=collection_name, dimension=dimension)

        if backend_name == "qdrant":
            from annal.backends.qdrant import QdrantBackend
            url = backend_config.get("url", "http://localhost:6333")
            return QdrantBackend(url=url, collection_name=collection_name, dimension=dimension)

        raise ValueError(f"Unknown backend: {backend_name}")

    def get_store(self, project: str) -> MemoryStore:
        """Get or create a MemoryStore for the given project."""
        need_save = False
        with self._lock:
            if project not in self._stores:
                logger.info("Creating store for project '%s'", project)
                backend = self._create_backend(project)
                embedder = self._get_embedder()
                self._stores[project] = MemoryStore(backend, embedder)
                if project not in self._config.projects:
                    self._config.add_project(project)
                    need_save = True
                    logger.info("Auto-registered project '%s' in config", project)
            store = self._stores[project]
        if need_save:
            self._config.save()
        return store

    def reconcile_project(self, project: str) -> int:
        """Reconcile file indexes for a project. Returns number of files indexed."""
        if project not in self._config.projects:
            return 0
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        count = watcher.reconcile()
        with self._lock:
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
            lock = self._get_index_lock(project)
            if not lock.acquire(blocking=False):
                logger.info("Indexing already in progress for '%s', waiting", project)
                lock.acquire()
            try:
                with self._lock:
                    self._index_started[project] = datetime.now(timezone.utc)
                if project not in self._config.projects:
                    return
                store = self.get_store(project)
                if clear_first:
                    store.delete_by_source("file:")
                proj_config = self._config.projects[project]
                watcher = FileWatcher(store=store, project_config=proj_config)
                count = watcher.reconcile(progress_callback=on_progress)
                with self._lock:
                    self._last_reconcile[project] = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "file_count": count,
                    }
                logger.info("Reconciled %d files for project '%s'", count, project)
                if on_complete:
                    on_complete(count)
            except Exception as exc:
                logger.exception("Reconciliation failed for project '%s'", project)
                event_bus.push(Event(
                    type="index_failed", project=project, detail=str(exc)
                ))
            finally:
                with self._lock:
                    self._index_started.pop(project, None)
                    self._reconcile_threads = [
                        t for t in self._reconcile_threads if t.is_alive()
                    ]
                lock.release()

        thread = threading.Thread(target=_run, daemon=True)
        with self._lock:
            self._reconcile_threads.append(thread)
        thread.start()

    def is_indexing(self, project: str) -> bool:
        """Check if a project is currently being indexed."""
        lock = self._get_index_lock(project)
        acquired = lock.acquire(blocking=False)
        if acquired:
            lock.release()
            return False
        return True

    def get_last_reconcile(self, project: str) -> dict | None:
        """Get the last reconcile info for a project."""
        with self._lock:
            return self._last_reconcile.get(project)

    def get_index_started(self, project: str) -> datetime | None:
        """Get the start time of the current indexing run, or None if idle."""
        with self._lock:
            return self._index_started.get(project)

    def start_watcher(self, project: str) -> None:
        """Start a file watcher for the given project (skipped if watch=false)."""
        if project not in self._config.projects:
            return
        if not self._config.projects[project].watch:
            logger.info("File watching disabled for project '%s'", project)
            return
        if project in self._watchers:
            return
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        watcher.start()
        self._watchers[project] = watcher
        logger.info("File watcher started for project '%s'", project)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Stop all active file watchers and wait for in-flight reconciliation."""
        # Wait for reconciliation threads to finish
        with self._lock:
            threads = list(self._reconcile_threads)
        for thread in threads:
            thread.join(timeout=timeout)
        with self._lock:
            self._reconcile_threads = [
                t for t in self._reconcile_threads if t.is_alive()
            ]

        for project, watcher in self._watchers.items():
            logger.info("Stopping watcher for project '%s'", project)
            watcher.stop()
        self._watchers.clear()
