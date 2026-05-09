"""
OpenAI provider for CodeDoc-AI.

Implements the LLMProvider interface using OpenAI's API (GPT-4o-mini by default).
Requires: ``pip install openai`` and ``OPENAI_API_KEY`` in .env.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from ..models.schemas import FunctionSchema
from .base import LLMProvider

load_dotenv()

# Reuse the same prompt templates
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


class OpenAIProvider(LLMProvider):
    """LLM provider using OpenAI's API (GPT-4o-mini default)."""

    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file or environment."
            )
        self._model = model

        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError:
            raise RuntimeError(
                "OpenAI SDK not installed. Run: pip install openai"
            )
        self._client = OpenAI(api_key=self._api_key)

    def generate_doc(self, func: FunctionSchema) -> str:
        """Generate a Google-style docstring for a single function."""
        prompt = (
            "You are a senior software engineer and technical writer.\n"
            "Given the function below, return ONLY a Google-style docstring enclosed in triple double-quotes.\n"
            "Include 1-line summary, Args, and Returns if applicable.\n"
            f"Function: {func.name}({', '.join(func.args)}) -> {func.return_type}\n"
            f"Source code:\n{func.source_code}\n\n"
            "Return ONLY the docstring. Do not include the function signature."
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
            )
            text = response.choices[0].message.content.strip()
            if not text.startswith('"""'):
                text = f'"""\n{text.strip("`")}\n"""'
            return text
        except Exception as exc:
            print(f"[OpenAI] generate_doc failed: {exc}")
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

        manifest_lines = []
        for f in functions:
            sig = f"{f.name}({', '.join(f.args)})"
            if f.return_type:
                sig += f" -> {f.return_type}"
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
                max_tokens=600,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[OpenAI] summarize_file failed: {exc}")
            return ""
