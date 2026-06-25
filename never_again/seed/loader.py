"""Cold-start the database from THIS project's own history.

Generic seeded failures were theater — pre-written entries rarely match a real
query. The signal that actually recurs is project-specific: the bugs this exact
codebase already fixed. So on a brand-new local DB we mine the project's git
history (always, no network) plus its GitHub issues (only if a token and github
remote are present) and seed those.
"""
from __future__ import annotations

from pathlib import Path

from never_again.config import Settings
from never_again.engine import Engine
from .project_history import seed_from_history


async def ensure_seeded(engine: Engine, settings: Settings) -> None:
    """Seed once, only on a brand-new local SQLite database.

    Guarded on the DB file not yet existing, so it runs on first install and
    never re-seeds (which would re-embed everything) on later startups. Skips
    the postgres/team and proxy cases, which manage their own data.
    """
    if settings.store != "sqlite" or settings.server_url:
        return
    if Path(settings.db).expanduser().exists():
        return
    try:
        await seed_from_history(engine)
    except Exception:
        pass
