"""Business-logic memory store for Annal, backed by a VectorBackend."""

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timezone

from annal.backend import Embedder, VectorBackend, VectorResult

FUZZY_TAG_THRESHOLD = 0.72

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?")


def _normalize_date_bound(value: str, end_of_day: bool) -> str | None:
    """Normalize a date-only string to include time for correct comparison.

    Returns None if the value is not a valid ISO 8601 date/datetime prefix.
    """
    if not _ISO_DATE_RE.match(value):
        return None
    if "T" in value:
        return value
    return value + ("T23:59:59" if end_of_day else "T00:00:00")


class MemoryStore:
    def __init__(self, backend: VectorBackend, embedder: Embedder) -> None:
        self._backend = backend
        self._embedder = embedder
        self._tag_cache: dict | None = None
        self._tag_cache_lock = threading.Lock()

    def _invalidate_tag_cache(self) -> None:
        """Clear the tag embedding cache. Called after store/update/delete."""
        with self._tag_cache_lock:
            self._tag_cache = None

    def _get_tag_embeddings(self) -> dict:
        """Get or build a cache of tag -> embedding for all tags in the store."""
        import numpy as np
        with self._tag_cache_lock:
            if self._tag_cache is not None:
                return self._tag_cache
        topics = self.list_topics()
        if not topics:
            with self._tag_cache_lock:
                self._tag_cache = {}
                return self._tag_cache
        tag_names = list(topics.keys())
        embeddings = self._embedder.embed_batch(tag_names)
        cache = {name: np.array(emb) for name, emb in zip(tag_names, embeddings)}
        with self._tag_cache_lock:
            self._tag_cache = cache
            return self._tag_cache

    def _expand_tags(self, filter_tags: list[str]) -> set[str]:
        """Expand filter tags to include semantically similar known tags."""
        import numpy as np
        tag_embeddings = self._get_tag_embeddings()
        if not tag_embeddings:
            return set(filter_tags)

        expanded = set(filter_tags)
        filter_embeddings = self._embedder.embed_batch(filter_tags)

        for i, filter_tag in enumerate(filter_tags):
            filter_emb = np.array(filter_embeddings[i])
            filter_norm = np.linalg.norm(filter_emb)
            if filter_norm == 0:
                continue
            for known_tag, known_emb in tag_embeddings.items():
                known_norm = np.linalg.norm(known_emb)
                if known_norm == 0:
                    continue
                similarity = np.dot(filter_emb, known_emb) / (filter_norm * known_norm)
                if similarity >= FUZZY_TAG_THRESHOLD:
                    expanded.add(known_tag)

        return expanded

    def _build_where(
        self,
        chunk_type: str | None = None,
        source_prefix: str | None = None,
        tags: list[str] | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> dict | None:
        """Build a where clause dict from filter parameters."""
        where: dict = {}
        if chunk_type:
            where["chunk_type"] = chunk_type
        if source_prefix:
            where["source"] = {"$prefix": source_prefix}
        if tags:
            expanded = self._expand_tags(tags)
            where["tags"] = {"$contains_any": list(expanded)}
        if after:
            where.setdefault("created_at", {})
            where["created_at"]["$gt"] = after
        if before:
            where.setdefault("created_at", {})
            where["created_at"]["$lt"] = before
        return where or None

    def store(
        self,
        content: str,
        tags: list[str],
        source: str = "",
        chunk_type: str = "agent-memory",
        file_mtime: float | None = None,
    ) -> str:
        mem_id = str(uuid.uuid4())
        embedding = self._embedder.embed(content)
        metadata: dict = {
            "tags": tags,
            "source": source,
            "chunk_type": chunk_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if file_mtime is not None:
            metadata["file_mtime"] = file_mtime
        self._backend.insert(mem_id, content, embedding, metadata)
        self._invalidate_tag_cache()
        return mem_id

    def search(
        self,
        query: str,
        limit: int = 5,
        tags: list[str] | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict]:
        if after:
            normalized = _normalize_date_bound(after, end_of_day=False)
            if normalized is None:
                raise ValueError(f"Invalid date format for 'after': expected ISO 8601, got '{after}'")
            after = normalized
        if before:
            normalized = _normalize_date_bound(before, end_of_day=True)
            if normalized is None:
                raise ValueError(f"Invalid date format for 'before': expected ISO 8601, got '{before}'")
            before = normalized

        if self._backend.count() == 0:
            return []

        embedding = self._embedder.embed(query)
        where = self._build_where(tags=tags, after=after, before=before)

        # Backends handle their own overfetch for post-filtering
        results = self._backend.query(embedding, limit=limit, where=where, query_text=query)

        memories = []
        for r in results:
            distance = r.distance if r.distance is not None else 0.0
            score = 1.0 - distance
            memories.append({
                "id": r.id,
                "content": r.text,
                "tags": r.metadata.get("tags", []),
                "source": r.metadata.get("source", ""),
                "chunk_type": r.metadata.get("chunk_type", ""),
                "score": score,
                "distance": distance,
                "created_at": r.metadata.get("created_at", ""),
                "updated_at": r.metadata.get("updated_at", ""),
            })

        return memories[:limit]

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Retrieve full memory records by their IDs."""
        if not ids:
            return []
        results = self._backend.get(ids)
        return [self._format_result(r) for r in results]

    def delete(self, mem_id: str) -> None:
        self._backend.delete([mem_id])
        self._invalidate_tag_cache()

    def update(
        self,
        mem_id: str,
        content: str | None = None,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> None:
        """Update an existing memory's content, tags, and/or source in place."""
        existing = self._backend.get([mem_id])
        if not existing:
            raise ValueError(f"Memory {mem_id} not found")

        old = existing[0]
        new_text = content if content is not None else None
        new_embedding = self._embedder.embed(content) if content is not None else None

        new_meta = dict(old.metadata)
        new_meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        if tags is not None:
            new_meta["tags"] = tags
        if source is not None:
            new_meta["source"] = source

        self._backend.update(mem_id, text=new_text, embedding=new_embedding, metadata=new_meta)
        self._invalidate_tag_cache()

    def retag(
        self,
        mem_id: str,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
        set_tags: list[str] | None = None,
    ) -> list[str]:
        """Modify tags on an existing memory. Returns the final tag list.

        Exactly one mode: either set_tags (replace all), or add/remove (delta).
        Raises ValueError if the memory doesn't exist or inputs are invalid.
        """
        if set_tags is not None and (add_tags or remove_tags):
            raise ValueError("Cannot mix set_tags with add_tags/remove_tags")
        if set_tags is None and not add_tags and not remove_tags:
            raise ValueError("Provide at least one of add_tags, remove_tags, or set_tags")

        existing = self._backend.get([mem_id])
        if not existing:
            raise ValueError(f"Memory {mem_id} not found")

        old = existing[0]
        current_tags: list[str] = old.metadata.get("tags", [])

        if set_tags is not None:
            final_tags = list(dict.fromkeys(set_tags))  # dedupe, preserve order
        else:
            tag_set = list(dict.fromkeys(current_tags))  # start from current, deduped
            if add_tags:
                for t in add_tags:
                    if t not in tag_set:
                        tag_set.append(t)
            if remove_tags:
                tag_set = [t for t in tag_set if t not in set(remove_tags)]
            final_tags = tag_set

        new_meta = dict(old.metadata)
        new_meta["tags"] = final_tags
        new_meta["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._backend.update(mem_id, text=None, embedding=None, metadata=new_meta)
        self._invalidate_tag_cache()
        return final_tags

    def delete_many(self, ids: list[str]) -> None:
        """Delete multiple memories by ID in batches."""
        for i in range(0, len(ids), 5000):
            self._backend.delete(ids[i:i + 5000])
        self._invalidate_tag_cache()

    def _iter_metadata(self) -> list[tuple[str, dict]]:
        """Iterate all (id, metadata) pairs via backend scan."""
        batch_size = 5000
        total = self._backend.count()
        pairs: list[tuple[str, dict]] = []
        offset = 0
        while offset < total:
            results, _ = self._backend.scan(offset=offset, limit=batch_size)
            if not results:
                break
            for r in results:
                pairs.append((r.id, r.metadata))
            offset += len(results)
        return pairs

    def list_topics(self) -> dict[str, int]:
        tag_counts: dict[str, int] = {}
        for _, meta in self._iter_metadata():
            for tag in meta.get("tags", []):
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
                self._backend.delete(ids_to_delete[i:i + 5000])
            self._invalidate_tag_cache()

    def get_all_file_mtimes(self) -> dict[str, float]:
        """Build a source-prefix -> mtime lookup map for all file-indexed chunks."""
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
        if self._backend.count() == 0:
            return [], 0

        where = self._build_where(
            chunk_type=chunk_type,
            source_prefix=source_prefix,
            tags=tags,
        )

        results, total = self._backend.scan(offset=offset, limit=limit, where=where)
        return [self._format_result(r) for r in results], total

    def stats(self) -> dict:
        """Return collection statistics: total count, type breakdown, tag distribution."""
        by_type: dict[str, int] = {}
        by_tag: dict[str, int] = {}
        total = 0
        for _, meta in self._iter_metadata():
            total += 1
            chunk_type = meta.get("chunk_type", "")
            by_type[chunk_type] = by_type.get(chunk_type, 0) + 1
            for tag in meta.get("tags", []):
                by_tag[tag] = by_tag.get(tag, 0) + 1
        return {"total": total, "by_type": by_type, "by_tag": by_tag}

    def count(self) -> int:
        return self._backend.count()

    @staticmethod
    def _format_result(r: VectorResult) -> dict:
        """Convert a VectorResult to the dict format expected by callers."""
        return {
            "id": r.id,
            "content": r.text,
            "tags": r.metadata.get("tags", []),
            "source": r.metadata.get("source", ""),
            "chunk_type": r.metadata.get("chunk_type", ""),
            "created_at": r.metadata.get("created_at", ""),
            "updated_at": r.metadata.get("updated_at", ""),
        }
