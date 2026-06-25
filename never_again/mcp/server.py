"""The product: a stdio MCP server exposing three tools over the Engine."""
from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from never_again.config import load
from never_again.engine import Engine
from never_again.seed.loader import ensure_seeded

settings = load()
_engine: Engine | None = None


def _require_engine() -> Engine:
    """Return the live engine, or fail loudly if the lifespan hasn't set it.

    The tools below can only run inside a request, by which point `lifespan`
    has assigned `_engine`. This helper makes that invariant explicit and lets
    the type checker see a concrete `Engine` instead of `Engine | None`.
    """
    if _engine is None:  # pragma: no cover - defensive; lifespan always runs first
        raise RuntimeError("Engine is not initialized; server lifespan did not run.")
    return _engine


@asynccontextmanager
async def lifespan(app: FastMCP):
    global _engine
    _engine = Engine.from_settings(settings)
    await ensure_seeded(_engine, settings)   # populate a fresh local DB once
    try:
        yield
    finally:
        await _engine.close()


mcp = FastMCP("never-again", lifespan=lifespan)


@mcp.tool()
async def query_failures(text: str, limit: int = 5) -> list[dict]:
    """Find past failures similar to this error or situation."""
    hits = await _require_engine().query(text, team=settings.team, limit=limit)
    return [
        {"id": h.failure.id, "error": h.failure.error,
         "solution": h.failure.solution, "rule": h.failure.rule,
         "verified": h.failure.verified, "score": round(h.score, 3)}
        for h in hits
    ]


@mcp.tool()
async def log_failure(error: str, solution: str = "", context: str = "",
                      scope: str = "local", rule: str | None = None) -> dict:
    """Capture a failure and its fix so future agents can avoid it.

    If you can, pass `rule` as a WHEN / CHECK / BECAUSE prevention rule you write
    yourself — you have the full context of the fix. If you omit it, one is
    generated from the fields you provide.
    """
    failure = await _require_engine().log(
        error=error, solution=solution, context=context,
        scope=scope, team=settings.team, rule=rule)
    return {"id": failure.id, "rule": failure.rule}


@mcp.tool()
async def verify_resolution(failure_id: str) -> dict:
    """Confirm that a fix worked. Increments the verified counter."""
    ok = await _require_engine().verify(failure_id)
    return {"verified": ok}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
