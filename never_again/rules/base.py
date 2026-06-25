"""The RuleGenerator contract: a Failure -> a prevention rule, or None."""
from __future__ import annotations
from typing import Protocol

from never_again.config import Settings
from never_again.core.models import Failure


class RuleGenerator(Protocol):
    async def generate(self, failure: Failure) -> str | None:
        """Return a WHEN / CHECK / BECAUSE prevention rule, or None."""
        ...


def open_rules(settings: Settings) -> RuleGenerator:
    """The fallback rule generator, used only when the caller supplies no rule.

    Agents that log a failure write the WHEN / CHECK / BECAUSE rule themselves —
    they have the full context of the fix. This verbatim generator just formats
    the provided fields for callers (like the CLI) that don't pass a rule.
    """
    from never_again.rules.verbatim import VerbatimRules
    return VerbatimRules()