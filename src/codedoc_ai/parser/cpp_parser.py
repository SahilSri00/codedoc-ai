"""
C++ parser for CodeDoc-AI.
Extracts FunctionSchema objects from .cpp / .hpp / .cc files.
"""
from tree_sitter import Parser, Language ,Node
import tree_sitter_cpp as tscpp
from pathlib import Path
from typing import List
from ..models.schemas import FunctionSchema

LANG = Language(tscpp.language())
parser = Parser()
parser.language = LANG



def _text(node: Node) -> str:
    """Safely decode node text."""
    return node.text.decode() if node else ""


def _extract_args(params_node: Node) -> List[str]:
    """Extract function arguments from parameter list node."""
    if not params_node:
        return []
    args = []
    if not params_node:
        return args
    for child in params_node.named_children:
        if child.type == "parameter_declaration":
            ident = child.child_by_field_name("declarator")
            args.append(_text(ident or child))
    return args


def _extract_doc(node: Node) -> str | None:
    """Look for comments (Javadoc or doxygen style) above the function."""
    parent = node.parent
    if not parent:
        return None

    for sibling in reversed(parent.children[:parent.children.index(node)]):
        if sibling.type == "comment":
            txt = _text(sibling).strip()
            if txt.startswith("/**") or txt.startswith("///"):
                return txt.lstrip("/* ").rstrip("*/").strip()
        elif sibling.type.strip() != "":
            break
    return None


def _parse_function_node(node: Node) -> FunctionSchema:
    """Parse a single function_definition or function_declaration node."""
    decl = node.child_by_field_name("declarator")
    name_node = decl.child_by_field_name("declarator") if decl else None
    params_node = decl.child_by_field_name("parameters")
    ret_type = node.child_by_field_name("type")

    return FunctionSchema(
        name=_text(name_node) if name_node else "<anonymous>",
        docstring=_extract_doc(node),
        args=_extract_args(params_node),
        return_type=_text(ret_type) if ret_type else None,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
    )


def parse_file(file_path: Path) -> List[FunctionSchema]:
    """Parse a C++ source/header file and return extracted functions."""
    source = file_path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node
    functions = []

    def walk(node: Node):
        if node.type in ("function_definition", "function_declaration"):
            functions.append(_parse_function_node(node))
        for child in node.children:
            walk(child)

    walk(root)
    return functions
