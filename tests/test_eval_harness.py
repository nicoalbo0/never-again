from __future__ import annotations

import json

import pytest

from never_again.config import Settings
from never_again.eval_harness import run_benchmark, run_eval


@pytest.mark.asyncio
async def test_benchmark_reports_ranking_and_abstention_metrics(tmp_path):
    cases = {
        "failures": [
            {
                "id": "asyncpg",
                "source": {"kind": "test", "where": "unit fixture"},
                "error": "asyncpg InterfaceError another operation in progress",
                "solution": "use a pool",
            }
        ],
        "queries": [
            {
                "id": "positive",
                "text": "asyncpg another operation in progress",
                "expected": ["asyncpg"],
            },
            {
                "id": "negative",
                "text": "rust borrow checker mutable reference",
                "expected": [],
            },
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")

    result = await run_benchmark(
        path,
        Settings(store="sqlite", db=str(tmp_path / "eval.db"), embedder="fts"),
    )

    assert result.total_positive == 1
    assert result.positive_hits == 1
    assert result.recall == 1.0
    assert result.summary.recall_at_1 == 1.0
    assert result.summary.mrr == 1.0
    assert result.summary.abstention_accuracy == 1.0
    assert result.false_positive_rate == 0.0
    assert result.categories["uncategorized"].queries == 2


@pytest.mark.asyncio
async def test_run_eval_alias_keeps_backward_compatibility(tmp_path):
    cases = {
        "failures": [
            {
                "id": "x",
                "source": {"kind": "test", "where": "unit fixture"},
                "error": "ValueError bad cast",
            }
        ],
        "queries": [{"id": "q", "text": "ValueError bad cast", "expected": ["x"]}],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")

    result = await run_eval(
        path,
        Settings(store="sqlite", db=str(tmp_path / "eval.db"), embedder="fts"),
    )

    assert result.summary.recall_at_k == 1.0


@pytest.mark.asyncio
async def test_benchmark_requires_failure_provenance(tmp_path):
    cases = {
        "failures": [{"id": "x", "error": "ValueError bad cast"}],
        "queries": [{"id": "q", "text": "ValueError bad cast", "expected": ["x"]}],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")

    with pytest.raises(ValueError, match="source.kind and source.where"):
        await run_benchmark(
            path,
            Settings(store="sqlite", db=str(tmp_path / "eval.db"), embedder="fts"),
        )
