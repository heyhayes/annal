# Developer Experience

## Problem

Several practical gaps make Annal harder to adopt, configure, and maintain than it needs to be. Project names aren't validated (spaces or slashes produce invalid ChromaDB collection names). Config and data live at hardcoded `~/.annal/` instead of OS-appropriate locations. There is no way to export or import memories for backup, portability, or testing. The CLI is limited to starting the server — there is no way to search, store, or inspect memories from the terminal without the full agent stack. These friction points compound for users managing multiple projects across platforms.

## Requirements

Project name sanitization: validate and slugify project names on input (lowercase, `[a-z0-9_-]`, collapse other characters to `_`). Store the original display name separately if provided. Reject or transform names that would produce invalid ChromaDB collection names.

Platform-native paths: use `platformdirs` to place config and data in OS-appropriate locations (`~/.config/annal/` + `~/.local/share/annal/` on Linux, `~/Library/Application Support/annal/` on macOS, `%APPDATA%\annal\` on Windows). Provide a migration path from existing `~/.annal/` installs — detect the old location and offer to move data.

Cross-platform path handling: audit and test all file path operations on macOS and Windows. File watcher paths, config paths, and watch pattern matching should work correctly across all three OSes.

`.gitignore` for data directory: ensure ChromaDB storage doesn't accidentally get committed if a project is initialized inside a git repo. Create a `.gitignore` in the data directory, or document the exclusion clearly.

Import/export: export a project's memories to JSONL (id, content, metadata per line), import from JSONL. Simple format, no external dependencies. Useful for backup, portability, testing, and open-source readiness.

CLI subcommands: extend the `annal` entry point beyond server startup. Add `annal search "query" --project foo --tags decision`, `annal store --project foo --tags decision`, `annal topics --project foo`, `annal export --project foo > backup.jsonl`. Makes Annal usable from the terminal without the agent stack — good for debugging, manual curation, and scripting.

Migration tooling: when config paths or collection naming changes, provide a migration command that moves existing data rather than requiring a fresh start.

Cold start performance: the first query loads the ONNX embedding model, which may cause a noticeable delay or MCP timeout. Evaluate whether eager loading (at server startup) or a warm-up probe is needed.

Watch pattern `.yml` support: default watch patterns include `**/*.yaml` but not `**/*.yml`. Add `**/*.yml` to defaults so both extensions are indexed without manual config.

`annal serve` dead weight: the `serve` subcommand was added but existing service files and scripts use bare `annal --transport ...`. Evaluate whether `serve` has any consumers and remove if not.

Path traversal protection: sanitize any tool parameter that accepts a filename or path to prevent agents from reading/writing files outside designated directories.

## Prior art

Backlog items: "Platform-native default paths", "Project name sanitization", "CLI subcommands", "Import/export", "Migration tooling", "Cold start performance", ".gitignore for data dir", "Cross-platform path handling", "`annal serve` subcommand may be dead weight".

Agent feedback: ChatGPT flagged the `.yml` watch pattern mismatch. Gemini flagged path traversal protection and directory existence checks. Claude noted the README test count staleness (tracked under minor polish).

## Priority

P2 — These are quality-of-life improvements that reduce adoption friction. Project name sanitization and path traversal protection are the most immediately impactful (preventing runtime errors and security issues). Import/export and CLI subcommands have the highest leverage for users managing memories outside the agent loop.
