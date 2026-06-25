"""Runtime configuration, read once from environment variables.

Configuration comes from environment variables. When run as an MCP server, the
agent's client supplies these via its config's `env` block; from the CLI, they
come from the shell. As a convenience for the CLI and local development, a
`.env` file in the current directory (or one named by NEVER_AGAIN_ENV_FILE) is
also read — but real environment variables always win, so an MCP client's `env`
block is never overridden by a stray file.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = Path.home() / ".never-again" / "failures.db"


def _load_dotenv() -> None:
    """Read KEY=value lines from a .env file into os.environ, without overriding.

    Deliberately tiny and dependency-free: supports `KEY=value`, `#` comments,
    blank lines, `export KEY=value`, and optional surrounding quotes. Anything
    already set in the real environment is left untouched.
    """
    path = Path(os.getenv("NEVER_AGAIN_ENV_FILE", ".env"))
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return  # no file, unreadable, or not a regular file — silently skip
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    store: str = "sqlite"
    db: str = str(DEFAULT_DB)
    embedder: str = "fts"
    team: str = "local"
    server_url: str | None = None
    ollama_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    # Relevance floor: drop hits below this bar so the system abstains instead
    # of returning a confident wrong match. cosine_floor gates the semantic path
    # (when embeddings are on); fused_floor gates the keyword-only path.
    cosine_floor: float = 0.45
    fused_floor: float = 0.10


def load() -> Settings:
    _load_dotenv()
    return Settings(
        store=os.getenv("NEVER_AGAIN_STORE", "sqlite"),
        db=os.getenv("NEVER_AGAIN_DB", str(DEFAULT_DB)),
        embedder=os.getenv("NEVER_AGAIN_EMBEDDER", "fts"),
        team=os.getenv("NEVER_AGAIN_TEAM", "local"),
        server_url=os.getenv("NEVER_AGAIN_URL"),
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        ollama_embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        cosine_floor=float(os.getenv("NEVER_AGAIN_COSINE_FLOOR", "0.45")),
        fused_floor=float(os.getenv("NEVER_AGAIN_FUSED_FLOOR", "0.10")),
    )