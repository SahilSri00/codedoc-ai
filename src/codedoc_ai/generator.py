"""
generator.py — Orchestrates the LLM documentation pipeline.

Uses the provider factory to select ONE active LLM provider (Groq, Gemini,
OpenAI, or Ollama) which generates both the per-function docstrings and the
file summary. The provider is configured via ``CODEDOC_PROVIDER`` in .env or
the ``--provider`` CLI flag (default: groq).
"""
from pathlib import Path
from .providers.factory import get_provider
from .router import detect_and_parse


def generate(file: Path, combined: bool = True, provider_name: str = None) -> dict:
    """
    Generate documentation for any supported source file.

    Runs the LLM pipeline:
    1. Parse the file into function/method schemas.
    2. Generate a Google-style docstring for every function.
    3. Generate a high-level file summary.
    4. Merge both outputs into a single Markdown document.

    Args:
        file: Path to the source file.
        combined: Reserved for future use.
        provider_name: Override the default provider (groq/gemini/openai/ollama).

    Returns:
        dict with keys:
            ``"summary"``   — Full Markdown document.
            ``"functions"`` — List of raw FunctionSchema dicts.
    """
    file = Path(file)
    source_code = file.read_text(encoding="utf-8", errors="ignore")
    provider = get_provider(provider_name)

    # Step 1 — Parse
    functions = detect_and_parse(file)

    # Step 2 — Per-function docstrings
    for func in functions:
        func.docstring = provider.generate_doc(func)

    # Step 3 — High-level file summary
    file_summary = provider.summarize_file(file, functions, source_code=source_code)

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
