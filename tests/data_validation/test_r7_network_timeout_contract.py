import ast
from pathlib import Path

import pytest


REQUEST_SOURCES = [
    Path("auth.py"),
    Path("token_manager.py"),
    Path("pull_data.py"),
    Path("summarize.py"),
]


def _request_calls_missing_timeout(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    misses: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id != "requests":
            continue
        if node.func.attr not in {"get", "post"}:
            continue

        has_timeout = any(k.arg == "timeout" for k in node.keywords if k.arg)
        if not has_timeout:
            misses.append(f"{source_path}:{node.lineno} requests.{node.func.attr} missing timeout")

    return misses


def test_all_http_calls_have_explicit_timeout():
    """Real-world failure: Oura or Anthropic stalls can block the daily run indefinitely."""
    violations: list[str] = []
    for source in REQUEST_SOURCES:
        violations.extend(_request_calls_missing_timeout(source))

    assert not violations, "\n".join(violations)
