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


def test_install_idempotent(fake_home):
    """Calling install twice should not crash or duplicate config entries."""
    with patch("annal.cli.Path.home", return_value=fake_home):
        result1 = install(start_service=False)
        result2 = install(start_service=False)

    assert "config.yaml" in result1
    assert "config.yaml" in result2

    # MCP json should still have exactly one annal entry
    mcp_json = fake_home / ".mcp.json"
    data = json.loads(mcp_json.read_text())
    assert "annal" in data["mcpServers"]

    # Codex config should not have duplicate sections
    codex = (fake_home / ".codex" / "config.toml").read_text()
    assert codex.count("[mcp_servers.annal]") == 1


def test_annal_executable_returns_list():
    """_annal_executable should return a list of strings, not a single string."""
    from annal.cli import _annal_executable
    result = _annal_executable()
    assert isinstance(result, list)
    assert all(isinstance(s, str) for s in result)
    assert len(result) >= 1


def test_install_adds_agent_instructions_to_claude_md(fake_home):
    (fake_home / ".claude").mkdir(exist_ok=True)
    (fake_home / ".claude" / "CLAUDE.md").write_text("# My instructions\n")
    with patch("annal.cli.Path.home", return_value=fake_home):
        result = install(start_service=False)

    assert "Added agent instructions" in result
    content = (fake_home / ".claude" / "CLAUDE.md").read_text()
    assert "<annal_semantic_memory>" in content
    assert "# My instructions" in content  # original content preserved


def test_install_creates_claude_md_if_missing(fake_home):
    # Remove the .claude dir created by fixture
    import shutil
    shutil.rmtree(fake_home / ".claude", ignore_errors=True)
    with patch("annal.cli.Path.home", return_value=fake_home):
        result = install(start_service=False)

    assert "Created ~/.claude/CLAUDE.md" in result
    content = (fake_home / ".claude" / "CLAUDE.md").read_text()
    assert "<annal_semantic_memory>" in content


def test_install_skips_agent_instructions_if_present(fake_home):
    (fake_home / ".claude").mkdir(exist_ok=True)
    (fake_home / ".claude" / "CLAUDE.md").write_text(
        "<annal_semantic_memory>\nexisting\n</annal_semantic_memory>\n"
    )
    with patch("annal.cli.Path.home", return_value=fake_home):
        result = install(start_service=False)

    assert "already in CLAUDE.md" in result


def test_uninstall_removes_agent_instructions(fake_home):
    (fake_home / ".claude").mkdir(exist_ok=True)
    (fake_home / ".claude" / "CLAUDE.md").write_text(
        "<annal_semantic_memory>\nstuff\n</annal_semantic_memory>\n\n# Keep this\n"
    )
    with patch("annal.cli.Path.home", return_value=fake_home):
        uninstall(stop_service=False)

    content = (fake_home / ".claude" / "CLAUDE.md").read_text()
    assert "<annal_semantic_memory>" not in content
    assert "# Keep this" in content


def test_install_creates_commit_hook(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        result = install(start_service=False)

    assert "post-commit reminder hook" in result
    hook = fake_home / ".claude" / "hooks" / "annal-commit-reminder.sh"
    assert hook.exists()
    assert "git commit" in hook.read_text()

    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    post_hooks = settings["hooks"]["PostToolUse"]
    assert any("annal-commit-reminder" in json.dumps(e) for e in post_hooks)


def test_install_commit_hook_idempotent(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)
        install(start_service=False)

    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    post_hooks = settings["hooks"]["PostToolUse"]
    annal_hooks = [e for e in post_hooks if "annal-commit-reminder" in json.dumps(e)]
    assert len(annal_hooks) == 1


def test_install_preserves_existing_settings(fake_home):
    """Install should not clobber existing hooks in settings.json."""
    (fake_home / ".claude").mkdir(exist_ok=True)
    existing = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]
        },
        "permissions": {"allow": ["Bash(*)"]}
    }
    (fake_home / ".claude" / "settings.json").write_text(json.dumps(existing))

    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)

    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    assert "SessionStart" in settings["hooks"]
    assert "PostToolUse" in settings["hooks"]
    assert settings["permissions"]["allow"] == ["Bash(*)"]


def test_uninstall_removes_commit_hook(fake_home):
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)
        uninstall(stop_service=False)

    hook = fake_home / ".claude" / "hooks" / "annal-commit-reminder.sh"
    assert not hook.exists()

    settings_path = fake_home / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        post_hooks = settings.get("hooks", {}).get("PostToolUse", [])
        assert not any("annal-commit-reminder" in json.dumps(e) for e in post_hooks)


def test_uninstall_removes_mcp_json_entry(fake_home):
    # First install
    with patch("annal.cli.Path.home", return_value=fake_home):
        install(start_service=False)
        uninstall(stop_service=False)

    mcp_json = fake_home / ".mcp.json"
    if mcp_json.exists():
        data = json.loads(mcp_json.read_text())
        assert "annal" not in data.get("mcpServers", {})
