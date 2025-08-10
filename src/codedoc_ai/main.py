import typer
from pathlib import Path
from rich.console import Console
from codedoc_ai.router import detect_and_parse
from codedoc_ai.generator import generate as generate_docs
from codedoc_ai.search import query as search_query
from codedoc_ai.indexer import build_index

console = Console(stderr=True)
app = typer.Typer()

# Map user-friendly language names to internal codes
LANG_ALIASES = {
    "py": "py",
    "python": "py",
    "js": "js",
    "javascript": "js",
    "ts": "js",
    "java": "java",
    "rs": "rust",
    "rust": "rust",
    "go": "go",
    "cpp": "cpp",
    "c++": "cpp",
}

# --------------------------------
# CLI 1 : inspect AST
# --------------------------------
@app.command()
def parse(file: Path):
    """Extract structured info from any supported file."""
    file = file.resolve()
    if not file.exists():
        console.print("[red]File not found[/red]", err=True)
        raise typer.Exit(1)

    functions = detect_and_parse(file)
    for f in functions:
        console.print_json(data=f.dict())

# --------------------------------
# CLI 2 : generate docs
# --------------------------------
@app.command()
def generate(
    path: Path,
    out: Path = typer.Option(Path("docs/generated"), "--out", help="Output directory for docs"),
):
    """
    Generate hybrid LLM docs (Gemini deep, Groq summary).
    Accepts either a single file or a folder (recursively).
    """

    path = path.resolve()
    if not path.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)

    # Ensure output directory exists
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    # Get list of files to process
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.suffix]

    for file in files:
        result = generate_docs(file)

        # Compose output markdown file path
        md_path = out / f"{file.stem}.md"

        # Write summary and function docstrings to Markdown file
        with open(md_path, "w", encoding="utf-8") as md_file:
            md_file.write(f"# Summary\n\n{result['summary']}\n\n")
            for fdata in result["functions"]:
                md_file.write(f"## {fdata['name']}\n\n")
                if fdata.get("docstring"):
                    md_file.write(f"{fdata['docstring']}\n\n")
                else:
                    md_file.write("_No docstring provided_\n\n")

        console.print(f"[bold cyan]Processed:[/bold cyan] {file}")
        console.print(f"[green]✅ Docs saved to {md_path}[/green]")


# --------------------------------
# CLI 3 : semantic search
# --------------------------------
@app.command()
def ask(query: str, lang: str = typer.Option("py", help="Language to search")):
    """Semantic Q&A over the indexed codebase."""
    key = lang.lower()
    if key not in LANG_ALIASES:
        console.print(f"[red]Unsupported language '{lang}'.[/red]")
        console.print(f"Available languages: {', '.join(LANG_ALIASES.keys())}")
        raise typer.Exit(1)
    normalized = LANG_ALIASES[key]
    hits = search_query(query, lang=normalized)
    console.print_json(data=hits)

# --------------------------------
# CLI 4 : build vector index
# --------------------------------
@app.command()
def index(
    repo_root: Path = typer.Argument(".", help="Root folder to scan"),
    lang: str = typer.Option(
        None,
        help="Language (auto-detected if omitted; choices: py,js,cpp,go,rust,java)",
    ),
):
    """Build Chroma vector index for any supported language."""
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        console.print("[red]Directory not found[/red]")
        raise typer.Exit(1)

    # auto-detect if not provided
    if lang is None:
        exts = {p.suffix.lstrip(".") for p in repo_root.rglob("*") if p.suffix}
        for cand in ("py", "js", "cpp", "go", "rust", "java"):
            if cand in exts:
                lang = cand
                break
        else:
            lang = "py"  # fallback

    key = lang.lower()
    if key not in LANG_ALIASES:
        console.print(f"[red]Unsupported language '{lang}'.[/red]")
        console.print(f"Available languages: {', '.join(LANG_ALIASES.keys())}")
        raise typer.Exit(1)
    normalized = LANG_ALIASES[key]

    build_index(repo_root, lang=normalized)
    console.print(f"[green]✅ Indexed .{normalized} files in {repo_root}[/green]")

# --------------------------------
# Entry-point
# --------------------------------
if __name__ == "__main__":
    app()
