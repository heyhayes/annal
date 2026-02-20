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
    ) -> list[dict]:
        # Over-fetch when filtering by tags since filtering is post-query
        limit_query = max(limit * 3, 20) if tags else limit

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
            })

        return memories[:limit]

    def delete(self, mem_id: str) -> None:
        self._collection.delete(ids=[mem_id])

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

    def get_file_mtime(self, source_prefix: str) -> float | None:
        """Get the stored mtime for a file's chunks. Returns None if not found."""
        for _, meta in self._iter_metadata():
            if meta.get("source", "").startswith(source_prefix):
                mtime = meta.get("file_mtime")
                if mtime is not None:
                    return float(mtime)
                return None
        return None

    def count(self) -> int:
        return self._collection.count()
