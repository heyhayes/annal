import os
import json
import pytest
import yaml
from memex.server import create_server
from memex.config import MemexConfig


@pytest.fixture
def server_env(tmp_data_dir, tmp_config_path, tmp_path):
    """Set up a config and environment for the server."""
    watch_dir = tmp_path / "project_files"
    watch_dir.mkdir()
    (watch_dir / "README.md").write_text("# Test Project\nSome docs\n")

    config = MemexConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={},
    )
    config.save()

    return {
        "config_path": tmp_config_path,
        "data_dir": tmp_data_dir,
        "watch_dir": str(watch_dir),
        "project": "testproject",
    }


def test_create_server(server_env):
    mcp = create_server(
        project=server_env["project"],
        config_path=server_env["config_path"],
    )
    assert mcp is not None
    # Server should have registered tools
    assert mcp.name == "memex"
