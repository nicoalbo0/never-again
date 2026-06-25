"""The Embedder contract: text -> vector, or None to fall back to keyword-only."""
from __future__ import annotations
from typing import Protocol

from never_again.config import Settings


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float] | None:
        """Return an embedding, or None if embeddings are unavailable."""
        ...


def open_embedder(settings: Settings) -> Embedder:
    """Pick the embedder from config. Heavy backends import only on demand."""
    if settings.embedder == "local":
        from never_again.embeddings.local import LocalEmbedder
        return LocalEmbedder()
    if settings.embedder == "ollama":
        from never_again.embeddings.ollama import OllamaEmbedder
        return OllamaEmbedder(settings.ollama_url, settings.ollama_embed_model)
    from never_again.embeddings.fts import FtsEmbedder
    return FtsEmbedder()