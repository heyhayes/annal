## Why

Agents currently need two round-trips to get useful search context: `search_memories(mode="probe")` to scan relevance, then `expand_memories()` to read the ones that matter. This doubles latency for the most common pattern — "do I know anything about this?" A summary mode that returns enough content to decide without expanding would eliminate the second call in most cases.

## What Changes

- `search_memories` gains a third `mode` value: `"summary"`
- Summary mode returns the first ~200 characters of each memory's content alongside full metadata (tags, score, source, dates, ID)
- Works with both `output="text"` and `output="json"` formats
- SERVER_INSTRUCTIONS updated to document the new mode

## Capabilities

### New Capabilities
- `search-summary-mode`: A middle-ground search output mode that returns truncated content previews with full metadata, sitting between probe (IDs + scores + one-liner) and full (complete content).

### Modified Capabilities

## Impact

- `src/annal/server.py`: Add summary formatting branch in `search_memories`, update docstring and SERVER_INSTRUCTIONS
- Tests: Add coverage for summary mode in both text and JSON output
