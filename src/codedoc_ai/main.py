import typer
from pathlib import Path
from rich.console import Console
from codedoc_ai.router import detect_and_parse
from codedoc_ai.generator import generate as generate_docs
from codedoc_ai.search import query as search_query
from codedoc_ai.indexer import build_index

console = Console(stderr=True)
app = typer.Typer()


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
def generate(file: Path):
    """Generate hybrid LLM docs (Gemini deep, Groq summary)."""
    file = file.resolve()
    if not file.exists():
        console.print("[red]File not found[/red]")
        raise typer.Exit(1)

    result = generate_docs(file)
    console.print(f"[bold cyan]Summary:[/bold cyan] {result['summary']}")
    for f in result["functions"]:
        console.print(f"[green]def {f['name']}[/green] ➜ {f['docstring']}")


# --------------------------------
# CLI 3 : semantic search
# --------------------------------
@app.command()
def ask(query: str, lang: str = typer.Option("py", help="Language to search")):
    """Semantic Q&A over the indexed codebase."""
    hits = search_query(query, lang=lang)
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

    build_index(repo_root, lang=lang)
    console.print(f"[green]✅ Indexed .{lang} files in {repo_root}[/green]")


# --------------------------------
# Entry-point
# --------------------------------
if __name__ == "__main__":
    app()