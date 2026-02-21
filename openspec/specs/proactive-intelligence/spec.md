# Proactive Intelligence

## Problem

Annal is currently passive — agents must explicitly call `search_memories` to retrieve context. In practice, agents often forget to search or don't know what to search for until they've already made a decision that contradicts prior knowledge. The most valuable memory system would surface relevant context automatically based on what the agent is currently doing, without requiring explicit queries. Gemini's field-testing feedback focused heavily on this gap.

## Requirements

Context injection: given the agent's current working files or diff, automatically identify and surface relevant memories. This could be triggered by file-change events from the watcher, a dedicated `get_context(project, files)` tool, or integration with agent hooks that fire on file open or edit. Returns a compact summary of relevant memories, not full content.

Git commit indexing: automatically index git commit messages and diffs as memories, providing a timeline of changes that agents can search. Triggered by a post-commit hook or periodic scan of `git log`. Each commit becomes a memory tagged with `indexed`, `git-commit`, and relevant file paths.

Semantic summarization: when search returns many results, optionally summarize them into a coherent narrative rather than returning individual items. Requires an LLM call (lightweight model) to synthesize. Useful for broad queries like "what do we know about the billing system" where 15 individual memories are less useful than a 3-paragraph summary.

## Prior art

Backlog items: "LLM enrichment" section (summarize the "why" from business documents, figure out where the "why" comes from). "Passive vs active memory problem" in the adoption section identifies the core tension — agents default to passive memory (MEMORY.md) because it requires no decisions about when to search.

Agent feedback: Gemini items 1-3 (context injection, git indexing, summarization).

## Priority

P3 — Future-facing. No spike planned yet. These features require LLM integration (summarization) or deeper agent-tool coupling (context injection) that goes beyond the current MCP tool model. Git commit indexing is the most self-contained piece and could be prototyped independently.
