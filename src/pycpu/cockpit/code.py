"""The code behind a part: the Python that built it, read live, for the Cockpit's code panel.

Think of a toy with a sticker on its back saying which page of the instruction booklet
built it. This module is that sticker, except it never copies the page: it opens the
booklet itself, the real source file, every time you ask. Because the code shown is read
from the module that is running, it cannot drift from the circuit it built.
"""

import inspect
import textwrap
from collections.abc import Callable
from pathlib import Path
from types import CodeType

import pycpu
from pycpu.cpu import GateMachine

DOCS_URL = "http://127.0.0.1:8000/concepts"  # where `uv run mkdocs serve` shows the pages
_PACKAGE_DIR = Path(pycpu.__file__).resolve().parent


def root_for(package_dir: Path) -> Path:
    """Pick the folder that file paths are shown relative to.

    In a checkout (`package_dir` is `<repo>/src/pycpu`, and `<repo>/pyproject.toml`
    exists) that is the repo, so paths read `src/pycpu/...`. Installed from a wheel it is
    the folder that holds the package, so paths read `pycpu/...`.
    """
    checkout = package_dir.parents[1]
    return checkout if (checkout / "pyproject.toml").is_file() else package_dir.parent


_REPO_ROOT = root_for(_PACKAGE_DIR)

# The concept page that explains each part: the one whose How It Works describes it.
PART_PAGES = {
    "cpu.alu": "the-alu",
    "cpu.registers": "registers",
    "ram": "ram",
    "cpu.halt": "what-happens-when-things-go-wrong",
    "cpu.write_back": "fetch-decode-execute",
    "cpu.address_mux": "fetch-decode-execute",
    "cpu.next_pc": "fetch-decode-execute",
    "cpu.next_sp": "the-stack",
}

# The title of each page the Cockpit links to: the part pages above and every walk's
# `see_also` page, as each page's own heading gives it.
PAGE_TITLES = {
    "the-alu": "The ALU",
    "registers": "Registers",
    "ram": "RAM",
    "what-happens-when-things-go-wrong": "What Happens When Things Go Wrong",
    "fetch-decode-execute": "Fetch, Decode, Execute",
    "the-stack": "The Stack",
    "stepping-a-pebble-line": "Stepping a Pebble Line",
    "variables-in-memory": "Variables in Memory",
    "the-clock": "The Clock",
    "how-a-function-call-really-works": "How a Function Call Really Works",
}


def page_link(stem: str) -> dict[str, str]:
    """Return the `title` and `url` of a concept page on the docs server on your own computer.

    Args:
        stem: The page's file name without `.md`, such as `"the-alu"`.

    Raises:
        KeyError: If the page has no title in `PAGE_TITLES`.

    """
    return {"title": PAGE_TITLES[stem], "url": f"{DOCS_URL}/{stem}/"}


def _block(lines: list[str], scope: str) -> tuple[int, list[str]]:
    """Cut the `with c.scope("<scope>"):` block out of a function's lines.

    Returns:
        The offset of the block's first line within `lines`, and the block's lines
        (the `with` line and everything indented deeper). When the function has no
        such line the whole function: offset 0 and all its lines.

    """
    # Edge cases this does not handle (none occur in the CPU's code today): a comment or a
    # multi-line string dedented to the `with` line's level ends the block early, the first
    # line that matches wins if a scope of the same name is nested earlier, and a `with`
    # line with a trailing comment or an `as` name is not found (the whole function shows).
    opener = f'with c.scope("{scope}"):'
    for start, line in enumerate(lines):
        if line.strip() == opener:
            indent = len(line) - len(line.lstrip())
            end = start + 1
            while end < len(lines):
                text = lines[end]
                if text.strip() and len(text) - len(text.lstrip()) <= indent:
                    break
                end += 1
            while not lines[end - 1].strip():
                end -= 1
            return start, lines[start:end]
    return 0, lines


def _relative(function: Callable[..., object]) -> str:
    """Name the function's file relative to the repo root, or as it is when outside it."""
    name = inspect.getsourcefile(function)
    if name is None:
        return ""
    try:
        return Path(name).resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return name


def built_by(gate: GateMachine, path: str) -> dict[str, object]:
    """Show the live source of the function that built the part `path`.

    When the function builds more than one part, such as `_build_write_back`, only the
    part's own `with c.scope(...)` block is kept, so the code shown is the code that
    made this part. The block is named by the part's recorded scope, or else by the last
    segment of its path. A part whose scope is opened somewhere else (the RAM's name is a
    variable) gets the whole function.

    Args:
        gate: The gate machine whose builders were recorded as it was wired up.
        path: The part's scope path, such as `"cpu.alu"`.

    Returns:
        `function` (a dotted name), `file` (relative to the repo), `line` (the first line
        shown, 1-based), `code` (None if Python cannot find the source) and `page`
        (`title` and `url` of the concept page that explains the part). If the source
        is missing, `line` is the function's first line (0 when it has no code object).

    Raises:
        KeyError: If the part has no builder recorded.

    """
    function, scope = gate.builders[path]
    code: str | None = None
    first = getattr(function, "__code__", None)
    line = first.co_firstlineno if isinstance(first, CodeType) else 0
    try:
        lines, start = inspect.getsourcelines(function)
    except OSError, TypeError:
        pass
    else:
        offset, kept = _block(
            [text.rstrip("\n") for text in lines], scope or path.rsplit(".", 1)[-1]
        )
        code = textwrap.dedent("\n".join(kept))
        line = start + offset
    return {
        "function": f"{function.__module__}.{function.__qualname__}",
        "file": _relative(function),
        "line": line,
        "code": code,
        "page": page_link(PART_PAGES[path]),
    }
