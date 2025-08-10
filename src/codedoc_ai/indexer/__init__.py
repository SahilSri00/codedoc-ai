import chromadb
import hashlib
from pathlib import Path
from typing import List, Set
from ..embedder import embed_function
from ..router import detect_and_parse

#CHROMA_PATH = Path(__file__).resolve().parent.parent.parent / ".codedoc-ai"
#CHROMA_PATH = Path(".codedoc-ai")  # folder, not file
CHROMA_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".codedoc-ai"
CHROMA_PATH.mkdir(parents=True, exist_ok=True)

print(f"[INDEXER] ChromaDB path: {CHROMA_PATH.resolve()}")

def make_unique_id(lang: str, function_name: str, file_path: str, start_line: int, start_col: int = 0) -> str:
    """
    Generate a truly unique ID for a function by incorporating all identifying information.
    """
    # Convert to Path object and get relative path for consistency
    path_obj = Path(file_path)
    
    # Use relative path components to create shorter but unique identifiers
    if len(path_obj.parts) > 2:
        # Use last 2 parts of the path (parent_dir/filename.py)
        relative_path = "/".join(path_obj.parts[-2:])
    else:
        relative_path = str(path_obj.name)  # Just filename if short path
    
    # Create a unique string combining all identifying information
    unique_string = f"{lang}:{function_name}:{relative_path}:{start_line}:{start_col}"
    
    # Create a hash to ensure uniqueness and reasonable length
    hash_obj = hashlib.md5(unique_string.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()[:8]  # Use first 8 characters of hash
    
    # Clean function name for readability
    clean_function_name = function_name.replace('__', '_').replace(' ', '_')[:20]  # Limit length
    
    # Create final ID: lang_functionname_hash
    unique_id = f"{lang}_{clean_function_name}_{hash_hex}"
    
    return unique_id

def clear_chroma_collection(client, collection_name: str):
    """Clear existing collection to avoid duplicate ID issues."""
    try:
        # Try to get the collection and delete all items
        try:
            collection = client.get_collection(collection_name)
            # Get all IDs and delete them
            all_data = collection.get()
            if all_data['ids']:
                collection.delete(ids=all_data['ids'])
                print(f"Cleared {len(all_data['ids'])} items from collection: {collection_name}")
        except Exception:
            # Collection doesn't exist, no need to clear
            pass
    except Exception as e:
        print(f"Error clearing collection {collection_name}: {e}")

def build_index(repo_root: Path, lang: str = "py"):
    """
    Build index with proper duplicate ID handling and error recovery.
    """
    client = chromadb.PersistentClient(str(CHROMA_PATH))
    coll_name = f"functions_{lang}"
    
    # Clear existing collection to start fresh
    clear_chroma_collection(client, coll_name)
    
    # Create new collection
    collection = client.get_or_create_collection(name=coll_name)

    # Find all files to parse
    pattern = f"**/*.{lang}"
    files = list(repo_root.glob(pattern))
    
    # Filter out virtual environment and other unwanted directories
    filtered_files = []
    exclude_patterns = {'.venv', 'venv', '__pycache__', '.git', 'node_modules', 'dist', 'build'}
    
    for file in files:
        # Check if any part of the path contains excluded patterns
        if not any(exclude_part in file.parts for exclude_part in exclude_patterns):
            filtered_files.append(file)
    
    files = filtered_files
    
    if not files:
        raise RuntimeError(f"No .{lang} files found in {repo_root}")

    print(f"Found {len(files)} .{lang} files to process")

    # Parse all functions
    functions: List = []
    seen_ids: Set[str] = set()
    duplicate_count = 0
    
    for file in files:
        try:
            funcs = detect_and_parse(file)
            print(f"Parsed {file.relative_to(repo_root)} → {len(funcs)} functions")
            
            # Process each function and ensure unique IDs
            for func in funcs:
                # Generate unique ID using the new strategy
                unique_id = make_unique_id(lang, func.name, func.file_path, func.start_line, 0)
                
                # Double-check for uniqueness (shouldn't be needed with hash, but safety first)
                if unique_id in seen_ids:
                    # Add timestamp as last resort
                    import time
                    unique_id = f"{unique_id}_{int(time.time()*1000000)}"
                    duplicate_count += 1
                    print(f"WARNING: Had to add timestamp to ID: {unique_id}")
                
                seen_ids.add(unique_id)
                
                # Update the function's ID
                func.id = unique_id
                functions.append(func)
                
        except Exception as e:
            print(f"Error parsing {file}: {e}")
            continue

    if not functions:
        print("No functions found to index.")
        return

    if duplicate_count > 0:
        print(f"WARNING: Found {duplicate_count} duplicate IDs that required timestamp resolution")

    print(f"Total functions to index: {len(functions)}")
    print(f"Sample IDs: {[f.id for f in functions[:5]]}")

    # Prepare data for ChromaDB
    try:
        docs = []
        ids = []
        metadatas = []
        embeds = []
        
        print("Generating embeddings...")
        for i, f in enumerate(functions):
            if i % 100 == 0:  # Progress indicator
                print(f"Processing function {i+1}/{len(functions)}")
            
            # Document text for search
            doc_text = f"{f.name} {f.docstring or ''}"
            docs.append(doc_text)
            
            # Use the unique ID we generated
            ids.append(f.id)
            
            # Metadata
            metadata = {
                "name": f.name,
                "docstring": f.docstring or "",
                "args": ", ".join(f.args) if f.args else "",
                "return_type": f.return_type or "",
                "start_line": f.start_line,
                "end_line": f.end_line,
                "file_path": f.file_path,
            }
            metadatas.append(metadata)
            
            # Generate embedding
            try:
                embed = embed_function(f)
                embeds.append(embed)
            except Exception as e:
                print(f"Error generating embedding for {f.name}: {e}")
                # Use a zero vector as fallback
                embeds.append([0.0] * 384)  # Adjust dimension as needed

        # Add to ChromaDB in batches to handle large datasets
        batch_size = 500
        total_added = 0
        
        for i in range(0, len(functions), batch_size):
            end_idx = min(i + batch_size, len(functions))
            batch_docs = docs[i:end_idx]
            batch_ids = ids[i:end_idx]
            batch_metadatas = metadatas[i:end_idx]
            batch_embeds = embeds[i:end_idx]
            
            try:
                collection.add(
                    documents=batch_docs,
                    metadatas=batch_metadatas,
                    ids=batch_ids,
                    embeddings=batch_embeds,
                )
                total_added += len(batch_ids)
                print(f"Added batch {i//batch_size + 1}: {total_added}/{len(functions)} functions")
                
            except Exception as e:
                print(f"Error adding batch {i//batch_size + 1}: {e}")
                # Try to add items one by one to identify the problematic one
                for j in range(len(batch_ids)):
                    try:
                        collection.add(
                            documents=[batch_docs[j]],
                            metadatas=[batch_metadatas[j]],
                            ids=[batch_ids[j]],
                            embeddings=[batch_embeds[j]],
                        )
                        total_added += 1
                    except Exception as item_error:
                        print(f"Failed to add function {batch_ids[j]}: {item_error}")

        print(f"Successfully indexed {total_added}/{len(functions)} functions")
        
        # Verify collection exists (MOVED INSIDE THE TRY BLOCK)
        try:
            verification_client = chromadb.PersistentClient(str(CHROMA_PATH))
            collections = [c.name for c in verification_client.list_collections()]
            print(f"[VERIFICATION] Available collections: {collections}")
            if coll_name in collections:
                print(f"[VERIFICATION] ✅ Collection '{coll_name}' exists and ready for search")
            else:
                print(f"[VERIFICATION] ❌ Collection '{coll_name}' NOT found")
        except Exception as e:
            print(f"[VERIFICATION] Error checking collections: {e}")
        
    except Exception as e:
        print(f"Error during indexing: {e}")
        raise

# Optional: Add a function to check collection status
def check_collection_status(lang: str = "py"):
    """Check the status of the ChromaDB collection."""
    try:
        client = chromadb.PersistentClient(str(CHROMA_PATH))
        coll_name = f"functions_{lang}"
        collection = client.get_collection(coll_name)
        
        count = collection.count()
        print(f"Collection '{coll_name}' contains {count} items")
        
        # Get a sample of data
        sample = collection.get(limit=5)
        print("Sample IDs:", sample['ids'])
        
        return count
    except Exception as e:
        print(f"Error checking collection status: {e}")
        return 0
