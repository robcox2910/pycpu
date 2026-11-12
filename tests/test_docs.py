"""Guard the documentation, which is the heart of this project.

Tests can catch a missing section or an example that no longer runs. They cannot
catch a bad explanation, so a human still reads every page as a curious 12-year-old.
"""

import ast
import contextlib
import importlib
import inspect
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pycpu.cockpit.picture import PART_NAMES
from pycpu.cockpit.walks import WALK_ORDER, load_walks
from pycpu.translator.runtime import RUNTIME

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
CONCEPT_PAGES = sorted((DOCS / "concepts").glob("*.md"))
REQUIRED_SECTIONS = ["## Try It", "## How It Works", "## Why Does This Matter?", "## What's Next"]
OUTPUT_MARKER = "# Output:"

# Each page, mapped to words it must contain. Later tasks add a line per page.
KEY_IDEAS: dict[str, list[str]] = {
    "index.md": ["nand", "pebble", "cockpit"],
    "from-scratch.md": ["petzold", "nand", "faking", "pebble"],
    "build-it-yourself.md": ["model kit", "nand", "ripple", "cockpit"],
    "you-built-a-computer.md": ["nand", "layer", "same program", "gates"],
    "concepts/bits-and-binary.md": ["bit", "binary", "hex"],
    "concepts/switches-and-nand.md": ["nand", "wire", "gate", "truth table"],
    "concepts/simulating-a-circuit.md": ["event", "settle", "oscillat", "netlist", "step"],
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
    "concepts/what-is-a-cpu.md": ["instruction", "register", "program counter"],
    "concepts/machine-code.md": ["opcode", "flag", "fault"],
    "concepts/assembly-language.md": ["assembler", "label", "mnemonic"],
    "concepts/the-control-unit.md": ["control unit", "decode", "register file"],
    "concepts/fetch-decode-execute.md": ["fetch", "execute", "instruction register"],
    "concepts/the-stack.md": ["stack", "push", "pop", "stack pointer"],
    "concepts/calling-and-returning.md": ["call", "return", "return address"],
    "concepts/two-engines.md": ["fast engine", "gate engine", "lockstep"],
    "concepts/pausing-and-rewinding.md": ["pause", "rewind", "resume"],
    "concepts/from-pebble-to-machine-code.md": ["bytecode", "translator", "assembly"],
    "concepts/variables-in-memory.md": ["variable", "frame", "frame pointer"],
    "concepts/why-16-bit-numbers-wrap.md": ["wrap", "16-bit", "overflow"],
    "concepts/if-and-while-as-jumps.md": ["jump", "condition", "loop"],
    "concepts/how-a-function-call-really-works.md": ["argument", "frame", "recursion"],
    "concepts/multiply-and-divide.md": ["multiply", "shift", "remainder"],
    "concepts/printing-a-number.md": ["digit", "character", "output port"],
    "concepts/what-happens-when-things-go-wrong.md": [
        "fault",
        "halt",
        "source map",
        "needs more stack room",
    ],
    "concepts/the-cockpit.md": [
        "cockpit",
        "register",
        "gate",
        "instruction",
        "pebble",
        "source map",
    ],
    "concepts/stepping-a-pebble-line.md": ["line", "step over", "step into"],
    "concepts/watching-it-run.md": ["live", "event", "pause"],
    "concepts/a-tour-of-the-cockpit.md": ["tour", "pebble line", "gate"],
    "concepts/the-magnifying-glass.md": ["depth", "magnifying glass", "step"],
    "concepts/what-just-happened.md": ["sentence", "what just happened", "real values"],
    "concepts/guided-walks.md": ["walk", "now you try", "replay"],
    "concepts/the-code-behind-a-part.md": ["built_by", "inspect", "drift", "live"],
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


def check_whats_next(text: str, name: str) -> None:
    """Fail unless the `## What's Next` section links to another .md page."""
    start = text.index("## What's Next")
    assert re.search(r"\]\([^)]*\.md\)", text[start:]), f"{name}'s What's Next links to no page"


def _last_nav_page() -> str:
    """Return the last concept page in mkdocs.yml, the one with nowhere further to climb.

    The Reference section sits after the climb, and is not a step on it.
    """
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    return re.findall(r":\s*(concepts/\S+\.md)\s*$", nav, flags=re.MULTILINE)[-1]


def _run_block(block: str, expected: list[str], name: str) -> None:
    """Run one python block on its own and fail unless it prints exactly `expected`."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(compile(block, name, "exec"), {"__name__": "__try_it__"})  # noqa: S102
    actual = [line.rstrip() for line in buffer.getvalue().splitlines()]
    assert actual == expected, f"{name} printed {actual}, expected {expected}"


def run_try_it(text: str, name: str) -> None:
    """Run every Try It block; each must exist, carry an Output marker, and match it."""
    blocks = _python_blocks(_try_it_section(text))
    assert blocks, f"{name} has no python block under ## Try It"
    for block in blocks:
        expected = _expected_output(block)
        assert expected is not None, f"{name} has a Try It block with no '# Output:' marker"
        _run_block(block, expected, name)


def run_marked_blocks(text: str, name: str) -> int:
    """Run every python block outside Try It that carries an Output marker; return how many.

    Try It blocks are run by `run_try_it`, so between the two every block that says
    what it prints, in any section of any page, is checked against what it really prints.
    """
    try_it: set[str] = set(_python_blocks(_try_it_section(text))) if "## Try It" in text else set()
    count = 0
    for block in _python_blocks(text):
        expected = _expected_output(block)
        if expected is None or block in try_it:
            continue
        _run_block(block, expected, name)
        count += 1
    return count


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


HOW_IT_WORKS_BLOCK = """
```python
print(2)
# Output:
# 2
```
"""


def test_a_marked_block_outside_try_it_is_run() -> None:
    """A block under How It Works with an Output marker runs, and a wrong one fails."""
    page = GOOD_PAGE + HOW_IT_WORKS_BLOCK
    assert run_marked_blocks(page, "good") == 1
    with pytest.raises(AssertionError, match="expected"):
        run_marked_blocks(page.replace("# 2\n", "# 3\n"), "bad")


def test_an_unmarked_block_outside_try_it_is_left_alone() -> None:
    """A block that does not say what it prints is shown to the reader, not run."""
    page = GOOD_PAGE + "```python\nraise SystemExit\n```\n"
    assert run_marked_blocks(page, "good") == 0


def test_a_whats_next_without_a_link_is_caught(tmp_path: Path) -> None:
    """A page whose What's Next links nowhere fails the climb guard."""
    check_whats_next("## What's Next\n\nRead [RAM](ram.md).\n", "good")
    bad = tmp_path / "bad.md"
    bad.write_text("## What's Next\n\nOn the next page we do RAM.\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="links to no page"):
        check_whats_next(bad.read_text(encoding="utf-8"), "bad")


def test_the_guards_work_on_a_page_on_disk(tmp_path: Path) -> None:
    """A page read from a temporary file goes through the same guards."""
    page = tmp_path / "page.md"
    page.write_text(GOOD_PAGE, encoding="utf-8")
    check_sections(page.read_text(encoding="utf-8"), "disk")


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_every_concept_page_has_every_required_section(page: Path) -> None:
    """Each concept page has the four headings in order, and a table before Try It."""
    check_sections(page.read_text(encoding="utf-8"), _page_id(page))


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_every_whats_next_links_to_the_next_page(page: Path) -> None:
    """Every concept page except the last in the nav points on to another page."""
    if page.relative_to(DOCS).as_posix() == _last_nav_page():
        pytest.skip("the last page has nowhere further to climb")
    check_whats_next(page.read_text(encoding="utf-8"), _page_id(page))


@pytest.mark.parametrize("page", _all_pages(), ids=_page_id)
def test_every_page_is_in_the_nav(page: Path) -> None:
    """Every page appears in mkdocs.yml, so a reader can reach it."""
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert page.relative_to(DOCS).as_posix() in nav


@pytest.mark.parametrize("page", CONCEPT_PAGES, ids=_page_id)
def test_try_it_examples_run(page: Path) -> None:
    """Each Try It has python blocks, and each prints exactly what its `# Output:` says."""
    run_try_it(page.read_text(encoding="utf-8"), _page_id(page))


@pytest.mark.parametrize("page", _all_pages(), ids=_page_id)
def test_every_marked_block_prints_what_it_says(page: Path) -> None:
    """Every python block with an `# Output:` marker, wherever it sits, prints exactly that."""
    run_marked_blocks(page.read_text(encoding="utf-8"), _page_id(page))


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


def test_every_walks_concept_page_links_to_that_walk_in_the_cockpit() -> None:
    """Each walk's `see_also` page holds exactly one link to the walk, on the local Cockpit."""
    names = {walk.see_also: name for name, walk in zip(WALK_ORDER, load_walks(), strict=True)}
    assert len(names) == len(WALK_ORDER)
    for page, name in names.items():
        text = (DOCS / "concepts" / f"{page}.md").read_text(encoding="utf-8")
        link = f"http://127.0.0.1:8765/#walk={name}"
        assert text.count(link) == 1, f"{page} must link to {link} exactly once"
        para = next(p for p in text.split("\n\n") if link in p)
        assert "uv run pycpu" in para
        assert para.startswith("**See it in the Cockpit.**")
        assert text.count("http://127.0.0.1:8765/#walk=") == 1, "only one walk link per page"


def test_no_page_links_to_the_cockpit_anywhere_but_the_local_address() -> None:
    """The Cockpit only runs on your own computer, so its links point only there."""
    for page in _all_pages():
        for url in re.findall(r"https?://[^\s)]*cockpit[^\s)]*", page.read_text(encoding="utf-8")):
            assert url.startswith("http://127.0.0.1:8765"), f"{_page_id(page)}: {url}"


BUILD_PAGE = DOCS / "build-it-yourself.md"
BUILD_COLUMNS = 6
WALK_LINK = re.compile(r"http://127\.0\.0\.1:8765/#walk=([a-z-]+)")
PART_WATCH = re.compile(r"open \*\*(.+?)\*\* from the Every part list at the part depth")
TICKED = re.compile(r"`([^`]+)`")


def _build_rows() -> list[list[str]]:
    """Read the numbered rows of the Build It Yourself table as lists of six cells."""
    rows: list[list[str]] = []
    for line in BUILD_PAGE.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == BUILD_COLUMNS, f"a table cell holds a pipe or is missing: {line}"
        rows.append(cells)
    return rows


def _nav_pages() -> list[str]:
    """List every page in mkdocs.yml, in menu order."""
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    return re.findall(r":\s*(\S+\.md)\s*$", nav, flags=re.MULTILINE)


def _resolve(dotted: str) -> object:
    """Import the longest module prefix of `dotted`, then walk the rest as attributes."""
    parts = dotted.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        try:
            thing: object = importlib.import_module(".".join(parts[:cut]))
        except ModuleNotFoundError:
            continue
        for name in parts[cut:]:
            thing = getattr(thing, name)
        return thing
    raise AssertionError(dotted)


def _test_exists(ref: str) -> bool:
    """Say whether `tests/<file>.py::[Class::]test` names a test that is really defined."""
    file, *path = ref.split("::")
    tree = ast.parse((ROOT / "tests" / file).read_text(encoding="utf-8"))
    body: list[ast.stmt] = tree.body
    for index, name in enumerate(path):
        kind = ast.FunctionDef if index == len(path) - 1 else ast.ClassDef
        found = [n for n in body if isinstance(n, kind) and n.name == name]
        if not found:
            return False
        body = found[0].body
    return True


def test_build_it_yourself_has_its_sections_and_a_runnable_pinned_try_it() -> None:
    """The top-level Build It Yourself page has the four sections, and its Try It is run."""
    text = BUILD_PAGE.read_text(encoding="utf-8")
    check_sections(text, "build-it-yourself.md")
    check_whats_next(text, "build-it-yourself.md")
    run_try_it(text, "build-it-yourself.md")


def test_you_built_a_computer_has_its_sections_and_a_runnable_try_it() -> None:
    """The closing page has the four sections, follows Build It Yourself, and its Try It is run."""
    text = (DOCS / "you-built-a-computer.md").read_text(encoding="utf-8")
    check_sections(text, "you-built-a-computer.md")
    check_whats_next(text, "you-built-a-computer.md")
    run_try_it(text, "you-built-a-computer.md")
    pages = _nav_pages()
    assert pages.index("you-built-a-computer.md") == pages.index("build-it-yourself.md") + 1


def test_build_it_yourself_follows_from_scratch_in_the_nav() -> None:
    """The page sits right after From Scratch in mkdocs.yml."""
    pages = _nav_pages()
    assert pages.index("build-it-yourself.md") == pages.index("from-scratch.md") + 1


def test_every_build_step_names_a_real_function_class_or_routine() -> None:
    """Each named piece is a function, class or method of pycpu, or a label in RUNTIME."""
    rows = _build_rows()
    assert rows
    for cells in rows:
        names = TICKED.findall(cells[2])
        assert names, cells[2]
        for name in names:
            if name.startswith("__"):
                assert f"\n{name}:" in RUNTIME, f"{name} is not a routine in RUNTIME"
                continue
            thing = _resolve(name)
            if name == "pycpu.translator.runtime.RUNTIME":
                assert thing is RUNTIME
                continue
            assert inspect.isclass(thing) or inspect.isroutine(thing), name
            assert getattr(thing, "__module__", "").startswith("pycpu"), name


def test_every_build_step_links_a_real_page_in_nav_order() -> None:
    """Page links exist, and the rows follow the menu's order."""
    pages = _nav_pages()
    positions: list[int] = []
    for cells in _build_rows():
        link = re.search(r"\]\(([^)]+\.md)\)", cells[3])
        assert link, cells
        assert (DOCS / link[1]).is_file(), link[1]
        positions.append(pages.index(link[1]))
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_every_build_step_names_its_own_real_test() -> None:
    """Each row names at least one test that exists, and no test is named twice."""
    named: list[str] = []
    for cells in _build_rows():
        refs = [r for r in TICKED.findall(cells[4]) if r.startswith("tests/")]
        assert refs, cells[4]
        for ref in (r.removeprefix("tests/") for r in refs):
            assert _test_exists(ref), f"{ref} is not a test"
            named.append(ref)
    assert len(set(named)) == len(named)


BUILD_STEPS = 29  # "When you reach row 29" in build-it-yourself.md


def test_the_build_rows_are_numbered_one_to_the_last() -> None:
    """Rows run 1, 2, 3... with no gap, and the page's "row N" is the last one."""
    numbers = [int(cells[0]) for cells in _build_rows()]
    assert numbers == list(range(1, BUILD_STEPS + 1))
    assert f"When you reach row {BUILD_STEPS}," in BUILD_PAGE.read_text(encoding="utf-8")


def test_the_test_finder_rejects_a_missing_test() -> None:
    """The finder says no to a test that is not defined, in a file or in a class."""
    assert _test_exists("test_simulator.py::test_nand_truth_table")
    assert not _test_exists("test_simulator.py::test_nothing_like_this")
    assert not _test_exists("test_translator.py::TestRunningPebble::test_nothing_like_this")


def test_every_runtime_routine_is_named_with_its_label() -> None:
    """Rows about the runtime name a routine, and the label is in RUNTIME."""
    labels = [n for cells in _build_rows() for n in TICKED.findall(cells[2]) if n.startswith("__")]
    assert labels == ["__mul", "__divmod", "__print_int"]


def test_every_watch_it_is_a_real_walk_or_a_real_part_and_every_walk_link_is_real() -> None:
    """Watch-it cells hold a walk, a part shown by its friendly name, or a dash; all are real."""
    part_names = set(PART_NAMES.values())
    for cells in _build_rows():
        watch = cells[5]
        if watch == "—":
            continue
        walk = WALK_LINK.fullmatch(watch)
        part = PART_WATCH.fullmatch(watch)
        assert walk or part, watch
        if part:
            assert part[1] in part_names, part[1]
    for name in WALK_LINK.findall(BUILD_PAGE.read_text(encoding="utf-8")):
        assert name in WALK_ORDER, name
