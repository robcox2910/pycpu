"""Check that sibling projects are pinned by git tag, never by local path."""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_no_dependency_source_uses_a_local_path() -> None:
    """A `path` source would only work on one machine, so none may exist."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    sources = data["tool"]["uv"]["sources"]
    for name, source in sources.items():
        assert "path" not in source, f"{name} must be a git tag, not a path"
