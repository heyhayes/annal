# Memex Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python MCP server that provides semantic memory storage and retrieval for AI agent teams using ChromaDB with local ONNX embeddings.

**Architecture:** A FastMCP-based server exposing 6 tools (store_memory, search_memories, delete_memory, list_topics, init_project, index_files). ChromaDB handles vector storage with its default ONNX embedding function. A file watcher (watchdog) auto-indexes markdown and config files. Config lives in YAML at `~/.memex/config.yaml`.

**Tech Stack:** Python 3.12, FastMCP (mcp SDK), ChromaDB, watchdog, PyYAML, pytest

---

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `src/memex/__init__.py`
- Create: `src/memex/server.py` (empty placeholder)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.gitignore`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "memex"
version = "0.1.0"
description = "Semantic memory server for AI agent teams"
requires-python = ">=3.12"
dependencies = [
    "mcp[cli]>=1.2.0",
    "chromadb>=0.5.0",
    "watchdog>=4.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/memex"]
```

**Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
```

**Step 3: Create package files**

`src/memex/__init__.py`:
```python
```

`src/memex/server.py`:
```python
"""Memex MCP server — semantic memory for AI agent teams."""
```

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
import pytest
import tempfile
import os


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for ChromaDB."""
    return str(tmp_path / "memex_data")


@pytest.fixture
def tmp_config_path(tmp_path):
    """Provide a temporary config file path."""
    return str(tmp_path / "config.yaml")
```

**Step 4: Create venv and install dependencies**

Run: `cd /home/hayes/development/personal/memex && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`

**Step 5: Verify install**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/python -c "import chromadb; from mcp.server.fastmcp import FastMCP; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add pyproject.toml src/ tests/ .gitignore
git commit -m "feat: project setup with dependencies"
```

---

### Task 2: Config System

**Files:**
- Create: `src/memex/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import os
import yaml
import pytest
from memex.config import MemexConfig, ProjectConfig


def test_load_config_creates_default_when_missing(tmp_config_path):
    config = MemexConfig.load(tmp_config_path)
    assert config.data_dir is not None
    assert config.projects == {}


def test_load_config_reads_existing(tmp_config_path):
    raw = {
        "data_dir": "/tmp/memex_test",
        "projects": {
            "myproject": {
                "watch_paths": ["/home/user/myproject"],
                "watch_patterns": ["**/*.md"],
                "watch_exclude": ["node_modules/**"],
            }
        },
    }
    os.makedirs(os.path.dirname(tmp_config_path), exist_ok=True)
    with open(tmp_config_path, "w") as f:
        yaml.dump(raw, f)

    config = MemexConfig.load(tmp_config_path)
    assert config.data_dir == "/tmp/memex_test"
    assert "myproject" in config.projects
    assert config.projects["myproject"].watch_paths == ["/home/user/myproject"]


def test_save_config(tmp_config_path):
    config = MemexConfig(
        config_path=tmp_config_path,
        data_dir="/tmp/test_data",
        projects={
            "testproj": ProjectConfig(
                watch_paths=["/home/user/testproj"],
            )
        },
    )
    config.save()

    with open(tmp_config_path) as f:
        raw = yaml.safe_load(f)
    assert raw["data_dir"] == "/tmp/test_data"
    assert "testproj" in raw["projects"]


def test_add_project(tmp_config_path):
    config = MemexConfig.load(tmp_config_path)
    config.add_project("newproj", watch_paths=["/home/user/newproj"])
    assert "newproj" in config.projects
    assert config.projects["newproj"].watch_patterns == [
        "**/*.md", "**/*.yaml", "**/*.toml", "**/*.json"
    ]


def test_get_project_raises_for_unknown(tmp_config_path):
    config = MemexConfig.load(tmp_config_path)
    with pytest.raises(KeyError):
        config.get_project("nonexistent")
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memex.config'`

**Step 3: Implement config module**

`src/memex/config.py`:
```python
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
            config = cls(config_path=config_path)
            return config

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
            data_dir=raw.get("data_dir", DEFAULT_DATA_DIR),
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/memex/config.py tests/test_config.py
git commit -m "feat: config system with YAML persistence"
```

---

### Task 3: Memory Store (ChromaDB wrapper)

**Files:**
- Create: `src/memex/store.py`
- Create: `tests/test_store.py`

**Step 1: Write the failing tests**

`tests/test_store.py`:
```python
import pytest
from memex.store import MemoryStore


@pytest.fixture
def store(tmp_data_dir):
    return MemoryStore(data_dir=tmp_data_dir, project="testproject")


def test_store_and_retrieve_memory(store):
    mem_id = store.store(
        content="The checkout flow goes through EnrolmentStoreController",
        tags=["billing", "checkout"],
        source="session observation",
    )
    assert mem_id is not None

    results = store.search("checkout flow", limit=1)
    assert len(results) == 1
    assert "EnrolmentStoreController" in results[0]["content"]
    assert results[0]["tags"] == ["billing", "checkout"]


def test_search_with_tag_filter(store):
    store.store(content="Billing uses Stripe", tags=["billing"])
    store.store(content="Frontend uses React", tags=["frontend"])

    results = store.search("uses", tags=["billing"], limit=5)
    assert len(results) == 1
    assert "Stripe" in results[0]["content"]


def test_delete_memory(store):
    mem_id = store.store(content="Temporary note", tags=["temp"])
    store.delete(mem_id)

    results = store.search("Temporary note", limit=5)
    assert len(results) == 0


def test_list_topics(store):
    store.store(content="Billing info", tags=["billing", "stripe"])
    store.store(content="Frontend info", tags=["frontend", "billing"])

    topics = store.list_topics()
    assert topics["billing"] == 2
    assert topics["stripe"] == 1
    assert topics["frontend"] == 1


def test_search_returns_similarity_score(store):
    store.store(content="The sky is blue", tags=["nature"])
    results = store.search("blue sky", limit=1)
    assert "score" in results[0]
    assert isinstance(results[0]["score"], float)


def test_store_with_source(store):
    store.store(content="Found in AGENT.md", tags=["docs"], source="AGENT.md > Overview")
    results = store.search("AGENT.md", limit=1)
    assert results[0]["source"] == "AGENT.md > Overview"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memex.store'`

**Step 3: Implement the memory store**

`src/memex/store.py`:
```python
"""ChromaDB-backed memory store for Memex."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import chromadb


class MemoryStore:
    def __init__(self, data_dir: str, project: str) -> None:
        self._client = chromadb.PersistentClient(path=data_dir)
        self._collection = self._client.get_or_create_collection(
            name=f"memex_{project}",
            metadata={"hnsw:space": "cosine"},
        )

    def store(
        self,
        content: str,
        tags: list[str],
        source: str = "",
        chunk_type: str = "agent-memory",
    ) -> str:
        mem_id = str(uuid.uuid4())
        metadata = {
            "tags": json.dumps(tags),
            "source": source,
            "chunk_type": chunk_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._collection.add(
            ids=[mem_id],
            documents=[content],
            metadatas=[metadata],
        )
        return mem_id

    def search(
        self,
        query: str,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[dict]:
        where = None
        if tags:
            # ChromaDB doesn't support list-contains natively on JSON strings,
            # so we filter post-query for tag matching
            limit_query = max(limit * 3, 20)
        else:
            limit_query = limit

        results = self._collection.query(
            query_texts=[query],
            n_results=min(limit_query, self._collection.count()) or 1,
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        memories = []
        for i, mem_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            mem_tags = json.loads(meta["tags"])

            if tags and not any(t in mem_tags for t in tags):
                continue

            distance = results["distances"][0][i] if results["distances"] else 0.0
            score = 1.0 - distance  # cosine distance to similarity

            memories.append({
                "id": mem_id,
                "content": results["documents"][0][i],
                "tags": mem_tags,
                "source": meta.get("source", ""),
                "chunk_type": meta.get("chunk_type", ""),
                "score": score,
                "created_at": meta.get("created_at", ""),
            })

        return memories[:limit]

    def delete(self, mem_id: str) -> None:
        self._collection.delete(ids=[mem_id])

    def list_topics(self) -> dict[str, int]:
        all_metadata = self._collection.get()["metadatas"]
        tag_counts: dict[str, int] = {}
        for meta in all_metadata or []:
            tags = json.loads(meta.get("tags", "[]"))
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts

    def delete_by_source(self, source_prefix: str) -> None:
        """Delete all chunks whose source starts with the given prefix."""
        all_data = self._collection.get(include=["metadatas"])
        ids_to_delete = []
        for i, meta in enumerate(all_data["metadatas"] or []):
            if meta.get("source", "").startswith(source_prefix):
                ids_to_delete.append(all_data["ids"][i])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)

    def count(self) -> int:
        return self._collection.count()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_store.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/memex/store.py tests/test_store.py
git commit -m "feat: ChromaDB memory store with search and tag filtering"
```

---

### Task 4: File Indexer (Markdown Chunking)

**Files:**
- Create: `src/memex/indexer.py`
- Create: `tests/test_indexer.py`

**Step 1: Write the failing tests**

`tests/test_indexer.py`:
```python
import os
import pytest
from memex.indexer import chunk_markdown, chunk_config_file, index_file
from memex.store import MemoryStore


def test_chunk_markdown_splits_by_headings():
    content = """# Overview
This is the overview section.

## Architecture
The system has three layers.

### Backend
PHP and Laravel.

## Frontend
React and TypeScript.
"""
    chunks = chunk_markdown(content, "README.md")
    assert len(chunks) == 4
    assert chunks[0]["heading"] == "README.md > Overview"
    assert "overview section" in chunks[0]["content"]
    assert chunks[1]["heading"] == "README.md > Architecture"
    assert chunks[2]["heading"] == "README.md > Architecture > Backend"
    assert chunks[3]["heading"] == "README.md > Frontend"


def test_chunk_markdown_single_section():
    content = "Just some text without headings."
    chunks = chunk_markdown(content, "NOTES.md")
    assert len(chunks) == 1
    assert chunks[0]["heading"] == "NOTES.md"
    assert "without headings" in chunks[0]["content"]


def test_chunk_config_file():
    content = '{"key": "value", "nested": {"a": 1}}'
    chunks = chunk_config_file(content, "config.json")
    assert len(chunks) == 1
    assert chunks[0]["heading"] == "config.json"
    assert '"key"' in chunks[0]["content"]


def test_index_file_stores_chunks(tmp_data_dir, tmp_path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Section A\nContent A\n\n# Section B\nContent B\n")

    store = MemoryStore(data_dir=tmp_data_dir, project="testproject")
    count = index_file(store, str(md_file))
    assert count == 2
    assert store.count() == 2

    results = store.search("Content A", limit=1)
    assert len(results) == 1
    assert results[0]["chunk_type"] == "file-indexed"


def test_reindex_file_replaces_old_chunks(tmp_data_dir, tmp_path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Version 1\nOld content\n")

    store = MemoryStore(data_dir=tmp_data_dir, project="testproject")
    index_file(store, str(md_file))
    assert store.count() == 1

    md_file.write_text("# Version 2\nNew content\n\n# Extra\nMore stuff\n")
    index_file(store, str(md_file))
    assert store.count() == 2

    results = store.search("Old content", limit=5)
    # Old content should not match well anymore since it was deleted
    for r in results:
        assert "Old content" not in r["content"]
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_indexer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memex.indexer'`

**Step 3: Implement the indexer**

`src/memex/indexer.py`:
```python
"""File indexing and markdown chunking for Memex."""

from __future__ import annotations

import re
from pathlib import Path

from memex.store import MemoryStore


def chunk_markdown(content: str, filename: str) -> list[dict]:
    """Split markdown content into chunks by heading boundaries."""
    lines = content.split("\n")
    chunks = []
    current_content: list[str] = []
    heading_stack: list[str] = []  # (level, text) pairs tracked as just text
    heading_levels: list[int] = []
    current_heading = filename

    for line in lines:
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            # Save previous chunk if it has content
            text = "\n".join(current_content).strip()
            if text:
                chunks.append({"heading": current_heading, "content": text})
            current_content = []

            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            # Update heading stack based on level
            while heading_levels and heading_levels[-1] >= level:
                heading_levels.pop()
                heading_stack.pop()

            heading_stack.append(heading_text)
            heading_levels.append(level)

            current_heading = filename + " > " + " > ".join(heading_stack)
        else:
            current_content.append(line)

    # Don't forget the last chunk
    text = "\n".join(current_content).strip()
    if text:
        chunks.append({"heading": current_heading, "content": text})

    return chunks


def chunk_config_file(content: str, filename: str) -> list[dict]:
    """Treat an entire config file as a single chunk."""
    return [{"heading": filename, "content": content.strip()}]


def index_file(store: MemoryStore, file_path: str) -> int:
    """Index a file into the memory store. Returns number of chunks created."""
    path = Path(file_path)
    if not path.exists():
        return 0

    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return 0

    # Delete any existing chunks from this file
    store.delete_by_source(f"file:{file_path}")

    # Chunk based on file type
    suffix = path.suffix.lower()
    if suffix == ".md":
        chunks = chunk_markdown(content, path.name)
    elif suffix in (".json", ".yaml", ".yml", ".toml"):
        chunks = chunk_config_file(content, path.name)
    else:
        chunks = [{"heading": path.name, "content": content}]

    # Store each chunk
    for chunk in chunks:
        tags = _derive_tags(path)
        store.store(
            content=chunk["content"],
            tags=tags,
            source=f"file:{file_path}|{chunk['heading']}",
            chunk_type="file-indexed",
        )

    return len(chunks)


def _derive_tags(path: Path) -> list[str]:
    """Derive automatic tags from the file path."""
    tags = ["indexed"]
    name_lower = path.name.lower()
    if "claude" in name_lower or "agent" in name_lower:
        tags.append("agent-config")
    if "readme" in name_lower:
        tags.append("docs")
    return tags
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_indexer.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/memex/indexer.py tests/test_indexer.py
git commit -m "feat: file indexer with markdown heading-based chunking"
```

---

### Task 5: File Watcher

**Files:**
- Create: `src/memex/watcher.py`
- Create: `tests/test_watcher.py`

**Step 1: Write the failing tests**

`tests/test_watcher.py`:
```python
import os
import time
import pytest
from pathlib import Path
from memex.watcher import FileWatcher, matches_patterns
from memex.store import MemoryStore
from memex.config import ProjectConfig


def test_matches_patterns():
    assert matches_patterns("docs/README.md", ["**/*.md"], []) is True
    assert matches_patterns("docs/README.md", ["**/*.yaml"], []) is False
    assert matches_patterns("node_modules/pkg/README.md", ["**/*.md"], ["node_modules/**"]) is False
    assert matches_patterns("src/config.yaml", ["**/*.yaml", "**/*.md"], []) is True


def test_reconcile_indexes_new_files(tmp_data_dir, tmp_path):
    # Create a markdown file
    md_file = tmp_path / "test.md"
    md_file.write_text("# Hello\nWorld\n")

    store = MemoryStore(data_dir=tmp_data_dir, project="testproject")
    project_config = ProjectConfig(
        watch_paths=[str(tmp_path)],
        watch_patterns=["**/*.md"],
    )

    watcher = FileWatcher(store=store, project_config=project_config)
    watcher.reconcile()

    assert store.count() == 1
    results = store.search("Hello World", limit=1)
    assert len(results) == 1


def test_reconcile_skips_excluded_dirs(tmp_data_dir, tmp_path):
    # Create a file in an excluded directory
    excluded = tmp_path / "node_modules" / "pkg"
    excluded.mkdir(parents=True)
    (excluded / "README.md").write_text("# Should be ignored\n")

    # And a non-excluded file
    (tmp_path / "docs.md").write_text("# Should be indexed\n")

    store = MemoryStore(data_dir=tmp_data_dir, project="testproject")
    project_config = ProjectConfig(
        watch_paths=[str(tmp_path)],
        watch_patterns=["**/*.md"],
        watch_exclude=["node_modules/**"],
    )

    watcher = FileWatcher(store=store, project_config=project_config)
    watcher.reconcile()

    assert store.count() == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_watcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memex.watcher'`

**Step 3: Implement the watcher**

`src/memex/watcher.py`:
```python
"""File watcher with startup reconciliation for Memex."""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
from watchdog.observers import Observer

from memex.config import ProjectConfig
from memex.indexer import index_file
from memex.store import MemoryStore

logger = logging.getLogger(__name__)


def matches_patterns(
    rel_path: str, patterns: list[str], excludes: list[str]
) -> bool:
    """Check if a relative path matches watch patterns and isn't excluded."""
    # Normalize separators
    rel_path = rel_path.replace(os.sep, "/")

    for exclude in excludes:
        if fnmatch.fnmatch(rel_path, exclude):
            return False
        # Also check if any path component matches
        parts = rel_path.split("/")
        for i in range(len(parts)):
            partial = "/".join(parts[: i + 1])
            if fnmatch.fnmatch(partial, exclude.rstrip("/**")):
                return False

    for pattern in patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True

    return False


class _IndexHandler(FileSystemEventHandler):
    """Watchdog handler that re-indexes files on change."""

    def __init__(
        self, store: MemoryStore, project_config: ProjectConfig, watch_root: str
    ) -> None:
        self._store = store
        self._config = project_config
        self._watch_root = watch_root

    def _should_index(self, path: str) -> bool:
        rel = os.path.relpath(path, self._watch_root)
        return matches_patterns(rel, self._config.watch_patterns, self._config.watch_exclude)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory and self._should_index(event.src_path):
            logger.info("File modified, re-indexing: %s", event.src_path)
            index_file(self._store, event.src_path)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory and self._should_index(event.src_path):
            logger.info("File created, indexing: %s", event.src_path)
            index_file(self._store, event.src_path)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if not event.is_directory and self._should_index(event.src_path):
            logger.info("File deleted, removing from store: %s", event.src_path)
            self._store.delete_by_source(f"file:{event.src_path}")


class FileWatcher:
    def __init__(self, store: MemoryStore, project_config: ProjectConfig) -> None:
        self._store = store
        self._config = project_config
        self._observer: Observer | None = None

    def reconcile(self) -> int:
        """Scan all watch paths and index any new or changed files. Returns file count."""
        total = 0
        for watch_path in self._config.watch_paths:
            root = Path(watch_path)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_dir():
                    continue
                rel = str(path.relative_to(root))
                if matches_patterns(rel, self._config.watch_patterns, self._config.watch_exclude):
                    index_file(self._store, str(path))
                    total += 1
        return total

    def start(self) -> None:
        """Start watching for file changes."""
        self._observer = Observer()
        for watch_path in self._config.watch_paths:
            if not Path(watch_path).exists():
                continue
            handler = _IndexHandler(self._store, self._config, watch_path)
            self._observer.schedule(handler, watch_path, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_watcher.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/memex/watcher.py tests/test_watcher.py
git commit -m "feat: file watcher with reconciliation and watchdog integration"
```

---

### Task 6: MCP Server (Tool Definitions)

**Files:**
- Modify: `src/memex/server.py`
- Create: `tests/test_server.py`

**Step 1: Write the failing tests**

`tests/test_server.py`:
```python
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
```

Note: Full integration testing of MCP tools via the protocol is complex. The primary test is that `create_server` wires everything together without error. The individual components (store, indexer, watcher) are already tested in isolation.

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_server.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_server' from 'memex.server'`

**Step 3: Implement the MCP server**

`src/memex/server.py`:
```python
"""Memex MCP server — semantic memory for AI agent teams."""

from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from memex.config import MemexConfig, DEFAULT_CONFIG_PATH
from memex.store import MemoryStore
from memex.watcher import FileWatcher

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


def create_server(
    project: str | None = None,
    config_path: str = DEFAULT_CONFIG_PATH,
) -> FastMCP:
    """Create and configure the Memex MCP server."""
    project = project or os.environ.get("MEMEX_PROJECT", "default")
    config = MemexConfig.load(config_path)

    mcp = FastMCP("memex")

    # Lazy-init store — created on first tool call so the server starts fast
    _store: MemoryStore | None = None
    _watcher: FileWatcher | None = None

    def get_store() -> MemoryStore:
        nonlocal _store, _watcher
        if _store is None:
            _store = MemoryStore(data_dir=config.data_dir, project=project)

            # If the project exists in config, reconcile and start watching
            if project in config.projects:
                proj_config = config.projects[project]
                _watcher = FileWatcher(store=_store, project_config=proj_config)
                logger.info("Reconciling files for project '%s'...", project)
                count = _watcher.reconcile()
                logger.info("Indexed %d files", count)
                _watcher.start()
                logger.info("File watcher started")

        return _store

    @mcp.tool()
    def store_memory(content: str, tags: list[str], source: str = "") -> str:
        """Store a piece of knowledge in the project's memory.

        Args:
            content: The knowledge to store
            tags: Domain labels like ["billing", "checkout", "pricing"]
            source: Where this knowledge came from (file path, "session observation", etc.)
        """
        store = get_store()
        mem_id = store.store(content=content, tags=tags, source=source)
        return f"Stored memory {mem_id}"

    @mcp.tool()
    def search_memories(query: str, tags: list[str] | None = None, limit: int = 5) -> str:
        """Search project memories using natural language.

        Args:
            query: Natural language search query
            tags: Optional tag filter — only return memories with at least one of these tags
            limit: Maximum number of results (default 5)
        """
        store = get_store()
        results = store.search(query=query, tags=tags, limit=limit)
        if not results:
            return "No matching memories found."

        lines = []
        for r in results:
            lines.append(
                f"[{r['score']:.2f}] ({', '.join(r['tags'])}) {r['content']}"
                + (f"\n  Source: {r['source']}" if r['source'] else "")
            )
        return "\n\n".join(lines)

    @mcp.tool()
    def delete_memory(memory_id: str) -> str:
        """Delete a specific memory by its ID.

        Args:
            memory_id: The ID of the memory to delete
        """
        store = get_store()
        store.delete(memory_id)
        return f"Deleted memory {memory_id}"

    @mcp.tool()
    def list_topics() -> str:
        """List all knowledge domains (tags) in the project with their counts."""
        store = get_store()
        topics = store.list_topics()
        if not topics:
            return "No topics found. The memory store is empty."

        lines = [f"  {tag}: {count} memories" for tag, count in sorted(topics.items(), key=lambda x: -x[1])]
        return "Topics:\n" + "\n".join(lines)

    @mcp.tool()
    def init_project(project_name: str, watch_paths: list[str] | None = None) -> str:
        """Initialize a new project in the Memex config.

        Args:
            project_name: Name for the project (used as the collection namespace)
            watch_paths: Optional list of directory paths to watch for file changes
        """
        config.add_project(project_name, watch_paths=watch_paths)
        config.save()
        return f"Project '{project_name}' initialized. Restart the server with MEMEX_PROJECT={project_name} to use it."

    @mcp.tool()
    def index_files() -> str:
        """Manually trigger re-indexing of all watched files for the current project."""
        store = get_store()
        if project not in config.projects:
            return f"Project '{project}' has no watch paths configured. Use init_project first."

        proj_config = config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        count = watcher.reconcile()
        return f"Re-indexed {count} files."

    return mcp


def main() -> None:
    """Entry point for running the server."""
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_server.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest -v`
Expected: All tests pass across all test files

**Step 6: Commit**

```bash
git add src/memex/server.py tests/test_server.py
git commit -m "feat: MCP server with all 6 tools wired up"
```

---

### Task 7: Integration Test — End to End

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

`tests/test_integration.py`:
```python
import os
import pytest
import yaml
from memex.config import MemexConfig
from memex.store import MemoryStore
from memex.indexer import index_file
from memex.watcher import FileWatcher


def test_full_workflow(tmp_data_dir, tmp_config_path, tmp_path):
    """Test the complete flow: config -> index files -> store memories -> search."""
    # 1. Create project files
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "CLAUDE.md").write_text(
        "# Project Rules\n\nAlways use TypeScript.\n\n"
        "## Testing\n\nRun tests with `npm test`.\n"
    )
    (project_dir / "AGENT.md").write_text(
        "# Agent Config\n\nBackend is PHP Laravel.\nFrontend is React.\n"
    )

    # 2. Create config
    config = MemexConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={},
    )
    config.add_project("myproject", watch_paths=[str(project_dir)])
    config.save()

    # 3. Create store and reconcile
    store = MemoryStore(data_dir=tmp_data_dir, project="myproject")
    proj_config = config.get_project("myproject")
    watcher = FileWatcher(store=store, project_config=proj_config)
    file_count = watcher.reconcile()
    assert file_count == 2  # CLAUDE.md + AGENT.md

    # 4. Search indexed content
    results = store.search("how to run tests", limit=3)
    assert len(results) > 0
    assert any("npm test" in r["content"] for r in results)

    # 5. Store an agent memory
    store.store(
        content="The pricing calculation has a timezone bug in CalculateSeasonPrice",
        tags=["billing", "bugs"],
        source="debugging session",
    )

    # 6. Search combines file-indexed and agent memories
    results = store.search("pricing calculation", limit=5)
    assert any("timezone bug" in r["content"] for r in results)

    # 7. Topic listing includes both sources
    topics = store.list_topics()
    assert "billing" in topics
    assert "indexed" in topics  # from file indexing
```

**Step 2: Run integration test**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_integration.py -v`
Expected: All PASS

**Step 3: Run full test suite one final time**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration test for full workflow"
```

---

### Task 8: CLI Entry Point and Claude Code Config

**Files:**
- Modify: `pyproject.toml` (add entry point)
- Create: `README.md` (replace placeholder)

**Step 1: Add entry point to pyproject.toml**

Add to `pyproject.toml` under `[project]`:
```toml
[project.scripts]
memex = "memex.server:main"
```

**Step 2: Verify the server starts and exits cleanly**

Run: `cd /home/hayes/development/personal/memex && timeout 3 .venv/bin/python -m memex.server 2>/dev/null; echo "Exit code: $?"`
Expected: Exit code 124 (killed by timeout, which means it started successfully and was waiting for stdin)

**Step 3: Write README.md**

Replace the existing README.md content with setup and usage instructions covering:
- What memex is (one paragraph)
- Install steps (`pip install -e .`)
- Config setup (`~/.memex/config.yaml` example)
- Claude Code integration (`.claude/settings.json` example)
- Available tools (one-line description each)

**Step 4: Commit**

```bash
git add pyproject.toml README.md
git commit -m "feat: CLI entry point and documentation"
```

---

### Task 9: Wire Into Claude Code (Manual Verification)

This is a manual step — not automated.

**Step 1: Create the memex config directory**

Run: `mkdir -p ~/.memex`

**Step 2: Create initial config**

Write `~/.memex/config.yaml`:
```yaml
data_dir: ~/.memex/data

projects:
  classmanager:
    watch_paths:
      - /home/hayes/development/work/classmanager
    watch_patterns:
      - "**/*.md"
      - "**/*.yaml"
      - "**/*.toml"
      - "**/*.json"
    watch_exclude:
      - "node_modules/**"
      - "vendor/**"
      - ".git/**"
      - "dist/**"
      - "build/**"
```

**Step 3: Add to Claude Code global settings**

Add the `memex` MCP server entry to `~/.claude/settings.json` under `mcpServers`:
```json
"mcpServers": {
  "memex": {
    "command": "/home/hayes/development/personal/memex/.venv/bin/python",
    "args": ["-m", "memex.server"],
    "env": {
      "MEMEX_PROJECT": "classmanager"
    }
  }
}
```

**Step 4: Test in a new Claude Code session**

Start a new Claude Code session in the classmanager project. Verify:
- The memex tools appear in the available tools list
- `search_memories` returns results from indexed markdown files
- `store_memory` successfully stores a test memory
- `list_topics` shows the indexed tags

**Step 5: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: wiring and manual verification complete"
```
