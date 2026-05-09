"""
base.py — Abstract base class for all LLM providers in CodeDoc-AI.

Every provider must implement two methods:
- ``generate_doc``  — per-function docstring generation
- ``summarize_file`` — high-level file summary generation

This allows the pipeline (generator.py, injector.py) to work with any LLM
without knowing the concrete provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from ..models.schemas import FunctionSchema


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Subclasses must implement ``generate_doc`` and ``summarize_file``.
    """

    name: str = "base"

    @abstractmethod
    def generate_doc(self, func: FunctionSchema) -> str:
        """
        Generate a Google-style docstring for a single function.

        Args:
            func: Parsed function schema with source code, args, return type, etc.

        Returns:
            Raw docstring text (will be formatted by the injector into
            language-native comment syntax), or empty string on failure.
        """
        ...

    @abstractmethod
    def summarize_file(
        self,
        file_path: Path,
        functions: List[FunctionSchema],
        source_code: Optional[str] = None,
    ) -> str:
        """
        Generate a high-level Markdown summary for an entire file.

        Args:
            file_path: Path to the source file.
            functions: Parsed function schemas from the file.
            source_code: Full source text. Read from disk if not provided.

        Returns:
            Markdown-formatted file summary string, or empty string on failure.
        """
        ...
