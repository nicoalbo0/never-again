"""Reciprocal Rank Fusion: blend ranked id-lists into one ordering."""
from __future__ import annotations
from collections import defaultdict
import re

RRF_K = 60  # damping constant; the standard default from the RRF paper


def fuse(*ranked_lists: list[str], k: int = RRF_K) -> list[tuple[str, float]]:
    """Merge ranked lists of ids by RRF, best first.

    Each list is ordered best-to-worst. An id ranked highly across several lists
    wins. Scores are normalised to 0..1, where 1.0 means "ranked first in every
    list that returned results" — so the number is meaningful to a reader instead
    of a raw RRF value like 0.016. Returns (id, score) pairs, best first.
    """
    scores: dict[str, float] = defaultdict(float)
    lists_used = 0
    for results in ranked_lists:
        if not results:
            continue
        lists_used += 1
        for rank, item_id in enumerate(results):
            scores[item_id] += 1.0 / (k + rank)
    if not scores:
        return []
    best_possible = lists_used / k  # rank 0 in every non-empty list
    return sorted(((i, s / best_possible) for i, s in scores.items()),
                  key=lambda pair: pair[1], reverse=True)


# Tiny stopword set: words too common to signal relevance. Kept minimal on
# purpose — these are the ones that otherwise make every error "match" every
# other (e.g. a keyword query for a Rust error matching a Python one on "error").
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "for", "with", "and", "or", "not", "no",
    "this", "that", "it", "its", "as", "by", "from", "error", "exception",
    "failed", "failure", "cannot", "can", "could", "would", "should", "when",
    "line", "file", "none", "null", "true", "false", "if", "else",
}


def content_terms(text: str) -> set[str]:
    """Meaningful lowercased tokens (len>=3, not a stopword, not pure digits)."""
    return {w for w in re.findall(r"[a-z][a-z0-9_]{2,}", text.lower())
            if w not in _STOP}


def overlap(query: str, candidate: str) -> int:
    """How many content terms the query and a candidate error share."""
    return len(content_terms(query) & content_terms(candidate))
