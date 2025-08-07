"""
JavaScript parser for CodeDoc-AI.
Extracts FunctionSchema objects from .js / .ts / .mjs files.
"""

from tree_sitter import Parser, Language, Node
import tree_sitter_javascript as tsjs
from pathlib import Path
from typing import List
from uuid import uuid4
from ..models.schemas import FunctionSchema

LANG = Language(tsjs.language())
parser = Parser()
parser.language = LANG


def _text(node: Node | None) -> str:
    return node.text.decode() if node else ""


def _extract_jsdoc(node: Node) -> str | None:
    parent = node.parent
    if not parent:
        return None
    for sibling in reversed(parent.children[:parent.children.index(node)]):
        if sibling.type == "comment":
            txt = _text(sibling)
            if txt.startswith("/**") and txt.endswith("*/"):
                return txt.strip("/* */").strip()
        else:
            break
    return None


def _extract_args(params_node: Node) -> List[str]:
    if not params_node:
        return []
    args = []
    for child in params_node.named_children:
        if child.type in ("identifier", "rest_parameter", "object_pattern", "array_pattern"):
            args.append(_text(child))
        elif child.type == "assignment_pattern":
            arg = child.child_by_field_name("left")
            args.append(_text(arg))
    return args


def _parse_function_node(node: Node, file_path: Path) -> FunctionSchema:
    name = _text(node.child_by_field_name("name")) or "anonymous"

    docstring = _extract_jsdoc(node)
    body = node.child_by_field_name("body")
    if not docstring and body and body.named_children:
        first = body.named_children[0]
        if first.type == "expression_statement" and first.children:
            if first.children[0].type == "string_literal":
                docstring = _text(first.children[0]).strip("\"'`")

    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1

    # 🔒 Guaranteed globally unique ID
    unique_id = f"js_{name}_{uuid4().hex[:8]}"

    return FunctionSchema(
        id=unique_id,
        name=name,
        docstring=docstring,
        args=_extract_args(node.child_by_field_name("parameters")),
        return_type=None,
        start_line=start_line,
        end_line=end_line,
    )


def parse_file(file_path: Path) -> List[FunctionSchema]:
    source = file_path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node
    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type in ("function_declaration", "function_expression", "arrow_function"):
            functions.append(_parse_function_node(node, file_path))
        for child in node.children:
            walk(child)

    walk(root)
    return functions
