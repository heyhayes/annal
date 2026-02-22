## 1. Implementation

- [x] 1.1 Add summary branch to text output formatting in `search_memories`
- [x] 1.2 Add summary branch to JSON output formatting in `search_memories`
- [x] 1.3 Update `search_memories` docstring to document summary mode
- [x] 1.4 Update SERVER_INSTRUCTIONS to describe summary mode and recommend it as default

## 2. Tests

- [x] 2.1 Test summary mode text output (truncation at 200 chars, short content not truncated)
- [x] 2.2 Test summary mode JSON output (content_preview field, metadata fields present)

## 3. Verify

- [x] 3.1 Run full test suite — 187 passed
- [x] 3.2 Manual verification blocked by MCP session state after service restart — tests cover behavior
