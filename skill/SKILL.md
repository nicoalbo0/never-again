---
name: never-again
description: >-
  Stops a coding agent repeating a mistake it (or another agent) has already made.
  ALWAYS use this skill the moment an error, stack trace, failed test, or broken
  build appears — query it BEFORE attempting a fix — and AGAIN after the fix works,
  to record the lesson. Also use it before starting work that's historically fragile
  (database migrations, async code, auth flows, build/packaging, Docker networking).
  Backed by a local-first failure database via three MCP tools: query_failures,
  log_failure, verify_resolution.
license: Apache-2.0
compatibility: "Claude Code, Cursor, Gemini CLI, any MCP-compatible agent"
---

# never-again

A failure memory for coding agents. Capture a mistake once; never repeat it.

The whole point: the moment something breaks, check whether this exact failure is
already known and has a fix — instead of re-deriving the solution (or re-making the
mistake) from scratch. Then, once you've solved it, write it down so the next agent
gets the fix for free.

There are exactly three tools. Use them in this loop:

```
  error appears ──▶ query_failures ──▶ apply known fix ──▶ verify_resolution
        │                                     │
        └────────── no match ────────────────┘
                         │
                  solve it yourself
                         │
                         ▼
                   log_failure
```

---

## When to act

**Query immediately when you see:** an error message, a stack trace, a non-zero
exit, a failing test, a hung process, or output that contradicts what the code
should do. Query *before* you start theorising about the cause — a known fix is
faster than re-debugging.

**Query proactively before:** database migrations, schema changes, async/await
work, authentication or token flows, build and packaging steps, dependency
upgrades, and anything touching Docker networking. These fail in repeatable ways.

**Log after:** a fix is confirmed working — a red test goes green, a broken build
succeeds, a runtime error stops reproducing. Only log once you understand *what*
fixed it.

**Verify after:** you applied a fix that `query_failures` handed you and it worked.

Do not log while still debugging, and do not log guesses.

---

## Tool: query_failures

Search the database for failures similar to what you're seeing.

**Arguments**
- `text` (required): paste the error message verbatim, OR describe the task you're
  about to start. Verbatim error text matches best.
- `limit` (optional, default 5): how many results to return.

**Returns** a list, each item:
- `id` — the record's id (keep it; you'll need it for `verify_resolution`)
- `error` — the original error that was logged
- `solution` — what fixed it
- `rule` — a prevention rule as a plain string in WHEN / CHECK / BECAUSE form
- `score` — relevance (higher is a stronger match)

**What to do with results**

Read the top result's `rule` and `solution`. If its WHEN condition matches your
situation, apply the CHECK before going further, and surface it to the user like
this:

```
⚠ never-again: this looks like a known failure (match score 0.84)
<the rule string, as returned>
Fix that worked before: <solution>
```

Then try that fix first. If you apply it and it resolves the problem, call
`verify_resolution` with that result's `id`. If nothing comes back, or no result
actually matches your situation, solve it yourself and `log_failure` afterwards.

Don't silently ignore a strong match. Don't trust a weak, irrelevant one just
because it was returned — judge it by whether the WHEN genuinely fits.

---

## Tool: log_failure

Record a solved failure so future agents skip the pain.

**Arguments**
- `error` (required): the core error text. Keep the meaningful part of the message;
  strip the volatile noise (the fingerprinter already removes paths, numbers, and
  ids, but trim anything obviously machine-specific).
- `solution` (optional but strongly recommended): what actually fixed it, specific
  enough to act on. Describe the change; don't paste source code.
- `context` (optional): one line on what you were doing and the stack involved
  (e.g. "alembic migration on postgres 16 with a non-null column").
- `scope` (optional, default `"local"`): `"local"` keeps it in your own database,
  `"team"` shares it with your team, `"public"` contributes it to the shared
  database. **Ask the user before using `"public"`.**
- `rule` (optional but recommended): the WHEN / CHECK / BECAUSE prevention rule,
  written by you. You just solved this failure and have the full context, so you
  can write a far better rule than anything generated after the fact. Write it in
  the three-line format below. If you omit it, a basic rule is built from the
  fields you provide — but prefer to write your own.

**Returns** `{ "id": "...", "rule": "..." }` — the stored id and the prevention
rule (yours if you supplied one, otherwise the generated fallback).

**Before you call it — privacy**
- Remove absolute paths, secrets, tokens, and connection strings containing
  passwords from `error`, `solution`, and `context`.
- Describe the fix in words; never paste proprietary code.
- Duplicates are handled for you: logging the same failure again updates the
  existing record rather than creating a second one.

---

## Tool: verify_resolution

Confirm that a fix from `query_failures` actually worked. This bumps the record's
verified counter, which strengthens it for everyone next time.

**Arguments**
- `failure_id` (required): the `id` from the `query_failures` result you used.

**Returns** `{ "verified": true }` (or `false` if the id wasn't found).

Call this only when the fix you took from a result genuinely solved your problem.
It's a small step, but it's what makes good fixes rise and stale ones fade.

---

## The WHEN / CHECK / BECAUSE rule format

Every prevention rule is one string shaped like this:

```
WHEN: <observable condition that triggers the risk>
CHECK: <concrete thing to verify or do before proceeding>
BECAUSE: <the root cause — why skipping the check causes the failure>
```

A good rule is **observable** (the WHEN is detectable without running the code),
**actionable** (the CHECK is something you can do right now), and **causal** (the
BECAUSE explains the mechanism, not just the symptom). When you write `solution`
text in `log_failure`, aim for that quality — the rule generator builds on what you
give it.

Weak:
```
WHEN: doing database migrations
CHECK: be careful
BECAUSE: migrations can fail
```

Strong:
```
WHEN: adding a column to a table that already has rows in production
CHECK: the new column is nullable or has a server_default
BECAUSE: Postgres takes an ACCESS EXCLUSIVE lock during ALTER TABLE and fails
mid-migration if existing rows can't satisfy the constraint
```

---

## Setup notes

never-again runs as a local MCP server with no required infrastructure — it uses a
SQLite database at `~/.never-again/failures.db` out of the box, with optional
semantic search and a team server as opt-in upgrades.

Register it with your agent (Claude Code example, in your MCP config):

```json
{
  "mcpServers": {
    "never-again": { "command": "never-again-mcp" }
  }
}
```

Optional environment variables, set in the MCP config's `env` block:
- `NEVER_AGAIN_EMBEDDER` — `fts` (default, keyword-only), `local` (in-process
  semantic search), or `ollama` (semantic search via a running Ollama).
- `NEVER_AGAIN_TEAM` — your team slug, if sharing.
- `NEVER_AGAIN_URL` — a team server URL; when set, the tools talk to it instead of
  the local database.

With no configuration at all, everything still works on the local database — that's
the intended default.

---
