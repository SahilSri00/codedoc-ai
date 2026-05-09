import typer
from pathlib import Path
from rich.console import Console
from codedoc_ai.router import detect_and_parse , detect_lang
from codedoc_ai.generator import generate as generate_docs
from codedoc_ai.search import query as search_query
from codedoc_ai.indexer import build_index
from codedoc_ai.injector import inject_docstrings

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
        console.print("[red]File not found[/red]")
        raise typer.Exit(1)

    functions = detect_and_parse(file)
    for f in functions:
        console.print_json(data=f.model_dump())

# --------------------------------
# CLI 2 : generate docs
# --------------------------------
@app.command()
def generate(
    file: Path,
    out: Path = typer.Option(Path("docs/generated"), "--out", help="Output directory for docs"),
):
    """Generate hybrid LLM docs (Gemini deep, Groq summary)."""
    file = file.resolve()
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    if file.is_dir():
        paths = [p for p in file.rglob("*") if p.is_file()]
    else:
        paths = [file]

    for path in paths:
        try:
            lang = detect_lang(path)
            if lang == "unknown":
                console.print(f"[yellow]Skipping {path} (unknown language)[/yellow]")
                continue
            result = generate_docs(path)
            md_path = out / f"{path.stem}.md"
            with open(md_path, "w", encoding="utf-8") as md_file:
                md_file.write(result["summary"])
            console.print(f"[green]✅ Docs saved to {md_path}[/green]")
        except Exception as e:
            console.print(f"[red]Error processing {path}[/red]: {e}")



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
# CLI 5 : inject docstrings
# --------------------------------
@app.command()
def inject(
    file: Path,
    replace: bool = typer.Option(False, "--replace", help="Overwrite existing docstrings"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    backup: bool = typer.Option(False, "--backup", help="Create .bak copy before modifying"),
    out: Path = typer.Option(None, "--out", help="Write documented copy to this directory (original untouched)"),
):
    """Inject AI-generated docstrings directly into source files."""
    file = file.resolve()

    if not file.exists():
        console.print("[red]File or directory not found[/red]")
        raise typer.Exit(1)

    # Collect files to process
    if file.is_dir():
        paths = [p for p in file.rglob("*") if p.is_file()]
    else:
        paths = [file]

    total_injected = 0
    total_skipped = 0

    for path in paths:
        try:
            lang = detect_lang(path)
            if lang == "unknown":
                continue

            console.print(f"\n[bold]📄 {path.name}[/bold]")
            result = inject_docstrings(
                path,
                replace=replace,
                dry_run=dry_run,
                backup=backup,
                out_dir=out,
            )
            total_injected += result["injected"]
            total_skipped += result["skipped"]

            if not dry_run:
                mode = f"→ {result['file']}" if out else "(in-place)"
                console.print(f"  [green]✅ {result['injected']} injected, {result['skipped']} skipped {mode}[/green]")

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")

    console.print(f"\n[bold green]Done![/bold green] {total_injected} docstrings injected, {total_skipped} skipped.")

# --------------------------------
# Entry-point
# --------------------------------
if __name__ == "__main__":
    app()
