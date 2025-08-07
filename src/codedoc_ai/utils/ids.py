import hashlib

def make_unique_id(lang: str, name: str, file_path: str, line: int, col: int) -> str:
    name = name or "anonymous"
    id_source = f"{file_path}:{line}:{col}:{name}"
    short_hash = hashlib.sha1(id_source.encode()).hexdigest()[:6]
    func_id = f"{lang}_{name}_{line}_{col}_{short_hash}"
    
    print(f"[DEBUG] {func_id} from {id_source}")
    return func_id
