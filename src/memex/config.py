"""Configuration management for Memex."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_DATA_DIR = os.path.expanduser("~/.memex/data")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.memex/config.yaml")

DEFAULT_WATCH_PATTERNS = ["**/*.md", "**/*.yaml", "**/*.toml", "**/*.json"]
DEFAULT_WATCH_EXCLUDE = [
    "node_modules/**",
    "vendor/**",
    ".git/**",
    "dist/**",
    "build/**",
]


@dataclass
class ProjectConfig:
    watch_paths: list[str] = field(default_factory=list)
    watch_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_WATCH_PATTERNS))
    watch_exclude: list[str] = field(default_factory=lambda: list(DEFAULT_WATCH_EXCLUDE))


@dataclass
class MemexConfig:
    config_path: str = DEFAULT_CONFIG_PATH
    data_dir: str = DEFAULT_DATA_DIR
    projects: dict[str, ProjectConfig] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: str = DEFAULT_CONFIG_PATH) -> MemexConfig:
        path = Path(config_path)
        if not path.exists():
            return cls(config_path=config_path)

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        projects = {}
        for name, proj_data in raw.get("projects", {}).items():
            projects[name] = ProjectConfig(
                watch_paths=proj_data.get("watch_paths", []),
                watch_patterns=proj_data.get("watch_patterns", list(DEFAULT_WATCH_PATTERNS)),
                watch_exclude=proj_data.get("watch_exclude", list(DEFAULT_WATCH_EXCLUDE)),
            )

        return cls(
            config_path=config_path,
            data_dir=os.path.expanduser(raw.get("data_dir", DEFAULT_DATA_DIR)),
            projects=projects,
        )

    def save(self) -> None:
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        raw = {
            "data_dir": self.data_dir,
            "projects": {
                name: {
                    "watch_paths": proj.watch_paths,
                    "watch_patterns": proj.watch_patterns,
                    "watch_exclude": proj.watch_exclude,
                }
                for name, proj in self.projects.items()
            },
        }
        with open(path, "w") as f:
            yaml.dump(raw, f, default_flow_style=False)

    def add_project(self, name: str, watch_paths: list[str] | None = None) -> ProjectConfig:
        proj = ProjectConfig(watch_paths=watch_paths or [])
        self.projects[name] = proj
        return proj

    def get_project(self, name: str) -> ProjectConfig:
        if name not in self.projects:
            raise KeyError(f"Project '{name}' not found in config")
        return self.projects[name]
