"""Qdrant vector backend for Annal."""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    Range,
    VectorParams,
)

from annal.backend import VectorResult


class QdrantBackend:
    """VectorBackend implementation backed by a Qdrant server."""

    def __init__(self, url: str, collection_name: str, dimension: int) -> None:
        self._client = QdrantClient(url=url)
        self._collection = collection_name
        self._ensure_collection(dimension)

    def _ensure_collection(self, dimension: int) -> None:
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection not in collections:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )

    def insert(self, id: str, text: str, embedding: list[float], metadata: dict) -> None:
        payload = {**metadata, "text": text}
        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=id, vector=embedding, payload=payload)],
        )

    def update(
        self,
        id: str,
        text: str | None,
        embedding: list[float] | None,
        metadata: dict | None,
    ) -> None:
        # Build the new payload from metadata + text
        if metadata is not None or text is not None:
            # Fetch current payload to merge
            existing = self._client.retrieve(
                collection_name=self._collection,
                ids=[id],
                with_payload=True,
                with_vectors=bool(embedding is None),
            )
            if not existing:
                raise ValueError(f"Document {id} not found")

            old_payload = existing[0].payload or {}
            new_payload = dict(metadata) if metadata is not None else {
                k: v for k, v in old_payload.items() if k != "text"
            }
            new_payload["text"] = text if text is not None else old_payload.get("text", "")

            if embedding is not None:
                # Full re-upsert with new vector and payload
                self._client.upsert(
                    collection_name=self._collection,
                    points=[PointStruct(id=id, vector=embedding, payload=new_payload)],
                )
            else:
                # Payload-only update, keep existing vector
                self._client.set_payload(
                    collection_name=self._collection,
                    payload=new_payload,
                    points=[id],
                )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._client.delete(
                collection_name=self._collection,
                points_selector=PointIdsList(points=ids),
            )

    def query(
        self, embedding: list[float], limit: int, where: dict | None = None
    ) -> list[VectorResult]:
        qfilter = self._build_filter(where) if where else None
        results = self._client.query_points(
            collection_name=self._collection,
            query=embedding,
            limit=limit,
            query_filter=qfilter,
            with_payload=True,
        )
        return [self._to_result(p) for p in results.points]

    def get(self, ids: list[str]) -> list[VectorResult]:
        results = self._client.retrieve(
            collection_name=self._collection,
            ids=ids,
            with_payload=True,
        )
        return [self._to_result(p) for p in results]

    def scan(
        self, offset: int, limit: int, where: dict | None = None
    ) -> tuple[list[VectorResult], int]:
        qfilter = self._build_filter(where) if where else None

        # Get total count first
        total = self._client.count(
            collection_name=self._collection,
            count_filter=qfilter,
            exact=True,
        ).count

        if total == 0:
            return [], 0

        # Qdrant scroll is cursor-based, so we scroll past `offset` items
        # then collect `limit` items
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
        qfilter = self._build_filter(where) if where else None
        return self._client.count(
            collection_name=self._collection,
            count_filter=qfilter,
            exact=True,
        ).count

    # --- internal helpers ---

    @staticmethod
    def _build_filter(where: dict | None) -> Filter | None:
        """Convert the where clause grammar into Qdrant Filter conditions."""
        if not where:
            return None

        must: list[FieldCondition] = []

        for key, value in where.items():
            if isinstance(value, dict):
                # Operator conditions
                if "$contains_any" in value:
                    must.append(FieldCondition(
                        key=key,
                        match=MatchAny(any=value["$contains_any"]),
                    ))
                if "$prefix" in value:
                    # Qdrant doesn't have a native prefix filter on arbitrary strings.
                    # Use range: prefix <= value < prefix + high unicode char
                    prefix = value["$prefix"]
                    must.append(FieldCondition(
                        key=key,
                        range=Range(gte=prefix, lt=prefix + "\uffff"),
                    ))
                if "$gt" in value:
                    must.append(FieldCondition(
                        key=key,
                        range=Range(gt=value["$gt"]),
                    ))
                if "$lt" in value:
                    must.append(FieldCondition(
                        key=key,
                        range=Range(lt=value["$lt"]),
                    ))
            else:
                # Simple equality
                must.append(FieldCondition(
                    key=key,
                    match=MatchValue(value=value),
                ))

        return Filter(must=must) if must else None

    @staticmethod
    def _to_result(point) -> VectorResult:
        """Convert a Qdrant point/record to VectorResult."""
        payload = point.payload or {}
        text = payload.pop("text", "")
        score = getattr(point, "score", None)
        return VectorResult(
            id=point.id,
            text=text,
            metadata=payload,
            distance=1.0 - score if score is not None else None,
        )
