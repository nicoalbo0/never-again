"""Team-tier HTTP app. Thin wrapper over the Engine; routers do the work."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from never_again.config import load
from never_again.engine import Engine
from never_again.server.routers import health, log, query, verify


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = Engine.from_settings(load())
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.close()


app = FastAPI(title="never-again", lifespan=lifespan)
app.include_router(health.router)
app.include_router(log.router)
app.include_router(query.router)
app.include_router(verify.router)
