from pathlib import Path
from src.codedoc_ai.parser.python_parser import parse_file

print(parse_file(Path("scratch.py")))