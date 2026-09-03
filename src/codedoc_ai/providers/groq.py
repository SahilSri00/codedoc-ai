"""
Groq provider for CodeDoc-AI.

Implements the LLMProvider interface using Groq's OpenAI-compatible chat API.
Handles both per-function docstring generation and file-level summaries. The
model is configurable via GROQ_MODEL (default: openai/gpt-oss-20b).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from groq import Groq

from ..models.schemas import FunctionSchema
from .base import LLMProvider

load_dotenv()

# ---------------------------------------------------------------------------
# Prompt templates
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

_DOCSTRING_PROMPT = (
    "You are a senior software engineer and technical writer.\n"
    "Write API documentation for the {language} function below.\n\n"
    "{func_sig}\n"
    "Source code:\n{source_code}\n\n"
    "Requirements:\n"
    "- Open with a single-sentence summary of what the function does.\n"
    "- Then an 'Args:' section (one line per parameter) if it takes parameters.\n"
    "- Then a 'Returns:' section if it returns a value.\n"
    "- Output PLAIN TEXT only. Do NOT wrap it in markdown code fences or triple\n"
    "  quotes, and do NOT prefix lines with //, /*, * or any other comment\n"
    "  marker — the caller applies {language}'s own comment syntax afterwards.\n"
    "- Do not repeat the function signature or the source code.\n"
    "- Keep it under 120 words.\n"
)

# Used only to tell the model which language it is documenting, so the wording
# stays idiomatic. The comment syntax itself is applied by the injector.
_LANG_LABELS = {
    ".py": "Python",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".h": "C/C++",
    ".c": "C",
}


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------

class GroqProvider(LLMProvider):
    """LLM provider using Groq's OpenAI-compatible chat completions API."""

    name = "groq"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or os.getenv("GROQ_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file or environment."
            )
        # Groq retires models periodically (llama-3.1-8b-instant was shut down in
        # 2026). Default to a current production model, but allow an override via
        # GROQ_MODEL so a future deprecation is a .env change, not a code edit.
        self._model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self._client = Groq(api_key=self._api_key)

    def _reasoning_kwargs(self) -> dict:
        """
        GPT-OSS models on Groq are reasoning models: their chain-of-thought is
        emitted as output tokens and therefore eats the completion budget, which
        truncated docstrings mid-sentence. Request the cheapest reasoning tier.
        Other models are left alone — the parameter is not universally accepted.
        """
        if self._model.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low"}
        return {}

    def generate_doc(self, func: FunctionSchema) -> str:
        """Generate documentation text for a single function (plain text, no delimiters)."""
        language = _LANG_LABELS.get(Path(func.file_path).suffix.lower(), "source")
        func_sig = f"Function: {func.name}({', '.join(func.args)})"
        if func.return_type:
            func_sig += f" -> {func.return_type}"
        prompt = _DOCSTRING_PROMPT.format(
            language=language, func_sig=func_sig, source_code=func.source_code
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_completion_tokens=1024,
                **self._reasoning_kwargs(),
            )
            choice = response.choices[0]
            # A half-finished docstring is worse than none at all: it would put a
            # sentence that stops mid-word into the user's source file. Fail closed
            # and let the injector skip this function.
            if choice.finish_reason == "length":
                print(
                    f"[Groq] docstring for {func.name} hit the token limit — "
                    "skipping rather than injecting a truncated comment."
                )
                return ""
            return (choice.message.content or "").strip()
        except Exception as exc:
            print(f"[Groq] generate_doc failed: {exc}")
            return ""

    def summarize_file(
        self,
        file_path: Path,
        functions: List[FunctionSchema],
        source_code: Optional[str] = None,
    ) -> str:
        """Generate a high-level Markdown summary for a file."""
        if source_code is None:
            try:
                source_code = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                return f"_Could not read source file: {exc}_"

        # Build function manifest
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
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_completion_tokens=1600,
                **self._reasoning_kwargs(),
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[Groq] summarize_file failed: {exc}")
            return ""


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions
# ---------------------------------------------------------------------------
_default_provider: Optional[GroqProvider] = None


def _get_default() -> GroqProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = GroqProvider()
    return _default_provider


def generate_doc(func: FunctionSchema) -> str:
    return _get_default().generate_doc(func)


def summarize_file(
    file_path: Path,
    functions: List[FunctionSchema],
    source_code: Optional[str] = None,
) -> str:
    return _get_default().summarize_file(file_path, functions, source_code)
