"""Default ONNX embedder for Annal."""

from __future__ import annotations

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2


class OnnxEmbedder:
    """Default embedder using the ONNX MiniLM-L6-V2 model (384 dimensions)."""

    def __init__(self) -> None:
        self._fn = ONNXMiniLM_L6_V2()

    @property
    def dimension(self) -> int:
        return 384

    def embed(self, text: str) -> list[float]:
        return self._fn([text])[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [e.tolist() for e in self._fn(texts)]
