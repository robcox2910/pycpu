"""Guard the documentation, which is the heart of this project.

Tests can catch a missing section or an example that no longer runs. They cannot
catch a bad explanation, so a human still reads every page as a curious 12-year-old.
"""

import contextlib
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
CONCEPT_PAGES = sorted((DOCS / "concepts").glob("*.md"))
REQUIRED_SECTIONS = ["## Try It", "## How It Works", "## Why Does This Matter?", "## What's Next"]
OUTPUT_MARKER = "# Output:"

# Each page, mapped to words it must contain. Later tasks add a line per page.
KEY_IDEAS: dict[str, list[str]] = {
    "index.md": ["nand", "pebble", "cockpit"],
    "from-scratch.md": ["petzold", "nand", "faking", "pebble"],
}


def _page_id(path: Path) -> str:
    """Name a page by its path inside docs/."""
    return str(path.relative_to(DOCS))


def _all_pages() -> list[Path]:
    """List every published page, leaving out the design notes under superpowers/."""
    return sorted(p for p in DOCS.rglob("*.md") if "superpowers" not in p.relative_to(DOCS).parts)


def _try_it_section(text: str) -> str:
    """Return the text between `## Try It` and the next `##` heading."""
    start = text.index("## Try It")
    rest = text[start + len("## Try It") :]
    match = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest[: match.start()] if match else rest


def _python_blocks(section: str) -> list[str]:
    """Pull every fenced python block out of a section."""
    return re.findall(r"```python\n(.*?)```", section, flags=re.DOTALL)


def _expected_output(block: str) -> list[str] | None:
    """Read the lines after `# Output:`, or return None when the block has none."""
    lines = block.splitlines()
    if OUTPUT_MARKER not in (line.strip() for line in lines):
        return None
    index = [line.strip() for line in lines].index(OUTPUT_MARKER)
    expected: list[str] = []
    for line in lines[index + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("#"):
            break
        expected.append(stripped[1:].removeprefix(" ").rstrip())
    return expected


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_every_concept_page_has_every_required_section(page: Path) -> None:
    """Each concept page has the four headings in order, and a table before Try It."""
    text = page.read_text(encoding="utf-8")
    positions = [text.find(heading) for heading in REQUIRED_SECTIONS]
    assert all(p >= 0 for p in positions), f"{_page_id(page)} is missing a required section"
    assert positions == sorted(positions), f"{_page_id(page)} has its sections out of order"
    before_try_it = text[: positions[0]]
    assert re.search(r"^\|.*\|\s*$", before_try_it, flags=re.MULTILINE), (
        f"{_page_id(page)} needs a table before ## Try It"
    )


@pytest.mark.parametrize("page", _all_pages(), ids=_page_id)
def test_every_page_is_in_the_nav(page: Path) -> None:
    """Every page appears in mkdocs.yml, so a reader can reach it."""
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert page.relative_to(DOCS).as_posix() in nav


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_try_it_examples_run(page: Path) -> None:
    """Each Try It block runs, and prints exactly what its `# Output:` comment says."""
    section = _try_it_section(page.read_text(encoding="utf-8"))
    for block in _python_blocks(section):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exec(compile(block, str(page), "exec"), {"__name__": "__try_it__"})  # noqa: S102
        expected = _expected_output(block)
        if expected is not None:
            actual = [line.rstrip() for line in buffer.getvalue().splitlines()]
            assert actual == expected


@pytest.mark.parametrize(("page", "words"), sorted(KEY_IDEAS.items()), ids=lambda v: str(v))
def test_key_ideas_appear(page: str, words: list[str]) -> None:
    """Each page mentions the words it exists to teach."""
    text = (DOCS / page).read_text(encoding="utf-8").lower()
    for word in words:
        assert word.lower() in text, f"{page} never mentions '{word}'"


def test_site_builds_strictly(tmp_path: Path) -> None:
    """The whole site builds with `mkdocs build --strict`, so no link is broken."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "mkdocs", "build", "--strict", "-d", str(tmp_path / "site")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
