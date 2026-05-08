"""
Java parser for CodeDoc-AI.
Extracts FunctionSchema objects from .java files.
"""
import textwrap
from tree_sitter import Parser, Language, Node
import tree_sitter_java as tsjava
from pathlib import Path
from typing import List, Optional

from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id_uuid


# Initialize parser
LANG = Language(tsjava.language())
parser = Parser()
parser.language = LANG


# ----------------------------------------
# Helpers
# ----------------------------------------
def _text(node: Optional[Node]) -> str:
    return node.text.decode("utf-8") if node else ""


def _extract_doc(node: Node) -> Optional[str]:
    """
    Extracts the first block or line comment immediately preceding the method declaration.
    """
    # Primary: tree-sitter-java exposes javadoc in "documentation" field
    doc_node = node.child_by_field_name("documentation")
    if doc_node:
        return _text(doc_node).strip()

    # Fallback: scan the parent's children list to find the comment that
    # immediately precedes this method node (prev_siblings is not available in
    # older tree-sitter Python bindings).
    parent = node.parent
    if parent is None:
        return None

    children = parent.children
    try:
        idx = children.index(node)
    except ValueError:
        return None

    # Walk backwards from the node's position
    for i in range(idx - 1, -1, -1):
        sibling = children[i]
        if sibling.type in ("line_comment", "block_comment"):
            raw = _text(sibling)
            # Strip JavaDoc / block-comment markers
            cleaned = raw.strip().lstrip("/").lstrip("*").strip()
            return cleaned if cleaned else None
        # Stop as soon as we hit any other named node
        if sibling.is_named:
            break

    return None


def _extract_args(params_node: Optional[Node]) -> List[str]:
    args: List[str] = []
    if not params_node:
        return args
    # Java parameters appear as formal_parameter nodes
    for param in params_node.named_children:
        if param.type == "formal_parameter":
            name_node = param.child_by_field_name("name")
            if name_node:
                args.append(_text(name_node))
    return args


# ----------------------------------------
# Public API
# ----------------------------------------
def parse_file(file_path: Path, lang: str = "java") -> List[FunctionSchema]:
    """
    Parses a Java file into a list of FunctionSchema objects using Tree-sitter.
    """
    source_bytes = file_path.read_bytes()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        # Match Java method declarations
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            params_node = node.child_by_field_name("parameters")
            type_node = node.child_by_field_name("type")

            function_name = _text(name_node) or "<anonymous>"
            start_line = node.start_point[0] + 1
            start_col = node.start_point[1] + 1
            end_line = node.end_point[0] + 1

            # Extract docstring/javadoc
            docstring = _extract_doc(node)

            # Extract parameters
            args = _extract_args(params_node)

            # Extract raw source code and clean it
            raw_source = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
            cleaned_source = textwrap.dedent(raw_source).strip()

            # Generate unique ID
            func_id = make_unique_id_uuid(
                lang,
                function_name,
                str(file_path),
                start_line,
                start_col,
            )

            functions.append(FunctionSchema(
                id=func_id,
                name=function_name,
                source_code=cleaned_source,
                file_path=str(file_path),
                docstring=docstring,
                args=args,
                return_type=_text(type_node),
                start_line=start_line,
                end_line=end_line,
            ))

        # Recurse into children
        for child in node.children:
            walk(child)

    walk(root)
    return functions
