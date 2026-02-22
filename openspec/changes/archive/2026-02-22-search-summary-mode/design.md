## Context

`search_memories` currently supports two modes: `probe` (first line + scores, designed for scanning) and `full` (complete content). Agents typically probe first, then call `expand_memories` for results they care about — two round-trips for the common "do I know anything about this?" pattern.

## Goals / Non-Goals

Goals:
- Add `mode="summary"` that returns enough content to judge relevance without a follow-up call
- Keep it consistent with existing probe/full formatting patterns in both text and JSON output
- Update SERVER_INSTRUCTIONS so agents know to prefer summary over probe+expand

Non-Goals:
- Changing probe or full mode behavior
- Adding smart summarization (LLM-generated summaries) — raw truncation is sufficient
- Modifying the store layer — this is purely a presentation change in server.py

## Decisions

### Decision 1: 200-character truncation, consistent with JSON probe

JSON probe mode already returns `content_preview` at 200 chars. Summary mode uses the same limit for consistency. Text probe uses 150 chars of the first line — summary expands this to 200 chars of the full content (not just first line), which captures more context for multi-line memories.

### Decision 2: Summary as recommended default in SERVER_INSTRUCTIONS

The instructions should steer agents toward summary as the go-to mode. Probe remains available for when context window is extremely tight. Full remains available when the agent already knows it needs complete content (e.g. expanding a specific result).

### Decision 3: Reuse content_preview key in JSON output

Summary JSON uses `content_preview` (same key as probe JSON) rather than introducing a new field name. This keeps the response schema simple — consumers already handle `content_preview`.
