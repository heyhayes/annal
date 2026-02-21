"""ChromaDB-backed memory store for Annal."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import chromadb


class MemoryStore:
    def __init__(self, data_dir: str, project: str) -> None:
        self._client = chromadb.PersistentClient(path=data_dir)
        self._collection = self._client.get_or_create_collection(
            name=f"annal_{project}",
            metadata={"hnsw:space": "cosine"},
        )

    def store(
        self,
        content: str,
        tags: list[str],
        source: str = "",
        chunk_type: str = "agent-memory",
        file_mtime: float | None = None,
    ) -> str:
        mem_id = str(uuid.uuid4())
        metadata = {
            "tags": json.dumps(tags),
            "source": source,
            "chunk_type": chunk_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if file_mtime is not None:
            metadata["file_mtime"] = file_mtime
        self._collection.add(
            ids=[mem_id],
            documents=[content],
            metadatas=[metadata],
        )
        return mem_id

    def search(
        self,
        query: str,
        limit: int = 5,
        tags: list[str] | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict]:
        if self._collection.count() == 0:
            return []

        # Over-fetch when filtering post-query (tags or temporal)
        needs_overfetch = tags or after or before
        limit_query = max(limit * 3, 20) if needs_overfetch else limit

        results = self._collection.query(
            query_texts=[query],
            n_results=min(limit_query, self._collection.count()) or 1,
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        memories = []
        for i, mem_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            mem_tags = json.loads(meta["tags"])

            if tags and not any(t in mem_tags for t in tags):
                continue

            # Temporal filtering (ISO 8601 strings are lexicographically orderable)
            created_at = meta.get("created_at", "")
            if after and created_at < after:
                continue
            if before and created_at > before:
                continue

            distance = results["distances"][0][i] if results["distances"] else 0.0
            score = 1.0 - distance

            memories.append({
                "id": mem_id,
                "content": results["documents"][0][i],
                "tags": mem_tags,
                "source": meta.get("source", ""),
                "chunk_type": meta.get("chunk_type", ""),
                "score": score,
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
            })

        return memories[:limit]

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Retrieve full memory records by their IDs."""
        if not ids:
            return []
        results = self._collection.get(ids=ids, include=["documents", "metadatas"])
        memories = []
        for i, mem_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            mem_tags = json.loads(meta["tags"])
            memories.append({
                "id": mem_id,
                "content": results["documents"][i],
                "tags": mem_tags,
                "source": meta.get("source", ""),
                "chunk_type": meta.get("chunk_type", ""),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
            })
        return memories

    def delete(self, mem_id: str) -> None:
        self._collection.delete(ids=[mem_id])

    def update(
        self,
        mem_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> None:
        """Update an existing memory's content, tags, and/or source in place."""
        # Fetch current state
        current = self._collection.get(ids=[mem_id], include=["documents", "metadatas"])
        if not current["ids"]:
            raise ValueError(f"Memory {mem_id} not found")

        old_meta = current["metadatas"][0]
        old_doc = current["documents"][0]

        new_doc = content if content is not None else old_doc
        new_meta = dict(old_meta)
        new_meta["updated_at"] = datetime.now(timezone.utc).isoformat()

        if tags is not None:
            new_meta["tags"] = json.dumps(tags)
        if source is not None:
            new_meta["source"] = source

        self._collection.update(
            ids=[mem_id],
            documents=[new_doc],
            metadatas=[new_meta],
        )

    def delete_many(self, ids: list[str]) -> None:
        """Delete multiple memories by ID in batches."""
        for i in range(0, len(ids), 5000):
            self._collection.delete(ids=ids[i:i + 5000])

    def _iter_metadata(self) -> list[tuple[str, dict]]:
        """Iterate all (id, metadata) pairs in batches to avoid SQLite variable limits."""
        batch_size = 5000
        total = self._collection.count()
        pairs: list[tuple[str, dict]] = []
        for offset in range(0, total, batch_size):
            batch = self._collection.get(
                include=["metadatas"],
                limit=batch_size,
                offset=offset,
            )
            for i, doc_id in enumerate(batch["ids"]):
                pairs.append((doc_id, batch["metadatas"][i]))
        return pairs

    def list_topics(self) -> dict[str, int]:
        tag_counts: dict[str, int] = {}
        for _, meta in self._iter_metadata():
            tags = json.loads(meta.get("tags", "[]"))
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts

    def delete_by_source(self, source_prefix: str) -> None:
        """Delete all chunks whose source starts with the given prefix."""
        ids_to_delete = [
            doc_id for doc_id, meta in self._iter_metadata()
            if meta.get("source", "").startswith(source_prefix)
        ]
        if ids_to_delete:
            for i in range(0, len(ids_to_delete), 5000):
                self._collection.delete(ids=ids_to_delete[i:i + 5000])

    def get_all_file_mtimes(self) -> dict[str, float]:
        """Build a source-prefix -> mtime lookup map for all file-indexed chunks.

        Returns a dict mapping "file:/path/to/file" to the stored mtime.
        Used by reconcile() to avoid O(n*m) per-file metadata scans.
        """
        mtimes: dict[str, float] = {}
        for _, meta in self._iter_metadata():
            source = meta.get("source", "")
            if not source.startswith("file:"):
                continue
            mtime = meta.get("file_mtime")
            if mtime is None:
                continue
            file_key = source.split("|")[0]
            if file_key not in mtimes:
                mtimes[file_key] = float(mtime)
        return mtimes

    def browse(
        self,
        offset: int = 0,
        limit: int = 50,
        chunk_type: str | None = None,
        source_prefix: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated retrieval with optional filters. Returns (results, total_matching)."""
        if self._collection.count() == 0:
            return [], 0

        where = {"chunk_type": chunk_type} if chunk_type else None

        batch_size = 5000
        total = self._collection.count()
        all_items: list[dict] = []
        for batch_offset in range(0, total, batch_size):
            batch = self._collection.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=batch_offset,
                where=where,
            )
            for i, doc_id in enumerate(batch["ids"]):
                meta = batch["metadatas"][i]
                mem_tags = json.loads(meta.get("tags", "[]"))

                if source_prefix and not meta.get("source", "").startswith(source_prefix):
                    continue
                if tags and not any(t in mem_tags for t in tags):
                    continue

                all_items.append({
                    "id": doc_id,
                    "content": batch["documents"][i],
                    "tags": mem_tags,
                    "source": meta.get("source", ""),
                    "chunk_type": meta.get("chunk_type", ""),
                    "created_at": meta.get("created_at", ""),
                    "updated_at": meta.get("updated_at", ""),
                })

        filtered_total = len(all_items)
        page = all_items[offset:offset + limit]
        return page, filtered_total

    def stats(self) -> dict:
        """Return collection statistics: total count, type breakdown, tag distribution."""
        by_type: dict[str, int] = {}
        by_tag: dict[str, int] = {}
        total = 0
        for _, meta in self._iter_metadata():
            total += 1
            chunk_type = meta.get("chunk_type", "")
            by_type[chunk_type] = by_type.get(chunk_type, 0) + 1
            mem_tags = json.loads(meta.get("tags", "[]"))
            for tag in mem_tags:
                by_tag[tag] = by_tag.get(tag, 0) + 1
        return {"total": total, "by_type": by_type, "by_tag": by_tag}

    def count(self) -> int:
        return self._collection.count()
