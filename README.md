
# never-again

A failure memory for coding agents. When an agent hits an error, it can check whether that same failure was already solved — in this repo, by an earlier session — instead of debugging it again from scratch. Once solved, the fix is written down so the next session gets it for free.

It runs locally on top of a SQLite file. No server to stand up, no API keys, no data leaving your machine. `pip install`, point your agent at it, done.

## What it does

`never-again` exposes three tools to an MCP-compatible agent (Claude Code, Cursor, Gemini CLI, or anything that speaks MCP):

* **`query_failures(text, limit)`** — search past failures similar to an error or task. Each result includes the fix that worked and a short `WHEN / CHECK / BECAUSE` prevention rule. If nothing genuinely matches, it returns an empty list rather than a confident wrong answer.
* **`log_failure(error, solution, context, scope)`** — record a solved failure. Secrets, tokens, emails, and usernames are stripped before anything is written.
* **`verify_resolution(failure_id)`** — confirm a fix worked, which nudges it higher in future results.

The intended loop is simple:

```
error ──▶ query_failures ──▶ apply known fix ──▶ verify_resolution
   │                               │
   └────────── no match ───────────┘
                  │
            solve it yourself ──▶ log_failure
```

## What it doesn't do

* It isn't a shared public knowledge base. By default everything stays in a local SQLite file scoped to you. Team sharing is opt-in (see below).
* It doesn't fix anything itself. It surfaces a prior fix and a rule; your agent decides whether the situation actually matches and applies it.
* It won't always have an answer. A memory that always responds would send agents chasing fixes for problems they don't have, so it abstains when the match is weak. Empty results are the expected case early on, and on a brand-new repo.

## When it helps (and when it doesn't)

Being honest about this up front, because it sets the right expectations:

**It pays off when**

* You work in a **mature repo** with a history of recurring, stack-specific
  failures (migrations, async pitfalls, build/packaging quirks, Docker
  networking). These fail in repeatable ways, which is exactly what a memory
  catches.
* The same class of error shows up **across sessions or across agents** — the
  durable edge here is cross-session memory, the part a model's context window
  doesn't cover.
* A team hits the **same problems** and wants the first person's fix to save the
  next person's afternoon (team tier).

**It won't do much when**

* You're on a **brand-new or greenfield** project — there's little history to
  seed from, so early queries return empty. That's correct behavior, but it means
  the value arrives later, as failures accumulate.
* The bugs are **one-off and novel** rather than recurring — there's nothing to
  remember.

The payoff is a non-event: an error you *didn't* have to debug a second time. That
makes it easy to under-notice when it's working. Give it a few weeks of real use
before judging it.

## Install

```bash
pip install never-again
```

If you want the `never-again` command available globally — recommended, and
required if you use the session-start hook (see [Agent skill](skill/SKILL.md)) —
install it as a tool instead, so it lands on your `PATH`:

```bash
uv tool install never-again      # or: pipx install never-again
```

Register it with your agent. For Claude Code, add to your MCP config:

```json
{
  "mcpServers": {
    "never-again": { "command": "never-again-mcp" }
  }
}
```

That's the whole setup. It stores failures in `~/.never-again/failures.db`.

On first run inside a git repo, it seeds your memory from the repo's own history — mining fix-shaped commits from `git log` so the first few queries can already match something real. This reads `git log` only; nothing leaves your machine. (If `GITHUB_TOKEN` is set and the repo has a GitHub remote, it also pulls error text from closed issues.)

## CLI

The same operations are available from a terminal:

```bash
never-again search "asyncpg cannot determine parameter type"
never-again log        # interactive prompt
never-again verify <id>
never-again health     # show config and whether Ollama is reachable
```

## Optional upgrades

Everything below is off by default. Configuration is read from environment
variables. There are two ways to set them:

**In your MCP client's config (recommended).** This is where MCP server settings
belong — the client passes them straight to the server, regardless of which
project your agent is working in:

```json
{
  "mcpServers": {
    "never-again": {
      "command": "never-again-mcp",
      "env": { "NEVER_AGAIN_EMBEDDER": "local" }
    }
  }
}
```

**With a `.env` file.** Copy [`.env.example`](.env.example) to `.env` and edit
it. This is handy for the CLI and local development. Note that the MCP server is
launched by your agent's client, not from your project folder, so a bare `.env`
sitting in a project directory will **not** be picked up by the server. To use a
file with the MCP server, point at it with an absolute path:

```json
{ "env": { "NEVER_AGAIN_ENV_FILE": "/home/you/.never-again/.env" } }
```

Either way, real environment variables always take precedence over the file.

The base install matches errors by keyword (SQLite FTS5). That catches errors phrased similarly to a past one. To also match errors that mean the same thing but are worded differently, turn on semantic search:

```bash
pip install "never-again[local]"
```

```
NEVER_AGAIN_EMBEDDER=local
```

`local` runs an embedding model in-process via `fastembed` — still no server, nothing leaves the machine. If you already run [Ollama](https://ollama.com/), `ollama` uses it for embeddings instead.

| Variable                     | Default              | Purpose                                                               |
| ---------------------------- | -------------------- | --------------------------------------------------------------------- |
| `NEVER_AGAIN_EMBEDDER`     | `fts`              | `local`(in-process semantic search) or`ollama`                    |
| `NEVER_AGAIN_LOCAL_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model used by `local` semantic search              |
| `NEVER_AGAIN_EMBED_DIMENSION` | *unset*          | optional Postgres vector dimension for indexed team search             |
| `NEVER_AGAIN_COSINE_FLOOR` | `0.45`             | min similarity to count as a match (semantic path)                    |
| `NEVER_AGAIN_TEAM`         | `local`            | your team slug, when sharing                                          |
| `NEVER_AGAIN_URL`          | *unset*            | a team server URL; when set, tools talk to it instead of local SQLite |
| `OLLAMA_EMBED_MODEL`       | `nomic-embed-text` | any Ollama embedding model                                            |

### Team sharing

To share failures across a team, run the included server (FastAPI + Postgres with pgvector) and point clients at it with `NEVER_AGAIN_URL`. The deployment files are in `deploy/` — see `deploy/docker-compose.yml`.

The initial Postgres schema accepts vectors from any supported embedder. Once a
team has standardized on one embedding model, add a dimension-specific pgvector
ANN index using `deploy/vector_index_templates.sql` and set
`NEVER_AGAIN_EMBED_DIMENSION` to the same dimension so queries use it.

## How it works

Each error is fingerprinted — paths, numbers, hex, and UUIDs are normalized away — so the same error logged twice is deduplicated rather than stored twice. Search blends keyword ranking (FTS) with optional semantic ranking using Reciprocal Rank Fusion, then drops anything below a relevance floor so weak matches are filtered out instead of returned. Each entry carries a `WHEN / CHECK / BECAUSE` prevention rule, written by the agent that logged the failure (or formatted from the recorded fix when none is supplied, such as from the CLI).

## Tiers at a glance

| Tier           | Install                               | What you get                               |
| -------------- | ------------------------------------- | ------------------------------------------ |
| Base           | `pip install never-again`           | SQLite + keyword search, zero dependencies |
| Local semantic | `pip install "never-again[local]"`  | in-process embeddings via fastembed        |
| Ollama         | `pip install "never-again[ollama]"` | semantic embeddings via a running Ollama   |
| Team           | see`deploy/`                        | shared Postgres + pgvector across a team   |

## Development

```bash
pip install -e ".[local]"
pip install pytest pytest-asyncio fastapi httpx mcp
pytest
never-again-eval
```

The test suite is fully mocked — no network, no real embedding models, no external services.
`never-again-eval` runs the curated retrieval benchmark in
`never_again/evals/`. The corpus is made of anonymized observed development
failures plus hard negatives. Use `never-again-eval --check` when you want
threshold gating in CI.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup
and the design principles to keep in mind, and [ARCHITECTURE.md](ARCHITECTURE.md)
for how the pieces fit together and why. The most-wanted improvements are better
cold-start seeding and an eval harness; both are described there.

Release notes live in [CHANGELOG.md](CHANGELOG.md).

## License

[Apache-2.0](LICENSE)
