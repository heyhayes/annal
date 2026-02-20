# Spike 3 Design — API Hardening, Live Dashboard, One-Shot Install

## Goal

Harden the MCP API based on real multi-client battle testing (Codex, Gemini, Claude), add live feedback to the dashboard, improve watcher resilience, and provide a zero-config install experience.

## Items

### 1. Tags input normalization

Coerce `tags` from `str | list[str]` to `list[str]` at the MCP tool boundary in `server.py`. Lowercase and dedupe on store. No changes to the store layer. Affects `store_memory`, `search_memories`, and `expand_memories` (the `memory_ids` param is fine as-is).

### 2. Default min_score cutoff

Add `min_score: float = 0.0` param to `search_memories`. Suppress negative scores by default. Filter after `store.search()` returns, before formatting. One-line filter: `results = [r for r in results if r["score"] >= min_score]`.

### 3. Dashboard SSE live updates

SSE endpoint at `/events` in dashboard routes. Server maintains an `asyncio.Queue` per connected client. Events pushed from `store_memory`, `delete_memory`, `index_files` in `server.py` via a shared event bus (simple list of queues). HTMX subscribes with `hx-ext="sse"` — events trigger a refetch of `/memories/table` rather than pushing HTML over SSE. Activity indicator in nav shows "Indexing..." during reconciliation via same SSE channel.

### 4. Watcher resilience

Wrap `index_file()` calls in `_IndexHandler` event handlers with try/except — log error, continue. Same for `reconcile()` loop — catch per-file exceptions so one bad file doesn't kill reconciliation.

### 5. update_memory tool

New MCP tool: `update_memory(project, memory_id, content?, tags?, source?)`. Uses `collection.update()` to modify in place. Preserves ID and `created_at`, adds `updated_at`. New `update` method on `MemoryStore`.

### 6. annal install

New CLI subcommand. Auto-detects OS and installed MCP clients. Creates `~/.annal/config.yaml` if missing. Installs OS service (systemd/launchd/Windows scheduled task) with correct Python path. Configures Claude Code (`~/.mcp.json`), Codex (`~/.codex/config.toml`), Gemini (`~/.gemini/settings.json`) — only clients that are detected. Enables and starts the service. Prints summary. Counterpart `annal uninstall` removes everything.

## Key files

- `src/annal/server.py` — tags normalization, min_score, update_memory tool, event bus
- `src/annal/store.py` — update() method
- `src/annal/watcher.py` — try/except in handlers and reconcile
- `src/annal/dashboard/routes.py` — SSE endpoint
- `src/annal/dashboard/templates/memories.html` — SSE subscription, activity indicator
- `src/annal/dashboard/templates/base.html` — activity indicator in nav
- `src/annal/cli.py` — new module for install/uninstall subcommands
- `contrib/` — service file templates (already exist for systemd/launchd/Windows)
- `tests/` — tests for each item
