# codedoc-ai

> **AI-powered docstring generation and injection for multiple languages, backed by a single pluggable LLM provider (Groq, Gemini, OpenAI, or Ollama).**

`codedoc-ai` is a CLI tool that parses your source files with language-specific parsers (Python's built-in `ast` and Tree-sitter grammars), extracts each function/method, and uses an LLM to generate documentation. It can print structured metadata, produce standalone Markdown docs, and **safely** inject doc comments back into your source files.

You choose **one** provider at a time (default: Groq / Llama 3.1 8B Instant) via `CODEDOC_PROVIDER` in `.env` or `--provider` per command. The same provider generates both the per-function docstrings and the file summary.

### Scope

CodeDoc-AI is a **documentation generator**, not a code analyzer, linter, or type checker. It extracts functions/methods, generates natural-language docs with one configurable LLM, and can inject them back into source safely. It does **not** evaluate documentation quality, verify the factual accuracy of generated text, or route between multiple models. See [Known limitations](#known-limitations).

---

## Supported Languages

Function extraction (the `parse` command) is smoke-tested for all of the
languages below. "Injection test coverage" means an automated round-trip test
in `tests/` exercises `inject` end to end for that language:

| Language | Extension(s) | Parser | Injection test coverage |
|---|---|---|---|
| Python | `.py` | stdlib `ast` | ✅ golden round-trip test |
| Rust | `.rs` | Tree-sitter | ✅ golden round-trip test |
| Java | `.java` | Tree-sitter | ⚠️ safety-gated, no golden test yet |
| JavaScript / TypeScript | `.js`, `.ts`, `.mjs`, `.tsx` | Tree-sitter | ⚠️ safety-gated, no golden test yet |
| Go | `.go` | Tree-sitter | ⚠️ safety-gated, no golden test yet |
| C / C++ | `.cpp`, `.cc`, `.h`, `.hpp` | Tree-sitter | ⚠️ safety-gated, no golden test yet |

Regardless of language, injection is **fail-closed** — see [Injection safety](#injection-safety).

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
# Choose your LLM provider: groq (default), gemini, openai, ollama
CODEDOC_PROVIDER=groq

# Provider API keys (only the one you're using needs to be set)
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Ollama (local, no API key needed)
# OLLAMA_MODEL=llama3.1
# OLLAMA_BASE_URL=http://localhost:11434
```

Get your keys:
- Groq: https://console.groq.com/keys (free tier)
- Gemini: https://aistudio.google.com/app/apikey
- OpenAI: https://platform.openai.com/api-keys
- Ollama: https://ollama.ai (local, no key needed)

Or override per-command: `codedoc-ai generate file.py --provider openai`

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

Generate Markdown docs with the configured provider: a docstring for every
function plus a high-level file summary, merged into one document.

```bash
# Single file
codedoc-ai generate path/to/file.py

# Entire directory (auto-detects language)
codedoc-ai generate src/ --out docs/generated
```

Each source file produces one Markdown file: the file summary first, then a
`## Function Documentation` section with one entry per function. Every section
is produced by the single configured provider (there is no per-section model
routing).

---

### `inject` — Inject docstrings into source code

Generates doc comments and writes them **into your source files** using each
language's native comment syntax.

**Safe by default:** `inject` runs as a **dry-run preview** unless you pass
`--write`. Every write is validated before it touches disk (the result must
still parse and must contain the same number of functions), the write is
atomic, and a `.bak` backup is kept unless you pass `--no-backup`. If
validation fails, the file is left untouched. See
[Injection safety](#injection-safety).

```bash
# Preview changes (default — nothing is written)
codedoc-ai inject path/to/file.java

# Actually write the changes (atomic; keeps a .bak backup)
codedoc-ai inject path/to/file.java --write

# Write without creating a .bak backup
codedoc-ai inject path/to/file.java --write --no-backup

# Write a documented copy elsewhere (original untouched)
codedoc-ai inject path/to/file.java --write --out docs/injected/

# Replace existing docstrings with fresh ones
codedoc-ai inject path/to/file.java --write --replace

# Process an entire directory
codedoc-ai inject src/ --write --out docs/injected/
```

**Before:**
```java
public class Demo1 {
    public int add(int a, int b, int c) {
        return a + b - c;
    }
}
```

**After:**
```java
public class Demo1 {
    /**
     * Adds three integers together, subtracting the third from the sum.
     *
     * @param a The first integer to add.
     * @param b The second integer to add.
     * @param c The integer to subtract from the sum.
     * @return The result of (a + b - c).
     */
    public int add(int a, int b, int c) {
        return a + b - c;
    }
}
```

Language-specific formats: Python `"""..."""`, Java/JS `/** */`, Go `//`, Rust `///`, C++ `/** */`.

#### Injection safety

`inject` is **fail-closed**. Before writing any file it:

1. **Parses the proposed result** (Python via `ast`, other languages via Tree-sitter) and refuses to write if it no longer parses.
2. **Checks a structural invariant** — the number of functions must be unchanged, so documentation can never add or delete code.
3. **Writes atomically** via a temp file + `os.replace`, so an interrupted run can't leave a half-written file.
4. **Preserves encoding and line endings** (strict UTF-8; CRLF/LF kept as-is) and keeps a `.bak` backup unless `--no-backup` is passed.

If any check fails, the run is reported as *aborted* and the original file is left byte-for-byte unchanged. This behaviour is covered by automated tests in [`tests/test_injector_safety.py`](tests/test_injector_safety.py).

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

### Diff-Aware Mode (All Commands)

All commands that process files (`generate`, `inject`, `index`) support diff-aware mode to skip unchanged files:

```bash
# Hash-based: skip files unchanged since last run (works everywhere)
codedoc-ai generate src/ --changed-only
codedoc-ai inject src/ --changed-only
codedoc-ai index . --changed-only

# Git-based: only process files changed in git
codedoc-ai generate src/ --git-diff
codedoc-ai inject src/ --git-diff
```

File hashes are stored in `.codedoc-ai/manifest.json`. On large repos, this saves significant time and LLM API calls.

---

## Project Structure

```
src/codedoc_ai/
├── main.py          ← Typer CLI entry-point (5 commands)
├── router.py        ← Language detection + parser dispatch
├── generator.py     ← Orchestrates the LLM doc pipeline (single provider)
├── injector.py      ← Docstring injection engine (in-place + copy)
├── safety.py        ← Fail-closed validation for the injector
├── tracker.py       ← Diff-aware file change tracking (hash + git)
├── parser/          ← Per-language parsers (Tree-sitter + stdlib ast)
├── providers/
│   ├── base.py            ← LLMProvider abstract base
│   ├── factory.py         ← Provider selection (env / --provider)
│   ├── groq.py            ← Groq (Llama 3.1) — default
│   ├── gemini_provider.py ← Google Gemini
│   ├── openai_provider.py ← OpenAI
│   └── ollama_provider.py ← Ollama (local)
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

## Testing

```bash
poetry run python -m pytest tests -v
```

Tests are fully **offline and deterministic** — the LLM provider is replaced
with a fake, so no API keys or network access are required. The suite covers
the injector's safety guarantees and Python/Rust round-trip injection, and CI
runs it on every push and pull request.

---

## Known limitations

- **Python docstring placement:** injected docs are placed *above* the `def`
  line, so in Python they read as a comment / module-level string rather than a
  `__doc__` docstring inside the function body. (Doc comments above the
  declaration are the idiomatic form for Java, JS, Go, Rust, and C++.)
- **Decorated / async Python functions:** the Python parser handles `def` only
  (not `async def`), and for a decorated function the injector would place the
  block between the decorator and the `def` — which breaks syntax, so the
  safety gate **aborts** and leaves the file unchanged rather than documenting it.
- **Generation quality is not evaluated:** there is no automated check that the
  generated text is accurate or complete; output reflects whatever the chosen
  LLM returns.
- **One provider at a time:** there is no multi-model routing.

---

## License

MIT