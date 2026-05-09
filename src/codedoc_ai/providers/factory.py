"""
factory.py — Provider factory for CodeDoc-AI.

Reads ``CODEDOC_PROVIDER`` from .env (default: "groq") and returns the
appropriate LLMProvider instance. Can be overridden at runtime via the
``--provider`` CLI flag.

Supported providers:
- ``groq``    — Groq API (Llama 3.1 8B Instant) [default]
- ``gemini``  — Google Gemini 2.0 Flash
- ``openai``  — OpenAI API (GPT-4o-mini)
- ``ollama``  — Local Ollama server (100% offline)
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

from .base import LLMProvider

load_dotenv()

# Cache the provider instance
_cached_provider: Optional[LLMProvider] = None
_cached_name: Optional[str] = None

SUPPORTED_PROVIDERS = ("groq", "gemini", "openai", "ollama")


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """
    Return an LLMProvider instance for the given provider name.

    Args:
        name: Provider name ("groq", "gemini", "openai", "ollama").
              If None, reads from ``CODEDOC_PROVIDER`` env var (default: "groq").

    Returns:
        A configured LLMProvider instance (cached after first call).
    """
    global _cached_provider, _cached_name

    if name is None:
        name = os.getenv("CODEDOC_PROVIDER", "groq").lower().strip()

    # Return cached instance if same provider
    if _cached_provider is not None and _cached_name == name:
        return _cached_provider

    if name == "groq":
        from .groq import GroqProvider
        _cached_provider = GroqProvider()

    elif name == "gemini":
        from .gemini_provider import GeminiProvider
        _cached_provider = GeminiProvider()

    elif name == "openai":
        from .openai_provider import OpenAIProvider
        _cached_provider = OpenAIProvider()

    elif name == "ollama":
        from .ollama_provider import OllamaProvider
        _cached_provider = OllamaProvider()

    else:
        raise ValueError(
            f"Unknown provider '{name}'. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    _cached_name = name
    return _cached_provider
