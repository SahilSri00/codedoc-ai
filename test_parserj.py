from pathlib import Path
from src.codedoc_ai.parser.java_parser import parse_file

if __name__ == "__main__":
    print(parse_file(Path("Demo1.java")))