import pytest


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for ChromaDB."""
    return str(tmp_path / "memex_data")


@pytest.fixture
def tmp_config_path(tmp_path):
    """Provide a temporary config file path."""
    return str(tmp_path / "config.yaml")
