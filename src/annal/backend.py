"""Backend protocols for Annal vector storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2


@dataclass
class VectorResult:
    """A single result from a vector backend operation."""

    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    distance: float | None = None


class VectorBackend(Protocol):
    """Low-level vector storage operations."""

    def insert(
        self, id: str, text: str, embedding: list[float], metadata: dict
    ) -> None: ...

    def update(
        self,
        id: str,
        text: str | None,
        embedding: list[float] | None,
        metadata: dict | None,
    ) -> None: ...

    def delete(self, ids: list[str]) -> None: ...

    def query(
        self, embedding: list[float], limit: int, where: dict | None = None
    ) -> list[VectorResult]: ...

    def get(self, ids: list[str]) -> list[VectorResult]: ...

    def scan(
        self, offset: int, limit: int, where: dict | None = None
    ) -> tuple[list[VectorResult], int]: ...

    def count(self, where: dict | None = None) -> int: ...


class Embedder(Protocol):
    """Text to vector embedding."""

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class OnnxEmbedder:
    """Default embedder using the ONNX MiniLM-L6-V2 model."""

    def __init__(self) -> None:
        self._fn = ONNXMiniLM_L6_V2()
        self._dimension = len(self._fn(["test"])[0])

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        return self._fn([text])[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [e.tolist() for e in self._fn(texts)]
