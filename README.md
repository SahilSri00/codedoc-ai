# codedoc-ai

> **AI-powered code documentation for any codebase — using a hybrid Gemini + Groq pipeline.**

`codedoc-ai` is a CLI tool that reads your source files, parses every function and class with language-specific ASTs, and generates rich, professional documentation using two complementary LLMs:

| Model | Provider | Role |
|---|---|---|
| **Gemini 2.0 Flash** | Google | Per-function Google-style docstrings (precise, typed) |
| **Llama 3.1 8B Instant** | Groq | High-level file summaries (fast, conversational) |

Combine the two and you get documentation that is both **technically accurate** and **human readable** — without the cost and latency of a single heavyweight model doing everything.

---

## Supported Languages

| Language | Extension(s) |
|---|---|
| Python | `.py` |
| JavaScript / TypeScript | `.js`, `.ts`, `.mjs`, `.tsx` |
| Java | `.java` |
| Go | `.go` |
| Rust | `.rs` |
| C / C++ | `.cpp`, `.cc`, `.h`, `.hpp` |

---

## Installation

Requires Python **3.11**.

```bash
# Install dependencies
poetry install

# Activate the virtual environment
poetry shell
```

---

## Configuration

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# Optional overrides
CODEDOC_GEMINI_MODEL=gemini-2.0-flash
CODEDOC_GEMINI_TEMPERATURE=0.2
CODEDOC_GEMINI_MAX_TOKENS=2048
```

Get your keys:
- Gemini: https://aistudio.google.com/app/apikey
- Groq: https://console.groq.com/keys

---

## CLI Commands

### `parse` — Inspect AST output

Extract structured function metadata from any supported file.

```bash
codedoc-ai parse path/to/file.py
```

Prints JSON for each function: name, args, return type, docstring, source lines.

---

### `generate` — Generate documentation

Run the hybrid LLM pipeline and save Markdown docs.

```bash
# Single file
codedoc-ai generate path/to/file.py

# Entire directory (auto-detects language)
codedoc-ai generate src/ --out docs/generated
```

Output format per file:
```
## Overview          ← Groq (Llama 3.1): readable file summary
## Key Components    ← Groq: bullet list of functions
## Data Flow         ← Groq: how data moves through the file
---
### `function_name`  ← Gemini: Google-style docstring per function
```

---

### `index` — Build the vector search index

Embed every function in a repo and store it in ChromaDB for semantic search.

```bash
# Auto-detect language
codedoc-ai index ./my-repo

# Specify language explicitly
codedoc-ai index ./my-repo --lang py
```

The index is stored in `.codedoc-ai/` (gitignored).

---

### `ask` — Semantic search over your codebase

Ask a natural-language question and get the most relevant functions back.

```bash
codedoc-ai ask "function that parses a file" --lang py
codedoc-ai ask "how is authentication handled" --lang java
```

Returns the top 3 matching functions with file path, line numbers, and similarity distance.

---

## Project Structure

```
src/codedoc_ai/
├── main.py          ← Typer CLI entry-point
├── router.py        ← Language detection + parser dispatch
├── generator.py     ← Orchestrates the hybrid LLM pipeline
├── parser/          ← Per-language AST parsers (tree-sitter + stdlib ast)
├── providers/
│   ├── gemini.py    ← Gemini 2.0 Flash — per-function docstrings
│   └── groq.py      ← Groq Llama 3.1 — file-level summaries
├── embedder/        ← sentence-transformers (all-MiniLM-L6-v2)
├── indexer/         ← ChromaDB index builder
├── search/          ← Semantic vector search
├── models/schemas.py ← Pydantic FunctionSchema
└── utils/ids.py     ← UUID5 deterministic ID generation
```

---

## How IDs Work

Every parsed function gets a **UUID5 deterministic ID** derived from:
```
lang : function_name : file_path : start_line : start_col
```

The same function always produces the same ID — re-indexing is safe and idempotent.

---

## License

MIT