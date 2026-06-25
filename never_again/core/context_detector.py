"""Auto-detect active technologies in the project directory."""
from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path

def detect_tech_stack(cwd: str | Path | None = None) -> list[str]:
    """Scan the workspace directory to build a tag list of active technologies.

    Cached per directory: the stack doesn't change mid-session, and this runs on
    the hot path of every log and query, so we don't want to re-read marker files
    each time.
    """
    if cwd is None:
        try:
            cwd = Path.cwd()
        except Exception:
            return []
    return list(_detect_cached(str(Path(cwd))))


@lru_cache(maxsize=32)
def _detect_cached(cwd_str: str) -> tuple[str, ...]:
    cwd = Path(cwd_str)

    stack = []
    
    # 1. Broad file/directory existence checks
    signatures = {
        "package.json": "Node.js",
        "tsconfig.json": "TypeScript",
        "pyproject.toml": "Python",
        "requirements.txt": "Python",
        "setup.py": "Python",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "Gemfile": "Ruby",
        "composer.json": "PHP",
        "pom.xml": "Java",
        "build.gradle": "Java",
        "Dockerfile": "Docker",
        "docker-compose.yml": "Docker",
        "Makefile": "Makefile",
        ".git": "Git",
        "CMakeLists.txt": "C++",
    }
    
    for filename, tech in signatures.items():
        try:
            if (cwd / filename).exists():
                if tech not in stack:
                    stack.append(tech)
        except Exception:
            continue
            
    # 2. Deeper dependency scanning to identify frameworks and databases
    # Node dependencies
    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Simple regex checks to avoid parsing JSON if malformed
                frameworks = {
                    r'"react"': "React",
                    r'"vue"': "Vue",
                    r'"next"': "Next.js",
                    r'"express"': "Express",
                    r'"nestjs"': "NestJS",
                    r'"svelte"': "Svelte",
                    r'"pg"': "PostgreSQL",
                    r'"mysql"': "MySQL",
                    r'"mongodb"': "MongoDB",
                    r'"sqlite3"': "SQLite",
                    r'"prisma"': "Prisma",
                    r'"mongoose"': "Mongoose",
                }
                for pattern, name in frameworks.items():
                    if re.search(pattern, content):
                        if name not in stack:
                            stack.append(name)
        except Exception:
            pass

    # Python dependencies
    py_files = ["requirements.txt", "pyproject.toml"]
    py_content = ""
    for py_file in py_files:
        p = cwd / py_file
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    py_content += f.read() + "\n"
            except Exception:
                pass
                
    if py_content:
        py_frameworks = {
            r"\bfastapi\b": "FastAPI",
            r"\bdjango\b": "Django",
            r"\bflask\b": "Flask",
            r"\bsqlalchemy\b": "SQLAlchemy",
            r"\balembic\b": "Alembic",
            r"\basyncpg\b": "PostgreSQL",
            r"\bpsycopg\b": "PostgreSQL",
            r"\baiosqlite\b": "SQLite",
            r"\bpydantic\b": "Pydantic",
            r"\bcelery\b": "Celery",
            r"\bpandapower\b|\bpandas\b": "Pandas",
            r"\bnumpy\b": "NumPy",
            r"\btensorflow\b|\btorch\b": "MachineLearning",
        }
        for pattern, name in py_frameworks.items():
            if re.search(pattern, py_content, re.IGNORECASE):
                if name not in stack:
                    stack.append(name)

    return tuple(sorted(stack))
