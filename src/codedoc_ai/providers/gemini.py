from __future__ import annotations

import os
import json
import time
from typing import List, Optional
from pathlib import Path

from dotenv import load_dotenv
import google.generativeai as genai

from ..models.schemas import FunctionSchema

# ----------------------------
# Environment & Client Setup
# ----------------------------
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to your environment or GitHub Secrets.")

genai.configure(api_key=GEMINI_API_KEY)

DEFAULT_MODEL_NAME = os.getenv("CODEDOC_GEMINI_MODEL", "gemini-2.0-flash")

GENERATION_CONFIG = {
    "temperature": float(os.getenv("CODEDOC_GEMINI_TEMPERATURE", "0.2")),
    "top_p": float(os.getenv("CODEDOC_GEMINI_TOP_P", "0.9")),
    "top_k": int(os.getenv("CODEDOC_GEMINI_TOP_K", "40")),
    "max_output_tokens": int(os.getenv("CODEDOC_GEMINI_MAX_TOKENS", "2048")),
}

SAFETY_SETTINGS = None

MODEL = genai.GenerativeModel(
    model_name=DEFAULT_MODEL_NAME,
    generation_config=GENERATION_CONFIG,
    safety_settings=SAFETY_SETTINGS,
)

# ----------------------------
# System Instructions
# ----------------------------
DOCSTRING_SYSTEM = """You are a senior software engineer and technical writer.
Given a function signature and body, return ONLY a Google-style docstring, enclosed in triple double-quotes.
Include sections if applicable: 1-line summary, Args (with types), Returns, Raises (if any).
Be concise and precise. Do not include extra prose, backticks, or markdown outside the docstring.
"""

FILE_DOC_SYSTEM = """You are a senior technical writer producing professional documentation for an entire code file.
Write structured, multi-paragraph documentation covering:
1. Overview — purpose of the file and its role in a larger system.
2. Detailed Function/Class Descriptions — purpose, key parameters/behavior, and notable exceptions.
3. Interactions — how functions/classes relate and flow.
4. Potential Edge Cases — limitations, performance, or correctness pitfalls.
5. Example Usage — short, relevant code snippet(s) if useful.

Style: crisp, professional, actionable. Avoid filler. Use plain text (no markdown fences). Keep sections clearly labeled.
"""

COMBINED_DOC_SYSTEM = """You are a senior software engineer and technical writer.
Produce documentation in the following exact structure:

# Summary
<Full professional file summary, as described in FILE_DOC_SYSTEM.>

For each function or class method below, write:

## <function_name>
<Google-style docstring inside triple double quotes, as described in DOCSTRING_SYSTEM.>

Do not skip any function, even if it already has a docstring.
Do not include any Markdown code fences except the triple double quotes for docstrings.
"""

# ----------------------------
# Helpers
# ----------------------------
def _get_language_from_path(path: str) -> str:
    ext = Path(path).suffix.lower().lstrip(".")
    return {
        "py": "Python",
        "js": "JavaScript",
        "ts": "TypeScript",
        "java": "Java",
        "rs": "Rust",
        "go": "Go",
        "cpp": "C++",
        "hpp": "C++",
        "cc": "C++",
        "cxx": "C++",
        "c": "C",
    }.get(ext, ext or "source code")

def _retry_generate_content(prompt: str, retries: int = 2, backoff: float = 1.5) -> Optional[str]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = MODEL.generate_content(prompt)
            text = getattr(resp, "text", None)
            if text:
                return text
            if hasattr(resp, "candidates") and resp.candidates:
                for cand in resp.candidates:
                    if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                        parts_text = "".join(getattr(p, "text", "") for p in cand.content.parts)
                        if parts_text.strip():
                            return parts_text
            return None
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
            else:
                print(f"[Gemini] Failed after {retries+1} attempts: {e}")
    return None

def _ensure_docstring_block(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
    if not s.startswith('"""'):
        s = f'"""\n{s}\n"""'
    return s

# ----------------------------
# Public API
# ----------------------------
def generate_doc(func: FunctionSchema) -> str:
    language = _get_language_from_path(func.file_path or "")
    existing = func.docstring or "None"

    function_blob = {
        "name": func.name,
        "language": language,
        "file_path": func.file_path,
        "start_line": func.start_line,
        "end_line": func.end_line,
        "arguments": func.args,
        "return_type": func.return_type or "",
        "existing_docstring": existing,
        "source_code": func.source_code or "",
    }

    prompt = (
        f"{DOCSTRING_SYSTEM}\n\n"
        f"Function metadata (JSON):\n{json.dumps(function_blob, ensure_ascii=False, indent=2)}\n\n"
        "Return ONLY the Google-style docstring (triple double-quoted)."
    )

    text = _retry_generate_content(prompt)
    if not text:
        return ""
    return _ensure_docstring_block(text)

def generate_file_documentation(file_path: Path, functions: List[FunctionSchema]) -> str:
    file_path = Path(file_path)
    if not file_path.exists():
        return ""

    try:
        code_content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[Gemini] Could not read file {file_path}: {e}")
        return ""

    language = _get_language_from_path(file_path.name)

    parsed_info = [
        {
            "name": f.name,
            "args": f.args,
            "return_type": f.return_type or "",
            "has_existing_docstring": bool(f.docstring),
            "start_line": f.start_line,
            "end_line": f.end_line,
        }
        for f in functions
    ]

    prompt = (
        f"{FILE_DOC_SYSTEM}\n\n"
        f"File: {str(file_path)}\n"
        f"Language: {language}\n\n"
        f"Parsed elements (JSON):\n{json.dumps(parsed_info, ensure_ascii=False, indent=2)}\n\n"
        "Full source code follows:\n"
        "----- BEGIN SOURCE -----\n"
        f"{code_content}\n"
        "----- END SOURCE -----\n\n"
        "Produce the documentation now."
    )

    text = _retry_generate_content(prompt)
    return (text or "").strip()

def generate_combined_file_output(file_path: Path, functions: List[FunctionSchema]) -> str:
    """Generate a single document containing file summary and per-function docstrings."""
    file_path = Path(file_path)
    if not file_path.exists():
        return ""

    try:
        code_content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[Gemini] Could not read file {file_path}: {e}")
        return ""

    language = _get_language_from_path(file_path.name)

    parsed_info = [
        {
            "name": f.name,
            "args": f.args,
            "return_type": f.return_type or "",
            "source_code": f.source_code or "",
        }
        for f in functions
    ]

    prompt = (
        f"{COMBINED_DOC_SYSTEM}\n\n"
        f"File: {str(file_path)}\n"
        f"Language: {language}\n\n"
        f"Parsed elements (JSON):\n{json.dumps(parsed_info, ensure_ascii=False, indent=2)}\n\n"
        "Full source code follows:\n"
        "----- BEGIN SOURCE -----\n"
        f"{code_content}\n"
        "----- END SOURCE -----\n\n"
        "Produce the combined output now."
    )

    return (_retry_generate_content(prompt) or "").strip()

def generate_docs_for_functions(functions: List[FunctionSchema]) -> List[str]:
    return [generate_doc(f) for f in functions]
