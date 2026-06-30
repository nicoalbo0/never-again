"""Regression tests for two bugs that previously had zero coverage.

1. Query/log embedding asymmetry — `query` must embed the SAME stack-enriched
   text that `log` bakes into its embedding input, or semantic recall silently
   degrades (keyword path enriched, vector path not).
2. HttpStore must send the caller's `team` on search/add and honor it, instead
   of dropping it (which collapsed every team to the server default).
"""
from __future__ import annotations

import pytest

from never_again.config import Settings
from never_again.core.models import Failure
from never_again.engine import Engine


# ---------------- 1. embedding enrichment symmetry ----------------
class _RecordingEmbedder:
    """Captures every text it is asked to embed; returns a constant vector."""
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.seen.append(text)
        return [1.0, 0.0, 0.0]


class _NullStore:
    def __init__(self) -> None:
        self.add_calls: list[dict] = []
        self.search_calls: list[dict] = []

    async def add(self, failure, embedding=None):
        self.add_calls.append({"failure": failure, "embedding": embedding})
        failure.id = "x"
        return failure

    async def search(self, *a, **k):
        self.search_calls.append({"args": a, "kwargs": k})
        return []

    async def verify(self, failure_id):
        return True

    async def close(self):
        return None


class _NullRules:
    async def generate(self, failure):
        return "WHEN: x"


@pytest.mark.asyncio
async def test_query_embeds_stack_enriched_text(monkeypatch):
    # Force a deterministic detected stack so enrichment is observable.
    monkeypatch.setattr("never_again.engine.detect_tech_stack",
                        lambda *a, **k: ["Python", "FastAPI"])
    emb = _RecordingEmbedder()
    eng = Engine(_NullStore(), emb, _NullRules(), settings=Settings())

    await eng.query("connection pool exhausted")

    assert emb.seen, "embedder was never called"
    embedded = emb.seen[-1]
    # The vector path must see the same stack tokens the keyword path sees.
    assert "connection pool exhausted" in embedded
    assert "Python" in embedded and "FastAPI" in embedded


@pytest.mark.asyncio
async def test_query_without_stack_embeds_plain_text(monkeypatch):
    monkeypatch.setattr("never_again.engine.detect_tech_stack",
                        lambda *a, **k: [])
    emb = _RecordingEmbedder()
    eng = Engine(_NullStore(), emb, _NullRules(), settings=Settings())

    await eng.query("plain query")
    assert emb.seen[-1] == "plain query"


@pytest.mark.asyncio
async def test_engine_defaults_to_configured_team(monkeypatch):
    monkeypatch.setattr("never_again.engine.detect_tech_stack",
                        lambda *a, **k: [])
    store = _NullStore()
    eng = Engine(store, _RecordingEmbedder(), _NullRules(),
                 settings=Settings(team="acme"))

    await eng.log("boom")
    await eng.query("boom")

    assert store.add_calls[-1]["failure"].team == "acme"
    assert store.search_calls[-1]["kwargs"]["team"] == "acme"


@pytest.mark.asyncio
async def test_query_accepts_explicit_relevance_floors(monkeypatch):
    monkeypatch.setattr("never_again.engine.detect_tech_stack",
                        lambda *a, **k: [])
    store = _NullStore()
    eng = Engine(store, _RecordingEmbedder(), _NullRules(),
                 settings=Settings(cosine_floor=0.45, fused_floor=0.10))

    await eng.query("boom", cosine_floor=0.7, fused_floor=0.2)

    kwargs = store.search_calls[-1]["kwargs"]
    assert kwargs["cosine_floor"] == 0.7
    assert kwargs["fused_floor"] == 0.2


# ---------------- 2. HttpStore threads team ----------------
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Records POST payloads; returns canned responses by URL suffix."""
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, json=None):
        self.calls.append((url, json or {}))
        if url.endswith("/failures/query"):
            return _FakeResponse({"results": []})
        if url.endswith("/verify"):
            return _FakeResponse({"verified": True})
        return _FakeResponse({"id": "abc", "rule": "WHEN: x"})

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_http_store_sends_team_on_search():
    from never_again.store.http import HttpStore
    store = HttpStore("http://server.test", team="acme")
    store._client = _FakeClient()

    await store.search("some error", team="acme")
    url, payload = store._client.calls[-1]
    assert url.endswith("/failures/query")
    assert payload["team"] == "acme"


@pytest.mark.asyncio
async def test_http_store_sends_relevance_floors_on_search():
    from never_again.store.http import HttpStore
    store = HttpStore("http://server.test", team="acme")
    store._client = _FakeClient()

    await store.search("some error", cosine_floor=0.7, fused_floor=0.2)
    _, payload = store._client.calls[-1]
    assert payload["cosine_floor"] == 0.7
    assert payload["fused_floor"] == 0.2


@pytest.mark.asyncio
async def test_http_store_sends_team_on_add():
    from never_again.store.http import HttpStore
    store = HttpStore("http://server.test", team="acme")
    store._client = _FakeClient()

    f = Failure(error="boom", team="acme")
    await store.add(f)
    url, payload = store._client.calls[-1]
    assert url.endswith("/failures")
    assert payload["team"] == "acme"


@pytest.mark.asyncio
async def test_open_store_passes_team_to_http():
    from never_again.store.base import open_store
    from never_again.store.http import HttpStore
    s = Settings(server_url="http://server.test", team="acme")
    store = open_store(s)
    assert isinstance(store, HttpStore)
    assert store._team == "acme"


def test_open_store_passes_embedding_dimension_to_postgres():
    from never_again.store.base import open_store
    from never_again.store.postgres import PostgresStore

    store = open_store(Settings(store="postgres", db="postgresql://db", embed_dimension=384))
    assert isinstance(store, PostgresStore)
    assert store._embedding_dimension == 384
