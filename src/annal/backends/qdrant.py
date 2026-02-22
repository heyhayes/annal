"""Qdrant vector backend for Annal."""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    Prefetch,
    Range,
    SparseVectorParams,
    Modifier,
    VectorParams,
)

from annal.backend import VectorResult

# Fixed namespace for deterministic string→UUID conversion
_ANNAL_NS = uuid.UUID("a4b1c2d3-e5f6-7890-abcd-ef1234567890")


class QdrantBackend:
    """VectorBackend implementation backed by a Qdrant server."""

    def __init__(self, url: str, collection_name: str, dimension: int, hybrid: bool = False) -> None:
        self._client = QdrantClient(url=url)
        self._collection = collection_name
        self._hybrid = hybrid
        self._ensure_collection(dimension)

    @staticmethod
    def _to_uuid(id: str) -> str:
        """Convert a string ID to a deterministic UUID string for Qdrant."""
        try:
            uuid.UUID(id)
            return id
        except ValueError:
            return str(uuid.uuid5(_ANNAL_NS, id))

    def _ensure_collection(self, dimension: int) -> None:
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection not in collections:
            sparse_config = {"bm25": SparseVectorParams(modifier=Modifier.IDF)} if self._hybrid else None
            vectors_config = (
                {"dense": VectorParams(size=dimension, distance=Distance.COSINE)}
                if self._hybrid
                else VectorParams(size=dimension, distance=Distance.COSINE)
            )
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_config,
            )

    def insert(self, id: str, text: str, embedding: list[float], metadata: dict) -> None:
        payload = {**metadata, "text": text, "_annal_id": id}
        if self._hybrid:
            vector = {
                "dense": embedding,
                "bm25": Document(text=text, model="Qdrant/bm25"),
            }
        else:
            vector = embedding
        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=self._to_uuid(id), vector=vector, payload=payload)],
        )

    def update(
        self,
        id: str,
        text: str | None,
        embedding: list[float] | None,
        metadata: dict | None,
    ) -> None:
        uid = self._to_uuid(id)
        # Build the new payload from metadata + text
        if metadata is not None or text is not None:
            # Fetch current payload to merge
            existing = self._client.retrieve(
                collection_name=self._collection,
                ids=[uid],
                with_payload=True,
                with_vectors=bool(embedding is None),
            )
            if not existing:
                raise ValueError(f"Document {id} not found")

            old_payload = existing[0].payload or {}
            new_payload = dict(metadata) if metadata is not None else {
                k: v for k, v in old_payload.items() if k not in ("text", "_annal_id")
            }
            new_payload["text"] = text if text is not None else old_payload.get("text", "")
            new_payload["_annal_id"] = id

            if embedding is not None:
                if self._hybrid:
                    vector = {
                        "dense": embedding,
                        "bm25": Document(text=new_payload["text"], model="Qdrant/bm25"),
                    }
                else:
                    vector = embedding
                self._client.upsert(
                    collection_name=self._collection,
                    points=[PointStruct(id=uid, vector=vector, payload=new_payload)],
                )
            else:
                self._client.set_payload(
                    collection_name=self._collection,
                    payload=new_payload,
                    points=[uid],
                )

    def delete(self, ids: list[str]) -> None:
        if ids:
            uids = [self._to_uuid(i) for i in ids]
            self._client.delete(
                collection_name=self._collection,
                points_selector=PointIdsList(points=uids),
            )

    def query(
        self, embedding: list[float], limit: int, where: dict | None = None,
        query_text: str | None = None,
    ) -> list[VectorResult]:
        native, post = self._split_where(where) if where else (None, None)
        qfilter = self._build_filter(native) if native else None
        fetch_limit = limit * 3 if post else limit

        is_rrf = self._hybrid and query_text
        if is_rrf:
            results = self._client.query_points(
                collection_name=self._collection,
                prefetch=[
                    Prefetch(query=embedding, using="dense", limit=fetch_limit),
                    Prefetch(
                        query=Document(text=query_text, model="Qdrant/bm25"),
                        using="bm25",
                        limit=fetch_limit,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=fetch_limit,
                query_filter=qfilter,
                with_payload=True,
            )
        elif self._hybrid:
            results = self._client.query_points(
                collection_name=self._collection,
                query=embedding,
                using="dense",
                limit=fetch_limit,
                query_filter=qfilter,
                with_payload=True,
            )
        else:
            results = self._client.query_points(
                collection_name=self._collection,
                query=embedding,
                limit=fetch_limit,
                query_filter=qfilter,
                with_payload=True,
            )

        items = [self._to_result(p, rrf=is_rrf) for p in results.points]
        if post:
            items = [r for r in items if self._matches_post_filter(r, post)]
        return items[:limit]

    def get(self, ids: list[str]) -> list[VectorResult]:
        uids = [self._to_uuid(i) for i in ids]
        results = self._client.retrieve(
            collection_name=self._collection,
            ids=uids,
            with_payload=True,
        )
        return [self._to_result(p) for p in results]

    def scan(
        self, offset: int, limit: int, where: dict | None = None
    ) -> tuple[list[VectorResult], int]:
        native, post = self._split_where(where) if where else (None, None)
        qfilter = self._build_filter(native) if native else None

        if post:
            # With post-filters we need to scan everything and filter in Python
            all_results: list[VectorResult] = []
            next_offset = None
            while True:
                records, next_offset = self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=qfilter,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                )
                if not records:
                    break
                for record in records:
                    result = self._to_result(record)
                    if self._matches_post_filter(result, post):
                        all_results.append(result)
                if next_offset is None:
                    break
            total = len(all_results)
            return all_results[offset:offset + limit], total

        # No post-filter: use count + cursor-based scroll with offset skipping
        total = self._client.count(
            collection_name=self._collection,
            count_filter=qfilter,
            exact=True,
        ).count

        if total == 0:
            return [], 0

        collected: list[VectorResult] = []
        skipped = 0
        next_offset = None

        while len(collected) < limit:
            batch_size = min(limit - len(collected) + (offset - skipped if skipped < offset else 0), 100)
            if batch_size <= 0:
                batch_size = limit

            records, next_offset = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=qfilter,
                limit=batch_size,
                offset=next_offset,
                with_payload=True,
            )

            if not records:
                break

            for record in records:
                if skipped < offset:
                    skipped += 1
                    continue
                collected.append(self._to_result(record))
                if len(collected) >= limit:
                    break

            if next_offset is None:
                break

        return collected, total

    def count(self, where: dict | None = None) -> int:
        native, post = self._split_where(where) if where else (None, None)
        qfilter = self._build_filter(native) if native else None
        if post:
            # Must scan and count matching items in Python
            matched = 0
            next_offset = None
            while True:
                records, next_offset = self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=qfilter,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                )
                if not records:
                    break
                for record in records:
                    result = self._to_result(record)
                    if self._matches_post_filter(result, post):
                        matched += 1
                if next_offset is None:
                    break
            return matched
        return self._client.count(
            collection_name=self._collection,
            count_filter=qfilter,
            exact=True,
        ).count

    # --- internal helpers ---

    @staticmethod
    def _split_where(where: dict | None) -> tuple[dict | None, dict | None]:
        """Split where clause into Qdrant-native and post-query filters.

        Native: equality, $contains_any
        Post-query: $prefix, $gt, $lt (Qdrant Range only supports numeric values)
        """
        if not where:
            return None, None
        native: dict = {}
        post: dict = {}
        for key, value in where.items():
            if isinstance(value, dict):
                if "$contains_any" in value:
                    native[key] = value
                else:
                    post[key] = value
            else:
                native[key] = value
        return (native or None), (post or None)

    @staticmethod
    def _build_filter(where: dict | None) -> Filter | None:
        """Convert native where clause into Qdrant Filter conditions."""
        if not where:
            return None

        must: list[FieldCondition] = []

        for key, value in where.items():
            if isinstance(value, dict):
                if "$contains_any" in value:
                    must.append(FieldCondition(
                        key=key,
                        match=MatchAny(any=value["$contains_any"]),
                    ))
            else:
                must.append(FieldCondition(
                    key=key,
                    match=MatchValue(value=value),
                ))

        return Filter(must=must) if must else None

    @staticmethod
    def _matches_post_filter(result: VectorResult, post: dict) -> bool:
        """Check if a VectorResult passes all post-query filter conditions."""
        for key, conditions in post.items():
            val = result.metadata.get(key, "")
            if "$prefix" in conditions:
                if not val.startswith(conditions["$prefix"]):
                    return False
            if "$gt" in conditions:
                if not val > conditions["$gt"]:
                    return False
            if "$lt" in conditions:
                if not val < conditions["$lt"]:
                    return False
        return True

    @staticmethod
    def _to_result(point, rrf: bool = False) -> VectorResult:
        """Convert a Qdrant point/record to VectorResult."""
        payload = dict(point.payload or {})
        text = payload.pop("text", "")
        annal_id = payload.pop("_annal_id", str(point.id))
        score = getattr(point, "score", None)
        if score is None:
            distance = None
        elif rrf:
            # RRF scores are rank-based, not cosine. Use 1/score so lower
            # distance = better rank, preserving sort order for consumers
            # that treat distance as "lower is better".
            distance = 1.0 / score if score > 0 else 0.0
        else:
            distance = 1.0 - score
        return VectorResult(
            id=annal_id,
            text=text,
            metadata=payload,
            distance=distance,
        )
