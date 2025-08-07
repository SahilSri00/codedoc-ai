from tree_sitter import Parser, Language ,Node
import tree_sitter_java as tsjava
from pathlib import Path
from typing import List
from ..models.schemas import FunctionSchema

LANG = Language(tsjava.language())   # Wrap the capsule properly
parser = Parser()
parser.language = LANG 

def _text(node: Node) -> str:
    return node.text.decode() if node else ""

def parse_file(file_path: Path) -> List[FunctionSchema]:
    source = file_path.read_bytes()
    tree = parser.parse(source)
    root = tree.root_node
    functions: List[FunctionSchema] = []

    def walk(node: Node):
        if node.type == "method_declaration":          # Java uses "method_declaration"
            name_node   = node.child_by_field_name("name")
            params_node = node.child_by_field_name("parameters")
            type_node   = node.child_by_field_name("type")

            # docstring: first doc comment (/* ... */) inside body
            docstring = None
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "line_comment" or child.type == "block_comment":
                        docstring = _text(child).strip("/* */")
                        break

            # parameters
            args = []
            if params_node:
                for param in params_node.named_children:
                    if param.type in ("identifier", "formal_parameter"):
                        id_node = param.child_by_field_name("name") or param
                        args.append(_text(id_node))

            functions.append(FunctionSchema(
                name=_text(name_node),
                docstring=docstring,
                args=args,
                return_type=_text(type_node),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            ))

        for child in node.children:
            walk(child)

    walk(root)
    return functions