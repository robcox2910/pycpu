"""Check that every part view carries the live source of the code that built it."""

import inspect
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
from pynet.loop import run as run_loop
from pyweb.testing import TestClient, TestResponse

from pycpu.cockpit import code as code_module
from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.code import DOCS_URL, PAGE_TITLES, PART_PAGES, built_by, root_for
from pycpu.cockpit.picture import part_picture, walk_picture
from pycpu.cockpit.session import Cockpit
from pycpu.cockpit.walks import load_walks
from pycpu.cpu import GateMachine

ROOT = Path(__file__).parent.parent
PUBLIC_CONCEPTS = "https://robcox2910.github.io/pycpu/concepts/"
CONCEPTS = ROOT / "docs" / "concepts"
BITS = 6
WALK_BITS = 8  # the walks' programs need more memory than the part views do
OK = 200
# "ram" opens `c.scope(name)`, so there is no literal block to cut; "cpu.alu" makes its flags
# after its block closes, so only the whole function shows every gate its view reads.
WHOLE_FUNCTION = {"ram", "cpu.alu"}
EVERY_PART = sorted(GateMachine(BITS).taps)


@pytest.fixture(scope="module")
def gate() -> GateMachine:
    """Build one small gate machine to ask about."""
    return GateMachine(BITS)


class TestEveryPart:
    """Every tapped part has a builder, a page and a source."""

    def test_every_title_belongs_to_a_page_the_cockpit_links(self) -> None:
        """PAGE_TITLES holds the part pages and the walks' pages, and nothing else."""
        assert set(PAGE_TITLES) == {*PART_PAGES.values(), *(w.see_also for w in load_walks())}

    def test_every_tap_has_a_builder_and_a_page(self, gate: GateMachine) -> None:
        """Taps, builders and PART_PAGES name exactly the same parts."""
        assert set(gate.builders) == set(gate.taps)
        assert set(PART_PAGES) == set(gate.taps)

    def test_every_page_stem_names_a_concept_page_with_a_title(self) -> None:
        """Each stem is a file in docs/concepts and has a menu title."""
        for stem in {*PART_PAGES.values(), *(walk.see_also for walk in load_walks())}:
            assert (CONCEPTS / f"{stem}.md").is_file(), stem
            assert stem in PAGE_TITLES
            heading = (CONCEPTS / f"{stem}.md").read_text(encoding="utf-8").splitlines()[0]
            assert heading == f"# {PAGE_TITLES[stem]}"

    @pytest.mark.parametrize("path", EVERY_PART)
    def test_each_part_answers_with_its_live_source(self, gate: GateMachine, path: str) -> None:
        """The record names the function, a repo file, a line and a docs URL."""
        record = built_by(gate, path)
        function = gate.builders[path][0]
        assert record["function"] == f"{function.__module__}.{function.__qualname__}"
        file = ROOT / str(record["file"])
        assert file.is_file()
        code = cast("str", record["code"])
        first = code.splitlines()[0].strip()
        assert (
            file.read_text(encoding="utf-8").splitlines()[cast("int", record["line"]) - 1].strip()
            == first
        )
        stem = PART_PAGES[path]
        assert record["page"] == {"title": PAGE_TITLES[stem], "url": f"{DOCS_URL}/{stem}/"}


class TestTheRightBlock:
    """A method that builds two parts shows only the viewed part's block."""

    def test_write_back_shows_no_stack_pointer_code(self, gate: GateMachine) -> None:
        """The write-back view starts at its own scope and stops before next_sp."""
        code = cast("str", built_by(gate, "cpu.write_back")["code"])
        assert code.startswith('with c.scope("write_back"):')
        assert 'with c.scope("next_sp"):' not in code

    def test_next_sp_shows_no_write_back_code(self, gate: GateMachine) -> None:
        """The stack-pointer view starts at its own scope and holds no write-back."""
        code = cast("str", built_by(gate, "cpu.next_sp")["code"])
        assert code.startswith('with c.scope("next_sp"):')
        assert 'with c.scope("write_back"):' not in code
        assert "ram_data" not in code

    def test_alu_points_at_its_line_in_arithmetic(self, gate: GateMachine) -> None:
        """The ALU's code holds its scope, and file and line find the `def` line."""
        record = built_by(gate, "cpu.alu")
        code = cast("str", record["code"])
        assert 'with c.scope("alu"):' in code
        assert record["file"] == "src/pycpu/arithmetic.py"
        lines = (ROOT / "src/pycpu/arithmetic.py").read_text(encoding="utf-8").splitlines()
        assert lines[cast("int", record["line"]) - 1].startswith("def alu(")

    def test_alu_shows_the_return_that_makes_its_flags_reach_the_view(
        self, gate: GateMachine
    ) -> None:
        """The whole `alu` shows, so the `return AluOutput(...)` after the block is there."""
        code = cast("str", built_by(gate, "cpu.alu")["code"])
        assert code.startswith("def alu(")
        assert "AluOutput(" in code

    def test_halt_shows_the_fault_block_that_makes_its_wires(self, gate: GateMachine) -> None:
        """The halt view reads wires made in the `fault` block of `_build_checks`."""
        record = built_by(gate, "cpu.halt")
        assert record["function"] == "pycpu.cpu.GateMachine._build_checks"
        code = cast("str", record["code"])
        assert code.startswith('with c.scope("fault"):')
        assert "halt_load" in code
        assert "mux_bus(c, bad, w.imm8, fault_code)" in code
        assert 'with c.scope("port"):' not in code

    @pytest.mark.parametrize("path", [p for p in EVERY_PART if p not in WHOLE_FUNCTION])
    def test_every_part_starts_at_its_own_scope_line(self, gate: GateMachine, path: str) -> None:
        """Except the named whole-function cases, the code opens with the part's own scope."""
        scope = gate.builders[path][1] or path.rsplit(".", 1)[-1]
        code = cast("str", built_by(gate, path)["code"])
        assert code.splitlines()[0] == f'with c.scope("{scope}"):'

    def test_ram_falls_back_to_the_whole_function(self, gate: GateMachine) -> None:
        """RAM opens `c.scope(name)`, so there is no literal block and the whole method shows."""
        record = built_by(gate, "ram")
        code = cast("str", record["code"])
        assert record["function"] == "pycpu.memory.Ram.__init__"
        assert code.startswith("def __init__(")
        assert "with c.scope(name):" in code


class TestWithoutSource:
    """When Python cannot find the source the record is still filled in."""

    def test_code_is_none_and_the_rest_remains(
        self, gate: GateMachine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OSError from inspect gives code None, but function, file, line and page stay."""

        def fail(*_args: object) -> Any:
            """Pretend the source is not on this computer."""
            raise OSError

        monkeypatch.setattr(inspect, "getsource", fail)
        monkeypatch.setattr(inspect, "getsourcelines", fail)
        record = built_by(gate, "cpu.alu")
        assert record["code"] is None
        assert record["function"] == "pycpu.arithmetic.alu"
        assert record["file"] == "src/pycpu/arithmetic.py"
        assert record["line"] == gate.builders["cpu.alu"][0].__code__.co_firstlineno
        assert cast("dict[str, str]", record["page"])["title"] == "The ALU"

    def test_file_is_still_named_when_only_compiled_code_is_installed(
        self, gate: GateMachine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no `.py` file found, `file` falls back to the compiled file's path."""

        def no_source(*_args: object) -> None:
            """Pretend only compiled code is installed."""

        monkeypatch.setattr(inspect, "getsourcefile", no_source)
        assert built_by(gate, "cpu.alu")["file"] != ""


class TestInThePartView:
    """The part picture and the route carry `built_by`."""

    def test_part_picture_holds_built_by(self) -> None:
        """`part_picture` adds the same record `built_by` gives."""
        cockpit = Cockpit(BITS)
        picture = part_picture(cockpit, "cpu.alu")
        assert picture["built_by"] == built_by(cockpit.computer.gate, "cpu.alu")

    def test_the_route_answers_built_by(self) -> None:
        """`/api/part` includes `built_by` for the ALU and for RAM."""

        async def main() -> list[TestResponse]:
            """Ask for two parts."""
            client = TestClient(create_cockpit(address_bits=BITS))
            return [await client.get(f"/api/part?path={p}") for p in ("cpu.alu", "ram")]

        for response, name in zip(run_loop(main()), ("alu", "Ram.__init__"), strict=True):
            assert response.status == OK
            body = cast("dict[str, Any]", response.json())
            assert name in body["built_by"]["function"]


class TestFilePaths:
    """File paths are repo-relative in a checkout and package-relative when installed."""

    def test_a_checkout_is_relative_to_the_repo(self, tmp_path: Path) -> None:
        """With a pyproject.toml above src/, the root is the repo."""
        package = tmp_path / "src" / "pycpu"
        package.mkdir(parents=True)
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        assert root_for(package) == tmp_path

    def test_an_installed_package_is_relative_to_its_parent(self, tmp_path: Path) -> None:
        """Without a pyproject.toml, paths start at the package folder's name."""
        package = tmp_path / "lib" / "site-packages" / "pycpu"
        package.mkdir(parents=True)
        assert root_for(package) == package.parent

    def test_built_by_uses_the_installed_root(
        self, gate: GateMachine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the root is the package's parent, `file` reads `pycpu/arithmetic.py`."""
        monkeypatch.setattr(code_module, "_REPO_ROOT", code_module._PACKAGE_DIR.parent)
        assert built_by(gate, "cpu.alu")["file"] == "pycpu/arithmetic.py"


def test_docs_links_are_public(gate: GateMachine) -> None:
    """The built-by link and every walk's see_also link point at the public docs site."""
    page = cast("dict[str, str]", built_by(gate, "cpu.alu")["page"])
    assert page["url"].startswith(PUBLIC_CONCEPTS)
    cockpit = Cockpit(WALK_BITS)
    for walk in load_walks():
        cockpit.go_to_walk(walk.name, 0)
        picture = cast("dict[str, Any]", walk_picture(cockpit))
        assert picture["see_also"]["url"].startswith(PUBLIC_CONCEPTS)


def test_no_local_docs_server() -> None:
    """No file under src/ names the old local docs server."""
    for path in (ROOT / "src").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".html", ".toml", ".js", ".css"}:
            assert "127.0.0.1:8000" not in path.read_text(encoding="utf-8"), path


def test_console_script() -> None:
    """`pycpu` is a console script that runs `pycpu.__main__:main`."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["scripts"]["pycpu"] == "pycpu.__main__:main"
