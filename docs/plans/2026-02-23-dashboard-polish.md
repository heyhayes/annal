# Dashboard Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the dashboard from a static status display to an interactive, interconnected experience with timestamps, linked projects, expandable stats, and visual polish.

**Architecture:** Add `created_at` to Event for timestamps, extend SSE format with ISO timestamp, add `stale` to `/api/projects` for stats breakdowns. Alpine.js manages stats expand/collapse. CSS adds left-border colors, hover effects, transitions. SVG favicon as data URI.

**Tech Stack:** HTMX, Alpine.js (CDN), Jinja2, Starlette, SSE

**Design review notes (incorporated below):**
- Feed entries use CSS grid (not flex) for aligned columns
- Breakdown panel uses `grid-template-rows: 0fr/1fr` transition (not `max-height`)
- Stats ribbon gets contained background (`bg-surface` + border)
- Body gets subtle dot grid background texture
- Command palette focus gets stronger double box-shadow glow
- Feed left-borders are 3px (not 2px)
- Source Sans 3 used deliberately for non-data text (feed-detail, empty states)
- Favicon uses `<path>` elements (not `<text>`) for clean 16px rendering

---

### Task 1: Event Timestamps

Add `created_at` to the `Event` dataclass and extend the SSE data format.

**Files:**
- Modify: `src/annal/events.py`
- Modify: `src/annal/dashboard/routes.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add to `tests/test_dashboard.py`:

```python
def test_event_has_created_at():
    """Events should have a created_at timestamp."""
    from datetime import datetime, timezone
    from annal.events import Event

    event = Event(type="memory_stored", project="test", detail="d")
    assert hasattr(event, "created_at")
    assert isinstance(event.created_at, str)
    # Should be a valid ISO timestamp
    parsed = datetime.fromisoformat(event.created_at)
    assert parsed.tzinfo is not None
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_event_has_created_at -v`
Expected: FAIL — `Event` has no `created_at` attribute

**Step 3: Implement**

In `src/annal/events.py`, add to imports:

```python
from datetime import datetime, timezone
```

Update the `Event` dataclass — add a `created_at` field with a factory default:

```python
from dataclasses import dataclass, field

@dataclass
class Event:
    """A dashboard event."""
    type: str
    project: str
    detail: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_event_has_created_at -v`
Expected: PASS

**Step 5: Update SSE format**

In `src/annal/dashboard/routes.py`, in the `events()` handler, change the SSE data line from:

```python
yield f"event: {event.type}\ndata: {safe_project}|{safe_detail}\n\n"
```

to:

```python
yield f"event: {event.type}\ndata: {safe_project}|{safe_detail}|{event.created_at}\n\n"
```

**Step 6: Update SSE test**

The existing `test_sse_endpoint_streams_events` asserts `"data: test|id123"`. Update to check for the timestamp field:

Change:
```python
assert "data: test|id123" in chunk
```
to:
```python
assert "data: test|id123|" in chunk
```

**Step 7: Run full dashboard tests**

Run: `.venv/bin/pytest tests/test_dashboard.py -v`
Expected: All pass

**Step 8: Commit**

```bash
git add src/annal/events.py src/annal/dashboard/routes.py tests/test_dashboard.py
git commit -m "feat(dashboard): add created_at timestamp to Event and SSE format"
```

---

### Task 2: Activity Feed — Links and Timestamps

Update the activity feed to show linked project names and relative timestamps.

**Files:**
- Modify: `src/annal/dashboard/templates/dashboard.html`
- Modify: `src/annal/dashboard/static/style.css`

**Step 1: Update Jinja template for server-rendered entries**

In `src/annal/dashboard/templates/dashboard.html`, replace the feed entry block (lines 76-84):

```html
{% for event in recent_events %}
<div class="feed-entry">
  <a href="/memories?project={{ event.project }}" class="feed-project">{{ event.project }}</a>
  <span class="feed-dot">&middot;</span>
  <span class="feed-action feed-action--{{ event.type }}">{{ event.type.replace('_', ' ') }}</span>
  {% if event.detail %}
  <span class="feed-dot">&middot;</span>
  <span class="feed-detail">{{ event.detail[:80] }}</span>
  {% endif %}
  <span class="feed-time" data-ts="{{ event.created_at }}"></span>
</div>
{% endfor %}
```

**Step 2: Update JS `prependFeedEntry` for live SSE entries**

In the `prependFeedEntry` function, update to:
1. Parse the third `|`-delimited field as the timestamp
2. Create a project link `<a>` instead of `<span>`
3. Add a timestamp `<span class="feed-time">`

Replace the function signature and the first few lines:

```javascript
function prependFeedEntry(value, action) {
  var parts = value.split('|');
  var project = parts[0] || '';
  var detail = parts[1] || '';
  var timestamp = parts[2] || new Date().toISOString();
  var eventType = action.replace(/ /g, '_');
  var container = document.getElementById('feed-container');
  if (!container) return;

  var empty = container.querySelector('.feed-empty');
  if (empty) empty.remove();

  var entry = document.createElement('div');
  entry.className = 'feed-entry';

  var projLink = document.createElement('a');
  projLink.className = 'feed-project';
  projLink.href = '/memories?project=' + encodeURIComponent(project);
  projLink.textContent = project;
  entry.appendChild(projLink);

  var dot1 = document.createElement('span');
  dot1.className = 'feed-dot';
  dot1.textContent = '\u00b7';
  entry.appendChild(dot1);

  var actionSpan = document.createElement('span');
  actionSpan.className = 'feed-action feed-action--' + eventType;
  actionSpan.textContent = action;
  entry.appendChild(actionSpan);

  if (detail) {
    var dot2 = document.createElement('span');
    dot2.className = 'feed-dot';
    dot2.textContent = '\u00b7';
    entry.appendChild(dot2);

    var detailSpan = document.createElement('span');
    detailSpan.className = 'feed-detail';
    detailSpan.textContent = detail.substring(0, 80);
    entry.appendChild(detailSpan);
  }

  var timeSpan = document.createElement('span');
  timeSpan.className = 'feed-time';
  timeSpan.dataset.ts = timestamp;
  timeSpan.textContent = timeAgo(timestamp);
  entry.appendChild(timeSpan);

  container.insertBefore(entry, container.firstChild);

  while (container.children.length > 20) {
    container.removeChild(container.lastChild);
  }
}
```

**Step 3: Add timeAgo helper and refresh interval**

Add before the SSE event listeners:

```javascript
function timeAgo(iso) {
  var now = Date.now();
  var then = new Date(iso).getTime();
  var seconds = Math.floor((now - then) / 1000);
  if (seconds < 5) return 'now';
  if (seconds < 60) return seconds + 's ago';
  var minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + 'm ago';
  var hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + 'h ago';
  var days = Math.floor(hours / 24);
  return days + 'd ago';
}

// Refresh all visible timestamps every 30s
setInterval(function() {
  document.querySelectorAll('.feed-time[data-ts]').forEach(function(el) {
    el.textContent = timeAgo(el.dataset.ts);
  });
}, 30000);

// Initial render of server-side timestamps
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.feed-time[data-ts]').forEach(function(el) {
    el.textContent = timeAgo(el.dataset.ts);
  });
});
```

**Step 4: Update feed CSS to use grid layout and add link/time styles**

In `src/annal/dashboard/static/style.css`, replace the existing `.feed-entry` rule and add new rules. The feed entry switches from flex to CSS grid for aligned columns:

```css
.feed-entry {
  display: grid;
  grid-template-columns: 120px auto 1fr auto;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.35rem 0;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  animation: feedIn 0.2s ease-out;
}
```

Add link and time styles:

```css
a.feed-project {
  color: var(--text-bright);
  font-weight: 500;
  text-decoration: none;
  transition: color 0.15s;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

a.feed-project:hover {
  color: var(--accent);
}

.feed-detail {
  font-family: var(--font-ui);
}

.feed-time {
  color: var(--text-muted);
  font-size: 0.68rem;
  white-space: nowrap;
  text-align: right;
}
```

Note: `.feed-detail` switches to `--font-ui` (Source Sans 3) to create visual hierarchy — data identifiers stay in mono, natural language description uses the proportional font.

**Step 5: Commit**

```bash
git add src/annal/dashboard/templates/dashboard.html src/annal/dashboard/static/style.css
git commit -m "feat(dashboard): add project links and relative timestamps to activity feed"
```

---

### Task 3: Expandable Stats Ribbon

Make each stat number clickable to expand a per-project breakdown panel.

**Files:**
- Modify: `src/annal/dashboard/routes.py` (add `stale` to api_projects)
- Modify: `src/annal/dashboard/templates/dashboard.html`
- Modify: `src/annal/dashboard/static/style.css`
- Test: `tests/test_dashboard.py`

**Step 1: Write failing test for stale in api_projects**

Add to `tests/test_dashboard.py`:

```python
def test_api_projects_includes_stale(dashboard_client):
    """GET /api/projects includes stale count per project."""
    data = dashboard_client.get("/api/projects").json()
    proj = data[0]
    assert "stale" in proj
    assert isinstance(proj["stale"], int)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_api_projects_includes_stale -v`
Expected: FAIL — `stale` key not in response

**Step 3: Add stale to api_projects**

In `src/annal/dashboard/routes.py`, in the `api_projects` handler, add to each project dict:

```python
projects.append({
    "name": name,
    "total": stats["total"],
    "agent_memory": stats["by_type"].get("agent-memory", 0),
    "file_indexed": stats["by_type"].get("file-indexed", 0),
    "stale": stats.get("stale_count", 0) + stats.get("never_accessed_count", 0),
})
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_api_projects_includes_stale -v`
Expected: PASS

**Step 5: Wrap stats ribbon in Alpine.js**

In `src/annal/dashboard/templates/dashboard.html`, replace the stats ribbon (lines 42-69) with:

```html
<!-- Zone 2: Stats Ribbon -->
<div class="stats-ribbon-container" x-data="statsBreakdown()">
  <div class="stats-ribbon">
    <div class="stat stat--clickable" @click="toggle('total')">
      <span class="stat-number">{{ total_memories }}</span>
      <span class="stat-label">memories</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat stat--clickable" @click="toggle('projects')">
      <span class="stat-number">{{ total_projects }}</span>
      <span class="stat-label">projects</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat stat--clickable" @click="toggle('agent')">
      <span class="stat-number">{{ total_agent }}</span>
      <span class="stat-label">agent</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat stat--clickable{% if total_stale > 0 %} stat--warning{% endif %}" @click="toggle('stale')">
      <span class="stat-number">{{ total_stale }}</span>
      <span class="stat-label">stale</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat">
      <span class="stat-status{% if indexing %} stat-status--active{% endif %}">
        <span class="status-dot{% if indexing %} status-dot--active{% endif %}"></span>
        {% if indexing %}indexing…{% else %}idle{% endif %}
      </span>
      <span class="stat-label">status</span>
    </div>
  </div>

  <!-- Breakdown panel — CSS grid transition, no Alpine x-transition needed -->
  <div class="stat-breakdown-wrapper" :class="expanded ? 'stat-breakdown--open' : ''">
    <div class="stat-breakdown">
      <template x-for="p in breakdownData" :key="p.name">
        <a :href="p.url" class="breakdown-row">
          <span class="breakdown-name" x-text="p.name"></span>
          <span class="breakdown-count" x-text="p.count"></span>
        </a>
      </template>
    </div>
  </div>
</div>
```

**Step 6: Add statsBreakdown Alpine component**

Add to the `<script>` section, before `commandPalette()`:

```javascript
function statsBreakdown() {
  return {
    expanded: null,
    projects: [],

    async init() {
      var resp = await fetch('/api/projects');
      this.projects = await resp.json();
    },

    toggle(stat) {
      if (this.expanded === stat) {
        this.expanded = null;
      } else {
        this.expanded = stat;
      }
    },

    get breakdownData() {
      if (!this.expanded || !this.projects.length) return [];
      var stat = this.expanded;
      return this.projects
        .map(function(p) {
          var count, filter;
          if (stat === 'total') { count = p.total; filter = ''; }
          else if (stat === 'projects') { count = p.total; filter = ''; }
          else if (stat === 'agent') { count = p.agent_memory; filter = '&type=agent-memory'; }
          else if (stat === 'stale') { count = p.stale; filter = '&stale=1'; }
          else { count = 0; filter = ''; }
          return {
            name: p.name,
            count: count,
            url: '/memories?project=' + p.name + filter
          };
        })
        .filter(function(p) { return p.count > 0; })
        .sort(function(a, b) { return b.count - a.count; });
    }
  };
}
```

**Step 7: Add CSS for expandable stats**

Append to `src/annal/dashboard/static/style.css`:

```css
/* ── Stats Ribbon — interactive ── */

.stats-ribbon-container {
  margin-bottom: 2.5rem;
}

.stats-ribbon-container .stats-ribbon {
  margin-bottom: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 1.25rem 1rem;
}

.stat--clickable {
  cursor: pointer;
  transition: transform 0.1s;
}

.stat--clickable:hover .stat-number {
  transform: scale(1.08);
}

.stat--clickable:hover .stat-label {
  color: var(--text-secondary);
}

.stat-number {
  transition: transform 0.1s;
  display: inline-block;
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--type-agent);
  margin-right: 0.3rem;
  vertical-align: middle;
}

.status-dot--active {
  background: var(--accent);
  animation: pulse 1.5s ease-in-out infinite;
}

/* Breakdown panel — grid-template-rows transition (no max-height jank) */

.stat-breakdown-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.2s ease;
}

.stat-breakdown-wrapper > .stat-breakdown {
  overflow: hidden;
}

.stat-breakdown--open {
  grid-template-rows: 1fr;
}

.stat-breakdown {
  padding: 0;
}

.stat-breakdown--open .stat-breakdown {
  padding: 0.75rem 0;
  border-top: 1px solid var(--border);
}

.breakdown-row {
  display: flex;
  justify-content: space-between;
  padding: 0.3rem 1rem;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  text-decoration: none;
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  transition: background 0.1s, color 0.1s;
}

.breakdown-row:hover {
  background: var(--bg-hover);
  color: var(--accent);
}

.breakdown-name {
  font-weight: 500;
}

.breakdown-count {
  color: var(--text-muted);
}
```

Note: The breakdown panel uses `grid-template-rows: 0fr` → `1fr` for a smooth expand/collapse transition. This avoids the jank of `max-height` transitions where the timing doesn't match the actual content height. The wrapper holds a single child with `overflow: hidden`, and the grid row height animates from zero to content-fit.

**Step 8: Commit**

```bash
git add src/annal/dashboard/routes.py src/annal/dashboard/templates/dashboard.html src/annal/dashboard/static/style.css tests/test_dashboard.py
git commit -m "feat(dashboard): expandable stats ribbon with per-project breakdown"
```

---

### Task 4: Visual Polish and Favicon

Add feed left-border colors, nav active state, favicon, body texture, and focus glow refinements.

**Files:**
- Modify: `src/annal/dashboard/templates/base.html`
- Modify: `src/annal/dashboard/templates/dashboard.html`
- Modify: `src/annal/dashboard/static/style.css`

**Step 1: Add favicon to base.html**

In `src/annal/dashboard/templates/base.html`, add inside `<head>` before the stylesheet link:

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%230a0e17'/><path d='M6 20l8-8M6 20l8 8' stroke='%23f0b429' stroke-width='3' stroke-linecap='round' fill='none'/><line x1='18' y1='28' x2='26' y2='28' stroke='%23f0b429' stroke-width='3' stroke-linecap='round'/></svg>">
```

**Step 2: Add nav active state**

In `src/annal/dashboard/templates/base.html`, update the nav links to accept an active class. Replace the nav-links div:

```html
<div class="nav-links">
  <a href="/projects" {% if request.url.path == '/projects' %}class="nav-link--active"{% endif %}>projects</a>
</div>
```

Note: Starlette's Jinja2Templates automatically makes `request` available in templates.

**Step 3: Add left-border colors to feed entries**

In `src/annal/dashboard/templates/dashboard.html`, update the feed entry div to include the event type as a modifier class:

```html
<div class="feed-entry feed-entry--{{ event.type }}">
```

Also update `prependFeedEntry` in JS to add the class:

```javascript
entry.className = 'feed-entry feed-entry--' + eventType;
```

**Step 4: Add CSS for all visual polish**

Append to `src/annal/dashboard/static/style.css`:

```css
/* ── Body texture — subtle dot grid ── */

body {
  background-image: radial-gradient(circle, var(--border) 1px, transparent 1px);
  background-size: 24px 24px;
}

/* ── Nav active state ── */

.nav-link--active {
  color: var(--accent) !important;
  border-bottom: 2px solid var(--accent);
  padding-bottom: 0.15rem;
}

/* ── Command palette focus — stronger glow ── */

.palette-input-wrapper:focus-within {
  border-color: var(--accent-dim);
  box-shadow: 0 0 0 1px var(--accent-glow), 0 0 12px var(--accent-glow);
}

/* ── Feed entry left borders (3px) ── */

.feed-entry {
  border-left: 3px solid transparent;
  padding-left: 0.5rem;
}

.feed-entry--memory_stored,
.feed-entry--memory_updated {
  border-left-color: var(--type-agent);
}

.feed-entry--memory_deleted {
  border-left-color: var(--danger);
}

.feed-entry--index_started,
.feed-entry--index_complete,
.feed-entry--index_progress {
  border-left-color: var(--type-file);
}

.feed-entry--index_failed {
  border-left-color: var(--danger);
}

/* ── Feed empty state — use UI font ── */

.feed-empty {
  font-family: var(--font-ui);
}
```

Note: The body dot grid creates subtle depth without overwhelming the content. The double box-shadow on command palette focus (inner outline + outer glow) gives a more intentional focus state. The 3px left borders on feed entries provide better visual weight. The font role separation (mono for data, Source Sans 3 for prose) is applied in Task 2's `.feed-detail` rule and here on `.feed-empty`.

**Step 5: Run full test suite**

Run: `.venv/bin/pytest -v`
Expected: All tests pass (273+)

**Step 6: Commit**

```bash
git add src/annal/dashboard/templates/base.html src/annal/dashboard/templates/dashboard.html src/annal/dashboard/static/style.css
git commit -m "feat(dashboard): favicon, nav active state, feed left-border colors"
```

---

## Task order

1 → 2 → 3 → 4

Task 1 is the foundation (Event.created_at + SSE format). Task 2 depends on it (timestamps in feed). Task 3 is independent but logically follows. Task 4 is visual polish that touches everything.

## Files

| File | Tasks |
|------|-------|
| `src/annal/events.py` | 1 |
| `src/annal/dashboard/routes.py` | 1, 3 |
| `src/annal/dashboard/templates/dashboard.html` | 2, 3, 4 |
| `src/annal/dashboard/templates/base.html` | 4 |
| `src/annal/dashboard/static/style.css` | 2, 3, 4 |
| `tests/test_dashboard.py` | 1, 3 |

## Verification

Run `.venv/bin/pytest -v` after task 4. Then restart annal service and test manually:
- Activity feed shows relative timestamps
- Project names in feed are clickable links
- Feed entries align in CSS grid columns (project, action, detail, time)
- Feed detail text renders in Source Sans 3 (proportional), project/action in JetBrains Mono
- Click a stat number → breakdown panel expands smoothly (grid-template-rows transition)
- Click project in breakdown → navigates to filtered memories page
- Click same stat → panel collapses smoothly
- Stats ribbon has contained background with border
- Feed entries have 3px colored left borders (teal for store/update, red for delete, indigo for index)
- `>_` favicon visible in browser tab (path-based SVG, renders clean at 16x16)
- Nav "projects" link highlighted when on `/projects` page
- Subtle dot grid texture visible on body background
- Command palette focus shows double glow (outline + diffuse)
