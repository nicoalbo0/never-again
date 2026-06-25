"""Embeddings via a running Ollama. Returns None if Ollama is unreachable."""
from __future__ import annotations

import httpx


class OllamaEmbedder:
    def __init__(self, url: str, model: str = "nomic-embed-text") -> None:
        self._url = url.rstrip("/") + "/api/embed"
        self._model = model

    async def embed(self, text: str) -> list[float] | None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._url, json={"model": self._model, "input": text})
                resp.raise_for_status()
                return resp.json()["embeddings"][0]
        except Exception:
            return None