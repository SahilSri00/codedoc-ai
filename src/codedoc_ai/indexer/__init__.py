import chromadb
from pathlib import Path
from typing import List
from ..embedder import embed_function
from ..router import detect_and_parse

#CHROMA_PATH = Path(__file__).resolve().parent.parent.parent / ".codedoc-ai"
CHROMA_PATH = Path(".codedoc-ai")  # folder, not file
CHROMA_PATH.mkdir(parents=True, exist_ok=True)

def build_index(repo_root: Path, lang: str = "py"):
    client = chromadb.PersistentClient(str(CHROMA_PATH))
    coll_name = f"functions_{lang}"
    collection = client.get_or_create_collection(name=coll_name)

    pattern = f"**/*.{lang}"
    files = list(repo_root.glob(pattern))
    if not files:
        raise RuntimeError(f"No .{lang} files found in {repo_root}")

    functions: List = []
    for file in files:
        funcs = detect_and_parse(file)
        print(f"Parsed {file} → {len(funcs)} functions")
        functions.extend(funcs)

    if not functions:
        #print(f"No functions found in .{lang} files; nothing to index.")
        print("No functions to index.")
        return

    docs   = [f"{f.name} {f.docstring or ''}" for f in functions]
    ids    = [f"{lang}_{f.name}_{f.start_line}" for f in functions]
    embeds = [embed_function(f) for f in functions]

    collection.add(
        documents=docs,
        metadatas=[
        {
            "name": f.name,
            "docstring": f.docstring or "",
            "args": ", ".join(f.args),          # ← list → string
            "return_type": f.return_type or "",
            "start_line": f.start_line,
            "end_line": f.end_line,
        }
        for f in functions
    ],
        ids=ids,
        embeddings=embeds,
    )