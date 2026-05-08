from pathlib import Path
from typing import List

from .models.schemas import FunctionSchema
from .parser.python_parser import parse_file as parse_py
from .parser.java_parser import parse_file as parse_java
from .parser.js_parser import parse_file as parse_js
from .parser.cpp_parser import parse_file as parse_cpp
from .parser.go_parser import parse_file as parse_go
from .parser.rust_parser import parse_file as parse_rs

# ---------------------------------------------------------------------------
# Extension → parser mapping
# ---------------------------------------------------------------------------
PARSERS = {
    # Python
    "py": parse_py,
    "python": parse_py,
    # JavaScript / TypeScript (tree-sitter-javascript handles both)
    "js": parse_js,
    "mjs": parse_js,
    "cjs": parse_js,
    "ts": parse_js,
    "tsx": parse_js,
    # Java
    "java": parse_java,
    # C / C++
    "cpp": parse_cpp,
    "cc": parse_cpp,
    "cxx": parse_cpp,
    "hpp": parse_cpp,
    "hxx": parse_cpp,
    "h": parse_cpp,
    # Go
    "go": parse_go,
    # Rust
    "rs": parse_rs,
}

# Content-sniff tokens that strongly suggest a language.
# Each entry: (language_key, list_of_required_tokens)
_SNIFF_RULES = [
    ("py",   ["def ", "import "]),
    ("java", ["public class", "package "]),
    ("go",   ["func ", "package "]),
    ("rs",   ["fn ", "use std"]),
    ("cpp",  ["#include", "std::"]),
    ("js",   ["function ", "const ", "=>"]),
]


def detect_lang(path: Path) -> str:
    """
    Detect the programming language of *path*.

    Strategy:
    1. Match the file extension against the ``PARSERS`` map.
    2. If the extension is unknown, sniff the first 2 KB of the file content
       using language-specific token sets (all tokens must appear for a match).
    3. Return ``"unknown"`` if no match is found.
    """
    ext = path.suffix.lstrip(".").lower()
    if ext in PARSERS:
        return ext

    # Heuristic fallback — require ALL tokens in the set to reduce false positives
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2048]
    except OSError:
        return "unknown"

    for lang_key, tokens in _SNIFF_RULES:
        if all(tok in head for tok in tokens):
            return lang_key

    return "unknown"


def detect_and_parse(path: Path) -> List[FunctionSchema]:
    """Parse *path* and return a list of FunctionSchema objects."""
    lang = detect_lang(path)
    if lang == "unknown":
        raise RuntimeError(f"Cannot detect language for '{path}'")
    return PARSERS[lang](path)
