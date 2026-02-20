"""Tests for the annal install/uninstall CLI."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from annal.cli import install, uninstall


@pytest.fixture
def fake_home(tmp_path):
    """Set up a fake home directory with expected client config dirs."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".codex").mkdir()
    (home / ".gemini").mkdir()

    # Codex needs a config.toml to exist
    (home / ".codex" / "config.toml").write_text('model = "gpt-5.3-codex"\n')
    # Gemini needs a settings.json to exist
    (home / ".gemini" / "settings.json").write_text('{}')

    return home


def test_install_creates_config(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        result = install(start_service=False)

    assert "config.yaml" in result
    config_path = fake_home / ".annal" / "config.yaml"
    assert config_path.exists()


def test_install_creates_mcp_json(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)

    mcp_json = fake_home / ".mcp.json"
    assert mcp_json.exists()
    data = json.loads(mcp_json.read_text())
    assert "annal" in data["mcpServers"]
    assert data["mcpServers"]["annal"]["url"] == "http://localhost:9200/mcp"


def test_install_configures_codex(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)

    config = (fake_home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.annal]" in config
    assert "http://127.0.0.1:9200/mcp" in config


def test_install_configures_gemini(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)

    data = json.loads((fake_home / ".gemini" / "settings.json").read_text())
    assert "annal" in data["mcpServers"]


def test_install_skips_missing_clients(tmp_path):
    """Should not crash if a client dir doesn't exist."""
    home = tmp_path / "home"
    home.mkdir()
    with patch("annal.cli.Path.home", return_value=home):
        result = install(start_service=False)
    assert "config.yaml" in result


def test_uninstall_removes_mcp_json_entry(fake_home):
    # First install
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)
        uninstall(stop_service=False)

    mcp_json = fake_home / ".mcp.json"
    if mcp_json.exists():
        data = json.loads(mcp_json.read_text())
        assert "annal" not in data.get("mcpServers", {})
