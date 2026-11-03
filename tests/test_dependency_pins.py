"""Check that sibling projects are PyPI releases, never git or path sources.

Think of a recipe that says "buy flour from the shop" rather than "use the
flour in my cupboard": anyone can follow it. A `path` or git source only
works on one machine, so PyCPU asks for released `fromscratch-*` packages.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
SIBLINGS = ("fromscratch-pyweb", "fromscratch-pebble", "fromscratch-pynet")
FLOOR = re.compile(r"^(?P<name>fromscratch-[a-z]+)>=\d+\.\d+\.\d+$")


def _load() -> dict[str, Any]:
    """Return the parsed pyproject.toml."""
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_no_dependency_sources_exist() -> None:
    """No `[tool.uv.sources]` table: no path, git or tag pins at all."""
    assert "sources" not in _load()["tool"].get("uv", {})


def test_every_sibling_is_a_fromscratch_release_floor() -> None:
    """Each sibling is listed as `fromscratch-<name>>=X.Y.Z`, and all three are present."""
    dependencies: list[str] = _load()["project"]["dependencies"]
    names = {m["name"] for d in dependencies if (m := FLOOR.match(d))}
    assert names == set(SIBLINGS)
    assert len(dependencies) == len(SIBLINGS)


def test_the_package_is_distributed_as_fromscratch_pycpu() -> None:
    """The distribution name follows the series; the import name stays `pycpu`."""
    assert _load()["project"]["name"] == "fromscratch-pycpu"
