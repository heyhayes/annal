# Dashboard Polish Design

## Goal

Upgrade the dashboard from a static status display to an interactive, interconnected experience. Activity entries link to projects and show timestamps. Stats expand inline to show per-project breakdowns with drill-down navigation. Visual polish brings transitions, color-coded feed entries, and a favicon.

## Changes

### Activity Feed — Timestamps and Links

The `Event` dataclass gains a `created_at: datetime` field defaulting to `datetime.now(timezone.utc)`. The ring buffer stores this along with existing fields. The SSE data format extends from `project|detail` to `project|detail|timestamp_iso` — backward compatible since the JS splits on `|` and treats missing parts as empty strings.

In the Jinja template, project names become `<a>` links to `/memories?project={name}`. Each entry gets a relative timestamp ("2m ago", "1h ago", "3d ago") computed from `event.created_at`. A small JS `timeAgo(iso)` helper handles both server-rendered and live SSE entries, with a 30-second `setInterval` to refresh all visible timestamps.

### Stats Ribbon — Expand Inline

Each stat number becomes a clickable toggle. Alpine.js manages an `expandedStat` state variable on the stats ribbon. Clicking a stat fetches per-project breakdown from `/api/projects` (already loaded by command palette, so this reuses cached data). Clicking the same stat again collapses the panel; clicking a different stat swaps content.

The breakdown panel slides down below the ribbon, showing each project's contribution as a row: project name (linked to `/memories?project={name}&type={filter}`) and count. The `/api/projects` endpoint adds a `stale` field to each project so all four numeric stats can be broken down.

### Visual Polish

- Nav active state: current page link gets a bottom border or highlight via a template variable
- Feed entry left borders: teal for memory_stored/updated, indigo for index_*, red for memory_deleted
- Stats hover effect: number scales up slightly on hover
- Expand panel: CSS transition (max-height + opacity) for smooth open/close
- Status indicator: small colored dot next to "idle"/"indexing" text
- Favicon: inline SVG data URI in base.html — `>_` in amber on dark background

### Files Affected

- `src/annal/events.py` — add `created_at` field to Event
- `src/annal/dashboard/routes.py` — update SSE format, add `stale` to api_projects, add nav active state
- `src/annal/dashboard/templates/dashboard.html` — feed links, timestamps, stats expand, Alpine.js changes
- `src/annal/dashboard/templates/base.html` — favicon, nav active state
- `src/annal/dashboard/static/style.css` — all visual polish
- `tests/test_dashboard.py` — update tests for new SSE format, api_projects stale field
