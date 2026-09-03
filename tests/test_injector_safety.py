"""
test_injector_safety.py — Proves the docstring injector is fail-closed.

The injector modifies real source files, so the contract under test is:
if the proposed result would not parse, or would change the number of
functions, the injector writes NOTHING and leaves the original file exactly
as it was.

These tests are fully offline and deterministic: the LLM is replaced with a
FakeProvider, so no API keys, network, or paid calls are needed.
"""
from __future__ import annotations

import ast

import pytest

from codedoc_ai import injector
from codedoc_ai.safety import (
    count_functions_in_text,
    syntax_ok,
    validate_modification,
)


class FakeProvider:
    """Offline stand-in for an LLM provider — returns fixed, valid doc text."""

    name = "fake"

    def generate_doc(self, func) -> str:
        return "Fake docstring for testing.\n\nReturns:\n    Nothing."

    def summarize_file(self, file_path, functions, source_code=None) -> str:
        return "# Fake summary"


# ---------------------------------------------------------------------------
# Unit tests for the validation primitives
# ---------------------------------------------------------------------------

def test_syntax_ok_accepts_valid_python():
    ok, reason = syntax_ok("def foo():\n    return 1\n", "py")
    assert ok is True
    assert reason == ""


def test_syntax_ok_rejects_broken_python():
    ok, reason = syntax_ok("def foo(:\n    return 1\n", "py")
    assert ok is False
    assert "syntax" in reason.lower()


def test_count_functions_matches_parser():
    text = "def a():\n    return 1\ndef b():\n    return 2\n"
    assert count_functions_in_text(text, "py", ".py") == 2


def test_validate_accepts_safe_docstring_insertion():
    original = "def foo():\n    return 1\n"
    # A module-level string above the def: still parses, still one function.
    modified = '"""Docs for foo."""\ndef foo():\n    return 1\n'
    ok, reason = validate_modification(original, modified, "py", ".py", 1)
    assert ok is True
    assert reason == ""


def test_validate_rejects_syntax_break():
    original = "def foo():\n    return 1\n"
    broken = "def foo(:\n    return 1\n"
    ok, reason = validate_modification(original, broken, "py", ".py", 1)
    assert ok is False
    assert "syntax" in reason.lower()


def test_validate_rejects_function_count_change():
    original = "def foo():\n    return 1\n"
    # Valid Python, but now two functions instead of one.
    modified = "def foo():\n    return 1\ndef bar():\n    return 2\n"
    ok, reason = validate_modification(original, modified, "py", ".py", 1)
    assert ok is False
    assert "structural" in reason.lower() or "function count" in reason.lower()


# ---------------------------------------------------------------------------
# End-to-end: the injector refuses to write corrupting output
# ---------------------------------------------------------------------------

def test_injector_aborts_when_formatted_block_is_garbage(tmp_path, monkeypatch):
    """If formatting yields syntactically invalid text, the file is untouched."""
    src = tmp_path / "sample.py"
    original = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
    src.write_text(original, encoding="utf-8", newline="")
    original_bytes = src.read_bytes()

    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())
    # Force the inserted block to be invalid Python regardless of the provider.
    monkeypatch.setattr(
        injector, "format_docstring", lambda lang, raw, indent: "@@@ not valid python @@@"
    )

    result = injector.inject_docstrings(src, dry_run=False, backup=True)

    assert result["aborted"] is True
    assert "syntax" in result.get("reason", "").lower()
    # The original file must be byte-for-byte unchanged.
    assert src.read_bytes() == original_bytes
    # No backup and no orphaned temp file may be left behind on abort.
    assert not (tmp_path / "sample.py.bak").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_injector_aborts_on_decorated_function_placement(tmp_path, monkeypatch):
    """
    Realistic placement bug: the injector inserts the doc block above the
    ``def`` line, which for a decorated function lands *between* the decorator
    and the def and breaks syntax. Using the REAL formatter, the fail-closed
    gate must still catch this and leave the file untouched.
    """
    src = tmp_path / "decorated.py"
    original = "import functools\n\n\n@functools.cache\ndef fib(n):\n    return n\n"
    src.write_text(original, encoding="utf-8", newline="")
    original_bytes = src.read_bytes()

    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    result = injector.inject_docstrings(src, dry_run=False, backup=True)

    assert result["aborted"] is True
    assert src.read_bytes() == original_bytes
    assert not (tmp_path / "decorated.py.bak").exists()


def test_dry_run_never_writes(tmp_path, monkeypatch):
    """A dry run (the default) previews but must not modify the file."""
    src = tmp_path / "sample.py"
    original = "def alpha():\n    return 1\n"
    src.write_text(original, encoding="utf-8", newline="")
    original_bytes = src.read_bytes()

    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    result = injector.inject_docstrings(src, dry_run=True, backup=True)

    assert result["aborted"] is False
    assert result["injected"] == 1
    assert src.read_bytes() == original_bytes  # unchanged
    assert not (tmp_path / "sample.py.bak").exists()


# ---------------------------------------------------------------------------
# Fail-fast: an unparseable input must not reach the LLM
# ---------------------------------------------------------------------------

class ExplodingProvider:
    """Fails the test if the injector asks it to generate anything."""

    name = "exploding"

    def __init__(self):
        self.calls = []

    def generate_doc(self, func) -> str:
        self.calls.append(func.name)
        raise AssertionError(
            "generate_doc was called for a file that can never be written"
        )

    def summarize_file(self, file_path, functions, source_code=None) -> str:
        return ""


def test_unparseable_input_aborts_without_calling_the_llm(tmp_path, monkeypatch):
    """
    A .ts file is routed to the JavaScript grammar, which cannot parse type
    annotations, so the fail-closed gate is guaranteed to refuse the write.
    Discovering that *after* generating docstrings costs real API spend, so the
    check must happen before any provider call.
    """
    # An untyped function (so at least one IS discovered, and we reach the
    # syntax gate rather than the earlier "no functions found" exit) alongside
    # a typed one that the JavaScript grammar cannot parse.
    src = tmp_path / "typed.ts"
    src.write_text(
        "export function makeId() {\n"
        "  return 1;\n"
        "}\n"
        "\n"
        "export function classify(status: number): number {\n"
        "  return status;\n"
        "}\n",
        encoding="utf-8",
        newline="",
    )
    before = src.read_bytes()

    provider = ExplodingProvider()
    monkeypatch.setattr(injector, "get_provider", lambda name=None: provider)

    result = injector.inject_docstrings(src, dry_run=False)

    assert result["aborted"] is True
    assert result["injected"] == 0
    assert provider.calls == []           # the LLM was never invoked
    assert src.read_bytes() == before     # byte-for-byte unchanged


def test_abort_reason_names_the_grammar(tmp_path, monkeypatch):
    """The message must point at the real cause, not imply we corrupted the file."""
    src = tmp_path / "typed.ts"
    src.write_text(
        "export function makeId() {\n"
        "  return 1;\n"
        "}\n"
        "\n"
        "export function f(a: number): number {\n"
        "  return a;\n"
        "}\n",
        encoding="utf-8",
        newline="",
    )
    monkeypatch.setattr(injector, "get_provider", lambda name=None: ExplodingProvider())

    reason = injector.inject_docstrings(src, dry_run=False)["reason"]

    assert "does not parse" in reason
    assert "ts" in reason
    # Must NOT blame the modification — nothing was modified.
    assert "modified source" not in reason
