"""Team-tier store: Postgres 16 + pgvector. Schema lives in deploy/migrations/."""
from __future__ import annotations
import uuid

import asyncpg

from never_again.core.models import Failure, Hit
from never_again.core.retrieval import fuse, overlap as _overlap


def _vec(embedding) -> str | None:
    return "[" + ",".join(map(str, embedding)) + "]" if embedding else None


class PostgresStore:
    def __init__(self, dsn: str, embedding_dimension: int | None = None) -> None:
        self._dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        self._embedding_dimension = embedding_dimension
        self._pool: asyncpg.Pool | None = None

    async def _p(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn)
        return self._pool

    async def add(self, failure: Failure, embedding=None) -> Failure:
        pool = await self._p()
        row = await pool.fetchrow(
            """INSERT INTO failures (id, fingerprint, error, context, solution, rule,
                                     scope, team, verified, embedding, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, CAST($10 AS vector), $11)
               ON CONFLICT (fingerprint, team, solution) DO UPDATE SET
                 rule=EXCLUDED.rule, embedding=EXCLUDED.embedding
               RETURNING id""",
            failure.id or uuid.uuid4().hex, failure.fingerprint, failure.error,
            failure.context, failure.solution, failure.rule, failure.scope,
            failure.team, failure.verified, _vec(embedding), failure.created_at)
        failure.id = row["id"]
        return failure

    async def search(self, text, embedding=None, team="local", limit=5,
                     cosine_floor=0.0, fused_floor=0.0) -> list[Hit]:
        pool = await self._p()
        visible = "(team = $2 OR scope = 'public')"

        kw = await pool.fetch(
            f"""SELECT id, error FROM failures
                WHERE search @@ plainto_tsquery('english', $1) AND {visible}
                ORDER BY ts_rank(search, plainto_tsquery('english', $1)) DESC LIMIT 50""",
            text, team)
        keyword_ids = [r["id"] for r in kw]
        error_by_id = {r["id"]: r["error"] for r in kw}

        semantic_ids = []
        cosine_by_id: dict[str, float] = {}
        if embedding:
            if self._embedding_dimension:
                distance_sql = (
                    f"embedding::vector({self._embedding_dimension}) "
                    f"<=> CAST($1 AS vector({self._embedding_dimension}))"
                )
            else:
                distance_sql = "embedding <=> CAST($1 AS vector)"
            # pgvector <=> is cosine DISTANCE; similarity = 1 - distance
            sem = await pool.fetch(
                f"""SELECT id, {distance_sql} AS dist
                    FROM failures WHERE embedding IS NOT NULL AND {visible}
                    ORDER BY dist LIMIT 50""",
                _vec(embedding), team)
            cosine_by_id = {r["id"]: 1.0 - float(r["dist"]) for r in sem}
            semantic_ids = [r["id"] for r in sem]

        ranked = fuse(keyword_ids, semantic_ids)

        # Relevance floor: abstain rather than surface a confident wrong match.
        #  - embeddings on  -> gate on cosine similarity.
        #  - keyword only   -> gate on shared content terms between query and
        #    candidate AND the fused score. ts_rank alone happily "matches"
        #    unrelated errors on a common word, so require real term overlap —
        #    the same discipline SqliteStore uses for its zero-dep default.
        min_overlap = 2
        kept = []
        for fid, score in ranked:
            if embedding:
                if cosine_by_id.get(fid, 0.0) >= cosine_floor:
                    kept.append((fid, score))
            else:
                cand = error_by_id.get(fid, "")
                if _overlap(text, cand) >= min_overlap and score >= fused_floor:
                    kept.append((fid, score))
        ranked = kept[:limit]

        hits = [Hit(await self._get(pool, fid), s) for fid, s in ranked]
        hits.sort(key=lambda h: (h.score, h.failure.verified), reverse=True)
        return hits

    async def verify(self, failure_id) -> bool:
        pool = await self._p()
        result = await pool.execute("UPDATE failures SET verified = verified + 1 WHERE id=$1",
                                    failure_id)
        return result.split()[-1] != "0"

    async def _get(self, pool, failure_id) -> Failure:
        r = await pool.fetchrow("SELECT * FROM failures WHERE id=$1", failure_id)
        return Failure(error=r["error"], context=r["context"], solution=r["solution"],
                       rule=r["rule"], fingerprint=r["fingerprint"], scope=r["scope"],
                       team=r["team"], verified=r["verified"], id=r["id"],
                       created_at=r["created_at"])

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
