"""
test_golden_tree_sitter.py — Round-trip golden tests for the Tree-sitter languages.

Java, JavaScript, Go and C++ were previously only smoke-tested at the parser
level: nothing proved that ``inject`` actually completed for them, so the README
could only claim they were "safety-gated". These tests close that gap. For each
language a known-good sample is injected end to end and the result must:

  * report ``aborted = False`` and document both functions,
  * contain the language's native doc-comment syntax,
  * still parse cleanly, and
  * still contain exactly two functions (structural invariant).

``test_typescript_injection_aborts_fail_closed`` is the counterpart: it pins the
documented TypeScript limitation in place rather than leaving it to prose.

Offline and deterministic — the LLM is a FakeProvider.
"""
from __future__ import annotations

import pytest

from codedoc_ai import injector
from codedoc_ai.router import detect_and_parse
from codedoc_ai.safety import syntax_ok

DOC_TEXT = "Documented by the test."

JAVA = (
    "public class Calc {\n"
    "    public int add(int a, int b) {\n"
    "        return a + b;\n"
    "    }\n"
    "\n"
    "    public int sub(int a, int b) {\n"
    "        return a - b;\n"
    "    }\n"
    "}\n"
)

JS = (
    "function add(a, b) {\n"
    "  return a + b;\n"
    "}\n"
    "\n"
    "function sub(a, b) {\n"
    "  return a - b;\n"
    "}\n"
)

GO = (
    "package main\n"
    "\n"
    "func Add(a int, b int) int {\n"
    "\treturn a + b\n"
    "}\n"
    "\n"
    "func Sub(a int, b int) int {\n"
    "\treturn a - b\n"
    "}\n"
)

CPP = (
    "int add(int a, int b) {\n"
    "    return a + b;\n"
    "}\n"
    "\n"
    "int sub(int a, int b) {\n"
    "    return a - b;\n"
    "}\n"
)

# TypeScript with type annotations: routed to the *JavaScript* grammar, which
# cannot parse it (see test_typescript_injection_aborts_fail_closed).
TS = (
    "function add(a: number, b: number): number {\n"
    "  return a + b;\n"
    "}\n"
    "\n"
    "function dist(x: number, y: number): number {\n"
    "  return Math.abs(x - y);\n"
    "}\n"
)

# (filename, source, lang key for syntax_ok, expected first line of the doc block)
CASES = [
    pytest.param("Calc.java", JAVA, "java", f" * {DOC_TEXT}", id="java"),
    pytest.param("calc.js", JS, "js", f" * {DOC_TEXT}", id="javascript"),
    pytest.param("main.go", GO, "go", f"// {DOC_TEXT}", id="go"),
    pytest.param("calc.cpp", CPP, "cpp", f" * {DOC_TEXT}", id="cpp"),
]


class FakeProvider:
    name = "fake"

    def generate_doc(self, func) -> str:
        return DOC_TEXT

    def summarize_file(self, file_path, functions, source_code=None) -> str:
        return "# summary"


def _write(tmp_path, filename, source):
    src = tmp_path / filename
    src.write_text(source, encoding="utf-8", newline="")
    return src


@pytest.mark.parametrize("filename,source,lang,expected_doc_line", CASES)
def test_injection_round_trip(
    tmp_path, monkeypatch, filename, source, lang, expected_doc_line
):
    src = _write(tmp_path, filename, source)
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    # Two functions to start with.
    assert len(detect_and_parse(src)) == 2

    result = injector.inject_docstrings(src, dry_run=False, backup=False)

    assert result["aborted"] is False, result.get("reason")
    assert result["injected"] == 2
    assert result["skipped"] == 0

    text = src.read_text(encoding="utf-8")
    # The doc block landed, in this language's native comment syntax.
    assert expected_doc_line in text
    # Still parses cleanly and keeps both functions.
    ok, reason = syntax_ok(text, lang)
    assert ok is True, reason
    assert len(detect_and_parse(src)) == 2


@pytest.mark.parametrize("filename,source,lang,expected_doc_line", CASES)
def test_dry_run_leaves_file_unchanged(
    tmp_path, monkeypatch, filename, source, lang, expected_doc_line
):
    src = _write(tmp_path, filename, source)
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())
    original_bytes = src.read_bytes()

    result = injector.inject_docstrings(src, dry_run=True, backup=False)

    assert result["injected"] == 2
    assert src.read_bytes() == original_bytes


def test_typescript_injection_aborts_fail_closed(tmp_path, monkeypatch):
    """
    Pins a known limitation: ``.ts``/``.tsx`` are routed to the JavaScript
    grammar (``tree-sitter-typescript`` is not a dependency), which reports a
    parse error on type annotations. Extraction still works because tree-sitter
    is error-tolerant, but the fail-closed gate refuses every write — so
    ``inject`` can never succeed on typed TypeScript.

    If ``tree-sitter-typescript`` is ever added, this test will fail. That is
    intentional: update the Supported Languages table in README.md at the same
    time so the documented coverage stays honest.
    """
    src = _write(tmp_path, "calc.ts", TS)
    original_bytes = src.read_bytes()
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    # Extraction works ...
    assert len(detect_and_parse(src)) == 2

    result = injector.inject_docstrings(src, dry_run=False, backup=False)

    # ... but nothing is written, and the original is byte-for-byte intact.
    assert result["aborted"] is True
    assert result["injected"] == 0
    assert src.read_bytes() == original_bytes
