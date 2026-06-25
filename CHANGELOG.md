# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-26

First public release.

### Added
- Local-first failure memory for coding agents, exposed as a stdio MCP server
  with three tools: `query_failures`, `log_failure`, `verify_resolution`.
- Zero-infrastructure base tier: SQLite + FTS5 keyword search, stdlib only.
- Optional semantic search: in-process embeddings via fastembed (`[local]`) or
  via a running Ollama (`[ollama]`).
- Optional team tier: FastAPI + Postgres 16 + pgvector, with clients pointed at
  it via `NEVER_AGAIN_URL`. Deployment files in `deploy/`.
- Reciprocal Rank Fusion blending keyword and semantic rankings, with scores
  normalized to 0..1.
- Relevance floor so the tool abstains (returns nothing) on weak matches instead
  of surfacing a confident wrong fix — cosine-gated on the semantic path,
  content-term-overlap-gated on the keyword-only path.
- Error fingerprinting (normalizes paths, numbers, hex, UUIDs) for dedup on
  `(fingerprint, team, solution)`.
- Privacy redaction (passwords in connection strings, emails, API tokens, home
  directory usernames) enforced in `Engine.log`.
- `WHEN / CHECK / BECAUSE` prevention rules, written by the logging agent or
  formatted from the recorded fields when none is supplied.
- Cold-start seeding from the repo's own git history (fix-shaped commits), with
  optional enrichment from closed GitHub issues when `GITHUB_TOKEN` is set.
- Tech-stack auto-detection from project marker files, used to enrich both the
  keyword and semantic sides of a query.
- CLI (`never-again search | log | verify | health`).
- Agent skill (`skill/SKILL.md`) and a fail-silent session-start hook.
- Fully mocked test suite (54 tests; no network, no real models).

### Notes for early adopters
- Empty results are expected on a fresh repo and in the early days of use — the
  tool is designed to stay quiet until it has a real match. This is intended
  behavior, not a failure.
- Redaction is best-effort, not a guarantee. Don't log anything you'd be
  unwilling to share at the failure's chosen `scope`.

[0.1.0]: https://github.com/<YOUR-HANDLE>/never-again/releases/tag/v0.1.0
