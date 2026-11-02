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
    "concepts/bits-and-binary.md": ["bit", "binary", "hex"],
    "concepts/switches-and-nand.md": ["nand", "wire", "gate", "truth table"],
    "concepts/simulating-a-circuit.md": ["event", "settle", "oscillat", "netlist"],
    "concepts/gates.md": ["nand", "truth table", "xor"],
    "concepts/choosing-and-decoding.md": ["mux", "decoder"],
    "concepts/looking-inside.md": ["scope", "zoom", "real", "faking"],
    "concepts/adding.md": ["half adder", "full adder", "carry", "ripple"],
    "concepts/negative-numbers.md": ["two's complement", "overflow", "wrap", "subtract"],
    "concepts/the-alu.md": ["alu", "flag", "zero", "carry", "overflow"],
    "concepts/remembering.md": ["feedback", "latch", "remember"],
    "concepts/the-clock.md": ["clock", "flip-flop", "rising edge", "two-phase"],
    "concepts/registers.md": ["register", "load", "counter"],
    "concepts/ram.md": ["address", "word line", "read", "write"],
    "concepts/how-big-is-our-memory.md": ["gates", "4k", "measured"],
    "concepts/the-bench.md": ["bench", "alu", "gate"],
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


def check_sections(text: str, name: str) -> None:
    """Fail unless the page has the four headings in order and a table before Try It."""
    positions = [text.find(heading) for heading in REQUIRED_SECTIONS]
    assert all(p >= 0 for p in positions), f"{name} is missing a required section"
    assert positions == sorted(positions), f"{name} has its sections out of order"
    assert re.search(r"^\|.*\|\s*$", text[: positions[0]], flags=re.MULTILINE), (
        f"{name} needs a table before ## Try It"
    )


def run_try_it(text: str, name: str) -> None:
    """Run every Try It block; each must exist, carry an Output marker, and match it."""
    blocks = _python_blocks(_try_it_section(text))
    assert blocks, f"{name} has no python block under ## Try It"
    for block in blocks:
        expected = _expected_output(block)
        assert expected is not None, f"{name} has a Try It block with no '# Output:' marker"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exec(compile(block, name, "exec"), {"__name__": "__try_it__"})  # noqa: S102
        actual = [line.rstrip() for line in buffer.getvalue().splitlines()]
        assert actual == expected, f"{name} printed {actual}, expected {expected}"


GOOD_PAGE = """# Title

## An Analogy

| thing | real thing |
|-------|------------|
| a | b |

## Try It

```python
print(1)
# Output:
# 1
```

## How It Works

## Why Does This Matter?

## What's Next
"""


def test_a_well_formed_page_passes_both_guards() -> None:
    """The guards accept a page that has everything."""
    check_sections(GOOD_PAGE, "good")
    run_try_it(GOOD_PAGE, "good")


def test_a_missing_section_is_caught() -> None:
    """Dropping a required heading fails the section guard."""
    with pytest.raises(AssertionError, match="missing"):
        check_sections(GOOD_PAGE.replace("## How It Works\n", ""), "bad")


def test_sections_in_the_wrong_order_are_caught() -> None:
    """Swapping two headings fails the section guard."""
    swapped = (
        GOOD_PAGE.replace("## How It Works", "## TMP")
        .replace("## Why Does This Matter?", "## How It Works")
        .replace("## TMP", "## Why Does This Matter?")
    )
    with pytest.raises(AssertionError, match="order"):
        check_sections(swapped, "bad")


def test_a_page_without_a_table_is_caught() -> None:
    """A page with no analogy table before Try It fails the section guard."""
    table = "| thing | real thing |\n|-------|------------|\n| a | b |\n"
    assert table in GOOD_PAGE
    with pytest.raises(AssertionError, match="table"):
        check_sections(GOOD_PAGE.replace(table, ""), "bad")


def test_wrong_output_is_caught() -> None:
    """A Try It whose real output differs from its comment fails."""
    with pytest.raises(AssertionError, match="expected"):
        run_try_it(GOOD_PAGE.replace("# 1\n", "# 2\n"), "bad")


def test_a_try_it_with_no_python_block_is_caught() -> None:
    """An empty Try It section fails."""
    with pytest.raises(AssertionError, match="no python block"):
        run_try_it(GOOD_PAGE.replace("```python", "```text"), "bad")


def test_a_block_without_an_output_marker_is_caught() -> None:
    """A Try It block that never says what it prints fails."""
    with pytest.raises(AssertionError, match="Output"):
        run_try_it(GOOD_PAGE.replace("# Output:\n# 1\n", ""), "bad")


def test_the_guards_work_on_a_page_on_disk(tmp_path: Path) -> None:
    """A page read from a temporary file goes through the same guards."""
    page = tmp_path / "page.md"
    page.write_text(GOOD_PAGE, encoding="utf-8")
    check_sections(page.read_text(encoding="utf-8"), "disk")


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_every_concept_page_has_every_required_section(page: Path) -> None:
    """Each concept page has the four headings in order, and a table before Try It."""
    check_sections(page.read_text(encoding="utf-8"), _page_id(page))


@pytest.mark.parametrize("page", _all_pages(), ids=_page_id)
def test_every_page_is_in_the_nav(page: Path) -> None:
    """Every page appears in mkdocs.yml, so a reader can reach it."""
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert page.relative_to(DOCS).as_posix() in nav


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_try_it_examples_run(page: Path) -> None:
    """Each Try It has python blocks, and each prints exactly what its `# Output:` says."""
    run_try_it(page.read_text(encoding="utf-8"), _page_id(page))


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
