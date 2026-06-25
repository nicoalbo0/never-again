"""No-op embedder: always None, so search stays keyword-only (FTS)."""
from __future__ import annotations


class FtsEmbedder:
    async def embed(self, text: str) -> None:
        return None