import pytest
from memex.pool import StorePool
from memex.config import MemexConfig, ProjectConfig


@pytest.fixture
def config_with_projects(tmp_data_dir, tmp_config_path, tmp_path):
    watch_dir = tmp_path / "myproject"
    watch_dir.mkdir()
    (watch_dir / "README.md").write_text("# Hello\nWorld\n")

    config = MemexConfig(
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
