"""
test_golden_rust.py — Round-trip golden test for Rust injection.

Doubles as a regression guard for the Rust extraction bug: the Rust parser
used to pass ``source_code=None``, which violated the (required) schema field
and made every Rust function silently fail to parse — so the parser returned an
empty list. These tests assert that Rust functions are extracted with a
non-empty ``source_code`` and that injecting doc comments keeps the file valid.

Offline and deterministic — the LLM is a FakeProvider.
"""
from __future__ import annotations

from codedoc_ai import injector
from codedoc_ai.router import detect_and_parse
from codedoc_ai.safety import syntax_ok

SAMPLE = (
    "fn add(a: i32, b: i32) -> i32 {\n"
    "    a + b\n"
    "}\n"
    "\n"
    "fn sub(a: i32, b: i32) -> i32 {\n"
    "    a - b\n"
    "}\n"
)


class FakeProvider:
    name = "fake"

    def generate_doc(self, func) -> str:
        return "Documented by the test."

    def summarize_file(self, file_path, functions, source_code=None) -> str:
        return "# summary"


def _write_sample(tmp_path):
    src = tmp_path / "lib.rs"
    src.write_text(SAMPLE, encoding="utf-8", newline="")
    return src


def test_rust_functions_are_extracted_with_source(tmp_path):
    """Regression guard: Rust parsing must not silently return []."""
    src = _write_sample(tmp_path)
    funcs = detect_and_parse(src)

    assert len(funcs) == 2
    names = {f.name for f in funcs}
    assert names == {"add", "sub"}
    for f in funcs:
        assert isinstance(f.source_code, str)
        assert f.source_code.strip() != ""


def test_rust_injection_round_trip(tmp_path, monkeypatch):
    src = _write_sample(tmp_path)
    monkeypatch.setattr(injector, "get_provider", lambda name=None: FakeProvider())

    result = injector.inject_docstrings(src, dry_run=False, backup=False)

    assert result["aborted"] is False
    assert result["injected"] == 2

    text = src.read_text(encoding="utf-8")
    # Rust doc-comment marker present.
    assert "///" in text
    # Still parses cleanly and keeps both functions.
    ok, reason = syntax_ok(text, "rust")
    assert ok is True, reason
    assert len(detect_and_parse(src)) == 2
