"""
generator.py — Orchestrates the hybrid LLM documentation pipeline.

Hybrid LLM Architecture
------------------------
- **Gemini 2.0 Flash** (deep, structured):  per-function Google-style docstrings.
- **Groq / Llama 3.1 8B** (fast, conversational): high-level file summary.

The two models complement each other — Gemini produces precise, typed documentation
while Groq frames the file in plain, readable prose.
"""
from pathlib import Path
from .providers.groq import generate_doc, summarize_file as groq_summarize
from .router import detect_and_parse


def generate(file: Path, combined: bool = True) -> dict:
    """
    Generate documentation for any supported source file.

    Runs the hybrid LLM pipeline:
    1. Parse the file into function/method schemas.
    2. Ask **Gemini** to write a Google-style docstring for every function.
    3. Ask **Groq** (Llama 3.1) to write a high-level file summary.
    4. Merge both outputs into a single Markdown document.

    Args:
        file: Path to the source file. Supported languages: Python, JavaScript,
              TypeScript, Java, Go, Rust, C++.
        combined: Reserved for future use; always runs the hybrid pipeline.

    Returns:
        dict with keys:
            ``"summary"``   — Full Markdown document (Groq overview + Gemini per-function docs).
            ``"functions"`` — List of raw FunctionSchema dicts from the parser.
    """
    file = Path(file)
    source_code = file.read_text(encoding="utf-8", errors="ignore")

    # Step 1 — Parse
    functions = detect_and_parse(file)

    # Step 2 — Gemini: per-function docstrings
    for func in functions:
        func.docstring = generate_doc(func)

    # Step 3 — Groq: high-level file summary
    file_summary = groq_summarize(file, functions, source_code=source_code)

    # Step 4 — Merge into a single Markdown document
    parts = []

    if file_summary:
        parts.append(file_summary)
    else:
        parts.append(f"# {file.name}\n\n_File summary unavailable._")

    parts.append("\n\n---\n\n## Function Documentation\n")

    for func in functions:
        parts.append(f"\n### `{func.name}`\n")
        if func.docstring:
            parts.append(func.docstring.strip())
        else:
            parts.append("_No documentation generated._")
        parts.append("")

    merged = "\n".join(parts).strip()

    return {
        "summary": merged,
        "functions": [f.model_dump() for f in functions],
    }
