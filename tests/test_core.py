"""Pure-function core tests: fingerprint, anonymize, RRF fusion, rules.
No I/O, no mocks needed — these are deterministic transformations."""
from __future__ import annotations

import pytest

from never_again.core.fingerprint import fingerprint, normalize
from never_again.core.anonymize import anonymize
from never_again.core.retrieval import fuse
from never_again.core.models import Failure
from never_again.rules.verbatim import VerbatimRules


# ---------------- fingerprint ----------------
def test_normalize_strips_volatile_bits():
    out = normalize("Error at 0xDEADBEEF in /home/alice/app.py line 42")
    assert "<hex>" in out and "<path>" in out and "<n>" in out
    assert "0xdeadbeef" not in out


def test_fingerprint_stable_across_incidentals():
    # same error, different line numbers / paths / addresses -> same fingerprint
    a = fingerprint("KeyError: 'foo' at /a/b.py line 10 addr 0x1")
    b = fingerprint("KeyError: 'foo' at /x/y.py line 99 addr 0xff")
    assert a == b


def test_fingerprint_distinguishes_real_differences():
    a = fingerprint("KeyError: 'foo'")
    b = fingerprint("KeyError: 'bar'")
    assert a != b


def test_fingerprint_is_short_hex():
    fp = fingerprint("anything")
    assert len(fp) == 16 and all(c in "0123456789abcdef" for c in fp)


# ---------------- anonymize ----------------
def test_anonymize_redacts_email():
    assert "<email>" in anonymize("contact alice@example.com for help")
    assert "alice@example.com" not in anonymize("alice@example.com")


def test_anonymize_redacts_connstring_password():
    out = anonymize("postgres://user:s3cr3t@localhost:5432/db")
    assert "s3cr3t" not in out and "<redacted>" in out


def test_anonymize_redacts_tokens():
    for secret in ["sk-abcdefghijklmnopqrstuvwx",
                   "ghp_abcdefghijklmnopqrstuvwxyz12",
                   "AKIA1234567890ABCDEF"]:
        assert "<token>" in anonymize(f"key is {secret}")
        assert secret not in anonymize(f"key is {secret}")


def test_anonymize_redacts_home_username():
    assert "<user>" in anonymize("/home/alice/project/main.py")
    assert "alice" not in anonymize("/home/alice/x")


def test_anonymize_leaves_clean_text_untouched():
    clean = "TypeError: unsupported operand type for +: int and str"
    assert anonymize(clean) == clean


def test_anonymize_handles_empty():
    assert anonymize("") == ""


# ---------------- RRF fusion ----------------
def test_fuse_empty_returns_empty():
    assert fuse([], []) == []


def test_fuse_single_list_orders_by_rank():
    out = fuse(["a", "b", "c"])
    ids = [i for i, _ in out]
    assert ids == ["a", "b", "c"]


def test_fuse_rewards_agreement():
    # 'x' is top in both lists -> should win overall
    out = fuse(["x", "y", "z"], ["x", "w", "v"])
    assert out[0][0] == "x"


def test_fuse_scores_normalized_0_to_1():
    out = fuse(["a", "b"], ["a", "c"])
    assert all(0.0 <= s <= 1.0 for _, s in out)
    # 'a' is rank-0 in both non-empty lists -> max normalized score 1.0
    assert out[0][0] == "a"
    assert out[0][1] == pytest.approx(1.0)


def test_fuse_ignores_empty_lists_in_normalization():
    # one empty list shouldn't change the best-possible denominator
    out = fuse(["a", "b"], [])
    assert out[0][1] == pytest.approx(1.0)


# ---------------- verbatim rules ----------------
@pytest.mark.asyncio
async def test_verbatim_rule_format():
    r = VerbatimRules()
    f = Failure(error="boom", solution="do x", context="because y")
    out = await r.generate(f)
    assert "WHEN: boom" in out and "CHECK: do x" in out and "BECAUSE: because y" in out


@pytest.mark.asyncio
async def test_verbatim_rule_omits_empty_fields():
    r = VerbatimRules()
    out = await r.generate(Failure(error="boom"))
    assert "WHEN: boom" in out
    assert "CHECK:" not in out and "BECAUSE:" not in out


# ---------------- .env loading ----------------
def test_dotenv_loads_and_real_env_wins(tmp_path, monkeypatch):
    import os
    from never_again.config import load

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "NEVER_AGAIN_EMBEDDER=ollama\n"
        "export NEVER_AGAIN_COSINE_FLOOR=0.55\n"
        'OLLAMA_EMBED_MODEL="nomic-embed-text"\n'
    )
    monkeypatch.setenv("NEVER_AGAIN_ENV_FILE", str(env_file))
    # a real env var must override the file
    monkeypatch.setenv("NEVER_AGAIN_EMBEDDER", "fts")
    # make sure these are not already set in the real environment
    monkeypatch.delenv("NEVER_AGAIN_COSINE_FLOOR", raising=False)
    monkeypatch.delenv("OLLAMA_EMBED_MODEL", raising=False)

    s = load()
    assert s.cosine_floor == 0.55                      # from file, export-prefixed
    assert s.ollama_embed_model == "nomic-embed-text"  # from file, quotes stripped
    assert s.embedder == "fts"                         # real env wins over file


def test_dotenv_missing_file_is_fine(tmp_path, monkeypatch):
    from never_again.config import load
    monkeypatch.setenv("NEVER_AGAIN_ENV_FILE", str(tmp_path / "does-not-exist.env"))
    monkeypatch.delenv("NEVER_AGAIN_EMBEDDER", raising=False)
    assert load().embedder == "fts"       # falls back to defaults
