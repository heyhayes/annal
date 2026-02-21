import queue as queue_mod
import threading
import time

import pytest
from annal.pool import StorePool
from annal.config import AnnalConfig, ProjectConfig
from annal.events import event_bus


@pytest.fixture
def config_with_projects(tmp_data_dir, tmp_config_path, tmp_path):
    watch_dir = tmp_path / "myproject"
    watch_dir.mkdir()
    (watch_dir / "README.md").write_text("# Hello\nWorld\n")

    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={
            "myproject": ProjectConfig(watch_paths=[str(watch_dir)]),
        },
    )
    return config


def test_get_store_creates_on_first_access(config_with_projects):
    pool = StorePool(config_with_projects)
    store = pool.get_store("myproject")
    assert store is not None
    assert store.count() >= 0


def test_get_store_returns_same_instance(config_with_projects):
    pool = StorePool(config_with_projects)
    store1 = pool.get_store("myproject")
    store2 = pool.get_store("myproject")
    assert store1 is store2


def test_get_store_creates_for_unknown_project(config_with_projects):
    pool = StorePool(config_with_projects)
    store = pool.get_store("newproject")
    assert store is not None


def test_reconcile_project_indexes_files(config_with_projects):
    pool = StorePool(config_with_projects)
    pool.get_store("myproject")
    pool.reconcile_project("myproject")
    store = pool.get_store("myproject")
    assert store.count() > 0


def test_reconcile_unknown_project_is_noop(config_with_projects):
    pool = StorePool(config_with_projects)
    pool.reconcile_project("nonexistent")


def test_shutdown_stops_watchers(config_with_projects):
    pool = StorePool(config_with_projects)
    pool.get_store("myproject")
    pool.start_watcher("myproject")
    pool.shutdown()


def test_store_pool_concurrent_get_store(tmp_data_dir, tmp_config_path):
    """Multiple threads calling get_store for a new project should not race."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.save()
    pool = StorePool(config)

    stores = []
    errors = []

    def get():
        try:
            s = pool.get_store("racetest")
            stores.append(s)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=get) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Race condition errors: {errors}"
    # All threads should get the same store instance
    assert len(set(id(s) for s in stores)) == 1


def test_reconcile_project_async(tmp_data_dir, tmp_config_path, tmp_path):
    """reconcile_project_async should return immediately and reconcile in background."""
    watch_dir = tmp_path / "docs"
    watch_dir.mkdir()
    (watch_dir / "test.md").write_text("# Test\nSome content\n")

    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.add_project("asynctest", watch_paths=[str(watch_dir)])
    config.save()
    pool = StorePool(config)

    pool.reconcile_project_async("asynctest")

    # Give the background thread time to finish
    time.sleep(2)

    store = pool.get_store("asynctest")
    assert store.count() > 0


def test_is_indexing(tmp_data_dir, tmp_config_path):
    """is_indexing should return False when no indexing is running."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.save()
    pool = StorePool(config)

    assert pool.is_indexing("anyproject") is False


def test_get_last_reconcile(tmp_data_dir, tmp_config_path, tmp_path):
    """get_last_reconcile should return info after reconciliation completes."""
    watch_dir = tmp_path / "docs"
    watch_dir.mkdir()
    (watch_dir / "test.md").write_text("# Test\nContent\n")

    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.add_project("lastrectest", watch_paths=[str(watch_dir)])
    config.save()
    pool = StorePool(config)

    # Before reconciliation
    assert pool.get_last_reconcile("lastrectest") is None

    # After synchronous reconciliation
    pool.reconcile_project("lastrectest")
    info = pool.get_last_reconcile("lastrectest")
    assert info is not None
    assert "timestamp" in info
    assert "file_count" in info


def test_reconcile_project_async_emits_index_failed_on_error(tmp_data_dir, tmp_config_path, tmp_path):
    """If reconciliation fails, an index_failed event should be emitted."""
    from unittest.mock import patch

    watch_dir = tmp_path / "docs"
    watch_dir.mkdir()
    (watch_dir / "test.md").write_text("# Test\n")

    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.add_project("failtest", watch_paths=[str(watch_dir)])
    config.save()
    pool = StorePool(config)

    events = []
    q = event_bus.subscribe()

    # Force reconcile to raise
    with patch("annal.watcher.FileWatcher.reconcile", side_effect=RuntimeError("boom")):
        pool.reconcile_project_async("failtest")
        time.sleep(2)

    # Drain the queue
    while True:
        try:
            events.append(q.get_nowait())
        except queue_mod.Empty:
            break
    event_bus.unsubscribe(q)

    # Should have emitted index_failed
    failed_events = [e for e in events if e.type == "index_failed"]
    assert len(failed_events) == 1
    assert failed_events[0].project == "failtest"
    assert "boom" in failed_events[0].detail

    # Pool should not be stuck in indexing state after failure
    assert pool.is_indexing("failtest") is False


def test_get_index_lock_returns_same_lock(tmp_data_dir, tmp_config_path):
    """_get_index_lock should return the same lock for the same project."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.save()
    pool = StorePool(config)

    lock1 = pool._get_index_lock("testproject")
    lock2 = pool._get_index_lock("testproject")
    assert lock1 is lock2


def test_get_index_lock_different_projects(tmp_data_dir, tmp_config_path):
    """_get_index_lock should return different locks for different projects."""
    config = AnnalConfig(config_path=tmp_config_path, data_dir=tmp_data_dir)
    config.save()
    pool = StorePool(config)

    lock1 = pool._get_index_lock("project_a")
    lock2 = pool._get_index_lock("project_b")
    assert lock1 is not lock2
