"""
test_llm_artifact_stripping.py — Pins the cleanup of raw LLM responses.

Models wrap docstring text in markdown fences, triple quotes, or both, and
reasoning models can emit a ``<think>`` trace into the message body. None of
that is documentation: if it survives into ``format_docstring`` it ends up as
literal ``python`` / ``\"\"\"`` lines inside a Javadoc block, which is exactly
the corruption these tests exist to prevent.

Every case here is a real shape observed from a provider. No LLM, no network.
"""
from __future__ import annotations

from codedoc_ai.injector import _strip_llm_artifacts, format_docstring


def test_fence_language_tag_is_not_left_behind():
    raw = '```python\n"""Allow a request.\n\nArgs:\n    x (int): A number.\n"""\n```'
    assert _strip_llm_artifacts(raw) == "Allow a request.\n\nArgs:\n    x (int): A number."


def test_double_wrapped_fence_inside_triple_quotes():
    # The shape a provider produces when it force-wraps an already-fenced reply:
    # triple quotes around ```python around triple quotes.
    raw = '"""\npython\n"""Determine whether a hit is allowed.\n"""\n"""'
    assert _strip_llm_artifacts(raw) == "Determine whether a hit is allowed."


def test_unterminated_triple_quote_is_stripped():
    # A response cut off by the token limit loses its closing delimiter; the
    # leading one must still go, or it lands in the comment body.
    raw = '"""\npython\n"""Removes stale timestamps from the sliding window'
    assert _strip_llm_artifacts(raw) == "Removes stale timestamps from the sliding window"


def test_reasoning_trace_is_removed():
    raw = "<think>The user wants a docstring. Let me read the code.</think>\nReturns the remaining quota."
    assert _strip_llm_artifacts(raw) == "Returns the remaining quota."


def test_plain_text_passes_through_untouched():
    raw = "Calculate the remaining quota.\n\nReturns:\n    int: The remainder."
    assert _strip_llm_artifacts(raw) == raw


def test_markdown_hard_breaks_do_not_leave_trailing_whitespace():
    # Two trailing spaces are markdown's line-break syntax; inside a comment
    # block they are just lint-flagged trailing whitespace.
    raw = "Allows a request.  \n\nArgs:  \n- hits: timestamps.  "
    cleaned = _strip_llm_artifacts(raw)
    assert cleaned == "Allows a request.\n\nArgs:\n- hits: timestamps."
    assert not any(line != line.rstrip() for line in cleaned.splitlines())


def test_indentation_inside_docstring_is_preserved():
    # Only *trailing* whitespace goes — leading indentation is meaningful.
    raw = "Summary.\n\nArgs:\n    burst (int): Cap.  "
    assert _strip_llm_artifacts(raw) == "Summary.\n\nArgs:\n    burst (int): Cap."


def test_java_javadoc_has_no_python_or_quote_artifacts():
    """End-to-end: the formatted Java block must be clean Javadoc."""
    raw = '```python\n"""Allow a request.\n\nArgs:\n    burst (int): Cap.\n"""\n```'
    block = format_docstring("java", raw, "    ")

    assert block.splitlines()[0] == "    /**"
    assert block.splitlines()[-1] == "     */"
    # The two artifacts that leaked into a real run.
    assert "python" not in block
    assert '"""' not in block
    assert "     * Allow a request." in block


def test_empty_after_stripping_yields_empty_block():
    # Nothing but wrapping -> no comment at all, so the caller can skip the
    # function instead of inserting an empty `/** */`.
    assert format_docstring("java", '```python\n```', "") == ""
