from pathlib import Path
from .providers.gemini import generate_doc
from .providers.groq import summarize_file
from .router import detect_and_parse  # we’ll stub it now

def generate(file: Path):
    functions = detect_and_parse(file)
    for f in functions:
        f.docstring = generate_doc(f)  # overwrite with LLM
    file_summary = summarize_file(functions)
    return {"summary": file_summary, "functions": [f.dict() for f in functions]}