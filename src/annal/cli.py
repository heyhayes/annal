"""Annal CLI — install/uninstall one-shot setup."""

from __future__ import annotations

import json
import logging
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MCP_URL = "http://localhost:9200/mcp"
INTERNAL_URL = "http://127.0.0.1:9200/mcp"

AGENT_INSTRUCTIONS_SNIPPET = """\
<annal_semantic_memory>
You have persistent semantic memory via Annal (mcp__annal__* tools). Memories survive across
sessions and are searchable by meaning. This is your long-term memory — MEMORY.md is a cheat
sheet, Annal is deep storage.

Why this matters: every session starts blank. Without Annal, you repeat investigations,
rediscover patterns, and miss prior decisions. With it, you inherit your past self's
understanding of the codebase.

When to search (use mode="probe" to scan, then expand_memories for details):
- Session start: load context for the current task area
- Unfamiliar code: before diving into a module you haven't seen this session
- "What happened" questions: anything about recent work, prior decisions, project state
- Before architectural changes: check for prior decisions in the same domain
- Familiar-feeling bugs: search for prior root causes

When to store (tag with type + domain, e.g. tags=["decision", "auth"]):
- Bug root causes and the fix that worked
- Architectural decisions and their rationale
- Codebase patterns that took effort to discover
- User preferences for workflow, tools, style
- Key file paths and module responsibilities in unfamiliar codebases

After completing a task, before moving on, always ask: what did I learn that I'd want to know
next time? If you discovered a root cause, mapped unfamiliar architecture, or found a pattern
that took effort — store it. This is the single most important habit for cross-session value.

Project name: use the basename of the current working directory.
</annal_semantic_memory>
"""

COMMIT_HOOK_SCRIPT = """\
#!/bin/bash
# Post-commit reminder to store learnings in Annal.
# Fires after Bash tool calls that contain git commit commands.
# stdout is injected back into the agent's context.

if echo "$TOOL_INPUT" | grep -q '"git commit'; then
  echo "You just committed work. Before moving on: what did you learn during this task that would be valuable in a future session? Consider storing it in Annal (root causes, architecture discoveries, patterns, approaches that worked or didn't)."
fi
"""


def _annal_executable() -> list[str]:
    """Find the annal executable path. Returns a list for subprocess/plist compatibility."""
    venv_bin = Path(sys.executable).parent / "annal"
    if venv_bin.exists():
        return [str(venv_bin)]
    found = shutil.which("annal")
    if found:
        return [found]
    return [sys.executable, "-m", "annal.server"]


def install(start_service: bool = True) -> str:
    """One-shot install: config, OS service, MCP client configs."""
    home = Path.home()
    actions: list[str] = []

    # 1. Create ~/.annal/config.yaml if missing
    annal_dir = home / ".annal"
    config_path = annal_dir / "config.yaml"
    if not config_path.exists():
        annal_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "data_dir": str(annal_dir / "data"),
            "port": 9200,
            "projects": {},
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False)
        actions.append(f"Created config.yaml at {config_path}")
    else:
        actions.append(f"config.yaml already exists at {config_path}")

    # 2. Configure Claude Code (~/.mcp.json)
    mcp_json = home / ".mcp.json"
    mcp_data: dict = {}
    if mcp_json.exists():
        try:
            mcp_data = json.loads(mcp_json.read_text())
        except json.JSONDecodeError:
            actions.append(f"Warning: {mcp_json} contains invalid JSON, skipped")
            mcp_data = None
    if mcp_data is not None:
        if "mcpServers" not in mcp_data:
            mcp_data["mcpServers"] = {}
        if "annal" not in mcp_data["mcpServers"]:
            mcp_data["mcpServers"]["annal"] = {"type": "http", "url": MCP_URL}
            mcp_json.write_text(json.dumps(mcp_data, indent=2) + "\n")
            actions.append("Configured Claude Code (~/.mcp.json)")
        else:
            actions.append("Claude Code already configured")

    # 3. Configure Codex (~/.codex/config.toml)
    codex_config = home / ".codex" / "config.toml"
    if codex_config.exists():
        content = codex_config.read_text()
        if "[mcp_servers.annal]" not in content:
            content += f'\n[mcp_servers.annal]\nurl = "{INTERNAL_URL}"\n'
            codex_config.write_text(content)
            actions.append("Configured Codex (~/.codex/config.toml)")
        else:
            actions.append("Codex already configured")
    else:
        actions.append("Codex not found, skipped")

    # 4. Configure Gemini (~/.gemini/settings.json)
    gemini_config = home / ".gemini" / "settings.json"
    if gemini_config.exists():
        try:
            gemini_data = json.loads(gemini_config.read_text())
        except json.JSONDecodeError:
            actions.append(f"Warning: {gemini_config} contains invalid JSON, skipped")
            gemini_data = None
        if gemini_data is not None:
            if "mcpServers" not in gemini_data:
                gemini_data["mcpServers"] = {}
            if "annal" not in gemini_data["mcpServers"]:
                gemini_data["mcpServers"]["annal"] = {"httpUrl": INTERNAL_URL}
                gemini_config.write_text(json.dumps(gemini_data, indent=2) + "\n")
                actions.append("Configured Gemini (~/.gemini/settings.json)")
            else:
                actions.append("Gemini already configured")
    else:
        actions.append("Gemini not found, skipped")

    # 5. Add agent instructions to CLAUDE.md
    claude_md = home / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if "<annal_semantic_memory>" not in content:
            claude_md.write_text(AGENT_INSTRUCTIONS_SNIPPET + "\n" + content)
            actions.append("Added agent instructions to ~/.claude/CLAUDE.md")
        else:
            actions.append("Agent instructions already in CLAUDE.md")
    else:
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        claude_md.write_text(AGENT_INSTRUCTIONS_SNIPPET)
        actions.append("Created ~/.claude/CLAUDE.md with agent instructions")

    # 6. Install post-commit reminder hook for Claude Code
    hook_script = home / ".claude" / "hooks" / "annal-commit-reminder.sh"
    hook_script.parent.mkdir(parents=True, exist_ok=True)
    hook_script.write_text(COMMIT_HOOK_SCRIPT)
    hook_script.chmod(hook_script.stat().st_mode | stat.S_IEXEC)

    settings_json = home / ".claude" / "settings.json"
    settings_data: dict = {}
    if settings_json.exists():
        try:
            settings_data = json.loads(settings_json.read_text())
        except json.JSONDecodeError:
            settings_data = {}
    if "hooks" not in settings_data:
        settings_data["hooks"] = {}
    hook_entry = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": str(hook_script)}],
    }
    post_hooks = settings_data["hooks"].get("PostToolUse", [])
    already = any(
        str(hook_script) in json.dumps(entry) for entry in post_hooks
    )
    if not already:
        post_hooks.append(hook_entry)
        settings_data["hooks"]["PostToolUse"] = post_hooks
        settings_json.write_text(json.dumps(settings_data, indent=2) + "\n")
        actions.append("Installed post-commit reminder hook (~/.claude/settings.json)")
    else:
        actions.append("Post-commit reminder hook already installed")

    # 7. Install OS service
    os_name = platform.system()
    exe = _annal_executable()

    if os_name == "Linux":
        service_dir = home / ".config" / "systemd" / "user"
        service_dir.mkdir(parents=True, exist_ok=True)
        service_file = service_dir / "annal.service"
        service_file.write_text(f"""\
[Unit]
Description=Annal semantic memory MCP server
After=network.target

[Service]
Type=simple
ExecStart={" ".join(exe)} --transport streamable-http
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
KillSignal=SIGINT

[Install]
WantedBy=default.target
""")
        actions.append(f"Installed systemd service at {service_file}")
        if start_service:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "--user", "enable", "annal.service"], check=False)
            subprocess.run(["systemctl", "--user", "start", "annal.service"], check=False)
            actions.append("Started annal.service")

    elif os_name == "Darwin":
        plist_dir = home / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_file = plist_dir / "com.annal.server.plist"
        prog_args = "\n        ".join(f"<string>{arg}</string>" for arg in exe)
        plist_file.write_text(f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.annal.server</string>
    <key>ProgramArguments</key>
    <array>
        {prog_args}
        <string>--transport</string>
        <string>streamable-http</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/annal.stdout.log</string>
    <key>StandardErrorPath</key><string>/tmp/annal.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
</dict>
</plist>
""")
        actions.append(f"Installed launchd plist at {plist_file}")
        if start_service:
            subprocess.run(["launchctl", "load", str(plist_file)], check=False)
            actions.append("Loaded launchd agent")

    elif os_name == "Windows":
        actions.append("Windows: run contrib/annal-service.ps1 manually for now")

    else:
        actions.append(f"Unknown OS '{os_name}', skipped service install")

    return "Annal installed:\n" + "\n".join(f"  - {a}" for a in actions)


def uninstall(stop_service: bool = True) -> str:
    """Remove Annal service and MCP client configs."""
    home = Path.home()
    actions: list[str] = []

    # Remove MCP client configs
    mcp_json = home / ".mcp.json"
    if mcp_json.exists():
        try:
            data = json.loads(mcp_json.read_text())
        except json.JSONDecodeError:
            data = None
        if data is not None and "annal" in data.get("mcpServers", {}):
            del data["mcpServers"]["annal"]
            mcp_json.write_text(json.dumps(data, indent=2) + "\n")
            actions.append("Removed from Claude Code (~/.mcp.json)")

    codex_config = home / ".codex" / "config.toml"
    if codex_config.exists():
        content = codex_config.read_text()
        if "[mcp_servers.annal]" in content:
            lines = content.split("\n")
            new_lines = []
            skip = False
            for line in lines:
                if line.strip() == "[mcp_servers.annal]":
                    skip = True
                    continue
                if skip and line.startswith("["):
                    skip = False
                if not skip:
                    new_lines.append(line)
            codex_config.write_text("\n".join(new_lines))
            actions.append("Removed from Codex (~/.codex/config.toml)")

    gemini_config = home / ".gemini" / "settings.json"
    if gemini_config.exists():
        try:
            data = json.loads(gemini_config.read_text())
        except json.JSONDecodeError:
            data = None
        if data is not None and "annal" in data.get("mcpServers", {}):
            del data["mcpServers"]["annal"]
            gemini_config.write_text(json.dumps(data, indent=2) + "\n")
            actions.append("Removed from Gemini (~/.gemini/settings.json)")

    # Remove agent instructions from CLAUDE.md
    claude_md = home / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()
        if "<annal_semantic_memory>" in content:
            import re
            cleaned = re.sub(
                r"<annal_semantic_memory>.*?</annal_semantic_memory>\n*",
                "",
                content,
                flags=re.DOTALL,
            )
            claude_md.write_text(cleaned)
            actions.append("Removed agent instructions from ~/.claude/CLAUDE.md")

    # Remove post-commit reminder hook
    hook_script = home / ".claude" / "hooks" / "annal-commit-reminder.sh"
    if hook_script.exists():
        hook_script.unlink()
        actions.append("Removed post-commit reminder hook script")

    settings_json = home / ".claude" / "settings.json"
    if settings_json.exists():
        try:
            settings_data = json.loads(settings_json.read_text())
        except json.JSONDecodeError:
            settings_data = None
        if settings_data is not None:
            post_hooks = settings_data.get("hooks", {}).get("PostToolUse", [])
            filtered = [
                entry for entry in post_hooks
                if "annal-commit-reminder" not in json.dumps(entry)
            ]
            if len(filtered) != len(post_hooks):
                if filtered:
                    settings_data["hooks"]["PostToolUse"] = filtered
                else:
                    settings_data.get("hooks", {}).pop("PostToolUse", None)
                settings_json.write_text(json.dumps(settings_data, indent=2) + "\n")
                actions.append("Removed post-commit hook from ~/.claude/settings.json")

    # Stop and remove OS service
    os_name = platform.system()
    if os_name == "Linux":
        if stop_service:
            subprocess.run(["systemctl", "--user", "stop", "annal.service"], check=False)
            subprocess.run(["systemctl", "--user", "disable", "annal.service"], check=False)
        service_file = home / ".config" / "systemd" / "user" / "annal.service"
        if service_file.exists():
            service_file.unlink()
            actions.append("Removed systemd service")
    elif os_name == "Darwin":
        plist_file = home / "Library" / "LaunchAgents" / "com.annal.server.plist"
        if stop_service and plist_file.exists():
            subprocess.run(["launchctl", "unload", str(plist_file)], check=False)
        if plist_file.exists():
            plist_file.unlink()
            actions.append("Removed launchd plist")

    return "Annal uninstalled:\n" + "\n".join(f"  - {a}" for a in actions) if actions else "Nothing to uninstall."
