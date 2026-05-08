import chromadb
from pathlib import Path
from typing import List, Set

from ..embedder import embed_function
from ..router import detect_and_parse
from ..utils.ids import make_unique_id_uuid

CHROMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".codedoc-ai"
CHROMA_PATH.mkdir(parents=True, exist_ok=True)


def clear_chroma_collection(client: chromadb.PersistentClient, collection_name: str) -> None:
    """Clear an existing ChromaDB collection to avoid stale/duplicate data on re-index."""
    try:
        collection = client.get_collection(collection_name)
        all_data = collection.get()
        if all_data["ids"]:
            collection.delete(ids=all_data["ids"])
            print(f"  Cleared {len(all_data['ids'])} existing items from '{collection_name}'")
    except Exception:
        # Collection doesn't exist yet — nothing to clear
        pass


def build_index(repo_root: Path, lang: str = "py") -> None:
    """
    Scan *repo_root* for source files of the given *lang*, parse every function/method,
    embed them with sentence-transformers (all-MiniLM-L6-v2), and store them in a
    persistent ChromaDB collection named ``functions_<lang>``.

    IDs are generated with UUID5 (deterministic, collision-safe) via
    ``utils.ids.make_unique_id_uuid`` — the same strategy used by every parser.
    """
    client = chromadb.PersistentClient(str(CHROMA_PATH))
    coll_name = f"functions_{lang}"

    # Start fresh so re-indexing is always clean
    clear_chroma_collection(client, coll_name)
    collection = client.get_or_create_collection(name=coll_name)

    # Collect files, skipping virtual envs and build artifacts
    EXCLUDE = {".venv", "venv", "__pycache__", ".git", "node_modules", "dist", "build"}
    files = [
        f
        for f in repo_root.glob(f"**/*.{lang}")
        if f.is_file() and not any(part in EXCLUDE for part in f.parts)
    ]

    if not files:
        raise RuntimeError(f"No .{lang} files found in {repo_root}")

    print(f"Found {len(files)} .{lang} file(s) to index in {repo_root}")

    # --- Parse ---
    functions: List = []
    seen_ids: Set[str] = set()

    for file in files:
        try:
            funcs = detect_and_parse(file)
            print(f"  Parsed {file.relative_to(repo_root)} → {len(funcs)} function(s)")
            for func in funcs:
                # UUID5 IDs are deterministic — collision is theoretically impossible,
                # but guard anyway for safety.
                uid = make_unique_id_uuid(lang, func.name, func.file_path, func.start_line, 0)
                if uid in seen_ids:
                    import time
                    uid = f"{uid}_{int(time.time() * 1_000_000)}"
                    print(f"  [WARN] Collision resolved with timestamp suffix for {func.name}")
                seen_ids.add(uid)
                func.id = uid
                functions.append(func)
        except Exception as exc:
            print(f"  [ERROR] Skipping {file}: {exc}")

    if not functions:
        print("No functions found — nothing to index.")
        return

    print(f"Total functions to embed & index: {len(functions)}")

    # --- Embed & store ---
    docs, ids, metadatas, embeds = [], [], [], []

    for i, func in enumerate(functions):
        if i % 50 == 0:
            print(f"  Embedding {i + 1}/{len(functions)}…")

        docs.append(f"{func.name} {func.docstring or ''}")
        ids.append(func.id)
        metadatas.append(
            {
                "name": func.name,
                "docstring": func.docstring or "",
                "args": ", ".join(func.args) if func.args else "",
                "return_type": func.return_type or "",
                "start_line": func.start_line,
                "end_line": func.end_line,
                "file_path": func.file_path,
            }
        )
        try:
            embeds.append(embed_function(func))
        except Exception as exc:
            print(f"  [WARN] Embedding failed for {func.name}: {exc} — using zero vector")
            embeds.append([0.0] * 384)

    # Batch insert with per-item fallback
    BATCH = 500
    total_added = 0

    for start in range(0, len(functions), BATCH):
        end = min(start + BATCH, len(functions))
        try:
            collection.add(
                documents=docs[start:end],
                metadatas=metadatas[start:end],
                ids=ids[start:end],
                embeddings=embeds[start:end],
            )
            total_added += end - start
            print(f"  Stored batch {start // BATCH + 1}: {total_added}/{len(functions)}")
        except Exception as batch_err:
            print(f"  [ERROR] Batch {start // BATCH + 1} failed ({batch_err}), retrying item-by-item…")
            for j in range(end - start):
                try:
                    collection.add(
                        documents=[docs[start + j]],
                        metadatas=[metadatas[start + j]],
                        ids=[ids[start + j]],
                        embeddings=[embeds[start + j]],
                    )
                    total_added += 1
                except Exception as item_err:
                    print(f"    [ERROR] Skipped {ids[start + j]}: {item_err}")

    print(f"✅ Indexed {total_added}/{len(functions)} functions into '{coll_name}'")


def check_collection_status(lang: str = "py") -> int:
    """Return the number of items in a ChromaDB collection, or 0 if it doesn't exist."""
    try:
        client = chromadb.PersistentClient(str(CHROMA_PATH))
        collection = client.get_collection(f"functions_{lang}")
        count = collection.count()
        print(f"Collection 'functions_{lang}' contains {count} item(s)")
        sample = collection.get(limit=5)
        print("Sample IDs:", sample["ids"])
        return count
    except Exception as exc:
        print(f"Error checking collection status: {exc}")
        return 0
