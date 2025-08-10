"""
C++ parser for CodeDoc-AI.
Extracts FunctionSchema objects from .cpp / .hpp / .cc files.
"""
import textwrap
from tree_sitter import Parser, Language, Node
import tree_sitter_cpp as tscpp
from pathlib import Path
from typing import List, Optional

from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id_uuid


# Initialize parser
LANG = Language(tscpp.language())
parser = Parser()
parser.language = LANG


# ----------------------------------------
# Helpers
# ----------------------------------------
def _text(node: Optional[Node]) -> str:
    """Safely decode node text."""
    return node.text.decode("utf-8") if node else ""


def _extract_args(params_node: Optional[Node]) -> List[str]:
    """Extract function arguments from parameter list node."""
    args: List[str] = []
    if not params_node:
        return args
    for child in params_node.named_children:
        if child.type == "parameter_declaration":
            # The declarator field holds the parameter name and perhaps type info
            ident = child.child_by_field_name("declarator") or child
            args.append(_text(ident).strip())
    return args


def _extract_doc(node: Node) -> Optional[str]:
    """Look for comments (Javadoc or Doxygen style) above the function."""
    parent = node.parent
    if not parent:
        return None

    docs: List[str] = []
    # Iterate siblings above function node
    for sibling in reversed(parent.children[: parent.children.index(node)]):
        if sibling.type == "comment":
            txt = _text(sibling).strip()
            if txt.startswith("/**") or txt.startswith("///"):
                # Strip markers for clean docstring
                lines = txt.strip("/").splitlines()
                cleaned = "\n".join(line.strip("* ").rstrip() for line in lines)
                docs.append(cleaned)
        elif sibling.is_named:
            # Stop at first non-comment named node
            break

    return "\n".join(reversed(docs)) if docs else None


def _parse_function_node(node: Node, file_path: Path, lang: str) -> FunctionSchema:
    """Parse a single function_definition or function_declaration node."""
    # The declarator node contains function name and params
    decl = node.child_by_field_name("declarator")
    name_node = (
        decl.child_by_field_name("declarator")
        if decl and decl.child_by_field_name("declarator")
        else decl
    )
    params_node = decl.child_by_field_name("parameters") if decl else None
    ret_type_node = node.child_by_field_name("type")

    function_name = _text(name_node) or "<anonymous>"
    start_line = node.start_point[0] + 1
    start_col = node.start_point[1] + 1
    end_line = node.end_point[0] + 1

    # Extract raw source and clean formatting
    raw_source = file_path.read_bytes()[node.start_byte : node.end_byte].decode("utf-8")
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
        docstring=_extract_doc(node),
        args=_extract_args(params_node),
        return_type=_text(ret_type_node) if ret_type_node else None,
        start_line=start_line,
        end_line=end_line,
    )


# ----------------------------------------
# Public API
# ----------------------------------------
def parse_file(file_path: Path, lang: str = "cpp") -> List[FunctionSchema]:
    """
    Parses a C++ source/header file into a list of FunctionSchema objects using Tree-sitter.
    """
    source_bytes = file_path.read_bytes()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type in ("function_definition", "function_declaration"):
            try:
                functions.append(_parse_function_node(node, file_path, lang))
            except Exception as e:
                print(f"Error parsing C++ function at {file_path}:{node.start_point}: {e}")
        for child in node.children:
            walk(child)

    walk(root)
    return functions
