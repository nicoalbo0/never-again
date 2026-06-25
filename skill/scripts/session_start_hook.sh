#!/usr/bin/env bash
# never-again — SessionStart hook.
#
# Surfaces known failures relevant to this project's stack so the agent sees them
# before writing any code. Whatever this prints to stdout is injected into Claude's
# context at session start.
#
# Designed to FAIL SILENT: if the CLI is missing, the stack is unknown, or anything
# errors, it prints nothing and exits 0. A session-start hook must never block or
# slow down a session.

# Claude Code sends a JSON payload on stdin that we don't need here — drain it so
# the writing end never gets a broken pipe.
cat >/dev/null 2>&1 || true

# If the CLI isn't on PATH, do nothing. (Install it where Claude Code can reach it:
# `uv tool install never-again` or `pipx install never-again` for a global command.)
command -v never-again >/dev/null 2>&1 || exit 0

dir="${CLAUDE_PROJECT_DIR:-$PWD}"

# Detect the stack from marker files — cheap, no parsing. Each match adds search
# terms; the CLI ORs them together when querying.
terms=""
{ [ -f "$dir/pyproject.toml" ] || [ -f "$dir/requirements.txt" ]; }      && terms="$terms python"
[ -f "$dir/package.json" ]                                                && terms="$terms javascript typescript node"
[ -f "$dir/go.mod" ]                                                      && terms="$terms go"
[ -f "$dir/Cargo.toml" ]                                                  && terms="$terms rust"
{ [ -f "$dir/Dockerfile" ] || [ -f "$dir/docker-compose.yml" ]; }         && terms="$terms docker"

# Nothing recognised — stay quiet.
[ -n "${terms// /}" ] || exit 0

# Query for known failures. Suppress errors; never let a failure here surface.
results="$(never-again search "$terms" --limit 5 2>/dev/null)" || exit 0
[ -n "$results" ] || exit 0
case "$results" in *"No matching failures"*) exit 0 ;; esac

# Frame the injected text so the agent knows what it is and what to do with it.
echo "never-again: known failures relevant to this project's stack (${terms# }):"
echo "Review these before starting. The moment any error appears, call query_failures."
echo
echo "$results"