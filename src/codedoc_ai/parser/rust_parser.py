"""
Rust parser for CodeDoc-AI.
Extracts FunctionSchema objects from .rs files.
"""
from tree_sitter import Parser, Language ,Node
import tree_sitter_rust as tsrust
from pathlib import Path
from typing import List
from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id

LANG = Language(tsrust.language())
parser = Parser()
parser.language = LANG

# ----------------------------------------
# Helpers
# ----------------------------------------
def _text(node: Node | None) -> str:
    return node.text.decode() if node else ""


def _extract_args(params_node: Node | None) -> List[str]:
    if not params_node:
        return []

    args = []
    for child in params_node.named_children:
        if child.type == "parameter":
            pattern = child.child_by_field_name("pattern")
            args.append(_text(pattern) if pattern else "_")
    return args


def _extract_doc(node: Node) -> str | None:
    """
    Look above the function node for line/block comments.
    Supports: ///, /** */, //!
    """
    parent = node.parent
    if not parent:
        return None

    docs = []
    for sibling in reversed(parent.children[:parent.children.index(node)]):
        if sibling.type in ("line_comment", "block_comment"):
            txt = _text(sibling).strip()
            if txt.startswith(("///", "//!", "/**")):
                docs.append(txt.strip("/ *"))
        elif sibling.type.strip() == "":
            continue
        else:
            break

    return "\n".join(reversed(docs)) if docs else None


def _parse_function_node(node: Node, file_path: Path) -> FunctionSchema:
    name_node = node.child_by_field_name("name")
    params_node = node.child_by_field_name("parameters")

    return FunctionSchema(
        id=make_unique_id(file_path, _text(name_node) or "<anonymous>", node.start_point[0]),
        name=_text(name_node) or "<anonymous>",
        docstring=_extract_doc(node),
        args=_extract_args(params_node),
        return_type=None,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
    )


# ----------------------------------------
# Public API
# ----------------------------------------
def parse_file(file_path: Path) -> List[FunctionSchema]:
    source = file_path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type == "function_item":
            functions.append(_parse_function_node(node, file_path))
        for child in node.children:
            walk(child)

    walk(root)
    return functions