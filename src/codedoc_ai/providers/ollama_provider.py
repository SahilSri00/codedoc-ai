"""
Ollama provider for CodeDoc-AI.

Implements the LLMProvider interface using a local Ollama server.
100% offline — no API keys needed, no data leaves your machine.

Requires:
- Ollama installed: https://ollama.ai
- A model pulled: ``ollama pull llama3.1``
- Server running: ``ollama serve`` (default: http://localhost:11434)
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from ..models.schemas import FunctionSchema
from .base import LLMProvider

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


class OllamaProvider(LLMProvider):
    """LLM provider using a local Ollama server (100% offline)."""

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
    ):
        self._model = os.getenv("OLLAMA_MODEL", model)
        self._base_url = os.getenv("OLLAMA_BASE_URL", base_url).rstrip("/")

        # Verify Ollama is reachable
        try:
            urlopen(f"{self._base_url}/api/tags", timeout=5)
        except (URLError, OSError) as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. "
                "Make sure Ollama is running: ollama serve"
            ) from exc

    def _chat(self, messages: list, temperature: float = 0.2, max_tokens: int = 600) -> str:
        """Send a chat request to the Ollama API."""
        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }).encode("utf-8")

        req = Request(
            f"{self._base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("message", {}).get("content", "").strip()
        except Exception as exc:
            print(f"[Ollama] API call failed: {exc}")
            return ""

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

        text = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )

        if text and not text.startswith('"""'):
            text = f'"""\n{text.strip("`")}\n"""'
        return text

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

        return self._chat(
            [
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=600,
        )
