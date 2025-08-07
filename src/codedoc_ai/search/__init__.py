import chromadb
from pathlib import Path
from typing import List
from ..embedder import embed_text

CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / ".codedoc-ai"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

def query(q: str, lang: str = "py", top_k: int = 3):
    client = chromadb.PersistentClient(str(CHROMA_DIR))
    coll = client.get_collection(f"functions_{lang}")
    from ..embedder import embed_text
    emb = embed_text(q)
    hits = coll.query(query_embeddings=[emb], n_results=top_k)
    return hits["metadatas"][0]