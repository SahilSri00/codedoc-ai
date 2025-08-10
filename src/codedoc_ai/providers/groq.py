import os
from groq import Groq
from ..models.schemas import FunctionSchema

# Create Groq client with API key from env
client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

def summarize_file(functions: list[FunctionSchema]) -> str:
    """
    Generate a detailed 4-5 line summary for a file based on its functions.
    """
    if not functions:
        return "This file contains no functions."

    # Convert list of functions into one text block
    text = "\n".join(
        f"{f.name}({', '.join(f.args)}) -> {f.return_type or 'None'}"
        for f in functions
    )

    prompt = f"Summarize in 3-4 lines what this file does:\n{text}"

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()
