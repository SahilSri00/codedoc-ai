"""
Gemini provider for CodeDoc-AI.

Implements the LLMProvider interface using Google's Gemini 2.0 Flash API.
Requires: ``GEMINI_API_KEY`` in .env.
"""
from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from ..models.schemas import FunctionSchema
from .base import LLMProvider

load_dotenv()

_DOCSTRING_SYSTEM = """You are a senior software engineer and technical writer.
Given a function signature and body, return ONLY a Google-style docstring, enclosed in triple double-quotes.
Include sections if applicable: 1-line summary, Args (with types), Returns, Raises (if any).
Be concise and precise. Do not include extra prose, backticks, or markdown outside the docstring.
"""

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


class GeminiProvider(LLMProvider):
    """LLM provider using Google Gemini 2.0 Flash."""

    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env file or environment."
            )

        import google.generativeai as genai
        genai.configure(api_key=self._api_key)

        self._model = genai.GenerativeModel(
            model_name=model,
            generation_config={
                "temperature": 0.2,
                "top_p": 0.9,
                "top_k": 40,
                "max_output_tokens": 2048,
            },
        )

    def _retry_generate(self, prompt: str, retries: int = 2, backoff: float = 1.5) -> str:
        """Generate content with retry logic for rate limits."""
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = self._model.generate_content(prompt)
                text = getattr(resp, "text", None)
                if text:
                    return text
                if hasattr(resp, "candidates") and resp.candidates:
                    for cand in resp.candidates:
                        if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                            parts_text = "".join(getattr(p, "text", "") for p in cand.content.parts)
                            if parts_text.strip():
                                return parts_text
                return ""
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                else:
                    print(f"[Gemini] Failed after {retries + 1} attempts: {e}")
        return ""

    def _ensure_docstring_block(self, s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s.strip("`").strip()
        if not s.startswith('"""'):
            s = f'"""\n{s}\n"""'
        return s

    def generate_doc(self, func: FunctionSchema) -> str:
        """Generate a Google-style docstring for a single function."""
        function_blob = {
            "name": func.name,
            "arguments": func.args,
            "return_type": func.return_type or "",
            "existing_docstring": func.docstring or "None",
            "source_code": func.source_code or "",
        }

        prompt = (
            f"{_DOCSTRING_SYSTEM}\n\n"
            f"Function metadata (JSON):\n{json.dumps(function_blob, ensure_ascii=False, indent=2)}\n\n"
            "Return ONLY the Google-style docstring (triple double-quoted)."
        )

        text = self._retry_generate(prompt)
        if not text:
            return ""
        return self._ensure_docstring_block(text)

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

        prompt = (
            f"{_SUMMARY_SYSTEM}\n\n"
            f"File: `{file_path}`\n\n"
            f"Parsed functions/methods:\n{manifest}\n\n"
            f"Full source code:\n```\n{source_code[:6000]}\n```\n\n"
            "Produce the file summary now."
        )

        return self._retry_generate(prompt)
