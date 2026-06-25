"""The Store contract. Every backend implements these four methods."""
from __future__ import annotations
from typing import Protocol

from never_again.config import Settings
from never_again.core.models import Failure, Hit


class Store(Protocol):
    async def add(self, failure: Failure, embedding: list[float] | None = None) -> Failure:
        """Insert a failure (dedup by fingerprint+team); returns it with an id."""
        ...

    async def search(self, text: str, embedding: list[float] | None = None,
                     team: str = "local", limit: int = 5,
                     cosine_floor: float = 0.0, fused_floor: float = 0.0) -> list[Hit]:
        """Keyword + optional vector search, scoped to a team.

        cosine_floor / fused_floor let the backend abstain on weak matches.
        """
        ...

    async def verify(self, failure_id: str) -> bool:
        """Bump the confirmed-fix counter; False if the id is unknown."""
        ...

    async def close(self) -> None:
        ...


def open_store(settings: Settings) -> Store:
    """Pick the store from config. HTTP store is used if server_url is configured."""
    if settings.server_url:
        from never_again.store.http import HttpStore
        return HttpStore(settings.server_url, team=settings.team)
    if settings.store == "postgres":
        from never_again.store.postgres import PostgresStore
        return PostgresStore(settings.db)
    from never_again.store.sqlite import SqliteStore
    return SqliteStore(settings.db)