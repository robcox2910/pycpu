"""Check that every part view carries the live source of the code that built it."""

import inspect
from pathlib import Path
from typing import Any, cast

import pytest
from pynet.loop import run as run_loop
from pyweb.testing import TestClient, TestResponse

from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.code import DOCS_URL, PAGE_TITLES, PART_PAGES, built_by
from pycpu.cockpit.picture import part_picture
from pycpu.cockpit.session import Cockpit
from pycpu.cpu import GateMachine

ROOT = Path(__file__).parent.parent
CONCEPTS = ROOT / "docs" / "concepts"
BITS = 6
OK = 200
EVERY_PART = sorted(GateMachine(BITS).taps)


@pytest.fixture(scope="module")
def gate() -> GateMachine:
    """Build one small gate machine to ask about."""
    return GateMachine(BITS)


class TestEveryPart:
    """Every tapped part has a builder, a page and a source."""

    def test_every_tap_has_a_builder_and_a_page(self, gate: GateMachine) -> None:
        """Taps, builders and PART_PAGES name exactly the same parts."""
        assert set(gate.builders) == set(gate.taps)
        assert set(PART_PAGES) == set(gate.taps)

    def test_every_page_stem_names_a_concept_page_with_a_title(self) -> None:
        """Each stem is a file in docs/concepts and has a menu title."""
        for stem in PART_PAGES.values():
            assert (CONCEPTS / f"{stem}.md").is_file(), stem
            assert stem in PAGE_TITLES
            heading = (CONCEPTS / f"{stem}.md").read_text(encoding="utf-8").splitlines()[0]
            assert heading == f"# {PAGE_TITLES[stem]}"

    @pytest.mark.parametrize("path", EVERY_PART)
    def test_each_part_answers_with_its_live_source(self, gate: GateMachine, path: str) -> None:
        """The record names the function, a repo file, a line and a docs URL."""
        record = built_by(gate, path)
        function = gate.builders[path]
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
        """The ALU's code holds its scope, and file and line find that line."""
        record = built_by(gate, "cpu.alu")
        code = cast("str", record["code"])
        assert 'with c.scope("alu"):' in code
        assert record["file"] == "src/pycpu/arithmetic.py"
        lines = (ROOT / "src/pycpu/arithmetic.py").read_text(encoding="utf-8").splitlines()
        assert lines[cast("int", record["line"]) - 1].strip() == 'with c.scope("alu"):'

    def test_halt_is_cut_out_of_build_cpu(self, gate: GateMachine) -> None:
        """The halt scope sits in `_build_cpu`, so that is the method shown, cut to the block."""
        record = built_by(gate, "cpu.halt")
        assert record["function"] == "pycpu.cpu.GateMachine._build_cpu"
        code = cast("str", record["code"])
        assert code.startswith('with c.scope("halt"):')
        assert "opcode_lines" not in code

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
        assert record["line"] == gate.builders["cpu.alu"].__code__.co_firstlineno
        assert cast("dict[str, str]", record["page"])["title"] == "The ALU"


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
