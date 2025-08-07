"""
demo.py – a small kitchen-sink file to exercise the parser.
"""

import math
from typing import List, Optional


def greet(name: str, greeting: str = "Hello") -> str:
    """Return a personalized greeting."""
    return f"{greeting}, {name}!"

def add(a: float, b: float) -> float:
    """Add two floats."""
    return a + b


class Calculator:
    """A tiny calculator class."""

    def __init__(self, precision: int = 2):
        self.precision = precision

    def add(self, a: float, b: float) -> float:
        """Add two floats with stored precision."""
        return round(a + b, self.precision)

    def factorial(self, n: int) -> int:
        """Compute factorial (no docstring on same line)."""
        if n < 0:
            raise ValueError("n must be non-negative")
        return math.factorial(n)


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point."""
    print(greet("World"))
    calc = Calculator()
    print(calc.add(3, 4))
    print(calc.factorial(5))


if __name__ == "__main__":
    main()