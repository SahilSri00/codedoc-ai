from pathlib import Path
from codedoc_ai.parser.python_parser import parse_file

def test_parse_simple():
    code = Path("scratch.py")
    funcs = parse_file(code)
    assert len(funcs) == 1
    assert funcs[0].name == "add"
    assert funcs[0].return_type == "-> int"