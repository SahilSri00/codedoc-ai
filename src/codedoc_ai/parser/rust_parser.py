"""
Rust parser for CodeDoc-AI.
Extracts FunctionSchema objects from .rs files.
"""
import hashlib
from pathlib import Path
from typing import List, Optional

from tree_sitter import Parser, Language, Node
import tree_sitter_rust as tsrust

from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id_uuid as make_py_id  # reuse Python ID maker for consistency


# Initialize parser
LANG = Language(tsrust.language())
parser = Parser()
parser.language = LANG


# ----------------------------------------
# Helpers
# ----------------------------------------
def _text(node: Optional[Node]) -> str:
    return node.text.decode("utf-8") if node else ""


def _extract_args(params_node: Optional[Node]) -> List[str]:
    if not params_node:
        return []
    args: List[str] = []
    for child in params_node.named_children:
        if child.type == "parameter":
            pattern = child.child_by_field_name("pattern")
            args.append(_text(pattern) if pattern else "_")
    return args


def _extract_doc(node: Node) -> Optional[str]:
    """
    Look above the function node for line/block comments.
    Supports: ///, /** */, //!
    """
    parent = node.parent
    if not parent:
        return None

    docs: List[str] = []
    # Iterate siblings in reverse order up to this node
    for sibling in reversed(parent.children[: parent.children.index(node)]):
        if sibling.type in ("line_comment", "block_comment"):
            txt = _text(sibling).strip()
            # Consider Rust doc comment styles
            if txt.startswith("///") or txt.startswith("//!") or txt.startswith("/**"):
                # Strip marker characters
                docs.append(txt.lstrip("/!* ").rstrip("*/ ").strip())
        elif sibling.type.strip() == "":
            # Skip blank lines
            continue
        else:
            # Stop at first non-comment
            break

    return "\n".join(reversed(docs)) if docs else None


def _make_unique_rust_id(
    lang: str, 
    name: str, 
    file_path: str, 
    start_line: int, 
    start_col: int = 0
) -> str:
    """
    Create a unique ID for Rust functions using the same strategy as Python.
    """
    return make_py_id(lang, name, file_path, start_line, start_col)


def _parse_function_node(node: Node, file_path: Path, lang: str) -> FunctionSchema:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")

    function_name = _text(name_node) or "<anonymous>"
    start_line = node.start_point[0] + 1
    start_col = node.start_point[1] + 1

    # Generate unique ID
    func_id = _make_unique_rust_id(
        lang,
        function_name,
        str(file_path),
        start_line,
        start_col,
    )

    return FunctionSchema(
        id=func_id,
        name=function_name,
        source_code=None,            # Could be extracted if needed
        file_path=str(file_path),
        docstring=_extract_doc(node),
        args=_extract_args(params_node),
        return_type=None,            # Rust return types require extra parsing
        start_line=start_line,
        end_line=node.end_point[0] + 1,
    )


# ----------------------------------------
# Public API
# ----------------------------------------
def parse_file(file_path: Path, lang: str = "rs") -> List[FunctionSchema]:
    """
    Parses a Rust file into a list of FunctionSchema objects using Tree-sitter.
    """
    source = file_path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type == "function_item":
            try:
                functions.append(_parse_function_node(node, file_path, lang))
            except Exception as e:
                print(f"Error parsing Rust function at {file_path}:{node.start_point}: {e}")
        for child in node.children:
            walk(child)

    walk(root)
    return functions
