#!/usr/bin/env python3
"""Count the Python lines of the TARE core (acts/) and its test functions; write results/code_census.json."""
import ast
import json
import subprocess
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]


def py_lines(root: Path) -> int:
    return sum(len(p.read_text().splitlines()) for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts)


def test_functions(root: Path) -> int:
    count = 0
    for p in sorted(root.rglob("test_*.py")):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                count += 1
    return count


head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PIPE, capture_output=True, text=True).stdout.strip()
out = {
    "git_head": head,
    "acts_python_lines": py_lines(PIPE / "acts"),
    "test_python_lines": py_lines(PIPE / "tests"),
    "test_functions": test_functions(PIPE / "tests"),
    "method": "physical lines of *.py under acts/ and tests/ (including blank and comment lines); test_* functions counted by AST",
}
(PIPE / "results" / "code_census.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out))
