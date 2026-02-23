# Dashboard Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the project-list landing page with a terminal-style system dashboard featuring a command palette, stats ribbon, and live activity feed.

**Architecture:** New `dashboard.html` template becomes the `/` route. Existing project table moves to `/projects`. Command palette uses Alpine.js (CDN) for client-side fuzzy matching against a `/api/projects` JSON endpoint. Activity feed renders from a new ring buffer on `EventBus` and updates live via SSE.

**Tech Stack:** HTMX, Alpine.js (CDN), Jinja2, Starlette, SSE

---

### Task 1: Event Ring Buffer

Add a fixed-size ring buffer to `EventBus` so the dashboard can render recent activity on initial page load.

**Files:**
- Modify: `src/annal/events.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add to `tests/test_dashboard.py`:

```python
def test_event_bus_ring_buffer():
    """EventBus should store recent events in a ring buffer."""
    from annal.events import EventBus, Event

    bus = EventBus()
    for i in range(5):
        bus.push(Event(type="memory_stored", project="proj", detail=f"mem_{i}"))

    history = bus.recent(limit=3)
    assert len(history) == 3
    # Most recent first
    assert history[0].detail == "mem_4"
    assert history[2].detail == "mem_2"


def test_event_bus_ring_buffer_overflow():
    """Ring buffer should cap at max size, dropping oldest events."""
    from annal.events import EventBus, Event

    bus = EventBus(history_size=10)
    for i in range(25):
        bus.push(Event(type="test", project="p", detail=str(i)))

    history = bus.recent(limit=50)
    assert len(history) == 10
    assert history[0].detail == "24"  # most recent
    assert history[-1].detail == "15"  # oldest retained
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py::test_event_bus_ring_buffer tests/test_dashboard.py::test_event_bus_ring_buffer_overflow -v`
Expected: FAIL — `EventBus.__init__()` doesn't accept `history_size`, no `recent()` method

**Step 3: Implement ring buffer**

In `src/annal/events.py`, modify `EventBus`:

```python
from collections import deque

class EventBus:
    def __init__(self, history_size: int = 50) -> None:
        self._queues: list[queue.Queue[Event]] = []
        self._lock = threading.Lock()
        self._history: deque[Event] = deque(maxlen=history_size)

    def push(self, event: Event) -> None:
        """Push an event to all subscribers and record in history."""
        with self._lock:
            snapshot = list(self._queues)
            self._history.append(event)
        for q in snapshot:
            try:
                q.put_nowait(event)
            except queue.Full:
                logger.warning("SSE client queue full, dropping event")

    def recent(self, limit: int = 20) -> list[Event]:
        """Return the most recent events, newest first."""
        with self._lock:
            items = list(self._history)
        items.reverse()
        return items[:limit]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py::test_event_bus_ring_buffer tests/test_dashboard.py::test_event_bus_ring_buffer_overflow -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/annal/events.py tests/test_dashboard.py
git commit -m "feat(dashboard): add ring buffer to EventBus for activity history"
```

---

### Task 2: API Projects Endpoint

Add a JSON endpoint that returns project metadata for the command palette.

**Files:**
- Modify: `src/annal/dashboard/routes.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add to `tests/test_dashboard.py`:

```python
def test_api_projects(dashboard_client):
    """GET /api/projects returns JSON list of non-empty projects."""
    response = dashboard_client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1  # testproj has 3 memories
    proj = data[0]
    assert proj["name"] == "testproj"
    assert proj["total"] == 3
    assert proj["agent_memory"] == 2
    assert proj["file_indexed"] == 1


def test_api_projects_excludes_empty(tmp_data_dir, tmp_config_path):
    """GET /api/projects excludes projects with zero memories."""
    config = AnnalConfig(
        config_path=tmp_config_path,
        data_dir=tmp_data_dir,
        projects={"empty": ProjectConfig(), "nonempty": ProjectConfig()},
    )
    config.save()
    pool = StorePool(config)
    pool.get_store("nonempty").store("something", tags=["test"], source="test")
    app = create_dashboard_app(pool, config)
    client = TestClient(app)

    data = client.get("/api/projects").json()
    names = [p["name"] for p in data]
    assert "nonempty" in names
    assert "empty" not in names
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py::test_api_projects tests/test_dashboard.py::test_api_projects_excludes_empty -v`
Expected: FAIL — 404, no `/api/projects` route

**Step 3: Implement the endpoint**

In `src/annal/dashboard/routes.py`, add inside `create_routes()`:

```python
from starlette.responses import JSONResponse

async def api_projects(request: Request) -> Response:
    """JSON list of non-empty projects for command palette."""
    projects = []
    for name in sorted(config.projects):
        store = pool.get_store(name)
        stats = store.stats()
        if stats["total"] == 0:
            continue
        projects.append({
            "name": name,
            "total": stats["total"],
            "agent_memory": stats["by_type"].get("agent-memory", 0),
            "file_indexed": stats["by_type"].get("file-indexed", 0),
        })
    return JSONResponse(projects)
```

Add `Route("/api/projects", api_projects)` to the returned routes list.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py::test_api_projects tests/test_dashboard.py::test_api_projects_excludes_empty -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/annal/dashboard/routes.py tests/test_dashboard.py
git commit -m "feat(dashboard): add /api/projects JSON endpoint for command palette"
```

---

### Task 3: Move Project Table to /projects

Move the existing index route from `/` to `/projects`.

**Files:**
- Modify: `src/annal/dashboard/routes.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add to `tests/test_dashboard.py`:

```python
def test_projects_page(dashboard_client):
    """GET /projects shows the project table."""
    response = dashboard_client.get("/projects")
    assert response.status_code == 200
    html = response.text
    assert "testproj" in html
    assert "3" in html  # total memories
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py::test_projects_page -v`
Expected: FAIL — 404 or 405, no `/projects` route

**Step 3: Move the route**

In `src/annal/dashboard/routes.py`:

1. Rename the existing `index` function to `projects_page`
2. In the returned routes list, change `Route("/", index)` to `Route("/projects", projects_page)`
3. Don't add a new `/` route yet (next task)

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py::test_projects_page -v`
Expected: PASS

**Step 5: Update existing tests**

The existing `test_index_page` and `test_index_page_no_projects` tests hit `/` — they'll break. Update them:

- `test_index_page` → change URL to `/projects`, rename to `test_projects_page_with_data` (or keep existing + new)
- `test_index_page_no_projects` → change URL to `/projects`

Run: `pytest tests/test_dashboard.py -v`
Expected: some failures from `/` returning 404. That's OK — we'll fix in the next task.

**Step 6: Commit**

```bash
git add src/annal/dashboard/routes.py tests/test_dashboard.py
git commit -m "refactor(dashboard): move project table from / to /projects"
```

---

### Task 4: Dashboard Landing Page — Route and Template Skeleton

Create the new `/` route and `dashboard.html` template with the three-zone structure.

**Files:**
- Create: `src/annal/dashboard/templates/dashboard.html`
- Modify: `src/annal/dashboard/routes.py`
- Modify: `src/annal/dashboard/templates/base.html`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add to `tests/test_dashboard.py`:

```python
def test_dashboard_landing(dashboard_client):
    """GET / returns the dashboard page with stats and activity feed."""
    response = dashboard_client.get("/")
    assert response.status_code == 200
    html = response.text
    # Stats ribbon should show aggregate numbers
    assert "3" in html  # total memories
    # Command palette input should be present
    assert "search memories" in html.lower() or "jump to project" in html.lower()


def test_dashboard_empty(empty_dashboard_client):
    """GET / with no projects shows empty-friendly dashboard."""
    response = empty_dashboard_client.get("/")
    assert response.status_code == 200
    assert response.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py::test_dashboard_landing tests/test_dashboard.py::test_dashboard_empty -v`
Expected: FAIL — `/` returns 404

**Step 3: Create dashboard route**

In `src/annal/dashboard/routes.py`, add a new `dashboard` handler:

```python
async def dashboard(request: Request) -> Response:
    """System dashboard landing page."""
    total_memories = 0
    total_agent = 0
    total_stale = 0
    non_empty_projects = 0

    for name in sorted(config.projects):
        store = pool.get_store(name)
        stats = store.stats()
        if stats["total"] == 0:
            continue
        non_empty_projects += 1
        total_memories += stats["total"]
        total_agent += stats["by_type"].get("agent-memory", 0)
        total_stale += stats.get("stale_count", 0) + stats.get("never_accessed_count", 0)

    # Check if any project is currently indexing
    indexing = any(pool.is_indexing(name) for name in config.projects)

    recent_events = event_bus.recent(limit=20)

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_memories": total_memories,
        "total_projects": non_empty_projects,
        "total_agent": total_agent,
        "total_stale": total_stale,
        "indexing": indexing,
        "recent_events": recent_events,
    })
```

Add `Route("/", dashboard)` to the routes list. Import `event_bus` at the top of the function body (it's already imported at module level in some paths — check).

**Step 4: Create dashboard.html skeleton**

Create `src/annal/dashboard/templates/dashboard.html`:

```html
{% extends "base.html" %}

{% block title %}Annal{% endblock %}

{% block content %}
<!-- Zone 1: Command Palette -->
<div class="command-palette" x-data="commandPalette()">
  <div class="palette-input-wrapper">
    <span class="palette-prompt">&gt;_</span>
    <input type="text"
           class="palette-input"
           placeholder="search memories, jump to project..."
           x-model="query"
           @input="onInput()"
           @keydown.arrow-down.prevent="moveDown()"
           @keydown.arrow-up.prevent="moveUp()"
           @keydown.enter.prevent="select()"
           @keydown.escape="close()"
           @focus="open = query.length > 0">
  </div>
  <div class="palette-results" x-show="open" x-cloak>
    <template x-for="(item, index) in filtered" :key="item.name || item.type">
      <a :href="item.url"
         class="palette-result"
         :class="{ 'palette-result--active': index === activeIndex }"
         @mouseenter="activeIndex = index">
        <span class="palette-result-name" x-text="item.label"></span>
        <span class="palette-result-meta" x-text="item.meta"></span>
      </a>
    </template>
    <div class="palette-result palette-result--search"
         :class="{ 'palette-result--active': activeIndex === filtered.length }"
         @mouseenter="activeIndex = filtered.length"
         @click="searchAll()"
         x-show="query.length > 0">
      <span class="palette-result-name">Search all projects for '<span x-text="query"></span>'</span>
    </div>
  </div>
</div>

<!-- Zone 2: Stats Ribbon -->
<div class="stats-ribbon">
  <div class="stat">
    <span class="stat-number">{{ total_memories }}</span>
    <span class="stat-label">memories</span>
  </div>
  <div class="stat-divider"></div>
  <div class="stat">
    <span class="stat-number">{{ total_projects }}</span>
    <span class="stat-label">projects</span>
  </div>
  <div class="stat-divider"></div>
  <div class="stat">
    <span class="stat-number">{{ total_agent }}</span>
    <span class="stat-label">agent</span>
  </div>
  <div class="stat-divider"></div>
  <div class="stat{% if total_stale > 0 %} stat--warning{% endif %}">
    <span class="stat-number">{{ total_stale }}</span>
    <span class="stat-label">stale</span>
  </div>
  <div class="stat-divider"></div>
  <div class="stat">
    <span class="stat-status{% if indexing %} stat-status--active{% endif %}">
      {% if indexing %}indexing…{% else %}idle{% endif %}
    </span>
    <span class="stat-label">status</span>
  </div>
</div>

<!-- Zone 3: Activity Feed -->
<div class="activity-feed" hx-ext="sse" sse-connect="/events">
  <h2 class="feed-title">Activity</h2>
  <div class="feed-container" id="feed-container">
    {% for event in recent_events %}
    <div class="feed-entry">
      <span class="feed-project">{{ event.project }}</span>
      <span class="feed-dot">&middot;</span>
      <span class="feed-action feed-action--{{ event.type }}">{{ event.type.replace('_', ' ') }}</span>
      {% if event.detail %}
      <span class="feed-dot">&middot;</span>
      <span class="feed-detail">{{ event.detail[:80] }}</span>
      {% endif %}
    </div>
    {% endfor %}
    {% if not recent_events %}
    <div class="feed-empty">No recent activity. Memories will appear here as agents store and search.</div>
    {% endif %}
  </div>
</div>

<script>
function commandPalette() {
  return {
    query: '',
    open: false,
    activeIndex: 0,
    projects: [],

    async init() {
      const resp = await fetch('/api/projects');
      this.projects = await resp.json();
    },

    get filtered() {
      if (!this.query) return [];
      const q = this.query.toLowerCase();
      return this.projects
        .filter(p => p.name.toLowerCase().includes(q))
        .slice(0, 7)
        .map(p => ({
          label: p.name,
          meta: p.total + ' memories',
          url: '/memories?project=' + p.name,
        }));
    },

    onInput() {
      this.open = this.query.length > 0;
      this.activeIndex = 0;
    },

    moveDown() {
      const max = this.filtered.length; // +1 for search action
      if (this.activeIndex < max) this.activeIndex++;
    },

    moveUp() {
      if (this.activeIndex > 0) this.activeIndex--;
    },

    select() {
      if (this.activeIndex < this.filtered.length) {
        window.location.href = this.filtered[this.activeIndex].url;
      } else {
        this.searchAll();
      }
    },

    searchAll() {
      if (this.query) {
        window.location.href = '/memories?projects=*&q=' + encodeURIComponent(this.query);
      }
    },

    close() {
      this.open = false;
    }
  };
}
</script>
{% endblock %}
```

**Step 5: Update base.html**

Add Alpine.js CDN and update nav:

```html
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

Update nav links:

```html
<div class="nav-links">
  <a href="/projects">projects</a>
</div>
```

**Step 6: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py::test_dashboard_landing tests/test_dashboard.py::test_dashboard_empty -v`
Expected: PASS

**Step 7: Run full test suite**

Run: `pytest tests/test_dashboard.py -v`
Expected: All pass. Fix any broken tests that expected `/` to be the project table.

**Step 8: Commit**

```bash
git add src/annal/dashboard/templates/dashboard.html src/annal/dashboard/templates/base.html src/annal/dashboard/routes.py tests/test_dashboard.py
git commit -m "feat(dashboard): add terminal-style landing page with command palette, stats, activity feed"
```

---

### Task 5: CSS — Command Palette, Stats Ribbon, Activity Feed

Add all styles for the new dashboard components.

**Files:**
- Modify: `src/annal/dashboard/static/style.css`

**Step 1: Add command palette styles**

```css
/* ── Command Palette ── */

.command-palette {
  position: relative;
  margin-bottom: 2rem;
}

.palette-input-wrapper {
  display: flex;
  align-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 0.6rem 1rem;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.palette-input-wrapper:focus-within {
  border-color: var(--accent-dim);
  box-shadow: 0 0 0 1px var(--accent-glow);
}

.palette-prompt {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 1rem;
  color: var(--accent);
  margin-right: 0.6rem;
  user-select: none;
}

.palette-input {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-bright);
  caret-color: var(--accent);
}

.palette-input::placeholder {
  color: var(--text-muted);
}

.palette-results {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  z-index: 200;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

[x-cloak] { display: none !important; }

.palette-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 1rem;
  text-decoration: none;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.1s;
}

.palette-result:hover,
.palette-result--active {
  background: var(--bg-hover);
}

.palette-result-meta {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.palette-result--search {
  border-top: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 0.8rem;
}
```

**Step 2: Add stats ribbon styles**

```css
/* ── Stats Ribbon ── */

.stats-ribbon {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 2.5rem;
  padding: 1.25rem 0;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}

.stat-number {
  font-family: var(--font-mono);
  font-size: 2rem;
  font-weight: 600;
  color: var(--text-bright);
  line-height: 1;
}

.stat-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-top: 0.4rem;
}

.stat--warning .stat-number {
  color: var(--accent);
}

.stat-status {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--type-agent);
}

.stat-status--active {
  color: var(--accent);
  animation: pulse 1.5s ease-in-out infinite;
}

.stat-divider {
  width: 1px;
  height: 2.5rem;
  background: var(--border);
}
```

**Step 3: Add activity feed styles**

```css
/* ── Activity Feed ── */

.feed-title {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.feed-container {
  max-height: 400px;
  overflow-y: auto;
  position: relative;
  mask-image: linear-gradient(to bottom, black 85%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black 85%, transparent 100%);
}

.feed-entry {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.35rem 0;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  animation: feedIn 0.2s ease-out;
}

@keyframes feedIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.feed-project {
  color: var(--text-bright);
  font-weight: 500;
}

.feed-dot {
  color: var(--text-muted);
}

.feed-action {
  padding: 0.05rem 0.4rem;
  border-radius: 3px;
  font-size: 0.7rem;
  white-space: nowrap;
}

.feed-action--memory_stored {
  background: rgba(45, 212, 191, 0.12);
  color: var(--type-agent);
}

.feed-action--memory_deleted {
  background: rgba(218, 54, 51, 0.12);
  color: var(--danger);
}

.feed-action--memory_updated {
  background: rgba(45, 212, 191, 0.12);
  color: var(--type-agent);
}

.feed-action--index_started,
.feed-action--index_complete,
.feed-action--index_progress {
  background: rgba(129, 140, 248, 0.12);
  color: var(--type-file);
}

.feed-action--index_failed {
  background: rgba(218, 54, 51, 0.12);
  color: var(--danger);
}

.feed-detail {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 500px;
}

.feed-empty {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  padding: 2rem 0;
  text-align: center;
}
```

**Step 4: Visual check**

Run the dashboard locally and verify:
- Command palette renders with `>_` prompt and amber glow on focus
- Stats ribbon shows numbers with dividers
- Activity feed shows "No recent activity" or events if any exist

**Step 5: Commit**

```bash
git add src/annal/dashboard/static/style.css
git commit -m "style(dashboard): command palette, stats ribbon, activity feed CSS"
```

---

### Task 6: SSE Activity Feed Updates

Wire the activity feed to receive live SSE events and prepend new entries.

**Files:**
- Modify: `src/annal/dashboard/templates/dashboard.html`

**Step 1: Add SSE event listeners to dashboard.html**

Add to the `<script>` section at the bottom of `dashboard.html`:

```javascript
// SSE activity feed updates
document.body.addEventListener('sse:memory_stored', function(e) {
  prependFeedEntry(e.detail.value, 'memory stored');
});
document.body.addEventListener('sse:memory_deleted', function(e) {
  prependFeedEntry(e.detail.value, 'memory deleted');
});
document.body.addEventListener('sse:memory_updated', function(e) {
  prependFeedEntry(e.detail.value, 'memory updated');
});
document.body.addEventListener('sse:index_started', function(e) {
  prependFeedEntry(e.detail.value, 'index started');
  updateStatus(true);
});
document.body.addEventListener('sse:index_complete', function(e) {
  prependFeedEntry(e.detail.value, 'index complete');
  updateStatus(false);
});

function prependFeedEntry(value, action) {
  var parts = value.split('|');
  var project = parts[0] || '';
  var detail = parts[1] || '';
  var eventType = action.replace(/ /g, '_');
  var container = document.getElementById('feed-container');
  if (!container) return;

  // Remove "no recent activity" message if present
  var empty = container.querySelector('.feed-empty');
  if (empty) empty.remove();

  var entry = document.createElement('div');
  entry.className = 'feed-entry';
  entry.innerHTML =
    '<span class="feed-project">' + project + '</span>' +
    '<span class="feed-dot">&middot;</span>' +
    '<span class="feed-action feed-action--' + eventType + '">' + action + '</span>' +
    (detail ? '<span class="feed-dot">&middot;</span><span class="feed-detail">' + detail.substring(0, 80) + '</span>' : '');
  container.insertBefore(entry, container.firstChild);

  // Cap visible entries
  while (container.children.length > 20) {
    container.removeChild(container.lastChild);
  }
}

function updateStatus(indexing) {
  var el = document.querySelector('.stat-status');
  if (!el) return;
  el.textContent = indexing ? 'indexing…' : 'idle';
  el.className = 'stat-status' + (indexing ? ' stat-status--active' : '');
}
```

**Step 2: Ensure SSE connection is in the template**

The `hx-ext="sse" sse-connect="/events"` attribute on the activity feed div handles this. Verify it's wired up correctly in the Zone 3 section of `dashboard.html`.

**Step 3: Manual test**

Start the server, open the dashboard, store a memory via MCP, and verify the feed updates in real time.

**Step 4: Commit**

```bash
git add src/annal/dashboard/templates/dashboard.html
git commit -m "feat(dashboard): wire SSE events to live activity feed"
```

---

### Task 7: Final Integration — Nav, Tests, Cleanup

Update nav links, fix any broken tests, run full suite.

**Files:**
- Modify: `src/annal/dashboard/templates/base.html`
- Modify: `tests/test_dashboard.py`

**Step 1: Update nav in base.html**

Ensure the nav has the correct links:

```html
<div class="nav-links">
  <a href="/projects">projects</a>
</div>
```

**Step 2: Fix broken tests**

Update all tests that hit `/` expecting the project table:
- `test_index_page` → rename to `test_projects_page_with_data`, change URL to `/projects`
- `test_index_page_no_projects` → rename to `test_projects_page_empty`, change URL to `/projects`
- `test_index_page_has_sse_connection` → change URL to `/` (dashboard) or `/projects` as appropriate

Ensure new tests cover:
- `test_dashboard_landing` — `/` returns 200 with stats
- `test_dashboard_empty` — `/` returns 200 with no projects
- `test_projects_page` — `/projects` returns 200 with project table
- `test_api_projects` — `/api/projects` returns JSON
- `test_event_bus_ring_buffer` — ring buffer works

**Step 3: Run full test suite**

Run: `pytest -v`
Expected: All 270+ tests pass

**Step 4: Commit**

```bash
git add -A
git commit -m "feat(dashboard): terminal dashboard redesign complete"
```
