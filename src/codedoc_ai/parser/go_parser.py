"""
Go parser for CodeDoc-AI.
Extracts FunctionSchema objects from .go files.
"""
from tree_sitter import Parser, Language , Node
import tree_sitter_go as tsgo
from pathlib import Path
from typing import List
from ..models.schemas import FunctionSchema

LANG = Language(tsgo.language())
parser = Parser()
parser.language = LANG


def _text(node: Node) -> str:
    """Decode node text or return empty string."""
    return node.text.decode() if node else ""


def _extract_args(params_node: Node) -> List[str]:
    """
    Extract function arguments from parameter_declaration nodes.
    Handles named params like `x int`, grouped like `x, y int`, and unnamed `_`.
    """
    if not params_node:
        return []
    args = []
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


def _extract_doc(node: Node) -> str | None:
    """
    Extract docstring comment immediately above the function.
    Supports `//` and `/* */` styles.
    """
    parent = node.parent
    if not parent:
        return None

    for sibling in reversed(parent.children[:parent.children.index(node)]):
        if sibling.type == "comment":
            txt = _text(sibling).strip()
            if txt.startswith("//") or txt.startswith("/*"):
                return txt.strip("/ *")
        else:
            break
    return None


def _parse_function_node(node: Node) -> FunctionSchema:
    """
    Converts a function_declaration node to FunctionSchema.
    """
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")
    body = node.child_by_field_name("body")
    docstring = _extract_doc(node)

    return FunctionSchema(
        name=_text(name_node) or "<anonymous>",
        docstring=docstring,
        args=_extract_args(params_node),
        return_type=None,  # Go doesn't have static return types easily parsed
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
    )


def parse_file(file_path: Path) -> List[FunctionSchema]:
    """
    Parse a Go source file and extract all functions.
    """
    source = file_path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node
    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type == "function_declaration":
            functions.append(_parse_function_node(node))
        for child in node.children:
            walk(child)

    walk(root)
    return functions
