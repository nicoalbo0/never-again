from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> dict[str, str | bool]:
    engine = request.app.state.engine
    return {
        "status": "ok",
        "store_type": type(engine.store).__name__,
        "embedder_type": type(engine.embedder).__name__,
    }
