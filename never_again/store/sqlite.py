"""Default zero-infra store: SQLite + FTS5. No extensions, no server."""
from __future__ import annotations
import json
import math
import re
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

from never_again.core.models import Failure, Hit
from never_again.core.retrieval import (
    content_terms as _content_terms,
    fuse,
    overlap as _overlap,
)

# `_content_terms` / `_overlap` are re-exported here (their historical home)
# for back-compat; the canonical definitions live in core.retrieval.
__all__ = ["SqliteStore", "_content_terms", "_overlap"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS failures (
    id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    error TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    solution TEXT NOT NULL DEFAULT '',
    rule TEXT,
    scope TEXT NOT NULL DEFAULT 'local',
    team TEXT NOT NULL DEFAULT 'local',
    verified INTEGER NOT NULL DEFAULT 0,
    embedding TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (fingerprint, team, solution)
);
CREATE VIRTUAL TABLE IF NOT EXISTS failures_fts
    USING fts5(id UNINDEXED, error, context, solution);
"""


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _terms(text: str) -> str:
    """Safe FTS query: OR the bare words so punctuation can't break MATCH."""
    words = re.findall(r"\w+", text.lower())
    return " OR ".join(words) if words else '""'




class SqliteStore:
    def __init__(self, path: str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self._path)
            self._db.row_factory = aiosqlite.Row
            await self._db.executescript(_SCHEMA)
            await self._db.commit()
        return self._db

    async def add(self, failure: Failure, embedding=None) -> Failure:
        db = await self._conn()
        cur = await db.execute("SELECT id FROM failures WHERE fingerprint=? AND team=? AND solution=?",
                               (failure.fingerprint, failure.team, failure.solution))
        row = await cur.fetchone()
        failure.id = row["id"] if row else uuid.uuid4().hex
        await db.execute(
            """INSERT INTO failures (id, fingerprint, error, context, solution, rule,
                                     scope, team, verified, embedding, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (id) DO UPDATE SET
                 solution=excluded.solution, rule=excluded.rule, embedding=excluded.embedding""",
            (failure.id, failure.fingerprint, failure.error, failure.context,
             failure.solution, failure.rule, failure.scope, failure.team,
             failure.verified, json.dumps(embedding) if embedding else None,
             failure.created_at.isoformat()))
        await db.execute("DELETE FROM failures_fts WHERE id=?", (failure.id,))
        await db.execute("INSERT INTO failures_fts (id, error, context, solution) VALUES (?,?,?,?)",
                         (failure.id, failure.error, failure.context, failure.solution))
        await db.commit()
        return failure

    async def search(self, text, embedding=None, team="local", limit=5,
                     cosine_floor=0.0, fused_floor=0.0,
                     min_overlap=2) -> list[Hit]:
        db = await self._conn()
        visible = "(f.team = ? OR f.scope = 'public')"

        cur = await db.execute(
            f"""SELECT f.id, f.error FROM failures_fts
                JOIN failures f ON f.id = failures_fts.id
                WHERE failures_fts MATCH ? AND {visible}
                ORDER BY rank LIMIT 50""",
            (_terms(text), team))
        kw_rows = await cur.fetchall()
        keyword_ids = [r["id"] for r in kw_rows]
        error_by_id = {r["id"]: r["error"] for r in kw_rows}

        semantic_ids: list[str] = []
        cosine_by_id: dict[str, float] = {}
        if embedding:
            cur = await db.execute(
                f"SELECT f.id, f.embedding FROM failures f WHERE f.embedding IS NOT NULL AND {visible}",
                (team,))
            scored = [(r["id"], _cosine(embedding, json.loads(r["embedding"])))
                      for r in await cur.fetchall()]
            scored.sort(key=lambda p: p[1], reverse=True)
            cosine_by_id = dict(scored)
            semantic_ids = [i for i, _ in scored[:50]]

        ranked = fuse(keyword_ids, semantic_ids)

        # Relevance floor: abstain rather than surface a confident wrong match.
        #  - embeddings on  -> gate on cosine (the signal that truly separates
        #    matches from noise; the fused RRF score does not).
        #  - keyword only   -> gate on shared content terms between query and
        #    candidate. FTS alone happily "matches" unrelated errors on a common
        #    word like "error", so a fused-score floor is not enough; requiring
        #    real term overlap is what makes the zero-dep default safe.
        kept: list[tuple[str, float]] = []
        for fid, score in ranked:
            if embedding:
                if cosine_by_id.get(fid, 0.0) >= cosine_floor:
                    kept.append((fid, score))
            else:
                cand = error_by_id.get(fid, "")
                if _overlap(text, cand) >= min_overlap and score >= fused_floor:
                    kept.append((fid, score))
        ranked = kept[:limit]

        hits = [Hit(await self._get(db, fid), score) for fid, score in ranked]
        # relevance stays primary; a more-verified fix wins ties.
        hits.sort(key=lambda h: (h.score, h.failure.verified), reverse=True)
        return hits

    async def verify(self, failure_id) -> bool:
        db = await self._conn()
        cur = await db.execute("UPDATE failures SET verified = verified + 1 WHERE id=?",
                               (failure_id,))
        await db.commit()
        return cur.rowcount > 0

    async def _get(self, db, failure_id) -> Failure:
        cur = await db.execute("SELECT * FROM failures WHERE id=?", (failure_id,))
        r = await cur.fetchone()
        return Failure(error=r["error"], context=r["context"], solution=r["solution"],
                       rule=r["rule"], fingerprint=r["fingerprint"], scope=r["scope"],
                       team=r["team"], verified=r["verified"], id=r["id"],
                       created_at=datetime.fromisoformat(r["created_at"]))

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
