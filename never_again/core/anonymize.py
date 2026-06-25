"""Strip personal data and secrets from failure text before it is stored.

Enforced in Engine.log so it applies no matter who calls in. The skill asks
agents to redact, but trusting the caller isn't enough once data can be shared
to a team or public scope.
"""
from __future__ import annotations
import re

# (pattern, replacement), applied in order. Deliberately conservative: catch the
# high-value leaks (credentials, emails, usernames) without mangling real errors.
_PATTERNS = [
    # password inside a connection string:  scheme://user:PASSWORD@host
    (re.compile(r"(\w+://[^:/\s]+:)[^@/\s]+(@)"), r"\1<redacted>\2"),
    # email addresses
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    # username in a home path:  /Users/alice/...  or  /home/alice/... or Windows C:\Users\alice\...
    (re.compile(r"([/\\]+(?:Users|home)[/\\]+)[^/\\\s]+"), r"\1<user>"),
    # common API key / token formats
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "<token>"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{30,}"), "<token>"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "<token>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<token>"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "<token>"),
    # bearer tokens
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"), "Bearer <token>"),
]


def anonymize(text: str) -> str:
    """Redact emails, secrets, tokens, and usernames. Best-effort, not a guarantee."""
    if not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text
