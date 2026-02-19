import pytest
from memex.server import create_server, SERVER_INSTRUCTIONS
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
    }


def test_create_server(server_env):
    mcp = create_server(config_path=server_env["config_path"])
    assert mcp is not None
    assert mcp.name == "memex"


def test_server_has_instructions(server_env):
    mcp = create_server(config_path=server_env["config_path"])
    assert mcp.instructions == SERVER_INSTRUCTIONS
