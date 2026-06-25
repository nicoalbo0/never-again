"""Store behavior + the relevance floor — the safety property of the tool.

The floor is what lets the system abstain instead of returning a confident
wrong fix. These tests pin that behavior on both the FTS (keyword-overlap) path
and the embedding (cosine) path. The cosine path uses a fake embedder so no
real model is loaded.
"""
from __future__ import annotations

import pytest

from never_again.config import Settings
from never_again.engine import Engine
from never_again.store.sqlite import SqliteStore, _overlap, _content_terms
from never_again.core.models import Failure


# ---------------- overlap helper (FTS floor primitive) ----------------
def test_content_terms_drops_stopwords_and_short():
    terms = _content_terms("the asyncpg InterfaceError on a connection")
    assert "asyncpg" in terms and "interfaceerror" in terms and "connection" in terms
    assert "the" not in terms and "on" not in terms and "a" not in terms
    assert "error" not in terms  # 'error' is a stopword (too common to signal)


def test_overlap_counts_shared_content_terms():
    assert _overlap("asyncpg operation in progress",
                    "asyncpg another operation already in progress") >= 2
    assert _overlap("rust borrow checker mutable",
                    "pydantic validation email required") == 0


# ---------------- FTS path: abstain on unrelated ----------------
@pytest.mark.asyncio
async def test_fts_returns_related_hit(engine: Engine):
    await engine.log(error="asyncpg InterfaceError another operation in progress",
                     solution="use a connection pool")
    hits = await engine.query("asyncpg another operation in progress on connection")
    assert len(hits) >= 1
    assert "asyncpg" in hits[0].failure.error


@pytest.mark.asyncio
async def test_fts_abstains_on_unrelated_query(engine: Engine):
    # the cold-start safety bug: an unrelated error must NOT match stored ones
    await engine.log(error="asyncpg InterfaceError another operation in progress",
                     solution="use a pool")
    await engine.log(error="pydantic ValidationError email field required",
                     solution="add EmailStr")
    hits = await engine.query("rust borrow checker error E0502 cannot borrow as mutable")
    assert hits == []  # abstain, not a confident wrong answer


@pytest.mark.asyncio
async def test_fts_abstains_on_empty_store(engine: Engine):
    assert await engine.query("anything at all") == []


# ---------------- dedup ----------------
@pytest.mark.asyncio
async def test_dedup_same_fingerprint_and_solution(engine: Engine):
    f1 = await engine.log(error="KeyError foo at line 10", solution="guard the key")
    f2 = await engine.log(error="KeyError foo at line 999", solution="guard the key")
    # same normalized error + same solution -> same row reused
    assert f1.id == f2.id


@pytest.mark.asyncio
async def test_different_solution_makes_new_row(engine: Engine):
    f1 = await engine.log(error="KeyError foo at line 10", solution="guard the key")
    f2 = await engine.log(error="KeyError foo at line 10", solution="use .get()")
    assert f1.id != f2.id


# ---------------- verify ----------------
@pytest.mark.asyncio
async def test_verify_increments_and_unknown_id_false(engine: Engine):
    f = await engine.log(error="some error here", solution="some fix")
    assert await engine.verify(f.id) is True
    assert await engine.verify("nonexistent-id") is False


# ---------------- cosine floor (embedding path) ----------------
class _FakeEmbedder:
    """Deterministic 3-d embedder: maps a keyword to a fixed unit vector so we
    can control cosine similarity exactly, with no real model."""
    _VECS = {
        "alpha": [1.0, 0.0, 0.0],
        "beta": [0.0, 1.0, 0.0],
        "gamma": [0.0, 0.0, 1.0],
    }

    async def embed(self, text: str):
        for k, v in self._VECS.items():
            if k in text.lower():
                return v
        return [0.577, 0.577, 0.577]  # neutral, low cosine to any axis


@pytest.mark.asyncio
async def test_cosine_floor_drops_below_threshold(tmp_db):
    settings = Settings(store="sqlite", db=tmp_db, embedder="fts",
                        cosine_floor=0.9, fused_floor=0.0)
    eng = Engine.from_settings(settings)
    eng.embedder = _FakeEmbedder()  # inject fake, bypass real model
    try:
        await eng.log(error="alpha problem occurred", solution="fix alpha")
        # query 'beta' -> orthogonal to 'alpha' (cosine 0) -> below 0.9 floor
        assert await eng.query("beta problem occurred") == []
        # query 'alpha' -> cosine 1.0 -> passes
        hits = await eng.query("alpha problem occurred")
        assert len(hits) == 1
    finally:
        await eng.close()


@pytest.mark.asyncio
async def test_cosine_floor_lenient_setting_keeps_more(tmp_db):
    settings = Settings(store="sqlite", db=tmp_db, embedder="fts",
                        cosine_floor=0.0, fused_floor=0.0)
    eng = Engine.from_settings(settings)
    eng.embedder = _FakeEmbedder()
    try:
        await eng.log(error="alpha problem", solution="fix")
        # floor 0.0 -> even orthogonal 'beta' query returns the hit
        hits = await eng.query("beta problem")
        assert len(hits) == 1
    finally:
        await eng.close()
