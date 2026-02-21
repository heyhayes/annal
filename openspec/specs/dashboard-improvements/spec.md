# Dashboard Improvements

## Problem

The dashboard is useful for inspecting and managing memories but has scaling and functionality gaps. `browse()` loads the entire collection into memory on every page view, which becomes expensive for projects with tens of thousands of file-indexed chunks. Dashboard search hard-limits results to a single page with no pagination. There is no way to create or edit memories from the dashboard — it is read-only plus delete. And there is no programmatic health check for monitoring the daemon in production.

## Requirements

Server-side browse pagination: `browse()` currently fetches all chunks, filters in Python, then slices for the requested page. For large projects (30k+ chunks from vendor directories), this is expensive per page view. Use ChromaDB's `where` filter for chunk_type natively (already passed), and implement cursor-based or offset-based pagination at the database layer rather than loading everything into memory.

Server-side search pagination: `_fetch_memories` in search mode hard-limits results to `PAGE_SIZE` and always reports `total_pages = 1`. As data grows, this caps discoverability. Expose offset/page parameters so agents and dashboard users can paginate through search results.

Memory creation UI: the dashboard supports browse, search, and delete, but not store or edit. Add a simple form to create and edit memories from the dashboard. This makes the dashboard useful as a standalone knowledge management tool, not just an inspector — valuable for manual curation, testing, and non-agent users.

Health check endpoint: add a `/health` endpoint returning service status, uptime, ChromaDB connectivity, and per-project indexing state. Useful for monitoring the daemon in production, especially under systemd/launchd where service health checks can trigger automatic restarts.

## Prior art

Backlog items: "Performance with large result sets" (dashboard section, marked as `[field]`). The spike 4 design doc acknowledged browse pagination as a non-goal for that spike but flagged it as a known limitation.

Agent feedback: Claude item 8 (browse loads entire collection, suggesting a lightweight metadata index). Claude item 18 (dashboard memory creation UI). Claude item 19 (health check endpoint). ChatGPT flagged dashboard search pagination and the hard-limit on search results.

## Priority

P2 — Server-side pagination is the most immediately impactful item, preventing the dashboard from becoming unusable on large projects. The health check endpoint is small and high-value for production deployments. Memory creation UI is a larger effort but would significantly expand the dashboard's utility.
