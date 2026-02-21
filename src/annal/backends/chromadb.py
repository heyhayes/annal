"""ChromaDB vector backend for Annal."""

from __future__ import annotations

import json

import chromadb

from annal.backend import VectorResult


class ChromaBackend:
    """VectorBackend implementation backed by ChromaDB PersistentClient."""

    def __init__(self, path: str, collection_name: str, dimension: int) -> None:
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def insert(self, id: str, text: str, embedding: list[float], metadata: dict) -> None:
        meta = self._serialize_meta(metadata)
        self._collection.add(
            ids=[id], documents=[text], embeddings=[embedding], metadatas=[meta]
        )

    def update(
        self,
        id: str,
        text: str | None,
        embedding: list[float] | None,
        metadata: dict | None,
    ) -> None:
        current = self._collection.get(ids=[id], include=["documents", "metadatas"])
        if not current["ids"]:
            raise ValueError(f"Document {id} not found")

        new_doc = text if text is not None else current["documents"][0]
        new_meta = self._serialize_meta(metadata) if metadata is not None else current["metadatas"][0]

        kwargs: dict = {"ids": [id], "documents": [new_doc], "metadatas": [new_meta]}
        if embedding is not None:
            kwargs["embeddings"] = [embedding]
        self._collection.update(**kwargs)

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)

    def query(
        self, embedding: list[float], limit: int, where: dict | None = None,
        query_text: str | None = None,
    ) -> list[VectorResult]:
        total = self._collection.count()
        if total == 0:
            return []

        chroma_where, post_filters = self._split_where(where)
        n = limit * 3 if post_filters else limit

        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(n, total) or 1,
            where=chroma_where or None,
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        out: list[VectorResult] = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = self._deserialize_meta(results["metadatas"][0][i])
            if not self._passes_post_filters(meta, post_filters):
                continue
            distance = results["distances"][0][i] if results["distances"] else None
            out.append(VectorResult(
                id=doc_id,
                text=results["documents"][0][i],
                metadata=meta,
                distance=distance,
            ))

        return out[:limit]

    def get(self, ids: list[str]) -> list[VectorResult]:
        results = self._collection.get(ids=ids, include=["documents", "metadatas"])
        out: list[VectorResult] = []
        for i, doc_id in enumerate(results["ids"]):
            meta = self._deserialize_meta(results["metadatas"][i])
            out.append(VectorResult(id=doc_id, text=results["documents"][i], metadata=meta))
        return out

    def scan(
        self, offset: int, limit: int, where: dict | None = None
    ) -> tuple[list[VectorResult], int]:
        if self._collection.count() == 0:
            return [], 0

        chroma_where, post_filters = self._split_where(where)

        if not post_filters:
            # Fast path: let ChromaDB paginate directly
            if chroma_where:
                all_filtered = self._collection.get(include=["metadatas"], where=chroma_where)
                total = len(all_filtered["ids"])
            else:
                total = self._collection.count()

            batch = self._collection.get(
                include=["documents", "metadatas"],
                limit=limit,
                offset=offset,
                where=chroma_where or None,
            )
            results = [
                VectorResult(
                    id=batch["ids"][i],
                    text=batch["documents"][i],
                    metadata=self._deserialize_meta(batch["metadatas"][i]),
                )
                for i in range(len(batch["ids"]))
            ]
            return results, total

        # Slow path: scan everything and post-filter
        batch_size = 5000
        total_docs = self._collection.count()
        all_items: list[VectorResult] = []
        for batch_offset in range(0, total_docs, batch_size):
            batch = self._collection.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=batch_offset,
                where=chroma_where or None,
            )
            for i in range(len(batch["ids"])):
                meta = self._deserialize_meta(batch["metadatas"][i])
                if self._passes_post_filters(meta, post_filters):
                    all_items.append(VectorResult(
                        id=batch["ids"][i],
                        text=batch["documents"][i],
                        metadata=meta,
                    ))

        filtered_total = len(all_items)
        page = all_items[offset:offset + limit]
        return page, filtered_total

    def count(self, where: dict | None = None) -> int:
        if where is None:
            return self._collection.count()

        chroma_where, post_filters = self._split_where(where)

        if not post_filters:
            if chroma_where:
                results = self._collection.get(include=[], where=chroma_where)
                return len(results["ids"])
            return self._collection.count()

        # Post-filter path: scan everything
        batch_size = 5000
        total_docs = self._collection.count()
        count = 0
        for batch_offset in range(0, total_docs, batch_size):
            batch = self._collection.get(
                include=["metadatas"],
                limit=batch_size,
                offset=batch_offset,
                where=chroma_where or None,
            )
            for i in range(len(batch["ids"])):
                meta = self._deserialize_meta(batch["metadatas"][i])
                if self._passes_post_filters(meta, post_filters):
                    count += 1
        return count

    # --- internal helpers ---

    @staticmethod
    def _serialize_meta(metadata: dict) -> dict:
        """Convert native list tags to JSON string for ChromaDB storage."""
        meta = dict(metadata)
        if "tags" in meta:
            meta["tags"] = json.dumps(meta["tags"])
        return meta

    @staticmethod
    def _deserialize_meta(meta: dict) -> dict:
        """Convert JSON string tags back to native lists."""
        result = dict(meta)
        if "tags" in result and isinstance(result["tags"], str):
            result["tags"] = json.loads(result["tags"])
        return result

    @staticmethod
    def _split_where(where: dict | None) -> tuple[dict | None, dict]:
        """Split where clause into ChromaDB-native filters and post-query filters.

        ChromaDB can natively handle simple equality (e.g. chunk_type == X).
        Everything else (tags.$contains_any, source.$prefix, created_at.$gt/$lt)
        must be applied post-query.
        """
        if not where:
            return None, {}

        chroma_where: dict = {}
        post_filters: dict = {}

        for key, value in where.items():
            if isinstance(value, dict):
                # Operator filters — all go to post-filter
                post_filters[key] = value
            else:
                # Simple equality — ChromaDB can handle this
                chroma_where[key] = value

        return chroma_where or None, post_filters

    @staticmethod
    def _passes_post_filters(meta: dict, post_filters: dict) -> bool:
        """Check if a document's metadata passes all post-query filters."""
        for key, condition in post_filters.items():
            if not isinstance(condition, dict):
                continue
            value = meta.get(key)

            if "$contains_any" in condition:
                if not isinstance(value, list):
                    return False
                if not any(t in value for t in condition["$contains_any"]):
                    return False

            if "$prefix" in condition:
                if not isinstance(value, str) or not value.startswith(condition["$prefix"]):
                    return False

            if "$gt" in condition:
                if not isinstance(value, str) or value <= condition["$gt"]:
                    return False

            if "$lt" in condition:
                if not isinstance(value, str) or value >= condition["$lt"]:
                    return False

        return True
