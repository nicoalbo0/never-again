# Retrieval Benchmark

This benchmark measures never-again's core retrieval contract on anonymized
real-usage cases: return the right prior failure when one exists, rank it highly,
and abstain when no stored failure matches.

## What It Measures

The harness seeds a temporary SQLite database from `retrieval_cases.json`, runs
fixed positive and negative queries, and reports:

- `recall@1`: positive queries where an expected failure is the top result.
- `recall@k`: positive queries where an expected failure appears within the top
  `k` results.
- `MRR`: mean reciprocal rank of the first expected result.
- `abstention accuracy`: negative queries that correctly returned no hits.
- `false-positive rate`: negative queries that returned any hit.
- category breakdowns for the same ranking/abstention metrics.

By default the command reports metrics and exits successfully. Use `--check` to
turn threshold gates on: `recall@5 >= 0.85`, `MRR >= 0.75`, and false-positive
rate `<= 0.05`.

## Why This Design

- **Deterministic and local**: no model calls, no network, no external services.
- **Observed-case corpus**: each stored failure has `source` metadata describing
  where it came from, such as an observed development session or a repo regression
  review. Do not add anonymous invented examples.
- **Positive and negative controls**: unrelated and near-unrelated queries are
  part of the corpus because abstention is as important as recall.
- **Ranking-aware**: recall alone can hide a relevant result buried under bad
  hits, so MRR and recall@1 are reported too.
- **Reviewable data**: failures and expected matches live in JSON, so changes to
  retrieval quality are visible as corpus and metric diffs.
- **Machine-readable output**: `--json` can be archived as a benchmark snapshot
  or compared in CI. This follows the same pattern as mature eval suites: fixed
  task data, a deterministic runner, explicit metrics, and reviewable outputs.

## Files

- `retrieval_cases.json`: seeded failures and fixed query expectations.
- `never_again/eval_harness.py`: benchmark runner behind `never-again-eval`.

## Run

```bash
never-again-eval
```

or from a checkout:

```bash
python -m never_again.eval_harness
```

For a snapshot:

```bash
never-again-eval --json --output benchmark.json
```

Use the snapshot to compare retrieval changes before and after a patch. The
human table is for quick inspection; the JSON output is the benchmark artifact.

For CI-style gating:

```bash
never-again-eval --check
```

## Adding Cases

Add both positive and negative cases. Every new stored failure must include a
`source` object with enough provenance for reviewers to understand why the case
is real. A useful positive case should represent a real repeated failure. A
useful negative case should be close enough to expose over-broad matching, not
just random unrelated text.

If a retrieval change intentionally shifts behavior, include the old and new
benchmark output in the PR so reviewers can see recall, rank, and abstention
tradeoffs.

## What This Does Not Measure

- **Semantic embedder quality by default**: the default command uses `fts` so it
  stays deterministic and dependency-free. Run `--embedder local` or
  `--embedder ollama` manually when tuning semantic retrieval.
- **Production distribution**: this is a curated benchmark built from observed
  development failures, not telemetry from real user databases. It should grow
  from real missed matches and false positives.
- **Multiple valid fixes**: each positive query currently names one expected id,
  though the runner supports multiple expected ids.
- **Statistical significance**: there is no sampling or repeated stochastic
  generation. Each case is a fixed regression/benchmark example.
