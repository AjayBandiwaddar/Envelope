"""
Structural test per THREAT_MODEL.md Section 3.6: the policy engine must
have no dependency on any LLM client, HTTP client, or the Django ORM.
This is checked at the AST level (import statements), not just "did the
test pass" - a runtime-only check could miss an unused-but-present
import that later gets wired up accidentally.
"""

import ast
import pathlib

import pytest

FORBIDDEN_SUBSTRINGS = [
    "django",
    "requests",
    "httpx",
    "anthropic",
    "openai",
    "urllib",
    "http.client",
]

ENGINE_DIR = pathlib.Path(__file__).resolve().parent.parent / "engine"


def _imported_module_names(tree: ast.Module) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", sorted(ENGINE_DIR.glob("*.py")))
def test_engine_module_has_no_forbidden_imports(path):
    tree = ast.parse(path.read_text())
    for name in _imported_module_names(tree):
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in name, (
                f"{path.name} imports '{name}', which contains the forbidden "
                f"substring '{forbidden}'. The policy engine must remain free "
                f"of Django/HTTP/LLM-client dependencies (THREAT_MODEL.md "
                f"Section 3.6, ARCHITECTURE.md Section 5.4)."
            )


def test_engine_directory_is_not_empty():
    # Guards against this test suite silently passing because the glob
    # above matched zero files (e.g. a path typo after a refactor).
    assert list(ENGINE_DIR.glob("*.py")), "Expected engine module files were not found."
