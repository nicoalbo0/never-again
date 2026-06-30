"""Deterministic retrieval benchmark for recall, ranking, and abstention."""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from never_again.config import Settings
from never_again.engine import Engine


@dataclass(frozen=True)
class QueryResult:
    id: str
    text: str
    category: str
    expected: list[str]
    actual: list[str]
    hit_rank: int | None

    @property
    def is_positive(self) -> bool:
        return bool(self.expected)

    @property
    def matched(self) -> bool:
        return self.hit_rank is not None

    @property
    def false_positive(self) -> bool:
        return not self.is_positive and bool(self.actual)


@dataclass(frozen=True)
class BenchmarkSummary:
    total_queries: int
    positive_queries: int
    negative_queries: int
    recall_at_1: float
    recall_at_k: float
    mrr: float
    abstention_accuracy: float
    false_positive_rate: float


@dataclass(frozen=True)
class CategorySummary:
    queries: int
    positive_queries: int
    negative_queries: int
    recall_at_k: float | None
    mrr: float | None
    false_positive_rate: float


@dataclass(frozen=True)
class BenchmarkResult:
    metadata: dict[str, str | int | float]
    summary: BenchmarkSummary
    categories: dict[str, CategorySummary]
    queries: list[QueryResult]

    @property
    def recall(self) -> float:
        return self.summary.recall_at_k

    @property
    def false_positive_rate(self) -> float:
        return self.summary.false_positive_rate

    @property
    def total_positive(self) -> int:
        return self.summary.positive_queries

    @property
    def total_negative(self) -> int:
        return self.summary.negative_queries

    @property
    def positive_hits(self) -> int:
        return sum(1 for query in self.queries if query.is_positive and query.matched)

    @property
    def false_positives(self) -> int:
        return sum(1 for query in self.queries if query.false_positive)


def _first_expected_rank(actual: list[str], expected: set[str]) -> int | None:
    for idx, label in enumerate(actual, start=1):
        if label in expected:
            return idx
    return None


def _validate_corpus(data: dict) -> None:
    for item in data.get("failures", []):
        source = item.get("source")
        if not isinstance(source, dict) or not source.get("kind") or not source.get("where"):
            raise ValueError(
                f"Benchmark failure {item.get('id', '<missing id>')} "
                "must include source.kind and source.where provenance."
            )


def _summarize(queries: list[QueryResult], limit: int) -> BenchmarkSummary:
    positives = [query for query in queries if query.is_positive]
    negatives = [query for query in queries if not query.is_positive]
    recall_at_1 = (
        sum(1 for query in positives if query.hit_rank == 1) / len(positives)
        if positives else 1.0
    )
    recall_at_k = (
        sum(1 for query in positives if query.matched) / len(positives)
        if positives else 1.0
    )
    mrr = (
        sum(1.0 / query.hit_rank for query in positives if query.hit_rank) / len(positives)
        if positives else 1.0
    )
    false_positives = sum(1 for query in negatives if query.false_positive)
    abstentions = sum(1 for query in negatives if not query.actual)
    false_positive_rate = false_positives / len(negatives) if negatives else 0.0
    abstention_accuracy = abstentions / len(negatives) if negatives else 1.0
    return BenchmarkSummary(
        total_queries=len(queries),
        positive_queries=len(positives),
        negative_queries=len(negatives),
        recall_at_1=recall_at_1,
        recall_at_k=recall_at_k,
        mrr=mrr,
        abstention_accuracy=abstention_accuracy,
        false_positive_rate=false_positive_rate,
    )


def _summarize_category(queries: list[QueryResult]) -> CategorySummary:
    positives = [query for query in queries if query.is_positive]
    negatives = [query for query in queries if not query.is_positive]
    matched = sum(1 for query in positives if query.matched)
    reciprocal_rank_sum = sum(
        1.0 / query.hit_rank for query in positives if query.hit_rank
    )
    false_positives = sum(1 for query in negatives if query.false_positive)
    return CategorySummary(
        queries=len(queries),
        positive_queries=len(positives),
        negative_queries=len(negatives),
        recall_at_k=matched / len(positives) if positives else None,
        mrr=reciprocal_rank_sum / len(positives) if positives else None,
        false_positive_rate=false_positives / len(negatives) if negatives else 0.0,
    )


def _summarize_categories(queries: list[QueryResult]) -> dict[str, CategorySummary]:
    categories = sorted({query.category for query in queries})
    return {
        category: _summarize_category(
            [query for query in queries if query.category == category]
        )
        for category in categories
    }


async def run_benchmark(path: Path, settings: Settings, limit: int = 5) -> BenchmarkResult:
    """Seed benchmark failures, run fixed queries, and compute retrieval metrics."""
    data = json.loads(path.read_text(encoding="utf-8"))
    _validate_corpus(data)
    engine = Engine.from_settings(settings)
    label_by_id: dict[str, str] = {}
    query_results: list[QueryResult] = []
    try:
        for item in data["failures"]:
            failure = await engine.log(
                error=item["error"],
                solution=item.get("solution", ""),
                context=item.get("context", ""),
                scope="local",
                team=settings.team,
                rule=item.get("rule"),
            )
            label_by_id[failure.id or ""] = item["id"]

        for item in data["queries"]:
            expected = set(item.get("expected", []))
            hits = await engine.query(item["text"], team=settings.team, limit=limit)
            actual = [
                label_by_id[hit.failure.id or ""]
                for hit in hits
                if (hit.failure.id or "") in label_by_id
            ]
            query_results.append(
                QueryResult(
                    id=item["id"],
                    text=item["text"],
                    category=item.get("category", "uncategorized"),
                    expected=sorted(expected),
                    actual=actual,
                    hit_rank=_first_expected_rank(actual, expected),
                )
            )

        return BenchmarkResult(
            metadata={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "corpus": str(path),
                "embedder": settings.embedder,
                "limit": limit,
                "cosine_floor": settings.cosine_floor,
                "fused_floor": settings.fused_floor,
            },
            summary=_summarize(query_results, limit),
            categories=_summarize_categories(query_results),
            queries=query_results,
        )
    finally:
        await engine.close()


async def run_eval(path: Path, settings: Settings, limit: int = 5) -> BenchmarkResult:
    """Backward-compatible alias for older tests/imports."""
    return await run_benchmark(path, settings, limit=limit)


def _as_json(result: BenchmarkResult) -> str:
    return json.dumps(asdict(result), indent=2)


def _print_markdown(result: BenchmarkResult) -> None:
    s = result.summary
    limit = result.metadata["limit"]
    print("| Metric | Value |")
    print("|--------|------:|")
    print(f"| queries | {s.total_queries} |")
    print(f"| positive queries | {s.positive_queries} |")
    print(f"| negative queries | {s.negative_queries} |")
    print(f"| recall@1 | {s.recall_at_1:.3f} |")
    print(f"| recall@{limit} | {s.recall_at_k:.3f} |")
    print(f"| MRR | {s.mrr:.3f} |")
    print(f"| abstention accuracy | {s.abstention_accuracy:.3f} |")
    print(f"| false-positive rate | {s.false_positive_rate:.3f} |")

    print()
    print("| Category | Queries | Recall | MRR | False-positive rate |")
    print("|----------|--------:|-------:|----:|--------------------:|")
    for category, category_summary in result.categories.items():
        recall = (
            f"{category_summary.recall_at_k:.3f}"
            if category_summary.recall_at_k is not None else "-"
        )
        mrr = (
            f"{category_summary.mrr:.3f}"
            if category_summary.mrr is not None else "-"
        )
        print(
            f"| {category} | {category_summary.queries} | "
            f"{recall} | "
            f"{mrr} | "
            f"{category_summary.false_positive_rate:.3f} |"
        )

    misses = [q for q in result.queries if q.is_positive and not q.matched]
    false_positives = [q for q in result.queries if q.false_positive]
    if misses or false_positives:
        print()
        print("Failures:")
        for query in misses:
            print(f"- MISS {query.id}: expected {query.expected}, got {query.actual}")
        for query in false_positives:
            print(f"- FALSE_POSITIVE {query.id}: expected abstention, got {query.actual}")


async def _main_async(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="never-again-benchmark-") as tmp:
        settings = Settings(
            store="sqlite",
            db=str(Path(tmp) / "benchmark.db"),
            embedder=args.embedder,
            team="benchmark",
            cosine_floor=args.cosine_floor,
            fused_floor=args.fused_floor,
        )
        result = await run_benchmark(Path(args.path), settings, limit=args.limit)

    if args.json:
        output = _as_json(result)
        if args.output:
            Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(output)
    else:
        _print_markdown(result)

    failed = False
    if args.check and result.summary.recall_at_k < args.min_recall:
        print(f"FAIL: recall@{args.limit} below {args.min_recall:.3f}")
        failed = True
    if args.check and result.summary.false_positive_rate > args.max_false_positive_rate:
        print(
            "FAIL: false-positive rate above "
            f"{args.max_false_positive_rate:.3f}"
        )
        failed = True
    if args.check and result.summary.mrr < args.min_mrr:
        print(f"FAIL: MRR below {args.min_mrr:.3f}")
        failed = True
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark never-again retrieval quality."
    )
    default_cases = files("never_again.evals").joinpath("retrieval_cases.json")
    parser.add_argument("path", nargs="?", default=str(default_cases))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--embedder", choices=["fts", "local", "ollama"], default="fts")
    parser.add_argument("--cosine-floor", type=float, default=0.45)
    parser.add_argument("--fused-floor", type=float, default=0.10)
    parser.add_argument("--min-recall", type=float, default=0.85)
    parser.add_argument("--min-mrr", type=float, default=0.75)
    parser.add_argument("--max-false-positive-rate", type=float, default=0.05)
    parser.add_argument("--check", action="store_true", help="Exit non-zero when thresholds fail.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--output", help="Write JSON output to this path.")
    raise SystemExit(asyncio.run(_main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
