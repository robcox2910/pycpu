"""Check that everything a learner can see in the source explains itself."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "pycpu"
MODULES = sorted(p for p in SRC.rglob("*.py") if p.name != "_version.py")
MIN_MODULE_DOCSTRING_LINES = 3


def _id(path: Path) -> str:
    """Name a module by its path inside the package."""
    return str(path.relative_to(SRC))


def _public_defs(tree: ast.Module) -> list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
    """Collect public classes and functions, including methods, from a module."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


@pytest.mark.parametrize("path", MODULES, ids=_id)
def test_every_public_name_has_a_docstring(path: Path) -> None:
    """The module, and each public class and function in it, has a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert ast.get_docstring(tree), f"{_id(path)} has no module docstring"
    for node in _public_defs(tree):
        assert ast.get_docstring(node), f"{_id(path)}: {node.name} has no docstring"


@pytest.mark.parametrize("path", MODULES, ids=_id)
def test_every_module_docstring_has_a_body(path: Path) -> None:
    """A module docstring is at least three lines, so a one-line label cannot pass."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstring = ast.get_docstring(tree) or ""
    assert len(docstring.splitlines()) >= MIN_MODULE_DOCSTRING_LINES, (
        f"{_id(path)} module docstring is too short"
    )
