"""Server router tests. A mock engine is attached to app.state, so the routers
run for real (validation, status codes, response models) but the engine does no
I/O. No lifespan, no real store."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from never_again.core.models import Failure, Hit
from never_again.server.routers import health, log, query, verify


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(log.router)
    app.include_router(query.router)
    app.include_router(verify.router)
    app.state.engine = AsyncMock()
    return TestClient(app)


def test_health_reports_types(client):
    # store/embedder are AsyncMock instances; endpoint reports their type names
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "store_type" in body and "embedder_type" in body


def test_log_failure_returns_id_and_rule(client):
    client.app.state.engine.log.return_value = Failure(
        error="boom", solution="fix", rule="WHEN: boom", id="id1")
    r = client.post("/failures", json={"error": "boom", "solution": "fix"})
    assert r.status_code == 200
    assert r.json() == {"id": "id1", "rule": "WHEN: boom"}


def test_log_failure_requires_error(client):
    r = client.post("/failures", json={"solution": "no error field"})
    assert r.status_code == 422  # pydantic validation


def test_query_failures_returns_results(client):
    f = Failure(error="boom", solution="fix", rule="r", verified=2, id="id1")
    client.app.state.engine.query.return_value = [Hit(failure=f, score=0.5)]
    r = client.post("/failures/query", json={"text": "boom", "limit": 5})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == "id1" and results[0]["score"] == 0.5


def test_query_empty_results(client):
    client.app.state.engine.query.return_value = []
    r = client.post("/failures/query", json={"text": "nothing"})
    assert r.status_code == 200
    assert r.json() == {"results": []}


def test_verify_resolution(client):
    client.app.state.engine.verify.return_value = True
    r = client.post("/failures/some-id/verify")
    assert r.status_code == 200
    assert r.json() == {"verified": True}


def test_query_handles_engine_error(client):
    client.app.state.engine.query.side_effect = RuntimeError("db down")
    r = client.post("/failures/query", json={"text": "x"})
    assert r.status_code == 500
