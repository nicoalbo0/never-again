"""Turn a noisy error message into a stable fingerprint for dedup."""
from __future__ import annotations
import hashlib
import re

# Applied in order — most specific patterns first.
_PATTERNS = [
    (re.compile(r"0x[0-9a-fA-F]+"), "<hex>"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "<uuid>"),
    (re.compile(r"(?:[a-zA-Z]:[/\\]+|[/\\]+)(?:[^/\\\r\n]+[/\\]+)*[^/\\\s]+"), "<path>"),
    (re.compile(r"\b\d+\b"), "<n>"),
]


def normalize(error: str) -> str:
    """Replace volatile bits (hex, uuids, paths, numbers) with placeholders."""
    text = error.strip().lower()
    for pattern, placeholder in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(error: str) -> str:
    """Short stable hash of the normalized error."""
    return hashlib.sha256(normalize(error).encode()).hexdigest()[:16]