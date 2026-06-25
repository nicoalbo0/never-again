"""Shared fixtures. Everything is in-memory or mocked — no real network, no
real embedding models, no external services."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from never_again.config import Settings
from never_again.engine import Engine


@pytest.fixture
def tmp_db(tmp_path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def fts_settings(tmp_db) -> Settings:
    """Default zero-dep config: SQLite + FTS, agent-written rules, floors on."""
    return Settings(store="sqlite", db=tmp_db, embedder="fts")


@pytest.fixture
async def engine(fts_settings) -> Engine:
    e = Engine.from_settings(fts_settings)
    try:
        yield e
    finally:
        await e.close()
