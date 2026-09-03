"""
test_parser_coverage.py — Pins the parser node-types that were previously missed.

Each parser used to match only a subset of the constructs that actually declare
a function in its language, so whole categories were silently skipped:

  * Go   — methods with a receiver (``func (s *Server) Handle()``)
  * JS   — class methods, constructors and accessors (``method_definition``)
  * Java — constructors (``constructor_declaration``)
  * Py   — ``async def`` (``ast.AsyncFunctionDef``)

These tests assert those constructs are now discovered by the real parser
dispatch. They are pure parse-level checks: no LLM, no injection, no network —
so they stay fast, offline and deterministic.
"""
from __future__ import annotations

from codedoc_ai.router import detect_and_parse

GO = (
    "package main\n"
    "\n"
    "type Server struct{}\n"
    "\n"
    "func New() *Server {\n"
    "\treturn &Server{}\n"
    "}\n"
    "\n"
    "func (s *Server) Handle(path string) int {\n"
    "\treturn len(path)\n"
    "}\n"
)

JS = (
    "export function makeId() {\n"
    "  return 1;\n"
    "}\n"
    "\n"
    "class Cache {\n"
    "  constructor(size) {\n"
    "    this.size = size;\n"
    "  }\n"
    "\n"
    "  lookup(key) {\n"
    "    return key;\n"
    "  }\n"
    "}\n"
)

JAVA = (
    "public class Point {\n"
    "    private int x;\n"
    "\n"
    "    public Point(int x) {\n"
    "        this.x = x;\n"
    "    }\n"
    "\n"
    "    public int getX() {\n"
    "        return x;\n"
    "    }\n"
    "}\n"
)

PY = (
    "import asyncio\n"
    "\n"
    "\n"
    "async def fetch(url):\n"
    "    return url\n"
    "\n"
    "\n"
    "def sync_helper():\n"
    "    return 1\n"
)


def _names(tmp_path, filename, source):
    src = tmp_path / filename
    src.write_text(source, encoding="utf-8", newline="")
    return {f.name for f in detect_and_parse(src)}


def test_go_methods_with_receiver_are_found(tmp_path):
    names = _names(tmp_path, "server.go", GO)
    # The receiver method was the one previously skipped.
    assert names == {"New", "Handle"}


def test_js_class_methods_are_found(tmp_path):
    names = _names(tmp_path, "cache.js", JS)
    # constructor + lookup are method_definition nodes; makeId is a declaration.
    assert names == {"makeId", "constructor", "lookup"}


def test_java_constructors_are_found(tmp_path):
    src = tmp_path / "Point.java"
    src.write_text(JAVA, encoding="utf-8", newline="")
    funcs = detect_and_parse(src)

    by_name = {f.name: f for f in funcs}
    assert set(by_name) == {"Point", "getX"}
    # A constructor has no return type — it must not carry a bogus one.
    assert by_name["Point"].return_type is None


def test_python_async_def_is_found(tmp_path):
    names = _names(tmp_path, "io.py", PY)
    assert names == {"fetch", "sync_helper"}
