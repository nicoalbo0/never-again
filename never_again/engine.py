"""Wiring: one object that ties the store, embedder, and rules together."""
from __future__ import annotations

from never_again.config import Settings
from never_again.core.anonymize import anonymize
from never_again.core.context_detector import detect_tech_stack
from never_again.core.fingerprint import fingerprint
from never_again.core.models import Failure, Hit
from never_again.embeddings.base import open_embedder
from never_again.rules.base import open_rules
from never_again.store.base import open_store


class Engine:
    def __init__(self, store, embedder, rules, settings: Settings | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.rules = rules
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> "Engine":
        return cls(open_store(settings), open_embedder(settings),
                   open_rules(settings), settings=settings)

    async def log(self, error: str, solution: str = "", context: str = "",
                  scope: str = "local", team: str = "local",
                  rule: str | None = None) -> Failure:
        """Capture a failure: redact, fingerprint, attach a rule, embed, store.

        If the caller supplies a `rule` (the logging agent usually can — it just
        solved the bug and has the full context), it's used as-is. Otherwise the
        rule is formatted from the provided fields (no model involved).
        """
        error, solution, context = anonymize(error), anonymize(solution), anonymize(context)
        rule = anonymize(rule) if rule else None
        detected = detect_tech_stack()
        if detected:
            stack_str = f"[Stack: {', '.join(detected)}]"
            if context:
                context = f"{context} {stack_str}"
            else:
                context = stack_str
        failure = Failure(error=error, solution=solution, context=context,
                          scope=scope, team=team, fingerprint=fingerprint(error))
        failure.rule = rule or await self.rules.generate(failure)
        vector = await self.embedder.embed(f"{error}\n{context}".strip())
        return await self.store.add(failure, vector)

    async def query(self, text: str, team: str = "local", limit: int = 5) -> list[Hit]:
        """Find past failures similar to the given text.

        The detected tech stack enriches BOTH retrieval paths symmetrically:
        the keyword query and the embedded text. This mirrors `log`, which bakes
        the same stack tag into the text it embeds — so a query and the failure
        it should match pass through the same transformation on both the keyword
        and the vector side. Enriching only one side (as an earlier version did)
        silently degraded semantic recall.

        The store applies a relevance floor so that a query with no real match
        returns an empty list instead of a confident-but-wrong fix. The floor
        gates on cosine similarity when embeddings are on (the signal that
        actually separates matches from noise) and on the fused score otherwise.
        """
        detected = detect_tech_stack()
        if detected:
            enriched_text = f"{text} {' '.join(detected)}"
        else:
            enriched_text = text
        vector = await self.embedder.embed(enriched_text)
        cosine_floor = self.settings.cosine_floor if self.settings else 0.0
        fused_floor = self.settings.fused_floor if self.settings else 0.0
        return await self.store.search(
            enriched_text, vector, team=team, limit=limit,
            cosine_floor=cosine_floor, fused_floor=fused_floor)

    async def verify(self, failure_id: str) -> bool:
        return await self.store.verify(failure_id)

    async def close(self) -> None:
        await self.store.close()
