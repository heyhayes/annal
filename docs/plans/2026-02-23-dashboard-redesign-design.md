# Dashboard Redesign — Terminal Dashboard

Date: 2026-02-23

## Problem

The current dashboard landing page is a project list table. It works functionally but reads as a data dump — two search inputs, empty projects cluttering the view, no visual hierarchy. Not compelling for screenshots or daily use.

## Design

Replace the landing page with a terminal-style system dashboard. The project table moves to a secondary `/projects` page. The new landing page has three zones.

### Zone 1: Command Palette

A full-width input styled like a terminal prompt with the `>_` prefix in amber, monospace font. Placeholder: "search memories, jump to project..."

When the user types, a dropdown appears below with two sections: matching projects (fuzzy-matched, showing name + memory count) and a "Search all projects for '...'" action. Enter on a project navigates to its memories page; Enter on the search action runs cross-project semantic search. Escape closes the dropdown.

Powered by Alpine.js for fuzzy matching and keyboard navigation (up/down arrows, Enter, Escape). Project data fetched from `/api/projects` on page load.

### Zone 2: Stats Ribbon

A horizontal row of 4-5 stats aggregated across all projects. Each stat is a vertical stack (big number in JetBrains Mono 600 weight ~2rem, label below in Source Sans 3 secondary text). Stats separated by subtle vertical dividers, no card borders.

Stats shown:
- Total memories (all projects)
- Projects (non-empty count)
- Agent memories (total across projects)
- Stale memories (total stale + never-accessed, amber accent if > 0)
- Status indicator: green "idle" or amber "indexing..." with pulse animation

### Zone 3: Activity Feed

A reverse-chronological log of recent operations, styled like terminal output. Each line is a single row: `[HH:MM]  project  ·  action  ·  detail`.

- Timestamp in muted text
- Project name in bright text
- Action in a coloured badge: green (stored), red (deleted), blue/indigo (indexed)
- Detail truncated with ellipsis

Capped at ~20 entries. Container has max-height with overflow-y scroll and a gradient fade at the bottom. New entries animate in from the top via SSE. Initial render pulls from an in-memory ring buffer.

### Navigation

The nav bar gains a second link. Landing page is `/` (dashboard). Project table moves to `/projects`. Optionally a "memories" link for cross-project search.

### Visual Design

Keeps the existing palette: dark deep blue `#0a0e17`, amber accent `#f0b429`, JetBrains Mono + Source Sans 3. No new fonts or colours.

Command palette: `--bg-surface` background, subtle border, amber glow on focus. Dropdown uses `--bg-raised`. Results highlighted on hover/keyboard.

Stats ribbon: numbers pop via larger monospace font. No card chrome — just numbers, labels, and dividers.

Activity feed: monospace, compact, left-aligned. Gradient fade at bottom edge.

## Routes

### New

- `GET /` — dashboard landing page. Computes aggregate stats, collects recent events from ring buffer. Returns `dashboard.html`.
- `GET /api/projects` — JSON list of `{name, total, agent_memory, file_indexed}` for non-empty projects. Used by the command palette for client-side fuzzy matching.

### Changed

- `GET /projects` — the existing project overview table, moved from `/`. Template unchanged (index.html).

### Unchanged

- `GET /memories` — memories browser page
- `GET /memories/table` — HTMX partial
- `POST /search` — HTMX search
- `POST /memories/bulk-delete` / `bulk-delete-filter`
- `GET /events` — SSE endpoint

## Implementation

### New files

- `src/annal/dashboard/templates/dashboard.html` — new landing page template
- Alpine.js added via CDN in `base.html`

### Modified files

- `src/annal/events.py` — add ring buffer (last 50 events) to `event_bus` for initial activity feed render
- `src/annal/dashboard/routes.py` — new `/` route (dashboard), new `/api/projects` JSON endpoint, existing index route moved to `/projects`
- `src/annal/dashboard/static/style.css` — styles for command palette, stats ribbon, activity feed
- `src/annal/dashboard/templates/base.html` — Alpine.js CDN link, updated nav links

### Dependencies

- Alpine.js via CDN (no build step, no npm)

## What stays the same

The memories browser page, project table page, all HTMX interactions, SSE subscriptions, bulk delete, filters, pagination, and existing CSS variables/components are untouched (except the project table's URL moving from `/` to `/projects`).
