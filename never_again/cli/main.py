from __future__ import annotations

import argparse
import asyncio

import httpx

from never_again.config import load, Settings
from never_again.engine import Engine


async def do_search(engine: Engine, query: str, limit: int) -> None:
    results = await engine.query(query, limit=limit)
    if not results:
        print("No matching failures found.")
        return

    print(format_header(len(results)))
    for i, hit in enumerate(results, 1):
        f = hit.failure
        if f.id is None:
            print(f"{i}. [unknown] {f.error}")
        else:
            print(f"{i}. [{f.id[:8]}] {f.error}")
        print(f"   Solution: {f.solution}")
        if f.rule:
            print(f"   Rule: {f.rule}")
        print(f"   Score: {hit.score:.3f}")
        print("-" * 40)


def format_header(count: int) -> str:
    return f"\nFound {count} results:\n" + "=" * 40


async def do_log(engine: Engine) -> None:
    print("Logging a new failure...")
    error = input("Error message: ").strip()
    if not error:
        print("Error message is required.")
        return
    solution = input("Solution/Resolution: ").strip()
    context = input("Context (optional): ").strip()
    scope = input("Scope (local/public) [local]: ").strip() or "local"

    try:
        failure = await engine.log(error, solution, context, scope=scope)
        print(f"\nSuccessfully logged failure! ID: {failure.id}")
        if failure.rule:
            print(f"Generated rule: {failure.rule}")
    except Exception as e:
        print(f"Error logging failure: {e}")


async def do_verify(engine: Engine, failure_id: str) -> None:
    try:
        success = await engine.verify(failure_id)
        if success:
            print(f"Failure {failure_id} marked as verified.")
        else:
            print(f"No failure found with id {failure_id}.")
    except Exception as e:
        print(f"Error verifying failure: {e}")


async def do_health(settings: Settings) -> None:
    print("Performing health check...")
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            if resp.status_code == 200:
                ollama_ok = True
    except Exception:
        pass

    print("-" * 40)
    print(f"Store type:    {settings.store}")
    print(f"Embedder type: {settings.embedder}")
    print(f"DB path:       {settings.db}")
    print(f"Ollama status: {'OK' if ollama_ok else 'UNREACHABLE'}")
    print("-" * 40)


def main() -> None:
    parser = argparse.ArgumentParser(description="never-again CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Search command
    search_p = subparsers.add_parser("search", help="Search for past failures")
    search_p.add_argument("query", help="The search query")
    search_p.add_argument("--limit", type=int, default=5, help="Number of results to return")

    # Log command
    subparsers.add_parser("log", help="Log a new failure interactively")

    # Verify command
    verify_p = subparsers.add_parser("verify", help="Verify a resolution")
    verify_p.add_argument("id", help="The ID of the failure to verify")

    # Health command
    subparsers.add_parser("health", help="Check system health")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    settings = load()
    engine = Engine.from_settings(settings)

    try:
        async def run_cmd():
            if args.command == "search":
                await do_search(engine, args.query, args.limit)
            elif args.command == "log":
                await do_log(engine)
            elif args.command == "verify":
                await do_verify(engine, args.id)
            elif args.command == "health":
                await do_health(settings)

        asyncio.run(run_cmd())
    except KeyboardInterrupt:
        print("\nAborted by user.")
    finally:
        asyncio.run(engine.close())


if __name__ == "__main__":
    main()