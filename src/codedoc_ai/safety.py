"""
safety.py — Fail-closed validation for the docstring injector.

The injector modifies real source files, so before anything is written to disk
the proposed result is validated **in memory**. Two independent checks must
both pass:

1. **Parse-back** — the modified source must still parse. If the original
   parsed cleanly but the modified source introduces a syntax/parse error, the
   modification is rejected.
2. **Structural invariant** — injecting documentation must not change program
   structure. The number of functions the parser finds must be identical before
   and after.

If either check fails the caller must write nothing and leave the original file
untouched. These helpers do no I/O of their own beyond a throwaway temp file
used to re-run the project's real parsers (so validation matches extraction
exactly); they never touch the target file.
"""
from __future__ import annotations

import ast
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

# Extension used to route text through the correct tree-sitter grammar.
_TREE_SITTER_GRAMMARS = {
    ("rs", "rust"): "tree_sitter_rust",
    ("go",): "tree_sitter_go",
    ("js", "javascript", "ts", "tsx", "mjs", "cjs"): "tree_sitter_javascript",
    ("java",): "tree_sitter_java",
    ("cpp", "cc", "cxx", "hpp", "hxx", "h"): "tree_sitter_cpp",
}


def _grammar_module_for(lang: str) -> Optional[str]:
    for keys, module in _TREE_SITTER_GRAMMARS.items():
        if lang in keys:
            return module
    return None


def _tree_sitter_has_error(text: str, lang: str) -> Optional[bool]:
    """
    Return True/False whether *text* has a tree-sitter parse error for *lang*,
    or None if the grammar can't be loaded (in which case we can't judge).
    """
    module_name = _grammar_module_for(lang)
    if module_name is None:
        return None
    try:
        import importlib

        from tree_sitter import Language, Parser

        grammar = importlib.import_module(module_name)
        parser = Parser()
        # Mirrors the pattern used by the language parsers (tree-sitter 0.25).
        parser.language = Language(grammar.language())
        tree = parser.parse(text.encode("utf-8"))
        return bool(tree.root_node.has_error)
    except Exception:
        return None


def syntax_ok(text: str, lang: str) -> Tuple[bool, str]:
    """
    Check that *text* parses for *lang*.

    Returns (True, "") if it parses (or can't be checked), else (False, reason).
    Python uses the stdlib ``ast``; other languages use their tree-sitter
    grammar. If a grammar can't be loaded we do not block on syntax here — the
    structural-invariant check still applies.
    """
    if lang in ("py", "python"):
        try:
            ast.parse(text)
            return True, ""
        except SyntaxError as exc:
            return False, f"modified source has a Python syntax error: {exc}"

    has_error = _tree_sitter_has_error(text, lang)
    if has_error is None:
        return True, ""  # cannot verify syntax for this language
    if has_error:
        return False, f"modified source has a tree-sitter parse error ({lang})"
    return True, ""


def count_functions_in_text(text: str, lang: str, suffix: str) -> int:
    """
    Count the functions the project's real parsers find in *text*.

    Writes *text* to a throwaway temp file (with *suffix* so language detection
    works) and runs the normal parser dispatch, so this count matches what
    extraction would produce. Returns -1 if parsing raises.
    """
    from .router import detect_and_parse

    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        try:
            return len(detect_and_parse(Path(tmp_name)))
        except Exception:
            return -1
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def validate_modification(
    original_text: str,
    modified_text: str,
    lang: str,
    suffix: str,
    original_func_count: int,
) -> Tuple[bool, str]:
    """
    Validate a proposed in-memory modification before it is written to disk.

    Args:
        original_text: The unmodified source (used only for context/parity).
        modified_text: The proposed result to be written.
        lang: Language key (e.g. "py", "rust").
        suffix: File suffix including dot (e.g. ".py") for language detection.
        original_func_count: Number of functions parsed from the original file.

    Returns:
        (True, "") if safe to write, otherwise (False, human-readable reason).
    """
    ok, reason = syntax_ok(modified_text, lang)
    if not ok:
        return False, reason

    new_count = count_functions_in_text(modified_text, lang, suffix)
    if new_count != original_func_count:
        return (
            False,
            "structural invariant violated: function count changed "
            f"({original_func_count} → {new_count})",
        )

    return True, ""
