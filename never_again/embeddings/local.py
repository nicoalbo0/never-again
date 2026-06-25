"""In-process embeddings via fastembed (ONNX). No Ollama, no server."""
from __future__ import annotations
import asyncio


class LocalEmbedder:
    def __init__(self) -> None:
        self._model = None  # loaded lazily on first embed (downloads once, then cached)

    def _encode(self, text: str) -> list[float]:
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding()
        return next(iter(self._model.embed([text]))).tolist()

    async def embed(self, text: str) -> list[float] | None:
        try:
            return await asyncio.to_thread(self._encode, text)
        except Exception:
            return None