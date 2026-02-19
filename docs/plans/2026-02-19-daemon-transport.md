# Memex Daemon Transport Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert memex from a per-session stdio MCP server to a shared HTTP daemon that multiple Claude Code sessions connect to simultaneously, eliminating redundant cold starts and ChromaDB concurrency issues.

**Architecture:** Refactor `create_server()` to manage a pool of MemoryStore/FileWatcher instances keyed by project name instead of binding to a single project at startup. Add a `project` parameter to every tool so the calling agent specifies which project it's working in. Switch transport from stdio to streamable-http with a configurable port. Add a systemd user service for process management. Keep stdio as a fallback for backward compatibility.

**Tech Stack:** Python 3.12, FastMCP (streamable-http transport), ChromaDB, watchdog, systemd

---

### Task 1: Add Port to Config

**Files:**
- Modify: `src/memex/config.py`
- Modify: `tests/test_config.py`

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_load_config_with_port(tmp_config_path):
    raw = {
        "data_dir": "/tmp/memex_test",
        "port": 9300,
        "projects": {},
    }
    os.makedirs(os.path.dirname(tmp_config_path), exist_ok=True)
    with open(tmp_config_path, "w") as f:
        yaml.dump(raw, f)

    config = MemexConfig.load(tmp_config_path)
    assert config.port == 9300


def test_load_config_default_port(tmp_config_path):
    config = MemexConfig.load(tmp_config_path)
    assert config.port == 9200
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_config.py::test_load_config_with_port tests/test_config.py::test_load_config_default_port -v`
Expected: FAIL — `AttributeError: 'MemexConfig' has no attribute 'port'`

**Step 3: Implement port config**

In `src/memex/config.py`, add `DEFAULT_PORT = 9200` alongside the other defaults, add `port: int = DEFAULT_PORT` to the `MemexConfig` dataclass, and read it in `load()`:

```python
DEFAULT_PORT = 9200
```

Add field to `MemexConfig`:

```python
port: int = DEFAULT_PORT
```

In `MemexConfig.load()`, add to the return statement:

```python
port=raw.get("port", DEFAULT_PORT),
```

In `MemexConfig.save()`, add to the raw dict:

```python
"port": self.port,
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/memex/config.py tests/test_config.py
git commit -m "feat: add configurable port to MemexConfig"
```

---

### Task 2: Multi-Project Store Pool

**Files:**
- Create: `src/memex/pool.py`
- Create: `tests/test_pool.py`

**Step 1: Write the failing tests**

`tests/test_pool.py`:

```python
import pytest
from memex.pool import StorePool
from memex.config import MemexConfig, ProjectConfig


@pytest.fixture
def config_with_projects(tmp_data_dir, tmp_config_path, tmp_path):
    watch_dir = tmp_path / "myproject"
    watch_dir.mkdir()
    (watch_dir / "README.md").write_text("# Hello\nWorld\n")

    config = MemexConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={
            "myproject": ProjectConfig(watch_paths=[str(watch_dir)]),
        },
    )
    return config


def test_get_store_creates_on_first_access(config_with_projects):
    pool = StorePool(config_with_projects)
    store = pool.get_store("myproject")
    assert store is not None
    assert store.count() >= 0


def test_get_store_returns_same_instance(config_with_projects):
    pool = StorePool(config_with_projects)
    store1 = pool.get_store("myproject")
    store2 = pool.get_store("myproject")
    assert store1 is store2


def test_get_store_creates_for_unknown_project(config_with_projects):
    pool = StorePool(config_with_projects)
    store = pool.get_store("newproject")
    assert store is not None


def test_reconcile_project_indexes_files(config_with_projects):
    pool = StorePool(config_with_projects)
    pool.get_store("myproject")
    pool.reconcile_project("myproject")
    store = pool.get_store("myproject")
    assert store.count() > 0


def test_reconcile_unknown_project_is_noop(config_with_projects):
    pool = StorePool(config_with_projects)
    pool.reconcile_project("nonexistent")


def test_shutdown_stops_watchers(config_with_projects):
    pool = StorePool(config_with_projects)
    pool.get_store("myproject")
    pool.start_watcher("myproject")
    pool.shutdown()
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_pool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memex.pool'`

**Step 3: Implement the store pool**

`src/memex/pool.py`:

```python
"""Multi-project store and watcher pool for Memex daemon mode."""

from __future__ import annotations

import logging

from memex.config import MemexConfig
from memex.store import MemoryStore
from memex.watcher import FileWatcher

logger = logging.getLogger(__name__)


class StorePool:
    """Manages MemoryStore and FileWatcher instances per project."""

    def __init__(self, config: MemexConfig) -> None:
        self._config = config
        self._stores: dict[str, MemoryStore] = {}
        self._watchers: dict[str, FileWatcher] = {}

    def get_store(self, project: str) -> MemoryStore:
        if project not in self._stores:
            logger.info("Creating store for project '%s'", project)
            self._stores[project] = MemoryStore(
                data_dir=self._config.data_dir, project=project
            )
        return self._stores[project]

    def reconcile_project(self, project: str) -> int:
        if project not in self._config.projects:
            return 0
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        count = watcher.reconcile()
        logger.info("Reconciled %d files for project '%s'", count, project)
        return count

    def start_watcher(self, project: str) -> None:
        if project not in self._config.projects:
            return
        if project in self._watchers:
            return
        store = self.get_store(project)
        proj_config = self._config.projects[project]
        watcher = FileWatcher(store=store, project_config=proj_config)
        watcher.start()
        self._watchers[project] = watcher
        logger.info("File watcher started for project '%s'", project)

    def shutdown(self) -> None:
        for project, watcher in self._watchers.items():
            logger.info("Stopping watcher for project '%s'", project)
            watcher.stop()
        self._watchers.clear()
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_pool.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/memex/pool.py tests/test_pool.py
git commit -m "feat: multi-project store pool for daemon mode"
```

---

### Task 3: Refactor Server to Use StorePool

**Files:**
- Modify: `src/memex/server.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing tests**

Replace `tests/test_server.py` with:

```python
import os
import pytest
import yaml
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
```

**Step 2: Run tests to verify current state**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_server.py -v`
Expected: FAIL — `create_server()` signature changed (no more `project` param)

**Step 3: Refactor server.py**

Replace `create_server()` and `main()` in `src/memex/server.py`. The key changes:

1. Remove the `project` parameter from `create_server()` — the server no longer binds to a single project
2. Replace the single-store lazy init with a `StorePool`
3. Add a `project` parameter to every tool
4. Boot all configured project watchers at startup
5. Add `--transport` CLI flag to `main()` and pass `host`/`port` from config to `FastMCP`

```python
def create_server(
    config_path: str = DEFAULT_CONFIG_PATH,
) -> FastMCP:
    """Create and configure the Memex MCP server."""
    config = MemexConfig.load(config_path)

    mcp = FastMCP(
        "memex",
        instructions=SERVER_INSTRUCTIONS,
        host="127.0.0.1",
        port=config.port,
    )

    pool = StorePool(config)

    # Reconcile and start watchers for all configured projects
    for project_name in config.projects:
        pool.reconcile_project(project_name)
        pool.start_watcher(project_name)

    atexit.register(pool.shutdown)

    @mcp.tool()
    def store_memory(project: str, content: str, tags: list[str], source: str = "") -> str:
        """Store a piece of knowledge in a project's memory.

        Args:
            project: Project name (e.g. "classmanager", "memex")
            content: The knowledge to store
            tags: Domain labels like ["billing", "checkout", "pricing"]
            source: Where this knowledge came from (file path, "session observation", etc.)
        """
        store = pool.get_store(project)
        mem_id = store.store(content=content, tags=tags, source=source)
        return f"[{project}] Stored memory {mem_id}"

    @mcp.tool()
    def search_memories(project: str, query: str, tags: list[str] | None = None, limit: int = 5) -> str:
        """Search project memories using natural language.

        Args:
            project: Project name to search in
            query: Natural language search query
            tags: Optional tag filter — only return memories with at least one of these tags
            limit: Maximum number of results (default 5)
        """
        store = pool.get_store(project)
        results = store.search(query=query, tags=tags, limit=limit)
        if not results:
            return f"[{project}] No matching memories found."

        lines = []
        for r in results:
            lines.append(
                f"[{r['score']:.2f}] ({', '.join(r['tags'])}) {r['content']}"
                + (f"\n  Source: {r['source']}" if r['source'] else "")
            )
        return f"[{project}] {len(results)} results:\n\n" + "\n\n".join(lines)

    @mcp.tool()
    def delete_memory(project: str, memory_id: str) -> str:
        """Delete a specific memory by its ID.

        Args:
            project: Project name the memory belongs to
            memory_id: The ID of the memory to delete
        """
        store = pool.get_store(project)
        store.delete(memory_id)
        return f"[{project}] Deleted memory {memory_id}"

    @mcp.tool()
    def list_topics(project: str) -> str:
        """List all knowledge domains (tags) in a project with their counts.

        Args:
            project: Project name to list topics for
        """
        store = pool.get_store(project)
        topics = store.list_topics()
        if not topics:
            return f"[{project}] No topics found. The memory store is empty."

        lines = [f"  {tag}: {count} memories" for tag, count in sorted(topics.items(), key=lambda x: -x[1])]
        return f"[{project}] Topics:\n" + "\n".join(lines)

    @mcp.tool()
    def init_project(project_name: str, watch_paths: list[str] | None = None) -> str:
        """Initialize a new project in the Memex config.

        Args:
            project_name: Name for the project (used as the collection namespace)
            watch_paths: Optional list of directory paths to watch for file changes
        """
        config.add_project(project_name, watch_paths=watch_paths)
        config.save()
        if watch_paths:
            pool.reconcile_project(project_name)
            pool.start_watcher(project_name)
        return f"Project '{project_name}' initialized with watch paths: {watch_paths or []}."

    @mcp.tool()
    def index_files(project: str) -> str:
        """Manually trigger re-indexing of all watched files for a project.

        Args:
            project: Project name to re-index
        """
        if project not in config.projects:
            return f"[{project}] No watch paths configured. Use init_project first."

        count = pool.reconcile_project(project)
        return f"[{project}] Re-indexed {count} files."

    return mcp


def main() -> None:
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Memex MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to config file",
    )
    args = parser.parse_args()

    mcp = create_server(config_path=args.config)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
```

Add the `StorePool` import at the top of server.py:

```python
from memex.pool import StorePool
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_server.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest -v`
Expected: All PASS (other tests don't touch server.py)

**Step 6: Commit**

```bash
git add src/memex/server.py tests/test_server.py
git commit -m "feat: refactor server to use StorePool with project param on all tools"
```

---

### Task 4: Update Server Instructions for Project Parameter

**Files:**
- Modify: `src/memex/server.py` (SERVER_INSTRUCTIONS string only)

**Step 1: Update the instructions**

Replace the "Automatic project detection" section in `SERVER_INSTRUCTIONS` with:

```
## Project parameter

Every tool requires a `project` parameter. Pass the project name that matches
your current working context. The project name is typically the directory name
of the codebase you're working in (e.g. "classmanager", "memex").

If you're unsure which project to use, check your CLAUDE.md or environment
for a MEMEX_PROJECT reference, or use the directory name of the current codebase.
```

**Step 2: Run tests**

Run: `cd /home/hayes/development/personal/memex && .venv/bin/pytest tests/test_server.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/memex/server.py
git commit -m "docs: update server instructions for project parameter"
```

---

### Task 5: Verify Streamable HTTP Transport

**Step 1: Test that the server starts with streamable-http transport**

Run: `cd /home/hayes/development/personal/memex && timeout 5 .venv/bin/python -m memex.server --transport streamable-http 2>&1; echo "Exit code: $?"`
Expected: Uvicorn startup logs on stderr, exit code 124 (killed by timeout — server was running)

**Step 2: Test that the server responds to health check**

In one terminal start the server:
```bash
cd /home/hayes/development/personal/memex && .venv/bin/python -m memex.server --transport streamable-http
```

In another terminal:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:9200/mcp
```
Expected: HTTP status code (405 Method Not Allowed is fine — it confirms the endpoint exists but only accepts POST)

**Step 3: Stop the test server and commit**

```bash
git add -A
git commit -m "test: verify streamable-http transport starts and listens"
```

---

### Task 6: Systemd User Service

**Files:**
- Create: `contrib/memex.service`

**Step 1: Create the service file**

`contrib/memex.service`:

```ini
[Unit]
Description=Memex semantic memory MCP server
After=network.target

[Service]
Type=simple
ExecStart=/home/hayes/development/personal/memex/.venv/bin/python -m memex.server --transport streamable-http
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

**Step 2: Install and enable the service**

Run:
```bash
mkdir -p ~/.config/systemd/user
cp /home/hayes/development/personal/memex/contrib/memex.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable memex
systemctl --user start memex
```

**Step 3: Verify the service is running**

Run: `systemctl --user status memex`
Expected: Active (running)

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:9200/mcp`
Expected: HTTP response (405 is fine)

**Step 4: Commit**

```bash
git add contrib/memex.service
git commit -m "feat: systemd user service for daemon mode"
```

---

### Task 7: Update Claude Code Config

**Step 1: Update Claude Code MCP server config**

Change `~/.claude/settings.json` memex entry from stdio to HTTP:

```json
{
  "mcpServers": {
    "memex": {
      "type": "http",
      "url": "http://localhost:9200/mcp"
    }
  }
}
```

Note: Remove the old `command`/`args`/`env` config entirely. The `MEMEX_PROJECT` env var is no longer needed — agents pass the project name on each tool call.

**Step 2: Update CLAUDE.md instructions**

Add a note to the project's CLAUDE.md or the user's global CLAUDE.md telling agents which project name to use. For example, in `~/.claude/CLAUDE.md` under `<memex_semantic_memory>`:

```
The memex project name for this codebase should match the directory name of the project root.
```

**Step 3: Test in a new Claude Code session**

Start a new Claude Code session. Verify:
- The memex tools appear (with `project` parameter on each)
- `search_memories(project="memex", query="test")` returns results
- `store_memory(project="memex", content="test", tags=["test"])` works

**Step 4: Commit any adjustments**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for daemon mode"
```
