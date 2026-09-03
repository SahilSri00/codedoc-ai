"""
injector.py — Docstring injection engine for CodeDoc-AI.

Generates AI-powered docstrings and injects them directly into source files,
using the correct comment syntax for each language (JavaDoc, Google-style
Python docstrings, JSDoc, Go/Rust doc comments, Doxygen for C++).

Key design decision: functions are processed **bottom-up** (last function first)
so that inserting lines above one function never shifts the line numbers of
functions that haven't been processed yet.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.syntax import Syntax

from .models.schemas import FunctionSchema
from .providers.factory import get_provider
from .router import detect_and_parse, detect_lang
from .safety import syntax_ok, validate_modification

_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Language-specific comment formatters
# ---------------------------------------------------------------------------

def _detect_indent(lines: List[str], start_line: int) -> str:
    """Return the leading whitespace of a given line (1-indexed)."""
    if 1 <= start_line <= len(lines):
        line = lines[start_line - 1]
        return line[: len(line) - len(line.lstrip())]
    return ""


#: Bare language tags a model may leave behind on their own line once the
#: surrounding ``` fence has been stripped.
_FENCE_LANGS = {
    "python", "py", "java", "javascript", "js", "jsx", "typescript", "ts",
    "tsx", "go", "golang", "rust", "rs", "cpp", "c++", "c", "text",
    "plaintext", "markdown", "md", "docstring",
}

#: Inline chain-of-thought some reasoning models emit into the message body.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _peel_once(text: str) -> str:
    """Strip one layer of fence / language tag / triple-quote wrapping."""
    text = text.strip()

    # ```lang ... ```  — drop the whole opening line so the language tag goes
    # with it, rather than surviving as a stray "python" line in the output.
    if text.startswith("```"):
        first_nl = text.find("\n")
        text = text[first_nl + 1:] if first_nl != -1 else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()

    # A language tag left on its own first line.
    lines = text.splitlines()
    if lines and lines[0].strip().lower() in _FENCE_LANGS:
        text = "\n".join(lines[1:]).strip()

    # Leading/trailing triple quotes. The leading one is removed even without a
    # matching closer: real documentation never *starts* with `"""`, and a
    # truncated response can easily lose its terminator.
    for quote in ('"""', "'''"):
        if text.startswith(quote):
            text = text[3:]
            if text.rstrip().endswith(quote):
                text = text.rstrip()[:-3]
            text = text.strip()

    return text.strip()


def _strip_llm_artifacts(raw: str) -> str:
    """
    Remove markdown fences, stray triple-quotes, and leading/trailing junk.

    Providers sometimes wrap their output more than once (a fenced block that
    then gets re-wrapped in triple quotes), so wrappers are peeled repeatedly
    until the text stops changing. Whatever survives is documentation *prose* —
    the caller adds the language's own comment syntax.
    """
    text = _THINK_RE.sub("", raw).strip()

    for _ in range(4):  # bounded: guards against a pathological payload
        peeled = _peel_once(text)
        if peeled == text:
            break
        text = peeled

    # Models end lines with two spaces (markdown's hard-break syntax). That has
    # no meaning inside a comment block and just leaves trailing whitespace that
    # linters flag, so drop it per line.
    text = "\n".join(line.rstrip() for line in text.splitlines())

    return text.strip()


def format_docstring(lang: str, raw_text: str, indent: str) -> str:
    """
    Convert raw LLM text into a language-native doc comment block.

    Args:
        lang: File extension / language key (e.g. "py", "java", "go").
        raw_text: The raw docstring text from the LLM.
        indent: Whitespace prefix to apply to every line.

    Returns:
        A fully-formatted, indented comment block ready to insert.
    """
    text = _strip_llm_artifacts(raw_text)
    if not text:
        return ""

    lines = text.splitlines()

    # --- Python: triple-quoted docstring ---
    if lang in ("py", "python"):
        out = [f'{indent}"""']
        for line in lines:
            out.append(f"{indent}{line}" if line.strip() else "")
        out.append(f'{indent}"""')
        return "\n".join(out)

    # --- Java / JS / TS / C++: block comment /** ... */ ---
    if lang in ("java", "js", "javascript", "ts", "tsx", "cpp", "cc", "hpp", "h"):
        out = [f"{indent}/**"]
        for line in lines:
            if line.strip():
                out.append(f"{indent} * {line}")
            else:
                out.append(f"{indent} *")
        out.append(f"{indent} */")
        return "\n".join(out)

    # --- Go: line comments ---
    if lang == "go":
        out = []
        for line in lines:
            if line.strip():
                out.append(f"{indent}// {line}")
            else:
                out.append(f"{indent}//")
        return "\n".join(out)

    # --- Rust: doc comments ---
    if lang in ("rs", "rust"):
        out = []
        for line in lines:
            if line.strip():
                out.append(f"{indent}/// {line}")
            else:
                out.append(f"{indent}///")
        return "\n".join(out)

    # Fallback: block comment
    out = [f"{indent}/**"]
    for line in lines:
        out.append(f"{indent} * {line}" if line.strip() else f"{indent} *")
    out.append(f"{indent} */")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Existing-docstring detection
# ---------------------------------------------------------------------------

def _has_existing_doc(lines: List[str], func_start_line: int, lang: str) -> bool:
    """
    Check whether a comment block already exists immediately above the function.
    Returns True if the function is already documented.
    """
    # Look at lines above the function definition (1-indexed → 0-indexed)
    idx = func_start_line - 2  # line immediately above the def

    # Skip blank lines
    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    if idx < 0:
        return False

    line = lines[idx].strip()

    # Python
    if lang in ("py", "python"):
        return line.endswith('"""') or line.endswith("'''")

    # Java / JS / C++
    if lang in ("java", "js", "javascript", "ts", "tsx", "cpp", "cc", "hpp", "h"):
        return line.endswith("*/")

    # Go
    if lang == "go":
        return line.startswith("//")

    # Rust
    if lang in ("rs", "rust"):
        return line.startswith("///")

    return False


def _remove_existing_doc(lines: List[str], func_start_line: int, lang: str) -> Tuple[List[str], int]:
    """
    Remove the existing doc comment block above a function.

    Returns:
        Tuple of (modified lines, number of lines removed).
    """
    idx = func_start_line - 2  # 0-indexed line above the def

    # Skip trailing blank lines
    blank_count = 0
    while idx >= 0 and not lines[idx].strip():
        idx -= 1
        blank_count += 1

    if idx < 0:
        return lines, 0

    line = lines[idx].strip()
    end_idx = idx  # inclusive bottom of comment block

    # Find the top of the comment block
    if lang in ("py", "python"):
        if line.endswith('"""') or line.endswith("'''"):
            quote = line[-3:]
            # Walk up to find opening quotes
            while idx >= 0:
                if lines[idx].strip().startswith(quote):
                    break
                idx -= 1

    elif lang in ("java", "js", "javascript", "ts", "tsx", "cpp", "cc", "hpp", "h"):
        if line.endswith("*/"):
            while idx >= 0:
                if "/*" in lines[idx]:
                    break
                idx -= 1

    elif lang == "go":
        while idx >= 0 and lines[idx].strip().startswith("//"):
            idx -= 1
        idx += 1  # went one too far

    elif lang in ("rs", "rust"):
        while idx >= 0 and lines[idx].strip().startswith("///"):
            idx -= 1
        idx += 1

    else:
        return lines, 0

    if idx < 0:
        idx = 0

    start_idx = idx
    removed = end_idx - start_idx + 1
    new_lines = lines[:start_idx] + lines[end_idx + 1:]
    return new_lines, removed


# ---------------------------------------------------------------------------
# Core injection logic
# ---------------------------------------------------------------------------

def inject_docstrings(
    file_path: Path,
    *,
    replace: bool = False,
    dry_run: bool = False,
    backup: bool = True,
    out_dir: Optional[Path] = None,
    provider_name: Optional[str] = None,
) -> dict:
    """
    Parse a source file, generate docstrings via LLM, and inject them.

    The write is **fail-closed**: the proposed result is validated in memory
    (must still parse; must have the same number of functions as the original)
    before anything touches disk, and the real write is atomic (temp file +
    ``os.replace``) so an interrupted run can never leave a half-written file.

    Args:
        file_path: Path to the source file.
        replace: If True, overwrite existing docstrings. Default: skip documented funcs.
        dry_run: If True, print a diff preview without writing.
        backup: If True (default), create a .bak copy before modifying in place.
        out_dir: If set, write the documented copy here instead of modifying in-place.

    Returns:
        dict with keys: "injected" (count), "skipped" (count), "file" (output
        path), "aborted" (bool — True if the write was refused for safety), and
        "reason" (str, present only when aborted).
    """
    file_path = Path(file_path).resolve()
    lang = detect_lang(file_path)

    if lang == "unknown":
        raise RuntimeError(f"Cannot detect language for '{file_path}'")

    # Parse functions
    functions = detect_and_parse(file_path)
    if not functions:
        _console.print(f"[yellow]No functions found in {file_path.name}[/yellow]")
        return {"injected": 0, "skipped": 0, "file": str(file_path), "aborted": False}

    original_func_count = len(functions)

    # Read file with strict UTF-8 and NO newline translation, so CRLF/LF are
    # preserved exactly. A non-UTF-8 file is refused rather than mangled.
    # (open(newline="") works on all 3.x; Path.read_text gained newline in 3.13.)
    try:
        with open(file_path, "r", encoding="utf-8", newline="") as handle:
            original_text = handle.read()
    except UnicodeDecodeError as exc:
        reason = f"file is not valid UTF-8 ({exc})"
        _console.print(f"  [red]✗ Refusing to modify {file_path.name}: {reason}[/red]")
        return {"injected": 0, "skipped": 0, "file": str(file_path),
                "aborted": True, "reason": reason}

    # Fail fast: if the file does not parse *before* we touch it, the fail-closed
    # gate is guaranteed to refuse the write later. Checking now means we don't
    # spend LLM calls (real money, real latency) generating docstrings that can
    # never be written. Verified: the read above happens before any provider call.
    pre_ok, _ = syntax_ok(original_text, lang)
    if not pre_ok:
        reason = (
            f"the file does not parse with the '{lang}' grammar, so no "
            "modification could be verified as safe"
        )
        _console.print(f"  [red]✗ Skipping {file_path.name}: {reason}[/red]")
        return {"injected": 0, "skipped": 0, "file": str(file_path),
                "aborted": True, "reason": reason}

    # Preserve the file's dominant line ending for any lines we insert.
    newline = "\r\n" if "\r\n" in original_text else "\n"
    lines = original_text.splitlines(keepends=True)

    # Sort functions bottom-up so insertions don't shift later line numbers
    functions_sorted = sorted(functions, key=lambda f: f.start_line, reverse=True)

    injected = 0
    skipped = 0

    for func in functions_sorted:
        # Check for existing documentation
        lines_no_endings = [l.rstrip("\r\n") for l in lines]
        has_doc = _has_existing_doc(lines_no_endings, func.start_line, lang)

        if has_doc and not replace:
            _console.print(f"  [dim]⏭ Skipping {func.name} (already documented)[/dim]")
            skipped += 1
            continue

        # If replacing, remove the old doc block first
        if has_doc and replace:
            lines_no_endings, removed = _remove_existing_doc(lines_no_endings, func.start_line, lang)
            # Rebuild lines with the file's own line ending
            lines = [l + newline for l in lines_no_endings]
            # Adjust this function's start_line
            func.start_line -= removed

        # Generate docstring via LLM
        _console.print(f"  [cyan]✨ Generating docstring for {func.name}…[/cyan]")
        provider = get_provider(provider_name)
        raw_doc = provider.generate_doc(func)
        if not raw_doc:
            _console.print(f"  [yellow]⚠ LLM returned empty for {func.name}[/yellow]")
            skipped += 1
            continue

        # Format into language-native comment syntax
        indent = _detect_indent([l.rstrip("\r\n") for l in lines], func.start_line)
        formatted = format_docstring(lang, raw_doc, indent)

        if not formatted:
            _console.print(
                f"  [yellow]⚠ Unusable response for {func.name} "
                "(nothing left after stripping fences/quotes)[/yellow]"
            )
            skipped += 1
            continue

        # Insert above the function definition
        insert_idx = func.start_line - 1  # 0-indexed
        insert_lines = [l + newline for l in formatted.splitlines()]
        lines = lines[:insert_idx] + insert_lines + lines[insert_idx:]
        injected += 1

    # Build the final output
    result_text = "".join(lines)

    # Nothing actually changed (everything skipped) — never touch the file.
    if result_text == original_text:
        if dry_run:
            _console.print("[dim]No changes.[/dim]")
        return {"injected": injected, "skipped": skipped, "file": str(file_path),
                "aborted": False}

    # ---- Fail-closed gate: validate BEFORE any write ----
    ok, reason = validate_modification(
        original_text, result_text, lang, file_path.suffix, original_func_count
    )
    if not ok:
        _console.print(
            f"  [red]✗ Refusing to write {file_path.name}: {reason}[/red]"
        )
        return {"injected": 0, "skipped": skipped, "file": str(file_path),
                "aborted": True, "reason": reason}

    if dry_run:
        _console.print(f"\n[bold]── Dry-run preview for {file_path.name} ──[/bold]\n")
        _show_diff(original_text, result_text, file_path.name, lang)
        return {"injected": injected, "skipped": skipped, "file": str(file_path),
                "aborted": False}

    # Determine output path
    if out_dir:
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / file_path.name
        make_backup = False  # writing a fresh copy; nothing to back up
    else:
        out_path = file_path
        make_backup = backup

    _atomic_write(out_path, result_text, backup=make_backup)
    return {"injected": injected, "skipped": skipped, "file": str(out_path),
            "aborted": False}


def _atomic_write(target: Path, text: str, *, backup: bool) -> None:
    """
    Write *text* to *target* atomically.

    The content is written to a temporary file in the same directory and then
    moved into place with ``os.replace`` (atomic on both POSIX and Windows), so
    an interrupted write can never leave a truncated or half-written source
    file. The temp file is written with ``newline=""`` so the exact bytes of
    *text* (including any CRLF endings) are preserved.

    If *backup* is True and *target* already exists, a ``.bak`` copy is made
    before the replace.
    """
    target = Path(target)
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=target.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if backup and target.exists():
            bak_path = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, bak_path)
            _console.print(f"  [dim]📋 Backup saved to {bak_path.name}[/dim]")
        os.replace(tmp_name, target)
    except Exception:
        # The replace never happened; remove the orphaned temp file.
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Diff display
# ---------------------------------------------------------------------------

def _show_diff(original: str, modified: str, filename: str, lang: str) -> None:
    """Print a side-by-side colored diff of original vs. modified."""
    import difflib

    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )

    diff_text = "\n".join(diff)
    if not diff_text.strip():
        _console.print("[dim]No changes.[/dim]")
        return

    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
    _console.print(syntax)
