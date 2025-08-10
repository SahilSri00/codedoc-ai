import hashlib
import uuid
from pathlib import Path

# Alternative: UUID-based approach (guaranteed unique)
def make_unique_id_uuid(lang: str, function_name: str, file_path: str, start_line: int, start_col: int) -> str:
    """
    Generate UUID-based unique ID (guaranteed no collisions).
    """
    # Create namespace from the unique string
    unique_string = f"{lang}:{function_name}:{file_path}:{start_line}:{start_col}"
    
    # Generate UUID5 (deterministic) based on the string
    namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # DNS namespace
    unique_uuid = uuid.uuid5(namespace, unique_string)
    
    return f"{lang}_{str(unique_uuid).replace('-', '_')}"
