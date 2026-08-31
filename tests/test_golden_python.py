"""
test_golden_python.py — Round-trip golden test for Python injection.

Verifies that injecting docstrings into a known-good Python file:
  * inserts the expected number of doc blocks,
  * leaves the result parseable,
  * preserves the number of functions (structural invariant),
  * is idempotent (a second run documents nothing new),
  * and, in dry-run mode, does not touch the file on disk.

Offline and deterministic — the LLM is a FakeProvider.
"""
from __future__ import annotations

import ast

from codedoc_ai import injector
from codedoc_ai.router import detect_and_parse

SAMPLE = (
    "def alpha(x):\n"
    "    return x + 1\n"
    "\n"
    "\n"
    "def beta(y):\n"
    "    return y * 2\n"
)


class FakeProvider:
    name = "fake"

    def generate_doc(self, func) -> str:
        return "Documented by the test.\n\nReturns:\n    A value."

    def summarize_file(self, file_path, functions, source_code=None) -> str:
        return "# summary"


def _write_sample(tmp_path):
    src = tmp_path / "mod.py"
    src.write_text(SAMPLE, encoding="utf-8", newline="")
    return src


def test_python_injection_round_trip(tmp_path, monkeypatch):
    src = _write_sample(tmp_path)
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    # Two functions to start with.
    assert len(detect_and_parse(src)) == 2

    result = injector.inject_docstrings(src, dry_run=False, backup=False)

    assert result["aborted"] is False
    assert result["injected"] == 2
    assert result["skipped"] == 0

    text = src.read_text(encoding="utf-8")
    # Still valid Python.
    ast.parse(text)
    # Structural invariant preserved.
    assert len(detect_and_parse(src)) == 2
    # The doc text actually landed in the file.
    assert "Documented by the test." in text


def test_python_injection_is_idempotent(tmp_path, monkeypatch):
    src = _write_sample(tmp_path)
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    injector.inject_docstrings(src, dry_run=False, backup=False)
    after_first = src.read_bytes()

    # Second run: both functions already documented -> nothing new, no change.
    second = injector.inject_docstrings(src, dry_run=False, backup=False)
    assert second["injected"] == 0
    assert second["skipped"] == 2
    assert src.read_bytes() == after_first


def test_python_dry_run_leaves_file_unchanged(tmp_path, monkeypatch):
    src = _write_sample(tmp_path)
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())
    original_bytes = src.read_bytes()

    result = injector.inject_docstrings(src, dry_run=True, backup=False)

    assert result["injected"] == 2
    assert src.read_bytes() == original_bytes
