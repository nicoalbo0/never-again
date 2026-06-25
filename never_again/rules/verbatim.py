"""Default rule generator: format the failure's own fields. No LLM."""
from __future__ import annotations

from never_again.core.models import Failure


class VerbatimRules:
    async def generate(self, failure: Failure) -> str:
        lines = [f"WHEN: {failure.error.strip()}"]
        if failure.solution.strip():
            lines.append(f"CHECK: {failure.solution.strip()}")
        if failure.context.strip():
            lines.append(f"BECAUSE: {failure.context.strip()}")
        return "\n".join(lines)