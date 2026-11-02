"""Check that the package can be imported at all."""

import pycpu


def test_the_package_imports_and_explains_itself() -> None:
    """Importing pycpu works and its docstring introduces the project."""
    assert pycpu.__doc__ is not None
    assert "NAND" in pycpu.__doc__
