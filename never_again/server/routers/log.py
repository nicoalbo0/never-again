from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel


class LogRequest(BaseModel):
    error: str
    solution: str = ""
    context: str = ""
    scope: str = "local"
    team: str = "local"
    rule: str | None = None


class LogResponse(BaseModel):
    id: str
    rule: str | None


router = APIRouter()


@router.post("/failures", response_model=LogResponse)
async def log_failure(request: Request, payload: LogRequest) -> LogResponse:
    engine = request.app.state.engine
    try:
        failure = await engine.log(
            error=payload.error,
            solution=payload.solution,
            context=payload.context,
            scope=payload.scope,
            team=payload.team,
            rule=payload.rule,
        )
        return LogResponse(id=failure.id or "", rule=failure.rule)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
