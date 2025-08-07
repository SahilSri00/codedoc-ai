from pathlib import Path
from sentence_transformers import SentenceTransformer
from typing import List

MODEL = SentenceTransformer("all-MiniLM-L6-v2")

def embed_text(text: str) -> List[float]:
    return MODEL.encode(text, normalize_embeddings=True).tolist()

def embed_function(func) -> List[float]:
    payload = f"{func.name}({', '.join(func.args)}) -> {func.return_type}\n{func.docstring or ''}"
    return embed_text(payload)