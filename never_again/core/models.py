"""Core domain types. Pure data — no database, no network."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Failure:
    """A captured failure and how it was resolved."""
    error: str                       # what went wrong (the error message)
    context: str = ""                # stack / framework / where it happened
    solution: str = ""               # what fixed it
    rule: str | None = None          # prevention rule (WHEN / CHECK / BECAUSE)
    fingerprint: str = ""            # normalized signature, for dedup
    scope: str = "local"             # local | team | public
    team: str = "local"
    verified: int = 0                # times the fix was confirmed to work
    id: str | None = None            # assigned by the store on insert
    created_at: datetime = field(default_factory=_now)


@dataclass
class Hit:
    """A search result: a failure plus its relevance score."""
    failure: Failure
    score: float