# Architecture

This document explains *why* never-again is built the way it is. For how to set
it up, see the [README](README.md); for how to contribute, see
[CONTRIBUTING](CONTRIBUTING.md).

## The one idea

A failure memory for coding agents is only useful if it knows when to stay quiet.

An agent that asks "have I seen this error before?" on every failure will, with a
naive store, *always* get an answer back — and a confidently-returned wrong fix is
worse than no answer at all, because it sends the agent debugging a problem it
doesn't have. So the central design constraint is **abstention**: return a strong
match or return nothing. Everything else in the architecture serves that
constraint or stays out of its way.

## Data flow

### Logging a failure

```
log_failure(error, solution, context, rule?)
        │
        ▼
   anonymize()         redact secrets/emails/usernames (enforced here, in Engine.log)
        │
        ▼
   detect_tech_stack() append a [Stack: …] tag from the project's marker files
        │
        ▼
   fingerprint()       normalize paths/numbers/hex/uuids -> stable dedup signature
        │
        ▼
   rule = caller's rule, or VerbatimRules formats one from the fields
        │
        ▼
   embed(error + context)   -> vector, or None if embeddings are off
        │
        ▼
   store.add(failure, vector)   dedup on (fingerprint, team, solution)
```

### Querying

```
query_failures(text)
        │
        ▼
   detect_tech_stack()  enrich the query with the same stack tokens
        │
        ▼
   embed(enriched_text) -> vector (must mirror what log embedded — see note below)
        │
        ▼
   store.search(enriched_text, vector, cosine_floor, fused_floor)
        │
        ├── keyword path:  FTS5 / tsvector ranking
        ├── semantic path: cosine over embeddings (if vector present)
        │
        ▼
   fuse() the two ranked id-lists with Reciprocal Rank Fusion
        │
        ▼
   RELEVANCE FLOOR  ── embeddings on  -> gate on cosine similarity
                    └─ keyword only   -> gate on shared content-term overlap
        │
        ▼
   return Hits (verified count breaks ties), or [] if nothing clears the floor
```

> **Symmetry note.** `log` embeds `error + context` where `context` already
> carries the `[Stack: …]` tag, and `query` embeds the stack-enriched query text.
> Both sides must push text through the *same* enrichment, or the vectors live in
> subtly different spaces and recall degrades. This symmetry is load-bearing and
> is covered by a regression test.

## Why these components

### Fingerprinting (`core/fingerprint.py`)

The same error recurs with different line numbers, paths, addresses, and ids.
Normalizing those away gives a stable signature, so "logged twice" becomes
"updated once." Dedup is on `(fingerprint, team, solution)` — the same error with
a *different* fix is legitimately a separate entry.

### The relevance floor (`core/retrieval.py`, applied in the stores)

Two gates, depending on what signal is available:

- **Semantic path (embeddings on):** gate on raw cosine similarity, *not* the
  fused RRF score. RRF is great for ordering but its absolute values don't
  separate "real match" from "noise"; cosine does.
- **Keyword-only path (the zero-dep default):** gate on how many meaningful
  content terms the query and candidate share. FTS will happily "match" a Rust
  error to a Python one on the word "error", so a score threshold isn't enough —
  requiring real term overlap is what makes the default tier safe. A small
  stopword set removes the words too common to signal relevance.

Both stores (SQLite and Postgres) apply the same discipline, so the safety
property doesn't change when a team upgrades tiers.

### Reciprocal Rank Fusion (`core/retrieval.py`)

Blends the keyword and semantic orderings into one. An id ranked highly by both
signals wins. Scores are normalized to 0..1 so the number returned to the agent
is interpretable (1.0 = ranked first in every list that returned results) rather
than a raw RRF value like 0.016.

### Pluggable layers

Three protocols, each with a factory that reads `Settings`:

| Layer       | Default        | Opt-in alternatives                          |
|-------------|----------------|----------------------------------------------|
| `store`     | SQLite + FTS5  | Postgres + pgvector (team), HTTP proxy        |
| `embeddings`| FTS no-op      | fastembed in-process (`[local]`), Ollama      |
| `rules`     | verbatim format| (room for an LLM-backed generator)            |

The point of the protocols is that the base install pulls in none of the heavy
machinery. You only pay for embeddings or a server when you ask for them.

## Tiers

| Tier            | Install                          | Storage / search                        |
|-----------------|----------------------------------|-----------------------------------------|
| Base            | `pip install never-again`        | SQLite + keyword (FTS5), zero infra      |
| Local semantic  | `pip install "never-again[local]"`| + in-process embeddings (fastembed)     |
| Ollama          | `pip install "never-again[ollama]"`| + embeddings via a running Ollama       |
| Team            | `deploy/` (Postgres + pgvector)  | shared store across a team via HTTP      |

When `NEVER_AGAIN_URL` is set, the client swaps its local store for an HTTP proxy
that talks to the team server. The agent-facing tools are identical regardless of
tier — only the store behind them changes.

## The MCP server is the product

`mcp/server.py` is the real surface: a stdio MCP server exposing exactly three
tools (`query_failures`, `log_failure`, `verify_resolution`). The CLI exists for
humans and debugging; the team server exists for sharing. But the thing an agent
talks to, and the thing the value proposition rests on, is those three tools over
the local SQLite store.

## Known limitations and open problems

- **Cold start.** A brand-new repo seeds little from git history and returns empty
  results until failures accumulate. Empty-is-correct, but empty-feels-broken;
  better seeding is the most-wanted improvement.
- **Retrieval benchmark corpus.** `never-again-eval` measures recall@1,
  recall@5, MRR, abstention accuracy, and false-positive rate on
  `never_again/evals/retrieval_cases.json`. The open problem is growing the
  corpus with real recurring failures before tuning retrieval internals.
- **Stack tag affects embeddings.** The `[Stack: …]` tag means the same logical
  failure logged from two different repos can embed slightly differently. Accepted
  trade-off for now, documented so it's not a surprise.
- **Redaction is best-effort.** The anonymizer catches the high-value leaks
  (credentials, emails, tokens, home-dir usernames) but is not a guarantee. Don't
  log anything you'd be unwilling to share at the failure's `scope`.
