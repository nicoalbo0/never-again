# Contributing to never-again

Thanks for considering a contribution. This project is small on purpose, and the
bar for changes is "does it make the tool more useful to a developer in the first
five minutes, without adding infrastructure?" Most of the value here is in
restraint — keep that in mind and you'll fit right in.

## Ground rules (the short version)

- **Local-first stays the default.** The base `pip install never-again` must keep
  working with zero infrastructure: stdlib + SQLite + FTS5, no server, no API
  keys, nothing leaving the machine. Anything heavier is an opt-in extra.
- **Abstention is a feature, not a bug.** The relevance floor that makes the tool
  return *nothing* on a weak match is the most important behavior in the codebase.
  Do not "improve recall" by weakening it without an eval that proves the
  false-positive rate didn't get worse.
- **Privacy is enforced in code, not prose.** Redaction lives in `Engine.log`, so
  it applies no matter who calls in. If you touch the capture path, keep it that
  way.
- **Minimal, readable code.** Prefer fewer lines and no unnecessary abstraction.
  Every file starts with `from __future__ import annotations`. Anything that
  touches I/O is `async`.

## Development setup

```bash
git clone https://github.com/<YOUR-HANDLE>/never-again
cd never-again

python -m venv .venv && source .venv/bin/activate   # Python 3.12+
pip install -e ".[local]"
pip install pytest pytest-asyncio fastapi httpx mcp ruff

pytest          # 54 tests, all mocked — no network, no real models
never-again-eval
ruff check .    # lint
```

The test suite is **fully mocked**: no real network calls, no real embedding
models, no external services. New tests must follow the same discipline — use
`unittest.mock`, FastAPI's `TestClient`, and `app.dependency_overrides` rather
than reaching out to anything real. A test that needs a live Postgres or a real
model download will not be accepted; mock the boundary instead.

## Project layout

```
never_again/
  config.py            # env-driven Settings; tiny dependency-free .env loader
  engine.py            # wiring: ties store + embedder + rules together
  core/                # pure logic, no I/O
    models.py          #   Failure / Hit dataclasses
    fingerprint.py     #   normalize an error -> stable dedup signature
    anonymize.py       #   redact secrets/emails/usernames (enforced in Engine.log)
    retrieval.py       #   RRF fusion + the keyword-overlap floor primitives
    context_detector.py#   detect the project's tech stack from marker files
  embeddings/          # text -> vector, pluggable (fts no-op / local / ollama)
  rules/               # Failure -> WHEN/CHECK/BECAUSE rule (verbatim default)
  store/               # persistence, pluggable (sqlite / postgres / http proxy)
  mcp/server.py        # THE PRODUCT: stdio MCP server, three tools
  cli/main.py          # same operations from a terminal
  server/              # optional team-tier FastAPI app
deploy/                # Dockerfile, compose, Postgres migrations (team tier)
skill/                 # SKILL.md + session-start hook (agent-facing skill)
tests/                 # fully mocked unit tests
```

The three layers you'll most often extend are **store**, **embeddings**, and
**rules**. Each is a `Protocol` with a small surface (see `store/base.py`,
`embeddings/base.py`, `rules/base.py`) and an `open_*` factory that picks the
implementation from `Settings`. Add a backend by implementing the protocol and
wiring it into the factory — nothing else should need to change.

## What makes a good pull request

- **One concern per PR.** Small, reviewable, with a clear "why."
- **Tests included.** New behavior needs a test; a bug fix needs a regression
  test that fails before your change and passes after.
- **Floors respected.** If your change affects retrieval, say in the PR
  description what it does to false positives. Run `never-again-eval` and include
  the recall / MRR / false-positive output; use `never-again-eval --check` for
  threshold gating. "It returns more results" is a red flag unless you can show
  the extra results are real matches.
- **No new required dependency in the base tier.** New libraries belong behind an
  optional extra in `pyproject.toml` (`[local]`, `[ollama]`, `[server]`).
- **Docs updated** if you changed a tool signature, an env var, or the install
  story. The README, `SKILL.md`, and `.env.example` should never drift from the
  code.

## High-value areas to contribute

These are the open problems where help is most welcome (see `ARCHITECTURE.md` and
the issue tracker for detail):

- **Cold-start seeding.** Git-history mining is the current approach; better
  strategies for making a fresh install useful before the first logged failure
  are wanted.
- **Benchmark corpus.** The `never-again-eval` harness exists; the next
  high-value work is adding more real positive and negative cases to
  `never_again/evals/`. New stored failures need source/provenance metadata;
  avoid invented tidy examples.
- **More agent integrations.** Tested setup recipes for editors and agents beyond
  Claude Code / Cursor / Gemini CLI.

## Reporting bugs

Open an issue with: what you ran, what you expected, what happened, and your
config (store, embedder, OS, Python version). If it involves a match that should
or shouldn't have been returned, include the query text and — if you can — the
logged error it did or didn't match. Never paste secrets; the tool redacts on
capture, but issues are public.

## Code of conduct

Be decent. Assume good faith, keep critique about the code, and remember that a
"no" to a feature is usually about keeping the tool small, not about you.

## License

By contributing, you agree your contributions are licensed under the project's
Apache 2.0 License.
