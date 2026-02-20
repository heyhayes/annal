"""Annal CLI — install/uninstall one-shot setup."""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MCP_URL = "http://localhost:9200/mcp"
INTERNAL_URL = "http://127.0.0.1:9200/mcp"


def _annal_executable() -> str:
    """Find the annal executable path."""
    venv_bin = Path(sys.executable).parent / "annal"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("annal")
    if found:
        return found
    return f"{sys.executable} -m annal.server"


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

    # 5. Install OS service
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
ExecStart={exe} --transport streamable-http
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
        plist_file.write_text(f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.annal.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
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
