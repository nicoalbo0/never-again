"""Cold-start from THIS project's own history.

Generic seeded failures were theater — they rarely match a real query. The
signal that actually recurs is project-specific: the bugs this codebase already
fixed. So on first run we mine the local git history for fix-shaped commits and
seed those. No network, nothing leaves the machine — it just reads `git log`.

A commit counts as a fix when its subject looks like one (fix/bug/revert/
resolve/patch/hotfix) and it isn't a merge. The subject becomes the solution;
any error-looking token in the subject or body becomes the error text, so a
later identical error can match. This is best-effort: a repo with tidy
conventional-commit messages seeds richly; a messy one seeds little, which is
fine — the store fills in from real logged failures either way.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from never_again.engine import Engine

# fix-shaped commit subjects (bug, bugfix, hotfix, fix, fixes, fixed, revert, resolve…)
_FIX_RE = re.compile(r"\b(bug ?fix(?:e[sd])?|hot ?fix|fix(?:e[sd])?|bug|revert|resolve[sd]?|patch)\b", re.I)
# an error/exception token we can use as the matchable error text
_ERR_RE = re.compile(r"[A-Za-z_][\w.]*(?:Error|Exception|Warning)\b[^\n]*")
# strip the leading "fix: " / "fix(scope): " conventional-commit prefix
_PREFIX_RE = re.compile(r"^\s*(?:fix|bug|revert|resolve|patch|hotfix)"
                        r"(?:\([^)]*\))?\s*:?\s*", re.I)

_MAX_COMMITS = 400   # cap so a huge repo's first run stays fast


def _git(args: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                             text=True, timeout=15)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def mine_fix_commits(cwd: Path) -> list[dict]:
    """Return [{error, solution, context}] derived from fix commits in cwd."""
    if not (cwd / ".git").exists():
        return []
    # record-separated log: subject \x1f body \x1e
    raw = _git(["log", f"-n{_MAX_COMMITS}", "--no-merges",
                "--pretty=format:%s%x1f%b%x1e"], cwd)
    if not raw:
        return []
    seeds: list[dict] = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        subject, _, body = record.partition("\x1f")
        subject = subject.strip()
        if not _FIX_RE.search(subject):
            continue
        solution = _PREFIX_RE.sub("", subject).strip() or subject
        # prefer a concrete error token from subject or body as the error text;
        # fall back to the cleaned subject so the entry is still matchable.
        err_match = _ERR_RE.search(subject) or _ERR_RE.search(body)
        error = err_match.group(0).strip() if err_match else solution
        # keep a little of the body as context — it carries the matchable detail
        # the one-line subject usually lacks.
        body_snippet = " ".join(body.split())[:300]
        context = "[seeded from project git history]"
        if body_snippet:
            context = f"{body_snippet} {context}"
        seeds.append({
            "error": error,
            "solution": solution,
            "context": context,
        })
    return seeds


def _github_remote(cwd: Path) -> tuple[str, str] | None:
    """Return (owner, repo) if origin is a github remote, else None."""
    url = _git(["remote", "get-url", "origin"], cwd).strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/.\s]+)", url)
    return (m.group(1), m.group(2)) if m else None


def mine_github_issues(cwd: Path, limit: int = 100) -> list[dict]:
    """OPTIONAL error-rich enrichment from the repo's own closed issues.

    Runs ONLY if origin is a github remote AND GITHUB_TOKEN is set; returns []
    otherwise. This is the one path that touches the network, and it never runs
    without an explicit token, keeping the default install fully local.
    Where git gives solution-rich/error-thin records, issues give the reverse:
    the reporter's pasted error as the matchable text.
    """
    import os
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return []
    remote = _github_remote(cwd)
    if not remote:
        return []
    try:
        import json as _json
        import urllib.request
        owner, repo = remote
        url = (f"https://api.github.com/repos/{owner}/{repo}/issues"
               f"?state=closed&per_page={min(limit, 100)}")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            issues = _json.loads(resp.read())
    except Exception:
        return []
    seeds: list[dict] = []
    for it in issues:
        if "pull_request" in it:
            continue
        body = it.get("body") or ""
        m = _ERR_RE.search(body)
        if not m:
            continue
        seeds.append({
            "error": m.group(0).strip()[:300],
            "solution": (it.get("title") or "").strip()[:300],
            "context": f"[seeded from github issue #{it.get('number')}]",
        })
    return seeds


async def seed_from_history(engine: Engine, cwd: Path | None = None) -> int:
    """Log mined fix commits plus optional GitHub issues. Returns count stored.

    git history is always mined (no network). GitHub issues are added only when
    a token + github remote are present. Records are deduped on (error, solution)
    so an overlap between the two sources never double-seeds.
    """
    cwd = Path(cwd) if cwd else Path.cwd()
    seeds = mine_fix_commits(cwd) + mine_github_issues(cwd)
    seen: set[tuple[str, str]] = set()
    count = 0
    for s in seeds:
        key = (s["error"], s["solution"])
        if key in seen:
            continue
        seen.add(key)
        try:
            await engine.log(error=s["error"], solution=s["solution"],
                             context=s["context"], scope="local")
            count += 1
        except Exception:
            continue
    return count
