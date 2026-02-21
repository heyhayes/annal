# Structured Output

## Problem

`search_memories` returns formatted text designed for human and LLM readability, but non-Claude clients (Codex, Gemini, custom integrations) need to process results programmatically. Parsing formatted text is fragile and wastes tokens. Codex specifically requested structured JSON responses during battle testing, and the count-only search mode (covered in the advanced-search spec) is another form of structured output that avoids unnecessary content transfer.

## Requirements

JSON mode: an optional `output` parameter on `search_memories` accepting `"text"` (default, current behavior) or `"json"`. When `"json"`, the response is a structured object:

```json
{
  "results": [
    {
      "id": "...",
      "content_preview": "first 200 chars...",
      "content": "full content (full mode only)",
      "tags": ["decision", "auth"],
      "score": 0.82,
      "source": "agent:code-reviewer",
      "created_at": "2026-02-20T...",
      "updated_at": "2026-02-20T..."
    }
  ],
  "meta": {
    "query": "authentication approach",
    "mode": "full",
    "project": "myapp",
    "total": 12,
    "returned": 5
  }
}
```

Probe mode compatibility: in JSON + probe mode, results include `content_preview` but omit full `content`, matching the current probe behavior.

Expand output: `expand_memories` also supports `output="json"` for consistency.

Backward compatible: text mode remains the default. Existing agent instructions and workflows are unaffected.

## Prior art

Backlog item: "Structured JSON responses" in the battle testing section, noting that Codex suggested `{results: [{id, content_preview, tags, score}], meta: {query, mode, total}}`.

Agent feedback: Codex item 3, Claude's count option (addressed in advanced-search spec as count-only mode).

## Priority

P2 — One agent explicitly requested this, but structured output benefits all non-Claude MCP clients and enables programmatic memory management workflows.
