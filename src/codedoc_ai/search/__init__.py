import chromadb
from pathlib import Path
from typing import List, Dict, Any

import typer

from ..embedder import embed_text

CHROMA_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".codedoc-ai"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# Language alias → canonical code
LANG_ALIASES = {
    "py": "py",
    "python": "py",
    "js": "js",
    "javascript": "js",
    "ts": "js",
    "typescript": "js",
    "java": "java",
    "rs": "rust",
    "rust": "rust",
    "go": "go",
    "cpp": "cpp",
    "c++": "cpp",
}


def query(q: str, lang: str = "py", top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Semantic search against the ChromaDB index built by ``codedoc-ai index``.

    Args:
        q: Natural-language query (e.g. "function that parses a file").
        lang: Source language of the index to search (default ``"py"``).
        top_k: Number of nearest-neighbour results to return (default 3).

    Returns:
        List of hit dicts, each with keys: ``id``, ``document``, ``metadata``, ``distance``.
    """
    key = lang.lower()
    if key not in LANG_ALIASES:
        typer.secho(
            f"Unsupported language '{lang}'. Available: {', '.join(LANG_ALIASES)}",
            fg="red",
        )
        raise typer.Exit(1)

    normalized = LANG_ALIASES[key]
    client = chromadb.PersistentClient(str(CHROMA_DIR))
    coll_name = f"functions_{normalized}"

    try:
        collection = client.get_collection(coll_name)
    except Exception:
        typer.secho(
            f"Collection '{coll_name}' does not exist. Run 'codedoc-ai index' first.",
            fg="red",
        )
        raise typer.Exit(1)

    emb = embed_text(q)
    results = collection.query(query_embeddings=[emb], n_results=top_k)

    hits: List[Dict[str, Any]] = []
    for idx in range(len(results["ids"][0])):
        hits.append(
            {
                "id": results["ids"][0][idx],
                "document": results["documents"][0][idx],
                "metadata": results["metadatas"][0][idx],
                "distance": results["distances"][0][idx] if "distances" in results else None,
            }
        )

    return hits
