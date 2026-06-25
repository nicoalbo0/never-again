"""MCP tool handler tests. The engine is mocked so we test ONLY the tool
handlers' wiring and output shape — no store, no embedder, no real I/O."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import never_again.mcp.server as srv
from never_again.core.models import Failure, Hit


@pytest.fixture
def mock_engine(monkeypatch):
    eng = AsyncMock()
    monkeypatch.setattr(srv, "_engine", eng)
    return eng


@pytest.mark.asyncio
async def test_query_failures_shapes_hits(mock_engine):
    f = Failure(error="boom", solution="fix it", rule="WHEN: boom",
                verified=3, id="abc")
    mock_engine.query.return_value = [Hit(failure=f, score=0.875)]
    out = await srv.query_failures("some error", limit=5)
    assert out == [{
        "id": "abc", "error": "boom", "solution": "fix it",
        "rule": "WHEN: boom", "verified": 3, "score": 0.875,
    }]
    mock_engine.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_failures_empty_is_empty_list(mock_engine):
    mock_engine.query.return_value = []
    assert await srv.query_failures("no match") == []


@pytest.mark.asyncio
async def test_log_failure_returns_id_and_rule(mock_engine):
    mock_engine.log.return_value = Failure(
        error="boom", solution="fix", rule="WHEN: boom", id="xyz")
    out = await srv.log_failure(error="boom", solution="fix")
    assert out == {"id": "xyz", "rule": "WHEN: boom"}
    mock_engine.log.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_failure_forwards_agent_supplied_rule(mock_engine):
    mock_engine.log.return_value = Failure(
        error="boom", solution="fix", rule="WHEN: agent rule", id="xyz")
    await srv.log_failure(error="boom", solution="fix", rule="WHEN: agent rule")
    # the agent's rule must reach the engine, not be silently dropped
    assert mock_engine.log.await_args.kwargs["rule"] == "WHEN: agent rule"


@pytest.mark.asyncio
async def test_verify_resolution_returns_bool(mock_engine):
    mock_engine.verify.return_value = True
    assert await srv.verify_resolution("some-id") == {"verified": True}
    mock_engine.verify.return_value = False
    assert await srv.verify_resolution("bad-id") == {"verified": False}
