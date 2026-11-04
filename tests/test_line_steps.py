"""Tests for stepping a Pebble line: over a call, into it, and every way a step can stop."""

import time
from pathlib import Path
from typing import Any, cast

import pytest
from pynet.loop import run
from pyweb.testing import TestClient, TestResponse

from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.session import (
    FINISHED_NOTE,
    LIMIT_REASON,
    MAX_LINE_INSTRUCTIONS,
    Cockpit,
    CockpitBusy,
    CockpitRefusal,
    LineStep,
)
from pycpu.computer import StepSize
from pycpu.fast import FastMachine
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.translator import FRAME_POINTER, translate

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "docs" / "concepts" / "stepping-a-pebble-line.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-11-01-pycpu-roadmap.md"
OK = 200
BAD_REQUEST = 400
BITS = 8
WORDS = 1 << BITS
COUNTDOWN = """\
let n = 2
while n > 0 {
    print(n)
    n = n - 1
}
"""
COUNTDOWN_TRACE = [1, 2, 3, 4, 2, 3, 4, 2]
SECOND_LINE = 2
FRAME_INSTRUCTIONS = 10
LINE_ONE_INSTRUCTIONS = 4
LINE_AFTER_WHILE = 3
DOUBLE = "fn double(n) {\n    return n * 2\n}\nprint(double(3))\n"
DOUBLE_BODY_LINE = 2
DOUBLE_X = "fn double(n) {\n    return n * 2\n}\nlet x = 3\nprint(double(x))\n"
DOUBLE_X_CALL_LINE = 5
MAX_INSTRUCTION_STEPS = 100
RECURSION = """\
fn f(n) {
    if n == 0 {
        return 0
    }
    return f(n - 1)
}
print(f(2))
"""
RECURSIVE_LINE = 5
RECURSION_CALLER_LINE = 7
RECURSION_FIRST_LINE = 2
ENDLESS = "while true { }\n"
LONG_CALL = """\
fn slow() {
    let i = 0
    while i < 2000 {
        i = i + 1
    }
    return i
}
let x = slow()
print(x)
"""
LONG_CALL_LINE = 8
DIVIDE_BY_ZERO = "let a = 7\nprint(a // 0)\n"
DIVIDE_LINE = 2
GATE_STEPS = 50
TOUR_COUNTDOWN = COUNTDOWN.replace("let n = 2", "let n = 3")
ONE_SECOND = 1.0
TOUR_LINE_STEPS = 6


def _pebble(source: str) -> Cockpit:
    """Build a 256-word Cockpit session with `source` loaded."""
    cockpit = Cockpit(BITS)
    cockpit.load_pebble(source)
    return cockpit


def _line(cockpit: Cockpit) -> int | None:
    """Return the Pebble line of the instruction the Cockpit is paused before."""
    assert cockpit.translated is not None
    return cockpit.translated.line_at(cockpit.computer.instruction_start.pc)


def _fp(cockpit: Cockpit) -> int:
    """Return the frame pointer at the paused instruction."""
    return cockpit.computer.instruction_start.registers[FRAME_POINTER]


def _trace(source: str) -> list[int]:
    """List the lines a run visits, as a line step should: ready, located words only.

    A separate fast engine runs the program to its halt. Before each instruction,
    the word counts if it has a ready frame and a line; a run of words with the same
    line and frame pointer is one entry.
    """
    translated = translate(source)
    machine = FastMachine(WORDS)
    machine.load_program(translated.program.words)
    seen: list[tuple[int, int]] = []
    while not machine.halted:
        pc, fp = machine.pc, machine.register(FRAME_POINTER)
        line = translated.line_at(pc)
        ready = translated.frames[pc] is not None
        if ready and line is not None and (not seen or seen[-1] != (line, fp)):
            seen.append((line, fp))
        machine.step()
    return [line for line, _ in seen]


def _words(path: Path) -> str:
    """Read a page with every run of spaces and line breaks squeezed to one space."""
    return " ".join(path.read_text(encoding="utf-8").split())


def _post(client: TestClient, path: str, body: object) -> TestResponse:
    """Send a JSON body to `path` and wait for the answer."""
    return run(client.post(path, json=body))  # pyright: ignore[reportArgumentType]


def _json(response: TestResponse) -> dict[str, Any]:
    """Read a response body as a JSON object."""
    return cast("dict[str, Any]", response.json())


class TestStepOverLines:
    """A line step runs to the next line of the same code, and stops ready to look inside."""

    def test_the_countdown_visits_the_same_lines_as_a_full_run(self) -> None:
        """Stepping until halted reaches each line a straight run visits after the first, in order.

        The trace's first entry is the line the program starts on, where the
        Cockpit already is after the load; every line step reaches the next entry.
        """
        assert _trace(COUNTDOWN) == COUNTDOWN_TRACE
        cockpit = _pebble(COUNTDOWN)
        assert _line(cockpit) == COUNTDOWN_TRACE[0]
        reached: list[int | None] = []
        while (step := cockpit.step_line(into=False)).stopped == "line":
            reached.append(_line(cockpit))
        assert step.stopped == "halted"
        assert reached == COUNTDOWN_TRACE[1:]
        assert cockpit.computer.state().output == tuple(b"2\n1\n")

    def test_every_stop_is_paused_on_a_ready_located_word(self) -> None:
        """Each stop is at a boundary in the gates, on a word with a ready frame and a line."""
        cockpit = _pebble(COUNTDOWN)
        translated = cockpit.translated
        assert translated is not None
        while cockpit.step_line(into=False).stopped == "line":
            pc = cockpit.computer.instruction_start.pc
            assert cockpit.computer.paused
            assert cockpit.computer.gate.at_boundary
            assert cockpit.computer.gate.state() == cockpit.computer.instruction_start
            assert translated.frames[pc] is not None
            assert translated.line_at(pc) is not None

    def test_the_note_counts_the_instructions_to_the_new_line(self) -> None:
        """A step that reaches a line says how many instructions it ran and where it got to."""
        cockpit = _pebble(COUNTDOWN)
        step = cockpit.step_line(into=False)
        assert cockpit.note == f"Ran {step.instructions} instructions to reach line 2."

    def test_the_first_step_is_ten_frame_instructions_then_four_of_line_one(self) -> None:
        """The countdown's first 14 instructions are 10 making main's frame and 4 storing `n`."""
        translated = translate(COUNTDOWN)
        machine = FastMachine(WORDS)
        machine.load_program(translated.program.words)
        ran = 0
        while translated.frames[machine.pc] is None:
            machine.step()
            ran += 1
        assert ran == FRAME_INSTRUCTIONS
        while translated.line_at(machine.pc) != SECOND_LINE:
            machine.step()
            ran += 1
        assert ran == FRAME_INSTRUCTIONS + LINE_ONE_INSTRUCTIONS
        assert "Ten instructions make the frame, and four more put 2 into `n`" in _words(PAGE)

    def test_the_first_step_after_a_load_reaches_the_second_line(self) -> None:
        """Just after a load main's frame is not made yet, and one step still reaches line 2."""
        cockpit = _pebble(COUNTDOWN)
        assert cockpit.translated is not None
        assert cockpit.translated.frames[cockpit.computer.instruction_start.pc] is None
        assert cockpit.step_line(into=False).stopped == "line"
        assert _line(cockpit) == SECOND_LINE

    def test_a_step_started_part_way_through_an_instruction_finishes_it_first(self) -> None:
        """After 50 gate steps, a line step finishes the instruction and stops at the next line."""
        cockpit, fresh = _pebble(COUNTDOWN), _pebble(COUNTDOWN)
        for session in (cockpit, fresh):
            session.step_line(into=False)
        cockpit.step(StepSize.GATE, GATE_STEPS)
        assert not cockpit.computer.gate.at_boundary
        assert cockpit.step_line(into=False).stopped == "line"
        assert fresh.step_line(into=False).stopped == "line"
        assert _line(cockpit) == LINE_AFTER_WHILE
        assert cockpit.computer.state() == fresh.computer.state()
        assert cockpit.computer.gate.at_boundary

    def test_a_line_step_marks_what_changed_and_clears_the_last_gate(self) -> None:
        """A line step is a move: `before` is the state it started from, and no gate is named."""
        cockpit = _pebble(COUNTDOWN)
        cockpit.step(StepSize.GATE, 1)
        start = cockpit.computer.state()
        cockpit.step_line(into=False)
        assert cockpit.before == start
        assert cockpit.last_gate is None


class TestOverAndInto:
    """Step over runs a whole call; step into stops on the called function's first line."""

    def test_step_into_stops_on_the_functions_first_line(self) -> None:
        """From the `print(double(3))` line, step into stops on `return n * 2`, in a lower frame."""
        cockpit = _pebble(DOUBLE)
        assert cockpit.step_line(into=True).stopped == "line"
        assert _line(cockpit) == DOUBLE_BODY_LINE
        assert cockpit.translated is not None
        assert cockpit.translated.frames[cockpit.computer.instruction_start.pc] is not None
        assert _fp(cockpit) < cockpit.computer.gate.words - 1

    def test_step_over_runs_the_whole_call(self) -> None:
        """From the same place, step over never stops inside `double`: it halts with 6 printed."""
        cockpit = _pebble(DOUBLE)
        assert cockpit.step_line(into=False).stopped == "halted"
        assert bytes(cockpit.computer.state().output) == b"6\n"

    @pytest.mark.parametrize("into", [False, True])
    def test_a_step_from_any_prologue_word_stops_at_the_next_different_line(
        self, *, into: bool
    ) -> None:
        """Started on any word of `double`'s prologue, a step runs on to line 5, back in main."""
        cockpit = _pebble(DOUBLE_X)
        cockpit.step_line(into=False)
        assert _line(cockpit) == DOUBLE_X_CALL_LINE
        main_fp = _fp(cockpit)
        translated = cockpit.translated
        assert translated is not None
        # Count the instruction steps from line 5 to each word of the prologue, which
        # the translator files under line 2 with no ready frame.
        prologue: list[int] = []
        for steps in range(1, MAX_INSTRUCTION_STEPS):
            cockpit.step(StepSize.INSTRUCTION)
            pc = cockpit.computer.instruction_start.pc
            if translated.line_at(pc) == DOUBLE_BODY_LINE:
                if translated.frames[pc] is not None:
                    break
                prologue.append(steps)
        assert len(prologue) > 1
        for steps in prologue:
            cockpit.load_pebble(DOUBLE_X)  # start again, on the same machine
            cockpit.step_line(into=False)
            for _ in range(steps):
                cockpit.step(StepSize.INSTRUCTION)
            assert cockpit.step_line(into=into).stopped == "line"
            assert _line(cockpit) == DOUBLE_X_CALL_LINE
            assert _fp(cockpit) == main_fp

    def test_step_over_a_recursive_call_stops_back_in_the_caller(self) -> None:
        """Over `return f(n - 1)` stops in a caller's frame, never in a callee or its prologue."""
        cockpit = _pebble(RECURSION)
        translated = cockpit.translated
        assert translated is not None
        while _line(cockpit) != RECURSIVE_LINE:
            assert cockpit.step_line(into=True).stopped == "line"
        start_fp = _fp(cockpit)
        assert cockpit.step_line(into=False).stopped == "line"
        assert _fp(cockpit) > start_fp
        assert _line(cockpit) == RECURSION_CALLER_LINE
        assert translated.frames[cockpit.computer.instruction_start.pc] is not None

    def test_step_into_a_recursive_call_stops_in_the_callee(self) -> None:
        """Into `return f(n - 1)` stops on the callee's first line, in a lower frame."""
        cockpit = _pebble(RECURSION)
        while _line(cockpit) != RECURSIVE_LINE:
            cockpit.step_line(into=True)
        start_fp = _fp(cockpit)
        cockpit.step_line(into=True)
        assert _fp(cockpit) < start_fp
        assert _line(cockpit) == RECURSION_FIRST_LINE


class TestStepsThatCannotReachALine:
    """A step that never reaches a new line stops anyway, says why, and never hangs."""

    def test_an_endless_one_line_loop_stops_at_the_limit(self) -> None:
        """`while true { }` runs exactly the limit, then pauses with a note naming 10,000."""
        cockpit = _pebble(ENDLESS)
        step = cockpit.step_line(into=False)
        assert step == LineStep(MAX_LINE_INSTRUCTIONS, "limit")
        assert MAX_LINE_INSTRUCTIONS == 10_000  # noqa: PLR2004 - the page says 10,000
        assert cockpit.note == (
            "Ran 10,000 instructions without reaching another line, so the step gave up "
            f"there; {LIMIT_REASON}."
        )
        page = Path(__file__).parent.parent / "docs" / "concepts" / "stepping-a-pebble-line.md"
        assert f'"{LIMIT_REASON}"' in " ".join(page.read_text(encoding="utf-8").split())
        assert cockpit.computer.paused
        assert cockpit.computer.gate.at_boundary

    def test_a_step_over_a_very_long_call_stops_at_the_limit_too(self) -> None:
        """A call that runs past 10,000 instructions is cut short like an endless loop."""
        cockpit = _pebble(LONG_CALL)
        while _line(cockpit) != LONG_CALL_LINE:
            cockpit.step(StepSize.INSTRUCTION)
        step = cockpit.step_line(into=False)
        assert step == LineStep(MAX_LINE_INSTRUCTIONS, "limit")
        assert cockpit.note is not None
        assert cockpit.note.endswith(f"{LIMIT_REASON}.")

    def test_a_halted_machine_does_not_move(self) -> None:
        """Once the program has finished, a line step runs nothing and says so."""
        cockpit = _pebble(COUNTDOWN)
        cockpit.run(1000)
        state = cockpit.computer.state()
        assert state.halted
        assert cockpit.step_line(into=True) == LineStep(0, "halted")
        assert cockpit.note == FINISHED_NOTE
        assert FINISHED_NOTE == "The program has finished, so there is no next line."
        assert cockpit.computer.state() == state

    def test_a_step_that_reaches_the_end_says_the_program_stopped(self) -> None:
        """The step that runs into the `halt` stops as halted, with a note saying so."""
        cockpit = _pebble(COUNTDOWN)
        while (step := cockpit.step_line(into=False)).stopped == "line":
            pass
        assert step.instructions > 0
        assert (
            cockpit.note == f"Ran {step.instructions} instructions, and then the program stopped."
        )

    def test_assembly_has_no_lines_to_step(self) -> None:
        """An assembly program gets a refusal, because it has no Pebble lines."""
        cockpit = Cockpit(BITS)
        with pytest.raises(CockpitRefusal, match="need a Pebble program"):
            cockpit.step_line(into=False)

    def test_a_step_that_goes_wrong_still_pauses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even if the fast engine fails mid-step, the computer is paused again afterwards."""
        cockpit = _pebble(COUNTDOWN)

        def broken() -> bool:
            """Fail the way an unexpected bug would."""
            raise RuntimeError

        monkeypatch.setattr(cockpit.computer.fast, "step", broken)
        with pytest.raises(RuntimeError):
            cockpit.step_line(into=False)
        assert cockpit.computer.paused

    def test_a_line_step_while_playing_is_busy(self) -> None:
        """While the computer plays, a line step is refused and the machine is left alone."""
        cockpit = _pebble(COUNTDOWN)
        cockpit.playing = True
        state = cockpit.computer.state()
        with pytest.raises(CockpitBusy):
            cockpit.step_line(into=False)
        assert cockpit.computer.state() == state


class TestTheRoute:
    """`POST /api/step` takes `"line"` and `"line_into"`, with no count but 1."""

    def test_a_line_step_answers_the_picture_with_its_note(self) -> None:
        """The answer is the machine picture, paused on the new line, with the step's note."""
        client = TestClient(create_cockpit(address_bits=BITS))
        _post(client, "/api/pebble", {"source": DOUBLE_X})
        _post(client, "/api/step", {"size": "line"})
        response = _post(client, "/api/step", {"size": "line_into"})
        assert response.status == OK
        machine = _json(response)
        assert machine["pebble"]["line"] == DOUBLE_BODY_LINE
        assert machine["note"] == "Ran 12 instructions to reach line 2."
        assert machine["variables"]["function"] == "double"

    def test_assembly_gets_a_400(self) -> None:
        """A line step on an assembly program is a bad request naming why."""
        client = TestClient(create_cockpit(address_bits=BITS))
        response = _post(client, "/api/step", {"size": "line"})
        assert response.status == BAD_REQUEST
        assert "line steps need a Pebble program" in _json(response)["message"]

    @pytest.mark.parametrize("size", ["line", "line_into"])
    def test_a_count_of_two_gets_a_400(self, size: str) -> None:
        """A line step is one line: a count of 2 is refused and nothing moves."""
        client = TestClient(create_cockpit(address_bits=BITS))
        _post(client, "/api/pebble", {"source": COUNTDOWN})
        before = _json(run(client.get("/api/machine")))
        response = _post(client, "/api/step", {"size": size, "count": 2})
        assert response.status == BAD_REQUEST
        assert _json(response)["message"] == "count is only for gate steps"
        assert _json(run(client.get("/api/machine"))) == before

    def test_an_unknown_size_lists_every_size(self) -> None:
        """The refusal for an unknown size names all five sizes."""
        client = TestClient(create_cockpit(address_bits=BITS))
        response = _post(client, "/api/step", {"size": "page"})
        assert response.status == BAD_REQUEST
        assert _json(response)["message"] == (
            'size must be one of "gate", "cycle", "instruction", "line", "line_into"'
        )

    def test_a_division_by_zero_halts_and_blames_its_line(self) -> None:
        """Line stepping into `print(a // 0)` halts with the fault, and the pane marks line 2."""
        client = TestClient(create_cockpit(address_bits=BITS))
        machine = _json(_post(client, "/api/pebble", {"source": DIVIDE_BY_ZERO}))
        while not machine["halted"]:
            machine = _json(_post(client, "/api/step", {"size": "line"}))
        assert machine["fault"] == "DIVIDE_BY_ZERO"
        assert machine["pebble"]["line"] == DIVIDE_LINE
        assert machine["pebble"]["message"] == "Division by zero at line 2"
        assert machine["note"].endswith("and then the program stopped.")


class TestTheMeasuredFigures:
    """Every figure the page quotes from the roadmap's measurements is in the roadmap."""

    @pytest.mark.parametrize(
        ("page_says", "roadmap_says"),
        [
            ("15 test programs", "the 15 programs in `tests/pebble_programs/`"),
            ("2026-11-03", "on 2026-11-03"),
            ("ran 22 instructions", "min 3, median 22,"),
            ("490,376 gate steps", "Median line step 490,376 gate steps"),
            ("about 6.7 million gate steps", "about 6.7 million"),
            ("about 15 seconds", "about 15 seconds"),
        ],
    )
    def test_the_page_quotes_the_roadmap(self, page_says: str, roadmap_says: str) -> None:
        """The page's figure and the roadmap's measured one agree."""
        assert page_says in _words(PAGE)
        assert roadmap_says in _words(ROADMAP)

    def test_the_page_names_the_limit(self) -> None:
        """The page's 10,000 is `MAX_LINE_INSTRUCTIONS`."""
        assert f"{MAX_LINE_INSTRUCTIONS:,} instructions" in _words(PAGE)


@pytest.mark.slow
def test_a_line_step_at_full_size_answers_in_under_a_second() -> None:
    """On the full 4K-word Cockpit, each line step of the tour countdown answers within 1 s."""
    client = TestClient(create_cockpit(address_bits=RAM_ADDRESS_BITS))
    _post(client, "/api/pebble", {"source": TOUR_COUNTDOWN})
    slowest = 0.0
    for _ in range(TOUR_LINE_STEPS):  # through line 3, `print(n)`, the slowest line
        started = time.perf_counter()
        response = _post(client, "/api/step", {"size": "line"})
        slowest = max(slowest, time.perf_counter() - started)
        assert response.status == OK
    print(f"slowest line step: {slowest:.3f} s")  # noqa: T201 - recorded in the report
    assert slowest < ONE_SECOND
