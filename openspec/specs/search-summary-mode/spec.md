# search-summary-mode Specification

## Purpose
TBD - created by archiving change search-summary-mode. Update Purpose after archive.
## Requirements
### Requirement: Summary mode returns truncated content with full metadata

The `search_memories` tool SHALL accept `mode="summary"` as a valid mode value. Summary mode SHALL return the first 200 characters of each memory's content alongside all metadata fields (tags, score, source, created_at, updated_at, ID).

#### Scenario: Summary mode text output

- **WHEN** agent calls `search_memories(project="foo", query="auth", mode="summary")`
- **THEN** each result includes content truncated to 200 characters with "…" suffix if truncated
- **AND** each result includes score, tags, source, date, and ID
- **AND** results that are 200 characters or fewer are shown in full without truncation marker

#### Scenario: Summary mode JSON output

- **WHEN** agent calls `search_memories(project="foo", query="auth", mode="summary", output="json")`
- **THEN** each result object includes a `content_preview` field with first 200 characters
- **AND** each result object includes `tags`, `score`, `source`, `created_at`, `updated_at`, and `id` fields
- **AND** the response `meta.mode` field is `"summary"`

#### Scenario: Summary mode with cross-project search

- **WHEN** agent calls `search_memories(project="foo", query="auth", mode="summary", projects="*")`
- **THEN** results include a `project` field identifying the source project
- **AND** content truncation and metadata behave identically to single-project summary

### Requirement: Summary mode documented in SERVER_INSTRUCTIONS

The MCP server instructions SHALL describe the summary mode alongside probe and full modes, explaining when agents should use each.

#### Scenario: Mode guidance in instructions

- **WHEN** an agent reads the MCP server instructions
- **THEN** the instructions describe three modes: probe (compact scan), summary (truncated content + metadata), and full (complete content)
- **AND** the instructions recommend summary as the default for most searches

