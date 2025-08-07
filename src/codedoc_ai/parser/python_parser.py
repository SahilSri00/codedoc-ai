from tree_sitter import Parser, Language, Node
import tree_sitter_python as tspython
from pathlib import Path
from typing import List
from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id

LANG = Language(tspython.language())  # ✅ wraps PyCapsule safely
parser = Parser()
parser.language = LANG

# --- Helpers
def _text(node: Node | None) -> str:
    return node.text.decode("utf-8") if node else ""

# --- Main parser
def parse_file(file_path: Path) -> List[FunctionSchema]:
    """
    Parses a Python file into a list of FunctionSchema objects.
    """
    source_code = file_path.read_bytes()
    syntax_tree = parser.parse(source_code)
    root_node = syntax_tree.root_node

    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type != "function_definition":
            for child in node.children:
                walk(child)
            return

        # --- Extract name
        name_node = node.child_by_field_name("name")
        function_name = _text(name_node) or "anonymous"

        # --- Extract parameters
        args: List[str] = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for param in params_node.named_children:
                if param.type in ("identifier", "typed_parameter", "default_parameter"):
                    name_node_param = param.child_by_field_name("name") or param
                    args.append(_text(name_node_param))

        # --- Extract return type (if annotated)
        return_type_node = node.child_by_field_name("return_type")
        return_type = _text(return_type_node) if return_type_node else None

        # --- Extract docstring
        docstring = None
        body_node = node.child_by_field_name("body")
        if body_node and body_node.named_child_count > 0:
            first_stmt = body_node.named_children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.named_children[0] if first_stmt.named_children else None
                if expr and expr.type in ("string", "string_literal"):
                    docstring = _text(expr).strip('\'"')

        # --- Extract position and unique ID
        start_line = node.start_point[0] + 1
        start_col = node.start_point[1] + 1
        end_line = node.end_point[0] + 1
        func_id = make_unique_id("py", function_name, str(file_path), start_line, start_col)

        # --- Store function metadata
        functions.append(FunctionSchema(
            id=func_id,
            name=function_name,
            docstring=docstring,
            args=args,
            return_type=return_type,
            start_line=start_line,
            end_line=end_line,
        ))

        # Recurse into nested functions
        for child in node.children:
            walk(child)

    walk(root_node)
    return functions
