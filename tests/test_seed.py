"""Project-history seed tests. Git operations run against a real throwaway repo
created in a tmp dir (fast, hermetic). GitHub is verified to stay OFF without a
token — never touching the network in tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from never_again.seed.project_history import (
    mine_fix_commits, mine_github_issues, _FIX_RE, seed_from_history,
)


def _make_repo(tmp_path: Path, subjects: list[str]) -> Path:
    d = tmp_path / "repo"
    d.mkdir()

    def run(*a):
        return subprocess.run(["git", *a], cwd=str(d), capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@t.com")
    run("config", "user.name", "t")
    run("config", "commit.gpgsign", "false")
    for i, subj in enumerate(subjects):
        (d / "f.txt").write_text(f"{i}")
        run("add", ".")
        run("commit", "-q", "-m", subj)
    return d


def test_fix_regex_matches_conventions():
    for good in ["fix: x", "fix(db): y", "bugfix: z", "hotfix: w",
                 "bug: v", "fixes #12", "resolved the crash", "revert bad commit"]:
        assert _FIX_RE.search(good), good


def test_fix_regex_rejects_non_fixes():
    for bad in ["feature: add thing", "fixture setup", "docs: update",
                "refactor module", "prefix handling"]:
        assert not _FIX_RE.search(bad), bad


def test_mine_extracts_only_fix_commits(tmp_path):
    repo = _make_repo(tmp_path, [
        "initial commit",
        "fix: asyncpg InterfaceError another operation in progress",
        "add a feature",
        "bugfix: TypeError unsupported operand NoneType",
        "docs: readme",
    ])
    seeds = mine_fix_commits(repo)
    assert len(seeds) == 2
    errors = " ".join(s["error"] for s in seeds)
    assert "InterfaceError" in errors and "TypeError" in errors


def test_mine_uses_error_token_when_present(tmp_path):
    repo = _make_repo(tmp_path, ["fix: resolve ValueError on null cast"])
    seeds = mine_fix_commits(repo)
    assert seeds and "ValueError" in seeds[0]["error"]


def test_mine_falls_back_to_subject_without_error_token(tmp_path):
    repo = _make_repo(tmp_path, ["fix: handle the empty list edge case"])
    seeds = mine_fix_commits(repo)
    assert seeds
    # no Error/Exception token -> error falls back to the cleaned subject
    assert "empty list" in seeds[0]["error"]


def test_mine_non_repo_returns_empty(tmp_path):
    assert mine_fix_commits(tmp_path) == []


def test_github_off_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = _make_repo(tmp_path, ["fix: x"])
    # even with a github remote, no token -> no network, empty result
    subprocess.run(["git", "remote", "add", "origin",
                    "https://github.com/owner/repo.git"], cwd=str(repo),
                   capture_output=True)
    assert mine_github_issues(repo) == []


@pytest.mark.asyncio
async def test_seed_from_history_logs_into_engine(tmp_path, engine, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = _make_repo(tmp_path, [
        "fix: asyncpg InterfaceError another operation",
        "bugfix: ValueError bad cast",
    ])
    n = await seed_from_history(engine, cwd=repo)
    assert n == 2
    # the seeded failures are now queryable
    hits = await engine.query("asyncpg InterfaceError operation")
    assert len(hits) >= 1
