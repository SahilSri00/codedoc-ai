from pathlib import Path
from typing import List
from .models.schemas import FunctionSchema
from .parser.python_parser import parse_file as parse_py
from .parser.java_parser import parse_file as parse_java
from .parser.js_parser import parse_file as parse_js
from .parser.cpp_parser import parse_file as parse_cpp
from .parser.go_parser import parse_file as parse_go
from .parser.rust_parser import parse_file as parse_rs

PARSERS = {
    "py": parse_py,
    "python": parse_py,
    "java": parse_java,
    "js": parse_js,
    "javascript": parse_js,
    "cpp": parse_cpp,
    "cc": parse_cpp,
    "hpp": parse_cpp,
    "h": parse_cpp,
    "go": parse_go,
    "rs": parse_rs,
    "rust": parse_rs,
}


def detect_lang(path: Path) -> str:
    ext = path.suffix.lstrip(".")
    if ext in PARSERS:
        return ext

    # Fallback by inspecting content
    head = path.read_text(encoding="utf-8", errors="ignore")[:2048]
    if "def " in head or "import " in head:
        return "py"
    if "public class" in head or "package " in head:
        return "java"
    if "function" in head or "const" in head:
        return "js"
    if "func " in head:
        return "go"
    if "fn " in head:
        return "rs"
    if "#include" in head or "std::" in head:
        return "cpp"
    
    return "unknown"

def detect_and_parse(path: Path) -> List[FunctionSchema]:
    lang = detect_lang(path)
    if lang == "unknown":
        raise RuntimeError(f"Cannot detect language for {path}")
    return PARSERS[lang](path)
