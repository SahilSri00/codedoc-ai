"""
Go parser for CodeDoc-AI.
Extracts FunctionSchema objects from .go files.
"""
import textwrap
from tree_sitter import Parser, Language, Node
import tree_sitter_go as tsgo
from pathlib import Path
from typing import List, Optional

from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id_uuid


# Initialize parser
LANG = Language(tsgo.language())
parser = Parser()
parser.language = LANG


# ----------------------------------------
# Helpers
# ----------------------------------------
def _text(node: Optional[Node]) -> str:
    """Decode node text or return empty string."""
    return node.text.decode("utf-8") if node else ""


def _extract_args(params_node: Optional[Node]) -> List[str]:
    """
    Extract function arguments from parameter_declaration nodes.
    Handles named params like `x int`, grouped like `x, y int`, and unnamed `_`.
    """
    args: List[str] = []
    if not params_node:
        return args

    for child in params_node.named_children:
        if child.type == "parameter_declaration":
            name_node = child.child_by_field_name("name")
            if name_node:
                args.append(_text(name_node))
            else:
                args.append("_")  # unnamed param
    return args


def _extract_doc(node: Node) -> Optional[str]:
    """
    Extract docstring comment immediately above the function.
    Supports `//` and `/* */` styles.
    """
    parent = node.parent
    if not parent:
        return None

    docs: List[str] = []
    for sibling in reversed(parent.children[: parent.children.index(node)]):
        if sibling.type == "comment":
            txt = _text(sibling).strip()
            if txt.startswith("//") or txt.startswith("/*"):
                cleaned = txt.lstrip("/ *").rstrip("*/ ").strip()
                docs.append(cleaned)
        elif sibling.is_named:
            break
    return "\n".join(reversed(docs)) if docs else None


def _parse_function_node(node: Node, file_path: Path, lang: str) -> FunctionSchema:
    """
    Converts a function_declaration node to FunctionSchema,
    including unique ID, source code, and metadata.
    """
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    start_line = node.start_point[0] + 1
    start_col = node.start_point[1] + 1
    end_line = node.end_point[0] + 1

    function_name = _text(name_node) or "<anonymous>"
    docstring = _extract_doc(node)

    # Extract raw source code and clean indentation
    raw_source = node.text.decode("utf-8")
    cleaned_source = textwrap.dedent(raw_source).strip()

    # Generate unique ID
    func_id = make_unique_id_uuid(
        lang,
        function_name,
        str(file_path),
        start_line,
        start_col,
    )

    return FunctionSchema(
        id=func_id,
        name=function_name,
        source_code=cleaned_source,
        file_path=str(file_path),
        docstring=docstring,
        args=_extract_args(params_node),
        return_type=None,  # Go return types require extra parsing if needed
        start_line=start_line,
        end_line=end_line,
    )


# ----------------------------------------
# Public API
# ----------------------------------------
def parse_file(file_path: Path, lang: str = "go") -> List[FunctionSchema]:
    """
    Parse a Go source file and extract all functions.
    """
    source_bytes = file_path.read_bytes()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type == "function_declaration":
            try:
                functions.append(_parse_function_node(node, file_path, lang))
            except Exception as e:
                print(f"Error parsing Go function at {file_path}:{node.start_point}: {e}")
        for child in node.children:
            walk(child)

    walk(root)
    return functions
