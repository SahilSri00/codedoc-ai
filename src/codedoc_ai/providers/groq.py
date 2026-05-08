"""
Groq provider for CodeDoc-AI.

Role in the hybrid LLM pipeline
---------------------------------
Groq (Llama 3.1 8B Instant) handles **high-level file summaries**: fast, conversational,
and well-suited for producing a readable overview of what a file does, how its pieces fit
together, and any obvious gotchas.

Gemini handles the deep, per-function Google-style docstrings.
Together, the two models produce documentation that is both precise *and* readable.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from groq import Groq

from ..models.schemas import FunctionSchema

load_dotenv()

# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------
_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file or environment."
            )
        _client = Groq(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
_SUMMARY_SYSTEM = """\
You are a senior software engineer writing concise, professional documentation.
Given a source file's full code and a list of its parsed functions/methods, produce
a Markdown-formatted file summary with the following sections:

## Overview
A 2–3 sentence description of what this file does and its role in a larger system.

## Key Components
A bullet list of the most important functions/classes and what each one is responsible for.

## Data Flow
1–3 sentences describing how data enters, is transformed, and exits this file.

## Notes
Any edge cases, performance considerations, or caveats worth calling out.

Rules:
- Be direct and precise. No filler phrases.
- Use plain Markdown only (headers, bullets, numbered lists, inline code).
- Do NOT reproduce the full source code.
- Keep the total output under 400 words.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def summarize_file(
    file_path: Path,
    functions: List[FunctionSchema],
    source_code: Optional[str] = None,
) -> str:
    """
    Generate a high-level Markdown summary for *file_path* using Groq (Llama 3.1).

    Args:
        file_path: Path to the source file.
        functions: Parsed function/method schemas extracted from the file.
        source_code: Full source text. If omitted, the file is read from disk.

    Returns:
        A Markdown-formatted string summarising the file, or an empty string on failure.
    """
    if source_code is None:
        try:
            source_code = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            return f"_Could not read source file: {exc}_"

    # Build a compact function manifest so the model knows what's in the file
    manifest_lines = []
    for f in functions:
        sig = f"{f.name}({', '.join(f.args)})"
        if f.return_type:
            sig += f" -> {f.return_type}"
        if f.docstring:
            sig += f"  # {f.docstring[:80].strip()}"
        manifest_lines.append(f"  - {sig}")

    manifest = "\n".join(manifest_lines) if manifest_lines else "  (no functions found)"

    user_prompt = (
        f"File: `{file_path}`\n\n"
        f"Parsed functions/methods:\n{manifest}\n\n"
        f"Full source code:\n```\n{source_code[:6000]}\n```\n\n"
        "Produce the file summary now."
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[Groq] summarize_file failed: {exc}")
        return ""

def generate_doc(func: FunctionSchema) -> str:
    """Generate a Google-style docstring for a single function using Groq."""
    prompt = (
        "You are a senior software engineer and technical writer.\n"
        "Given the function below, return ONLY a Google-style docstring enclosed in triple double-quotes.\n"
        "Include 1-line summary, Args, and Returns if applicable.\n"
        f"Function: {func.name}({', '.join(func.args)}) -> {func.return_type}\n"
        f"Source code:\n{func.source_code}\n\n"
        "Return ONLY the docstring. Do not include the function signature."
    )
    
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        text = response.choices[0].message.content.strip()
        if not text.startswith('"""'):
            text = f'"""\n{text.strip("`")}\n"""'
        return text
    except Exception as exc:
        print(f"[Groq] generate_doc failed: {exc}")
        return ""
