import ast
import textwrap
from pathlib import Path
from typing import List
from ..models.schemas import FunctionSchema
from ..utils.ids import make_unique_id_uuid


def parse_file(file_path: Path) -> List[FunctionSchema]:
    """
    Parses a Python file into a list of FunctionSchema objects using Python's built-in AST.
    """
    try:
        # Read the source code
        source_code = file_path.read_text(encoding='utf-8')
        
        # Parse the AST
        tree = ast.parse(source_code, filename=str(file_path))
        
        functions: List[FunctionSchema] = []
        
        # Find all function definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Extract function name
                function_name = node.name
                
                # Extract arguments
                args = []
                for arg in node.args.args:
                    args.append(arg.arg)
                
                # Extract return type annotation if present
                return_type = None
                if node.returns:
                    return_type = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
                
                # Extract docstring
                docstring = None
                if (node.body and 
                    isinstance(node.body[0], ast.Expr) and 
                    isinstance(node.body[0].value, ast.Constant) and 
                    isinstance(node.body[0].value.value, str)):
                    docstring = node.body[0].value.value.strip()
                
                # Extract source code for this function
                lines = source_code.split('\n')
                start_line = node.lineno
                end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line
                
                # Get the function source code
                if end_line:
                    function_lines = lines[start_line-1:end_line]
                    raw_source_code = '\n'.join(function_lines)
                else:
                    # Fallback: try to extract based on indentation
                    function_lines = [lines[start_line-1]]  # Start with the def line
                    for i in range(start_line, len(lines)):
                        line = lines[i]
                        if line.strip() == '':
                            function_lines.append(line)
                            continue
                        if line.startswith(' ') or line.startswith('\t'):
                            function_lines.append(line)
                        else:
                            break
                    raw_source_code = '\n'.join(function_lines)
                
                cleaned_source_code = textwrap.dedent(raw_source_code).strip()
                
                # Create unique ID
                start_col = node.col_offset + 1 if hasattr(node, 'col_offset') else 1
                func_id = make_unique_id_uuid("py", function_name, str(file_path), start_line, start_col)
                
                # Store function metadata
                functions.append(FunctionSchema(
                    id=func_id,
                    name=function_name,
                    source_code=cleaned_source_code,
                    file_path=str(file_path),
                    docstring=docstring,
                    args=args,
                    return_type=return_type,
                    start_line=start_line,
                    end_line=end_line or start_line,
                ))
        
        return functions
        
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return []
