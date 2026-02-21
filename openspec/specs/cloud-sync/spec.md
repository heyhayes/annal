# Cloud Sync

## Problem

Annal currently runs entirely on a single machine — ChromaDB stores data locally, the MCP server is a local daemon, and there is no mechanism for synchronizing memories across devices. Developers who work from multiple machines (laptop at home, desktop at the office, CI environments) lose access to their accumulated knowledge when they switch contexts. The local-only model also means all embedding computation happens on the user's hardware, which is fine for small stores but becomes a bottleneck as memory volume grows.

This is an aspirational, long-term capability that depends on adoption reaching a point where multi-device usage is a real friction point. The local-first model should remain the default — cloud sync is an opt-in layer for users who need it.

## Requirements

Memory synchronization: memories created or updated on one machine propagate to other machines associated with the same account. Conflict resolution strategy needed for concurrent edits — last-write-wins is simplest, but memory supersession (from the memory-relationships spec) could provide a more principled merge.

Cloud-hosted embedding and search: offload vector embedding and similarity search to a hosted service. For users with large stores, this shifts compute off the local machine. The local ONNX model remains available for offline use and low-latency queries against small stores — the cloud layer is a complement, not a replacement.

Account and authentication: some form of identity to associate memories with a user across devices. Could be as lightweight as a shared API key or as rich as OAuth. Should not require account creation for local-only usage — the cloud layer is entirely opt-in.

Selective sync: not all memories need to sync. Project-scoped sync (sync project X but not project Y) and tag-based sync (sync decisions but not indexed file chunks) would keep bandwidth and storage costs manageable. File-indexed chunks are derivable from the source files and shouldn't need cloud storage.

Encryption: memories may contain sensitive project knowledge, architectural decisions, and codebase-specific context. End-to-end encryption (client-side, before upload) is a baseline requirement. The cloud layer should never have access to plaintext memory content.

Offline-first: the local store remains the source of truth. Cloud sync is eventual-consistency — if the network is unavailable, everything works locally and syncs when connectivity returns. No degradation of local performance or functionality when offline.

Bring-your-own-backend or paid tier: hosting sync infrastructure has real costs (storage, bandwidth, compute for cloud embeddings). Two models should coexist. A managed hosted option behind a paywall for users who want zero-config sync. And a bring-your-own-backend option where users point at their own S3 bucket, Supabase instance, or similar — Annal provides the sync protocol and client, the user provides the storage. The core open-source project stays free and local-first; cloud sync is a premium layer.

## Prior art

No existing backlog items cover this — it's a new capability area. The current architecture (ChromaDB PersistentClient with file-based SQLite storage, project-namespaced collections) is inherently single-machine. A sync layer would sit above the store, replicating changes to/from a remote service.

Analogies in the ecosystem: Obsidian Sync (end-to-end encrypted markdown sync across devices), CouchDB/PouchDB (offline-first sync protocol), Logseq Sync. The common pattern is local-first with background replication.

## Priority

P3 — Future/aspirational. Depends on adoption reaching multi-device usage as a real pain point. The local-first architecture should be fully mature (operational hardening, retrieval quality, search improvements) before adding a sync layer. The most important near-term prerequisite is the import/export capability (in the developer-experience spec), which provides a manual sync escape hatch and validates the serialization format that cloud sync would eventually use.
