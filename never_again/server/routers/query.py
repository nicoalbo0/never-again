from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel


class QueryRequest(BaseModel):
    text: str
    team: str = "local"
    limit: int = 5
    cosine_floor: float | None = None
    fused_floor: float | None = None


class HitResponse(BaseModel):
    id: str
    error: str
    solution: str
    rule: str | None
    verified: int
    score: float
    scope: str


class QueryResponse(BaseModel):
    results: list[HitResponse]


router = APIRouter()


@router.post("/failures/query", response_model=QueryResponse)
async def query_failures(request: Request, payload: QueryRequest) -> QueryResponse:
    engine = request.app.state.engine
    try:
        hits = await engine.query(
            payload.text,
            team=payload.team,
            limit=payload.limit,
            cosine_floor=payload.cosine_floor,
            fused_floor=payload.fused_floor,
        )
        results = [
            HitResponse(
                id=hit.failure.id or "",
                error=hit.failure.error,
                solution=hit.failure.solution,
                rule=hit.failure.rule,
                verified=hit.failure.verified,
                score=round(hit.score, 3),
                scope=hit.failure.scope,
            )
            for hit in hits
        ]
        return QueryResponse(results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
