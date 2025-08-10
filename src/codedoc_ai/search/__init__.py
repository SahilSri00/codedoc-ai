import chromadb
from pathlib import Path
from typing import List, Dict, Any
from ..embedder import embed_text
import typer

#CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / ".codedoc-ai"
CHROMA_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".codedoc-ai"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

print(f"[SEARCH] ChromaDB path: {CHROMA_DIR.resolve()}")


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

def query(q: str, lang: str = "py", top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Semantic search against the ChromaDB index.
    Returns a list of hit dicts with id, document, metadata, and distance.
    """
    # Normalize language alias
    key = lang.lower()
    if key not in LANG_ALIASES:
        typer.secho(f"Unsupported language '{lang}'. Available: {', '.join(LANG_ALIASES.keys())}", fg="red")
        raise typer.Exit(1)
    normalized = LANG_ALIASES[key]

    client = chromadb.PersistentClient(str(CHROMA_DIR))
    coll_name = f"functions_{normalized}"
    try:
        collection = client.get_collection(coll_name)
    except Exception:
        typer.secho(f"Collection '{coll_name}' does not exist. Did you run 'codedoc-ai index'?", fg="red")
        raise typer.Exit(1)

    # Embed the query text
    emb = embed_text(q)

    # Perform the vector search
    results = collection.query(query_embeddings=[emb], n_results=top_k)

    # Extract and return structured hits
    hits: List[Dict[str, Any]] = []
    for idx in range(len(results["ids"][0])):
        hits.append({
            "id": results["ids"][0][idx],
            "document": results["documents"][0][idx],
            "metadata": results["metadatas"][0][idx],
            "distance": results["distances"][0][idx] if "distances" in results else None,
        })

    return hits
