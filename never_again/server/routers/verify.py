from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel


class VerifyResponse(BaseModel):
    verified: bool


router = APIRouter()


@router.post("/failures/{id}/verify", response_model=VerifyResponse)
async def verify_resolution(request: Request, id: str) -> VerifyResponse:
    engine = request.app.state.engine
    try:
        success = await engine.verify(id)
        return VerifyResponse(verified=success)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
