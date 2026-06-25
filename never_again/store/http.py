"""Team-tier client store: routes all operations via HTTP/JSON to a remote team server."""
from __future__ import annotations
import httpx

from never_again.core.models import Failure, Hit


class HttpStore:
    def __init__(self, server_url: str, team: str = "local") -> None:
        self._url = server_url.rstrip("/")
        self._team = team
        self._client = httpx.AsyncClient(timeout=10.0)

    async def add(self, failure: Failure, embedding: list[float] | None = None) -> Failure:
        payload = {
            "error": failure.error,
            "solution": failure.solution,
            "context": failure.context,
            "scope": failure.scope,
            "team": failure.team,
            "rule": failure.rule,
        }
        resp = await self._client.post(f"{self._url}/failures", json=payload)
        resp.raise_for_status()
        data = resp.json()
        failure.id = data["id"]
        failure.rule = data["rule"]
        return failure

    async def search(self, text: str, embedding: list[float] | None = None,
                      team: str = "local", limit: int = 5,
                      cosine_floor: float = 0.0, fused_floor: float = 0.0) -> list[Hit]:
        payload = {
            "text": text,
            "team": team or self._team,
            "limit": limit,
            "cosine_floor": cosine_floor,
            "fused_floor": fused_floor,
        }
        resp = await self._client.post(f"{self._url}/failures/query", json=payload)
        resp.raise_for_status()
        data = resp.json()
        hits = []
        for r in data["results"]:
            f = Failure(
                id=r["id"],
                error=r["error"],
                solution=r["solution"],
                rule=r["rule"],
                verified=r["verified"],
                scope=r.get("scope", "team"),
                team=team or self._team,
            )
            hits.append(Hit(failure=f, score=r["score"]))
        return hits

    async def verify(self, failure_id: str) -> bool:
        resp = await self._client.post(f"{self._url}/failures/{failure_id}/verify")
        resp.raise_for_status()
        return resp.json()["verified"]

    async def close(self) -> None:
        await self._client.aclose()
