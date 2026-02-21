"""Migrate documents between vector backends."""

from __future__ import annotations

import logging
import sys

from annal.backend import Embedder, VectorBackend

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def migrate(
    src: VectorBackend,
    dst: VectorBackend,
    embedder: Embedder,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Scan all documents from src, re-embed, and insert into dst.

    Returns the total number of documents migrated.
    """
    total = src.count()
    if total == 0:
        return 0

    migrated = 0
    offset = 0

    while offset < total:
        docs, _ = src.scan(offset=offset, limit=batch_size)
        if not docs:
            break

        texts = [doc.text for doc in docs]
        embeddings = embedder.embed_batch(texts)

        for doc, embedding in zip(docs, embeddings):
            dst.insert(doc.id, doc.text, embedding, doc.metadata)

        migrated += len(docs)
        offset += len(docs)
        print(f"  migrated {migrated}/{total}", file=sys.stderr)

    return migrated
