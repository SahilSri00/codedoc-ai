import os
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
from ..models.schemas import FunctionSchema

# Configure Gemini with API key from .env
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use free-tier Gemini model (fastest and still powerful)
GEMINI = genai.GenerativeModel("gemini-1.5-flash")

# System prompt to enforce clean docstring generation
SYSTEM = """
You are a senior Python/Java engineer.
Given a function signature and body, return ONLY a Google-style docstring (no extra prose).
Include: 1-line summary, Args (with types), Returns, Raises (if any).

Example format:
\"\"\"
Compute the square root.

Args:
    x (float): Non-negative number.

Returns:
    float: Square root of x.

Raises:
    ValueError: If x < 0.
\"\"\"
"""

def generate_doc(func: FunctionSchema) -> str:
    """
    Generates a Google-style docstring for the given function using Gemini.
    """
    prompt = f"{SYSTEM}\n\nFunction:\n{func.dict()}"
    response = GEMINI.generate_content(prompt)
    return response.text.strip()
