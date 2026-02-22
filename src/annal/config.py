"""Configuration management for Annal."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_DATA_DIR = os.path.expanduser("~/.annal/data")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.annal/config.yaml")
DEFAULT_PORT = 9200

DEFAULT_WATCH_PATTERNS = ["**/*.md", "**/*.yaml", "**/*.toml", "**/*.json"]
DEFAULT_WATCH_EXCLUDE = [
    "**/node_modules/**",
    "**/vendor/**",
    "**/.git/**",
    "**/.venv/**",
    "**/__pycache__/**",
    "**/dist/**",
    "**/build/**",
]


@dataclass
class ProjectConfig:
    watch_paths: list[str] = field(default_factory=list)
    watch_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_WATCH_PATTERNS))
    watch_exclude: list[str] = field(default_factory=lambda: list(DEFAULT_WATCH_EXCLUDE))
    watch: bool = True


@dataclass
class StorageConfig:
    backend: str = "chromadb"
    backends: dict[str, dict] = field(default_factory=dict)


@dataclass
class AnnalConfig:
    config_path: str = DEFAULT_CONFIG_PATH
    data_dir: str = DEFAULT_DATA_DIR
    port: int = DEFAULT_PORT
    projects: dict[str, ProjectConfig] = field(default_factory=dict)
    storage: StorageConfig = field(default_factory=StorageConfig)

    @classmethod
    def load(cls, config_path: str = DEFAULT_CONFIG_PATH) -> AnnalConfig:
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
                watch=proj_data.get("watch", True),
            )

        data_dir = os.path.expanduser(raw.get("data_dir", DEFAULT_DATA_DIR))

        storage_raw = raw.get("storage", {})
        storage = StorageConfig(
            backend=storage_raw.get("backend", "chromadb"),
            backends=storage_raw.get("backends", {"chromadb": {"path": data_dir}}),
        )
        # Expand ~ in backend paths
        for bconf in storage.backends.values():
            if "path" in bconf:
                bconf["path"] = os.path.expanduser(bconf["path"])

        return cls(
            config_path=config_path,
            data_dir=data_dir,
            port=raw.get("port", DEFAULT_PORT),
            projects=projects,
            storage=storage,
        )

    def save(self) -> None:
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        raw: dict = {
            "data_dir": self.data_dir,
            "port": self.port,
            "projects": {
                name: {
                    "watch_paths": proj.watch_paths,
                    "watch_patterns": proj.watch_patterns,
                    "watch_exclude": proj.watch_exclude,
                    "watch": proj.watch,
                }
                for name, proj in self.projects.items()
            },
        }
        if self.storage.backend != "chromadb" or len(self.storage.backends) > 1:
            raw["storage"] = {
                "backend": self.storage.backend,
                "backends": self.storage.backends,
            }
        with open(path, "w") as f:
            yaml.dump(raw, f, default_flow_style=False)

    def add_project(
        self,
        name: str,
        watch_paths: list[str] | None = None,
        watch_patterns: list[str] | None = None,
        watch_exclude: list[str] | None = None,
    ) -> ProjectConfig:
        if name in self.projects:
            proj = self.projects[name]
            if watch_paths:
                proj.watch_paths = watch_paths
            if watch_patterns is not None:
                proj.watch_patterns = watch_patterns
            if watch_exclude is not None:
                proj.watch_exclude = watch_exclude
            return proj
        self.projects[name] = ProjectConfig(
            watch_paths=watch_paths or [],
            watch_patterns=watch_patterns or list(DEFAULT_WATCH_PATTERNS),
            watch_exclude=watch_exclude or list(DEFAULT_WATCH_EXCLUDE),
        )
        return self.projects[name]

    def get_project(self, name: str) -> ProjectConfig:
        if name not in self.projects:
            raise KeyError(f"Project '{name}' not found in config")
        return self.projects[name]
