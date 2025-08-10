"""
JavaScript/TypeScript parser for CodeDoc-AI.
Extracts FunctionSchema objects from .js / .ts / .mjs files.
"""
import textwrap
from tree_sitter import Parser, Language, Node
import tree_sitter_javascript as tsjs
from pathlib import Path
from typing import List, Optional

from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id_uuid as make_id


# Initialize parser
LANG = Language(tsjs.language())
parser = Parser()
parser.language = LANG


# ----------------------------------------
# Helpers
# ----------------------------------------
def _text(node: Optional[Node]) -> str:
    return node.text.decode("utf-8") if node else ""


def _extract_jsdoc(node: Node) -> Optional[str]:
    """
    Extract JSDoc comment (`/** ... */`) immediately above the function node.
    """
    parent = node.parent
    if not parent:
        return None

    docs: List[str] = []
    for sibling in reversed(parent.children[: parent.children.index(node)]):
        if sibling.type == "comment":
            txt = _text(sibling).strip()
            if txt.startswith("/**") and txt.endswith("*/"):
                # Clean JSDoc markers
                lines = txt.splitlines()
                cleaned = "\n".join(line.strip("/* ").rstrip("*/ ").strip() for line in lines)
                docs.append(cleaned)
            else:
                # Non-JSDoc comment stops the search
                break
        elif sibling.is_named:
            break

    return "\n".join(reversed(docs)) if docs else None


def _extract_args(params_node: Optional[Node]) -> List[str]:
    """
    Extract parameter names from function parameters.
    Supports identifiers, rest parameters, destructuring, and default values.
    """
    args: List[str] = []
    if not params_node:
        return args

    for child in params_node.named_children:
        if child.type in ("identifier", "rest_parameter", "object_pattern", "array_pattern"):
            args.append(_text(child))
        elif child.type == "assignment_pattern":
            left = child.child_by_field_name("left")
            if left:
                args.append(_text(left))
    return args


# ----------------------------------------
# Public API
# ----------------------------------------
def parse_file(file_path: Path, lang: str = "js") -> List[FunctionSchema]:
    """
    Parses a JavaScript/TypeScript file into a list of FunctionSchema objects using Tree-sitter.
    """
    source_bytes = file_path.read_bytes()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type in ("function_declaration", "function_expression", "arrow_function"):
            # Extract basic metadata
            name_node = node.child_by_field_name("name")
            function_name = _text(name_node) or "<anonymous>"
            start_line = node.start_point[0] + 1
            start_col = node.start_point[1] + 1
            end_line = node.end_point[0] + 1

            # Extract JSDoc or inline string literal docstring
            docstring = _extract_jsdoc(node)
            if not docstring:
                body = node.child_by_field_name("body")
                if body and body.named_child_count > 0:
                    first = body.named_children[0]
                    if first.type == "expression_statement":
                        lit = first.child_by_field_name("expression") or first.child(0)
                        if lit and lit.type == "string":
                            docstring = _text(lit).strip("\"'`")

            # Extract raw source code snippet
            raw_source = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
            cleaned_source = textwrap.dedent(raw_source).strip()

            # Generate unique ID
            unique_id = make_id(
                lang,
                function_name,
                str(file_path),
                start_line,
                start_col,
            )

            # Extract arguments
            params_node = node.child_by_field_name("parameters")
            args = _extract_args(params_node)

            functions.append(FunctionSchema(
                id=unique_id,
                name=function_name,
                source_code=cleaned_source,
                file_path=str(file_path),
                docstring=docstring,
                args=args,
                return_type=None,
                start_line=start_line,
                end_line=end_line,
            ))

        # Recurse into children
        for child in node.children:
            walk(child)

    walk(root)
    return functions
