"""Tests for the Cockpit: the local page for watching the running computer."""

import json
import re
import time
from collections.abc import Coroutine
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from pynet.loop import run
from pyweb.app import App
from pyweb.aserver import AsyncServer
from pyweb.testing import TestClient, TestResponse

from pycpu import __main__ as entry
from pycpu.__main__ import HOST, banner, open_cockpit
from pycpu.assembler import assemble
from pycpu.circuit import Circuit
from pycpu.cockpit import picture as picture_module
from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.picture import (
    PART_NAMES,
    listing,
    machine_picture,
    part_for_instruction,
    variables_picture,
)
from pycpu.cockpit.session import (
    DEMO_PROGRAM,
    END_NOTE,
    MAX_GATE_STEPS,
    MAX_PEBBLE_CHARACTERS,
    MAX_RUN,
    NO_GATE_ENDING,
)
from pycpu.cockpit.session import Cockpit as Session
from pycpu.computer import Computer, StepSize
from pycpu.cpu import GateMachine
from pycpu.fast import FastMachine
from pycpu.isa import Opcode, decode
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.state import REGISTER_COUNT
from pycpu.translator import FRAME_POINTER, translate

OK = 200
BAD_REQUEST = 400
NOT_FOUND = 404
CONFLICT = 409
BUSY = "the computer is running: press pause first"
SMALL = 6
WORDS = 1 << SMALL
WINDOW = 16
BEHIND = 4
RUN_TO_ADD = 5  # li, lhi, li, call, li: then the add is next
GATE_BATCH = 500
ADD_ADDRESS = 8
HUNDRED = 100
SEVEN = 7
NEAR_END = 62
OUTSIDE = 100
JUMP_OUTSIDE = 0x6000 | OUTSIDE  # jmp 100, a word the assembler would refuse to write
JUMP_NEAR_END = 0x6000 | NEAR_END
ALU_GATE = "cpu.alu.adder.bit0.full_adder.half_adder.and"
TOO_MANY_WORDS = "\n".join([".word 0"] * (WORDS + 1))
PEBBLE_BITS = 8  # 256 words: room for a small Pebble program and its runtime routines
PEBBLE_WORDS = 1 << PEBBLE_BITS
PEBBLE_STACK_BITS = 7  # 128 words: three `print(1)` lines fit, with no room left for main's stack
PEBBLE_STACK_PRINTS = 3
COUNTDOWN = """\
let n = 2
while n > 0 {
    print(n)
    n = n - 1
}
"""
COUNTDOWN_LINES = 5
PRINT_LINE = 3
DIVIDE_BY_ZERO = "let a = 7\nprint(a // 0)\n"
DIVIDE_LINE = 2
DECIMAL_DIVIDE = "let a = 7\nprint(a / 2)\n"
DIVIDE_COLUMN = 9
TOUR_COUNTDOWN = COUNTDOWN.replace("let n = 2", "let n = 3")
TOUR_RUN = 180  # the second tour's Run, from the first instruction of the print routine
TOUR_DIVIDE = TOUR_COUNTDOWN.replace("print(n)", "print(10 // (n - 1))")
TOUR_LINE_AFTER_PRINT = 4
NOT_PEBBLE = "let x = \n"
NOT_PEBBLE_COLUMN = 9


def _run[T](job: Coroutine[Any, Any, T]) -> T:
    """Run one async test body to the end and hand back its result."""
    return run(job)


def _json(response: TestResponse) -> dict[str, Any]:
    """Read a response body as a JSON object."""
    return cast("dict[str, Any]", response.json())


class Cockpit:
    """A small Cockpit (64 words of memory) with plain, waiting-free helpers for each route."""

    def __init__(self, address_bits: int = SMALL) -> None:
        """Build the Cockpit (64 words unless told otherwise) and a pretend browser for it."""
        self.client = TestClient(create_cockpit(address_bits=address_bits))

    def machine(self) -> dict[str, Any]:
        """Return the machine picture from GET /api/machine."""
        return _json(_run(self.client.get("/api/machine")))

    def post(self, path: str, body: object) -> TestResponse:
        """Send a JSON body to `path` and return the raw response."""
        return _run(self.client.post(path, json=body))  # pyright: ignore[reportArgumentType]

    def step(self, size: str, count: int | None = None) -> dict[str, Any]:
        """Step by `size` (and `count`, if given), insisting the Cockpit agrees."""
        body: dict[str, object] = {"size": size}
        if count is not None:
            body["count"] = count
        response = self.post("/api/step", body)
        assert response.status == OK, response.text
        return _json(response)

    def run(self, instructions: int) -> dict[str, Any]:
        """Run `instructions` instructions, insisting the Cockpit agrees."""
        response = self.post("/api/run", {"instructions": instructions})
        assert response.status == OK, response.text
        return _json(response)

    def load(self, source: str) -> TestResponse:
        """Send assembly text to POST /api/program."""
        return self.post("/api/program", {"source": source})

    def pebble(self, source: str) -> TestResponse:
        """Send a Pebble program to POST /api/pebble."""
        return self.post("/api/pebble", {"source": source})

    def view(self, path: str) -> TestResponse:
        """Look inside the part at `path`."""
        return _run(self.client.get("/api/view", query={"path": path}))

    def wires(self, path: str) -> list[int]:
        """Collect every gate output under a scope, walking all the scopes inside it."""
        view = _json(self.view(path))
        values = [gate["value_out"] for gate in view["gates"]]
        for child in view["children"]:
            values += self.wires(f"{path}.{child['name']}")
        return values


def _fast_after(instructions: int) -> FastMachine:
    """Run the demo program on a fast engine of the same size, as a prediction."""
    machine = FastMachine(WORDS)
    machine.load_program(assemble(DEMO_PROGRAM, words=WORDS).words)
    machine.run(instructions)
    return machine


class TestTheMachinePicture:
    """GET /api/machine shows the paused computer, read from the gate engine."""

    def test_the_cockpit_opens_paused_before_the_first_instruction(self) -> None:
        """At the start every register is 0, sp is the RAM size and pc points at address 0."""
        machine = Cockpit().machine()
        assert machine["paused"] is True
        assert machine["phase"] == "fetch"
        assert machine["at_boundary"] is True
        assert machine["registers"] == [0] * REGISTER_COUNT
        assert machine["pc"] == 0
        assert machine["sp"] == WORDS
        assert machine["flags"] == {"zero": 0, "negative": 0, "carry": 0, "overflow": 0}
        assert machine["halted"] is False
        assert machine["halt_code"] == 0
        assert machine["output"] == ""

    def test_the_current_instruction_is_the_word_at_pc_as_assembly(self) -> None:
        """The demo program starts with `set r1, 0xFFFF`, whose first half is `li r1, 255`."""
        instruction = Cockpit().machine()["instruction"]
        first = assemble(DEMO_PROGRAM, words=WORDS).words[0]
        assert instruction == {"address": 0, "word": first, "text": "li r1, 255"}

    def test_the_memory_window_is_sixteen_words_from_zero_at_the_start(self) -> None:
        """With pc at 0 the window cannot start 4 behind, so it starts at 0."""
        memory = Cockpit().machine()["memory"]
        words = assemble(DEMO_PROGRAM, words=WORDS).words
        assert [cell["address"] for cell in memory] == list(range(WINDOW))
        assert memory[1] == {
            "address": 1,
            "word": words[1],
            "text": "lhi r1, 255",
            "part": "ram.word1",
        }

    def test_the_memory_window_starts_four_words_behind_pc(self) -> None:
        """Paused before the add at address 8, the window shows addresses 4 to 19."""
        machine = Cockpit().run(RUN_TO_ADD)
        assert machine["pc"] == ADD_ADDRESS
        assert machine["memory"][0]["address"] == ADD_ADDRESS - BEHIND
        assert len(machine["memory"]) == WINDOW
        assert machine["instruction"]["text"] == "add r3, r3, r2"

    def test_the_memory_window_slides_back_to_end_at_the_last_word(self) -> None:
        """Near the end of memory the window still holds 16 words, the last 16."""
        cockpit = Cockpit()
        assert cockpit.load(f".word {JUMP_NEAR_END}").status == OK
        machine = cockpit.step("instruction")
        assert machine["pc"] == NEAR_END
        assert [cell["address"] for cell in machine["memory"]] == list(range(WORDS - WINDOW, WORDS))

    def test_a_pc_outside_memory_shows_no_word_and_a_fault(self) -> None:
        """Jumping past the end faults on the next fetch; the instruction has no word."""
        cockpit = Cockpit()
        assert cockpit.load(f".word {JUMP_OUTSIDE}").status == OK
        cockpit.step("instruction")
        machine = cockpit.step("instruction")
        assert machine["halted"] is True
        assert machine["halt_code"] == 1
        assert machine["instruction"] == {"address": OUTSIDE, "word": None, "text": ""}
        assert machine["fault"] == "BAD_ADDRESS"
        assert [cell["address"] for cell in machine["memory"]] == list(range(WORDS - WINDOW, WORDS))

    def test_a_normal_halt_names_no_fault(self) -> None:
        """A program that halts with 0, or with a code that is no `Fault`, has `fault` null."""
        cockpit = Cockpit()
        assert cockpit.machine()["fault"] is None
        assert cockpit.load("halt").status == OK
        machine = cockpit.step("instruction")
        assert (machine["halted"], machine["halt_code"], machine["fault"]) == (True, 0, None)
        assert cockpit.load("halt 7").status == OK
        machine = cockpit.step("instruction")
        assert (machine["halt_code"], machine["fault"]) == (SEVEN, None)

    def test_a_programs_own_halt_one_to_three_shares_the_fault_names(self) -> None:
        """`halt 2` is indistinguishable from a stack overflow, so it is named as one."""
        cockpit = Cockpit()
        assert cockpit.load("halt 2").status == OK
        assert cockpit.step("instruction")["fault"] == "STACK_OVERFLOW"


class TestStepping:
    """POST /api/step moves the gate engine by a gate, a beat or an instruction."""

    def test_one_instruction_moves_the_machine_as_the_fast_engine_predicts(self) -> None:
        """After each instruction, the registers, pc, sp and output match a fast run."""
        cockpit = Cockpit()
        for done in range(1, RUN_TO_ADD + 2):
            machine = cockpit.step("instruction")
            predicted = _fast_after(done).state()
            assert machine["registers"] == list(predicted.registers)
            assert machine["pc"] == predicted.pc
            assert machine["sp"] == predicted.sp
            assert machine["output"] == predicted.output_text

    def test_a_cycle_step_leaves_the_add_fetched_but_not_obeyed(self) -> None:
        """Half way through the add, pc has moved on but the instruction is still the add."""
        cockpit = Cockpit()
        cockpit.run(RUN_TO_ADD)
        machine = cockpit.step("cycle")
        assert machine["phase"] == "execute"
        assert machine["at_boundary"] is False
        assert machine["pc"] == ADD_ADDRESS + 1
        assert machine["instruction"]["address"] == ADD_ADDRESS
        assert machine["instruction"]["text"] == "add r3, r3, r2"

    def test_gate_steps_change_the_phase_and_the_wires_over_one_instruction(self) -> None:
        """Stepping 500 gates at a time through an instruction, both beats appear and wires move."""
        cockpit = Cockpit()
        cockpit.run(RUN_TO_ADD)
        phases: set[str] = set()
        pictures = [cockpit.wires("cpu.pc.bit0")]
        machine = cockpit.step("gate", GATE_BATCH)
        while machine["instruction"]["address"] == ADD_ADDRESS:
            phases.add(machine["phase"])
            pictures.append(cockpit.wires("cpu.pc.bit0"))
            machine = cockpit.step("gate", GATE_BATCH)
        assert phases == {"fetch", "execute"}
        assert len({tuple(picture) for picture in pictures}) > 1
        assert machine["registers"][3] == ord("3")

    def test_a_count_of_a_hundred_is_the_same_as_a_hundred_single_gates(self) -> None:
        """The 100 gates button is a shortcut, not a different kind of step."""
        one_by_one, at_once = Cockpit(), Cockpit()
        for _ in range(HUNDRED):
            one_by_one.step("gate")
        machine, single = at_once.step("gate", HUNDRED), one_by_one.machine()
        # Only the sentence differs: the shortcut says how many gate steps it took.
        assert machine["happened"] == f"Took {HUNDRED} gate steps. {single['happened']}"
        assert {**machine, "happened": None} == {**single, "happened": None}
        assert at_once.wires("cpu") == one_by_one.wires("cpu")

    def test_gate_steps_stop_when_the_machine_halts(self) -> None:
        """A huge count on a program that halts at once finishes quickly and halts."""
        cockpit = Cockpit()
        assert cockpit.load("halt 7").status == OK
        machine = cockpit.step("gate", MAX_GATE_STEPS)
        assert machine["halted"] is True
        assert machine["halt_code"] == SEVEN

    def test_bad_step_requests_are_400s(self) -> None:
        """Unknown sizes, missing sizes, bad counts and counts on big steps are all refused."""
        bad: list[object] = [
            {"size": "giant"},
            {},
            {"size": 1},
            {"size": "gate", "count": 0},
            {"size": "gate", "count": MAX_GATE_STEPS + 1},
            {"size": "gate", "count": "5"},
            {"size": "gate", "count": True},
            {"size": "cycle", "count": 2},
            {"size": "instruction", "count": 2},
            [1, 2],
        ]
        cockpit = Cockpit()
        assert [cockpit.post("/api/step", item).status for item in bad] == [BAD_REQUEST] * len(bad)
        assert cockpit.machine()["pc"] == 0

    def test_a_cycle_or_instruction_step_may_say_count_one(self) -> None:
        """A count of 1 is what those steps already mean, so it is allowed."""
        cockpit = Cockpit()
        assert cockpit.step("cycle", 1)["phase"] == "execute"
        assert cockpit.step("instruction", 1)["at_boundary"] is True


class TestBrokenBodies:
    """A body that is not JSON at all, or is empty, is refused rather than crashing."""

    @pytest.mark.parametrize("path", ["/api/step", "/api/run", "/api/program", "/api/pebble"])
    @pytest.mark.parametrize("body", [b"{nope", b""], ids=["broken", "empty"])
    def test_a_broken_or_empty_body_is_a_400(self, path: str, body: bytes) -> None:
        """Broken JSON and an empty body both get 400, and the machine does not move."""
        cockpit = Cockpit()
        response = _run(cockpit.client.post(path, body=body))
        assert response.status == BAD_REQUEST
        assert cockpit.machine()["pc"] == 0


class TestRewindAndRun:
    """POST /api/rewind goes back to the instruction's start; POST /api/run runs fast."""

    def test_rewind_goes_back_to_the_start_of_the_instruction(self) -> None:
        """After some gates and a beat, rewind shows exactly the starting picture again."""
        cockpit = Cockpit()
        start = cockpit.machine()
        cockpit.step("gate", HUNDRED)
        cockpit.step("cycle")
        response = cockpit.post("/api/rewind", {})
        assert response.status == OK
        assert _without_changed(_json(response)) == _without_changed(start)

    def test_running_to_the_end_prints_the_countdown(self) -> None:
        """The demo program counts 3, 2, 1 and halts normally."""
        machine = Cockpit().run(MAX_RUN)
        assert machine["output"] == "321"
        assert machine["halted"] is True
        assert machine["halt_code"] == 0
        assert machine["paused"] is True

    def test_run_finishes_a_half_done_instruction_first(self) -> None:
        """Run 1 from half way through the add finishes the add and runs one more."""
        cockpit = Cockpit()
        cockpit.run(RUN_TO_ADD)
        cockpit.step("cycle")
        machine = cockpit.run(1)
        assert machine["at_boundary"] is True
        assert machine["registers"] == list(_fast_after(RUN_TO_ADD + 2).state().registers)

    def test_bad_run_requests_are_400s(self) -> None:
        """Zero, too many, text, a boolean, nothing and a list are all refused."""
        bad: list[object] = [
            {"instructions": 0},
            {"instructions": MAX_RUN + 1},
            {"instructions": "5"},
            {"instructions": True},
            {},
            [5],
        ]
        cockpit = Cockpit()
        assert [cockpit.post("/api/run", item).status for item in bad] == [BAD_REQUEST] * len(bad)


class TestLoadingAProgram:
    """POST /api/program puts new assembly into the computer, or says which line is wrong."""

    def test_a_new_program_starts_paused_at_its_first_instruction(self) -> None:
        """Loading `li r0, 7` and running it leaves 7 in r0."""
        cockpit = Cockpit()
        cockpit.run(RUN_TO_ADD)
        response = cockpit.load("li r0, 7\nhalt")
        assert response.status == OK
        machine = _json(response)
        assert machine["pc"] == 0
        assert machine["paused"] is True
        assert machine["sp"] == WORDS
        assert machine["instruction"]["text"] == "li r0, 7"
        assert cockpit.run(MAX_RUN)["registers"][0] == SEVEN

    def test_a_mistake_is_a_400_naming_the_line(self) -> None:
        """The assembler's own message, with its line number, comes back."""
        cockpit = Cockpit()
        response = cockpit.load("li r0, 7\nfly r1")
        assert response.status == BAD_REQUEST
        assert _json(response)["message"].startswith("line 2:")
        assert cockpit.machine()["instruction"]["text"] == "li r1, 255"

    def test_a_program_too_big_for_memory_is_a_400(self) -> None:
        """65 words do not fit in 64."""
        assert Cockpit().load(TOO_MANY_WORDS).status == BAD_REQUEST

    def test_source_that_is_not_text_is_a_400(self) -> None:
        """A number, nothing at all, or a list is not assembly."""
        cockpit = Cockpit()
        statuses = [cockpit.post("/api/program", item).status for item in ({"source": 5}, {}, [1])]
        assert statuses == [BAD_REQUEST] * len(statuses)


class TestPebbleOnTheCockpit:
    """POST /api/pebble translates a Pebble program, loads it, and the picture names its line."""

    def _cockpit(self) -> Cockpit:
        """Build a 256-word Cockpit with the countdown loaded, insisting the Cockpit agrees."""
        cockpit = Cockpit(PEBBLE_BITS)
        response = cockpit.pebble(COUNTDOWN)
        assert response.status == OK, response.text
        return cockpit

    def test_an_assembly_program_has_no_pebble(self) -> None:
        """The demo program is assembly, so `pebble` is null."""
        assert Cockpit().machine()["pebble"] is None

    def test_a_pebble_program_starts_paused_on_its_first_line(self) -> None:
        """The source comes back line by line, and line 1 runs first."""
        machine = self._cockpit().machine()
        assert machine["pc"] == 0
        assert machine["paused"] is True
        assert machine["sp"] == PEBBLE_WORDS
        assert machine["pebble"] == {"source": COUNTDOWN.splitlines(), "line": 1, "message": None}
        assert len(machine["pebble"]["source"]) == COUNTDOWN_LINES
        assert machine["instruction"]["word"] == translate(COUNTDOWN).program.words[0]

    def test_each_instruction_shows_the_line_that_made_it(self) -> None:
        """Stepping to the end, the line is always the source map's line for the instruction."""
        cockpit = self._cockpit()
        translated = translate(COUNTDOWN)
        machine = cockpit.machine()
        seen: set[int | None] = set()
        while not machine["halted"]:
            line = machine["pebble"]["line"]
            assert line == translated.line_at(machine["instruction"]["address"])
            seen.add(line)
            machine = cockpit.step("instruction")
        assert seen == {1, 2, PRINT_LINE, 4, None}

    def test_half_way_through_an_instruction_the_line_is_still_its_line(self) -> None:
        """The fetch moves `pc` on, but the line stays with the instruction being obeyed."""
        cockpit = self._cockpit()
        translated = translate(COUNTDOWN)
        machine = cockpit.machine()
        while translated.line_at(machine["pc"] + 1) == translated.line_at(machine["pc"]):
            machine = cockpit.step("instruction")
        here = translated.line_at(machine["pc"])
        machine = cockpit.step("cycle")
        assert translated.line_at(machine["pc"]) != here
        assert machine["pebble"]["line"] == here

    def test_running_to_the_end_says_the_program_finished(self) -> None:
        """The countdown prints 2 then 1, each on its own line; once halted no line is marked."""
        machine = self._cockpit().run(MAX_RUN)
        assert machine["output"] == "2\n1\n"
        assert machine["halted"] is True
        assert machine["pebble"]["line"] is None
        assert machine["pebble"]["message"] == "The program finished"

    def test_a_fault_names_its_pebble_line(self) -> None:
        """Dividing by zero halts on line 2, and the message says so."""
        cockpit = Cockpit(PEBBLE_BITS)
        assert cockpit.pebble(DIVIDE_BY_ZERO).status == OK
        machine = cockpit.run(MAX_RUN)
        assert machine["fault"] == "DIVIDE_BY_ZERO"
        assert machine["pebble"]["line"] == DIVIDE_LINE
        assert machine["pebble"]["message"] == f"Division by zero at line {DIVIDE_LINE}"

    def test_loading_assembly_afterwards_clears_the_pebble(self) -> None:
        """An assembly program has no Pebble source, so the pane empties."""
        cockpit = self._cockpit()
        assert cockpit.load("halt").status == OK
        assert cockpit.machine()["pebble"] is None

    def test_rewind_keeps_the_pebble_line(self) -> None:
        """Rewinding half an instruction shows exactly the picture from its start."""
        cockpit = self._cockpit()
        start = cockpit.step("instruction")
        cockpit.step("cycle")
        assert _without_changed(_json(cockpit.post("/api/rewind", {}))) == _without_changed(start)

    def test_an_unsupported_feature_is_a_400_with_its_line_and_column(self) -> None:
        """`/` is refused with the translator's message, line and column; nothing is loaded."""
        cockpit = self._cockpit()
        response = cockpit.pebble(DECIMAL_DIVIDE)
        assert response.status == BAD_REQUEST
        body = _json(response)
        assert body["message"].startswith("the / operator")
        assert (body["line"], body["column"]) == (DIVIDE_LINE, DIVIDE_COLUMN)
        assert cockpit.machine()["pebble"]["source"] == COUNTDOWN.splitlines()

    def test_a_pebble_mistake_is_a_400_with_its_line_and_column(self) -> None:
        """Pebble's own errors, such as a missing value, come back with their place."""
        cockpit = Cockpit(PEBBLE_BITS)
        response = cockpit.pebble(NOT_PEBBLE)
        assert response.status == BAD_REQUEST
        body = _json(response)
        assert "at line 1" in body["message"]
        assert (body["line"], body["column"]) == (1, NOT_PEBBLE_COLUMN)
        assert cockpit.machine()["pebble"] is None

    def test_a_program_whose_stack_has_no_room_is_a_400(self) -> None:
        """Three prints fit in 128 words, but main's first frame after them would not."""
        cockpit = Cockpit(address_bits=PEBBLE_STACK_BITS)
        source = "print(1)\n" * PEBBLE_STACK_PRINTS
        translated = translate(source)
        assert len(translated.program.words) <= (1 << PEBBLE_STACK_BITS)
        response = cockpit.pebble(source)
        assert response.status == BAD_REQUEST
        assert "room for its stack" in _json(response)["message"]
        assert cockpit.machine()["pebble"] is None

    def test_a_program_too_big_for_this_cockpits_memory_is_a_400(self) -> None:
        """The countdown and its routines need more than the 64-word Cockpit has."""
        cockpit = Cockpit()
        response = cockpit.pebble(COUNTDOWN)
        assert response.status == BAD_REQUEST
        words = len(translate(COUNTDOWN).program.words)
        assert _json(response)["message"] == (
            f"this program needs {words} words, but this Cockpit's memory has only {WORDS}"
        )
        assert cockpit.machine()["instruction"]["text"] == "li r1, 255"

    def test_the_second_tour_comes_out_of_the_print_routine_on_line_four(self) -> None:
        """Stepping into the print routine, then running 180, has printed 3 and is on line 4."""
        cockpit = Cockpit(PEBBLE_BITS)
        machine = _json(cockpit.pebble(TOUR_COUNTDOWN))
        while machine["pebble"]["line"] is not None:
            machine = cockpit.step("instruction")
        machine = cockpit.run(TOUR_RUN)
        assert machine["output"] == "3\n"
        assert machine["pebble"]["line"] == TOUR_LINE_AFTER_PRINT
        machine = cockpit.run(MAX_RUN)
        assert machine["output"] == "3\n2\n1\n"
        assert machine["pebble"]["message"] == "The program finished"

    def test_the_second_tours_divide_by_zero_prints_twice_then_names_line_three(self) -> None:
        """10 // 2 and 10 // 1 print, then 10 // 0 halts on line 3."""
        cockpit = Cockpit(PEBBLE_BITS)
        assert cockpit.pebble(TOUR_DIVIDE).status == OK
        machine = cockpit.run(MAX_RUN)
        assert machine["output"] == "5\n10\n"
        assert machine["pebble"]["line"] == PRINT_LINE
        assert machine["pebble"]["message"] == f"Division by zero at line {PRINT_LINE}"

    def test_a_text_too_long_to_ever_fit_is_a_400_before_translating(self) -> None:
        """One character over the limit is refused with a friendly message; nothing loads."""
        cockpit = Cockpit(PEBBLE_BITS)
        response = cockpit.pebble("#" * (MAX_PEBBLE_CHARACTERS + 1))
        assert response.status == BAD_REQUEST
        assert "at most 65,536 characters" in _json(response)["message"]
        assert cockpit.machine()["pebble"] is None

    def test_a_text_just_at_the_limit_is_translated(self) -> None:
        """A comment padded to exactly the limit is still a Pebble program."""
        source = "print(7)\n#"
        source += "x" * (MAX_PEBBLE_CHARACTERS - len(source))
        assert Cockpit(PEBBLE_BITS).pebble(source).status == OK

    def test_source_that_is_not_text_is_a_400(self) -> None:
        """A number, nothing at all, or a list is not a Pebble program."""
        cockpit = Cockpit(PEBBLE_BITS)
        statuses = [cockpit.post("/api/pebble", item).status for item in ({"source": 5}, {}, [1])]
        assert statuses == [BAD_REQUEST] * len(statuses)


class TestTheViewAndThePage:
    """GET /api/view looks into the gate engine's circuit; GET / serves the page."""

    def test_the_whole_circuit_holds_the_cpu_and_the_ram(self) -> None:
        """With no path the view is the top of the circuit."""
        view = _json(Cockpit().view(""))
        assert sorted(child["name"] for child in view["children"]) == ["cpu", "ram"]

    def test_the_alu_is_one_click_down_from_the_cpu(self) -> None:
        """`cpu` lists `alu` among its parts."""
        view = _json(Cockpit().view("cpu"))
        assert "alu" in [child["name"] for child in view["children"]]

    def test_the_tour_gates_show_forty_eight_plus_three_in_the_first_column(self) -> None:
        """After fetching the add, the first column's and sees a 0 and a 1, so nothing carries."""
        cockpit = Cockpit()
        cockpit.run(RUN_TO_ADD)
        cockpit.step("cycle")
        gates = _json(cockpit.view(ALU_GATE))["gates"]
        assert sorted((g["value_a"], g["value_b"]) for g in gates) == [(0, 1), (1, 1)]
        assert gates[-1]["value_out"] == 0

    def test_an_unknown_part_is_a_friendly_404(self) -> None:
        """Asking for a scope that does not exist says so, rather than crashing."""
        response = Cockpit().view("cpu.nope")
        assert response.status == NOT_FOUND
        assert "No part called cpu.nope" in response.text

    def test_the_front_page_has_the_machine_and_its_buttons(self) -> None:
        """GET / serves HTML with the step buttons, rewind, run and the load box."""
        response = _run(Cockpit().client.get("/"))
        assert response.status == OK
        assert "text/html" in (response.headers.get("Content-Type") or "")
        for words in ("Cockpit", "1 gate", "100 gates", "1 cycle", "1 instruction", "Rewind"):
            assert words in response.text
        assert "<script src" not in response.text

    def test_the_front_page_has_a_pebble_pane_that_never_injects_html(self) -> None:
        """The page loads Pebble and draws it with textContent, never innerHTML."""
        text = _run(Cockpit().client.get("/")).text
        for words in ("Pebble", "/api/pebble", "Load Pebble", TOUR_COUNTDOWN):
            assert words in text
        assert "innerHTML" not in text


def test_the_cockpit_opens_on_this_computer_only() -> None:
    """open_cockpit listens on 127.0.0.1, and the banner names the real address."""

    async def body() -> tuple[str, int]:
        server = await open_cockpit(0, address_bits=SMALL, start_example=None)
        try:
            return banner(server), server.port
        finally:
            await server.close()

    text, port = _run(body())
    assert HOST == "127.0.0.1"
    assert port > 0
    assert f"http://127.0.0.1:{port}" in text
    assert "Ctrl+C" in text


def test_main_closes_quietly_on_ctrl_c(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pressing Ctrl+C while serving prints a goodbye instead of a traceback."""

    def interrupted(job: Coroutine[Any, Any, None]) -> None:
        job.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(entry, "run", interrupted)
    entry.main()
    assert "closed" in capsys.readouterr().out


def test_serve_prints_the_banner_and_shuts_the_server_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Serve opens the Cockpit, prints where it is, and closes it when serving ends."""

    async def finish(_self: AsyncServer) -> None:
        """Stand in for serving forever by returning at once."""

    monkeypatch.setattr(AsyncServer, "serve_forever", finish)
    monkeypatch.setattr(entry, "PORT", 0)
    monkeypatch.setattr(entry, "ADDRESS_BITS", SMALL)
    monkeypatch.setattr(entry, "START_EXAMPLE", None)
    _run(entry.serve())
    out = capsys.readouterr().out
    assert "Building the computer" in out
    assert "The Cockpit is open at http://127.0.0.1:" in out


FULL_SIZE_TOUR_GATES = [610636, 610637]


@pytest.mark.slow
def test_the_full_size_tour_finds_the_gates_the_cockpit_page_names() -> None:
    """On the real 4K Cockpit, the tour's two gates are the numbers the docs give."""

    async def body() -> list[int]:
        client = TestClient(create_cockpit())
        await client.post("/api/run", json={"instructions": RUN_TO_ADD})
        await client.post("/api/step", json={"size": "cycle"})
        view = _json(await client.get("/api/view", query={"path": ALU_GATE}))
        return [gate["id"] for gate in view["gates"]]

    assert _run(body()) == FULL_SIZE_TOUR_GATES


DEMO_GATE_STEPS = {SMALL: (6736, 15213), RAM_ADDRESS_BITS: (6988, 43045)}


def _gate_steps_per_instruction(address_bits: int) -> list[int]:
    """Count the gate steps each instruction of the demo program takes, to the halt."""
    computer = Computer(assemble(DEMO_PROGRAM, words=1 << address_bits), address_bits)
    computer.pause()
    counts: list[int] = []
    taken = 0
    while True:
        taken += 1
        micro = computer.step(StepSize.GATE)
        assert micro is not None
        if micro.kind == "end":
            if computer.state().halted and taken == 1:
                return counts
            counts.append(taken)
            taken = 0


@pytest.mark.slow
@pytest.mark.parametrize("address_bits", sorted(DEMO_GATE_STEPS))
def test_the_cockpit_page_gives_the_real_gate_steps_per_instruction(address_bits: int) -> None:
    """The quickest and slowest demo instructions take the gate steps the docs give."""
    counts = _gate_steps_per_instruction(address_bits)
    assert (min(counts), max(counts)) == DEMO_GATE_STEPS[address_bits]


class TestSessionSeams:
    """The app's start example and busy answer, reached without adding public routes."""

    def test_an_unknown_start_example_is_refused(self) -> None:
        """A start_example that is not one of the examples raises ValueError."""
        with pytest.raises(ValueError, match="anything"):
            create_cockpit(SMALL, start_example="anything")

    def test_a_busy_session_answers_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A CockpitBusy from the session comes back as 409 with the usual body."""
        made: list[Session] = []

        class Recording(Session):
            """A Cockpit that tells the test about itself."""

            def __init__(self, address_bits: int) -> None:
                """Build as usual and record this session."""
                super().__init__(address_bits)
                made.append(self)

        monkeypatch.setattr("pycpu.cockpit.app.Cockpit", Recording)
        client = TestClient(create_cockpit(SMALL))
        made[0].playing = True
        response = _run(client.post("/api/rewind", json={}))  # pyright: ignore[reportArgumentType]
        assert response.status == CONFLICT
        assert _json(response) == {"error": "Conflict", "message": BUSY}


# --- Changed marks, the stack, the listing and zoom targets (Task 3) ---

FIRST_REGISTER = 1
NO_CHANGE: dict[str, object] = {
    "registers": [],
    "pc": False,
    "sp": False,
    "flags": [],
    "memory": [],
}
PUSH_PROGRAM = "li r1, 7\npush r1\npush r1\nhalt\n"
STACK_LIMIT = 16
BIG_BITS = 12
SCAN_BUDGET = 0.05  # seconds the full-size memory scan may take
SCAN_REPEATS = 20
DEMO_LOOP_ADDRESS = 3  # set takes two words, then li, then the label `loop`
SET_ROWS = (0, 1)
HALT_ONE = "halt 1\n"
SOME_GATE_STEPS = 40
ONE_OF_EACH = {
    "add r1, r2, r3": "cpu.alu",
    "cmp r1, r2": "cpu.alu",
    "addi r1, 1": "cpu.alu",
    "li r1, 5": "cpu.write_back",
    "lhi r1, 5": "cpu.write_back",
    "load r1, [r2]": "cpu.address_mux",
    "store r1, [r2]": "cpu.address_mux",
    "jmp 0": "cpu.next_pc",
    "br eq, 0": "cpu.next_pc",
    "call 0": "cpu.next_pc",
    "ret": "cpu.next_pc",
    "push r1": "cpu.next_sp",
    "pop r1": "cpu.next_sp",
    "getsp r1": "cpu.next_sp",
    "setsp r1": "cpu.next_sp",
    "halt 0": "cpu.halt",
}


def _without_changed(picture: dict[str, Any]) -> dict[str, Any]:
    """Return a picture minus its `changed` marks and `happened` sentence.

    Both describe the move just made, not the machine, so two equal machines reached
    by different moves differ only there.
    """
    return {key: value for key, value in picture.items() if key not in {"changed", "happened"}}


def _paused(source: str, bits: int = SMALL) -> Session:
    """Return a small session with the assembly `source` loaded."""
    session = Session(bits)
    session.load_assembly(source)
    return session


class TestChangedMarks:
    """The picture marks what the last move changed, by comparing before with now."""

    def test_nothing_is_marked_at_power_on(self) -> None:
        """Before any move, nothing differs."""
        assert machine_picture(Session(SMALL))["changed"] == NO_CHANGE

    def test_li_marks_its_register_and_pc(self) -> None:
        """After `li r1, 5` register 1 and the pc are marked."""
        session = _paused("li r1, 5\nhalt\n")
        session.step(StepSize.INSTRUCTION)
        assert machine_picture(session)["changed"] == {
            "registers": [1],
            "pc": True,
            "sp": False,
            "flags": [],
            "memory": [],
        }

    def test_a_push_marks_the_stack_pointer_and_the_pushed_address(self) -> None:
        """A push changes sp and the word it wrote at the new top of the stack."""
        session = _paused(PUSH_PROGRAM)
        session.step(StepSize.INSTRUCTION)
        session.step(StepSize.INSTRUCTION)
        picture = machine_picture(session)
        changed = cast("dict[str, Any]", picture["changed"])
        assert changed["sp"] is True
        assert changed["memory"] == [picture["sp"]]

    def test_flags_are_named(self) -> None:
        """A compare that makes the zero lamp light names it."""
        session = _paused("cmp r1, r2\nhalt\n")
        session.step(StepSize.INSTRUCTION)
        changed = cast("dict[str, Any]", machine_picture(session)["changed"])
        assert changed["flags"] == ["zero", "carry"]  # 0 - 0 sets zero, and no borrow sets carry

    def test_a_rewind_compares_with_the_state_before_the_rewind(self) -> None:
        """Rewinding half way through an instruction marks the pc that moved back."""
        session = _paused("li r1, 5\nhalt\n")
        session.step(StepSize.INSTRUCTION)
        session.step(StepSize.CYCLE)
        moved_on = machine_picture(session)["pc"]
        session.rewind()
        picture = machine_picture(session)
        assert moved_on != picture["pc"]
        assert cast("dict[str, Any]", picture["changed"])["pc"] is True

    def test_a_rewind_that_changes_nothing_marks_nothing(self) -> None:
        """Rewinding at an instruction boundary leaves the machine as it was."""
        session = _paused("li r1, 5\nhalt\n")
        session.rewind()
        assert machine_picture(session)["changed"] == NO_CHANGE

    def test_loading_marks_nothing_changed_and_clears_the_notes(self) -> None:
        """A load part-way through an instruction forgets the gate step and note, and marks nothing."""
        session = _paused("li r1, 5\nhalt\n")
        session.step(StepSize.INSTRUCTION)
        session.step(StepSize.GATE, SOME_GATE_STEPS)
        session.note = "something about the old program"
        session.load_assembly("li r2, 9\nhalt\n")
        picture = machine_picture(session)
        assert picture["last_gate"] is None
        assert picture["note"] is None
        changed = cast("dict[str, Any]", picture["changed"])
        assert changed["registers"] == []  # a load marks nothing changed
        listing_rows = cast("list[dict[str, Any]]", listing(session)["rows"])
        assert [row["text"] for row in listing_rows] == ["li r2, 9", "halt"]

    def test_loading_after_a_fault_leaves_nothing_of_the_old_program(self) -> None:
        """After a Pebble fault, loading assembly clears the Pebble pane, notes and listing."""
        session = Session(PEBBLE_BITS)
        session.load_pebble(DIVIDE_BY_ZERO)
        session.run(1000)
        assert machine_picture(session)["fault"] == "DIVIDE_BY_ZERO"
        session.load_assembly("li r1, 1\nhalt\n")
        picture = machine_picture(session)
        assert picture["pebble"] is None
        assert picture["fault"] is None
        assert picture["last_gate"] is None
        assert listing(session)["pebble"] is None
        assert [row["text"] for row in cast("list[dict[str, Any]]", listing(session)["rows"])] == [
            "li r1, 1",
            "halt",
        ]

    def test_loading_pebble_after_assembly_gives_the_new_listing(self) -> None:
        """Loading Pebble replaces the demo's listing, labels and all."""
        session = Session(PEBBLE_BITS)
        session.load_pebble(COUNTDOWN)
        rows = cast("list[dict[str, Any]]", listing(session)["rows"])
        assert len(rows) == len(session.program.words)
        assert all(row["text"] != "call show         ; print the digit for r2" for row in rows)

    @pytest.mark.slow
    def test_the_memory_scan_is_quick_at_full_size(self) -> None:
        """Comparing two full-size (4,096 word) states takes under 0.05 seconds."""
        # pycpu.cockpit.picture._changed is private: reach it through the module.
        scan = picture_module._changed
        before = FastMachine(1 << BIG_BITS).state()
        machine = FastMachine(1 << BIG_BITS)
        machine.load_program(assemble("li r1, 1\nhalt\n", words=1 << BIG_BITS).words)
        now = machine.state()
        start = time.perf_counter()
        for _ in range(SCAN_REPEATS):
            scan(before, now)
        assert (time.perf_counter() - start) / SCAN_REPEATS < SCAN_BUDGET


class TestStack:
    """The stack window shows words from sp upwards, top first."""

    def test_it_is_empty_at_power_on(self) -> None:
        """With sp at the end of memory there is nothing on the stack."""
        assert machine_picture(Session(SMALL))["stack"] == []

    def test_two_pushes_show_two_cells_top_first(self) -> None:
        """Two pushes give two cells, the top (at sp) first."""
        session = _paused(PUSH_PROGRAM)
        for _ in range(3):
            session.step(StepSize.INSTRUCTION)
        picture = machine_picture(session)
        stack = cast("list[dict[str, Any]]", picture["stack"])
        assert [cell["address"] for cell in stack] == [WORDS - 2, WORDS - 1]
        assert stack[0]["address"] == picture["sp"]
        assert [cell["word"] for cell in stack] == [SEVEN, SEVEN]
        assert stack[0]["part"] == f"ram.word{WORDS - 2}"

    def test_it_is_never_longer_than_sixteen_cells(self) -> None:
        """A deep stack shows only its top 16 words."""
        session = _paused("li r1, 1\nloop:\npush r1\njmp loop\n", bits=SMALL)
        session.run(40)
        assert len(cast("list[Any]", machine_picture(session)["stack"])) == STACK_LIMIT


class TestZoomTargets:
    """Every value links to a real part of the circuit."""

    def test_each_opcode_follows_the_table(self) -> None:
        """One word of each opcode maps to its part in the contract's table."""
        for source, part in ONE_OF_EACH.items():
            word = assemble(f"{source}\n", words=WORDS).words[0]
            assert part_for_instruction(word) == part, source

    def test_every_path_in_the_picture_exists_in_the_circuit(self) -> None:
        """Every `parts` path, every cell `part` and every table entry passes `has_scope`."""
        circuit = GateMachine(SMALL).simulator.circuit
        picture = machine_picture(Session(SMALL))
        parts = cast("dict[str, Any]", picture["parts"])
        paths = [
            *parts["registers"],
            parts["pc"],
            parts["sp"],
            parts["flags"],
            parts["instruction"],
        ]
        cells = [*cast("list[Any]", picture["memory"]), *cast("list[Any]", picture["stack"])]
        paths.extend(cell["part"] for cell in cells)
        paths.extend(ONE_OF_EACH.values())
        assert all(circuit.has_scope(path) for path in paths)
        assert len(parts["registers"]) == REGISTER_COUNT

    def test_every_memory_cell_part_exists(self) -> None:
        """Every word of a small RAM has its own scope, ram.word0 to the last."""
        circuit = GateMachine(SMALL).simulator.circuit
        assert all(circuit.has_scope(f"ram.word{a}") for a in range(WORDS))

    def test_the_picture_names_the_instruction_part(self) -> None:
        """For the demo's first word (li) the zoom target is the write-back."""
        parts = cast("dict[str, Any]", machine_picture(Session(SMALL))["parts"])
        assert parts["instruction"] == "cpu.write_back"

    def test_a_fetch_fault_zooms_to_the_whole_cpu(self) -> None:
        """When the instruction is outside memory there is no word, so the target is `cpu`."""
        session = Session(SMALL)
        session.computer.resume()
        session.computer.fast.load_state(replace(session.computer.fast.state(), pc=OUTSIDE))
        session.computer.pause()
        parts = cast("dict[str, Any]", machine_picture(session)["parts"])
        assert parts["instruction"] == "cpu"


class TestLastGate:
    """A gate step says which gate thought, and which part of the circuit it belongs to."""

    def test_a_gate_step_names_the_gate_and_its_part(self) -> None:
        """`last_gate.path` is the circuit's own scope for that gate."""
        session = Session(SMALL)
        circuit = session.computer.gate.simulator.circuit
        for _ in range(SOME_GATE_STEPS):
            session.step(StepSize.GATE)
            micro = session.last_gate
            assert micro is not None
            picture_gate = cast("dict[str, Any] | None", machine_picture(session)["last_gate"])
            if micro.kind == "gate":
                assert picture_gate is not None
                assert picture_gate["id"] == micro.gate
                assert picture_gate["path"] == circuit.scope_of(micro.gate)
                assert picture_gate["value"] == micro.value
            else:
                assert picture_gate is None

    def test_an_instruction_step_leaves_it_null(self) -> None:
        """After a gate step, an instruction step clears the last gate."""
        session = Session(SMALL)
        session.step(StepSize.GATE)
        session.step(StepSize.INSTRUCTION)
        assert machine_picture(session)["last_gate"] is None

    def test_the_route_carries_it(self) -> None:
        """GET /api/machine after a gate step includes `last_gate` with a real path."""
        cockpit = Cockpit()
        circuit = GateMachine(SMALL).simulator.circuit
        picture = cockpit.step("gate")
        for _ in range(SOME_GATE_STEPS):
            if picture["last_gate"] is not None:
                break
            picture = cockpit.step("gate")
        last = picture["last_gate"]
        assert last is not None
        assert last["path"] == circuit.scope_of(last["id"])
        assert picture["note"] is None


class TestPlayingPicture:
    """While the fast engine is live the picture reads it and shows no gate detail."""

    def test_it_reads_the_fast_engine(self) -> None:
        """Playing: phase is fetch, at a boundary, instruction is the word at pc."""
        session = Session(SMALL)
        session.computer.resume()
        session.computer.run(1)
        session.playing = True
        picture = machine_picture(session)
        assert picture["running"] is True
        assert picture["phase"] == "fetch"
        assert picture["at_boundary"] is True
        assert picture["last_gate"] is None
        assert cast("dict[str, Any]", picture["instruction"])["address"] == picture["pc"]
        assert picture["registers"] == list(session.computer.fast.state().registers)

    def test_a_paused_picture_is_not_running(self) -> None:
        """`running` follows `playing`."""
        assert machine_picture(Session(SMALL))["running"] is False


class TestListing:
    """GET /api/listing describes the whole loaded program."""

    def test_the_demo_has_a_row_for_each_word(self) -> None:
        """One row per word, the label at its address, `set` giving two rows."""
        cockpit = Cockpit()
        body = _json(_run(cockpit.client.get("/api/listing")))
        words = assemble(DEMO_PROGRAM, words=WORDS).words
        rows = body["rows"]
        assert len(rows) == len(words)
        assert [row["word"] for row in rows] == list(words)
        assert body["pebble"] is None
        assert rows[DEMO_LOOP_ADDRESS]["labels"] == ["loop"]
        assert [rows[i]["first"] for i in SET_ROWS] == [True, False]
        assert rows[0]["text"].startswith("set r1, 0xFFFF")
        assert rows[SET_ROWS[1]]["text"] == rows[0]["text"]
        assert all(row["pebble_line"] is None for row in rows)

    def test_a_pebble_program_lists_its_lines(self) -> None:
        """Every row's pebble_line is the translator's `line_at`, and `pebble` is the source."""
        cockpit = Cockpit(PEBBLE_BITS)
        assert cockpit.pebble(COUNTDOWN).status == OK
        body = _json(_run(cockpit.client.get("/api/listing")))
        translated = translate(COUNTDOWN)
        assert body["pebble"] == COUNTDOWN.splitlines()
        assert len(body["rows"]) == len(translated.program.words)
        for row in body["rows"]:
            assert row["pebble_line"] == translated.line_at(row["address"])

    def test_every_load_gives_the_picture_and_the_listing_a_new_program_number(self) -> None:
        """`program` counts loads, the same in both answers, even for the same text twice."""
        cockpit = Cockpit(PEBBLE_BITS)

        def numbers() -> tuple[object, object]:
            """Read `program` from the picture and from the listing."""
            machine = _json(_run(cockpit.client.get("/api/machine")))
            listed = _json(_run(cockpit.client.get("/api/listing")))
            return machine["program"], listed["program"]

        assert numbers() == (0, 0)  # the demo it starts with
        assert cockpit.pebble(COUNTDOWN).status == OK
        assert numbers() == (1, 1)
        assert cockpit.pebble(COUNTDOWN).status == OK  # the same text, loaded again
        assert numbers() == (2, 2)
        assert cockpit.load(DEMO_PROGRAM).status == OK
        assert numbers() == (LOADS_AFTER_THREE, LOADS_AFTER_THREE)
        session = Session(PEBBLE_BITS)
        session.step(StepSize.INSTRUCTION)
        session.run(1)
        assert machine_picture(session)["program"] == 0  # moves are not loads

    def test_a_refused_load_keeps_the_program_number(self) -> None:
        """A program the assembler refuses is not loaded, so the number stays put."""
        cockpit = Cockpit(PEBBLE_BITS)
        assert cockpit.load("nonsense r9\n").status == BAD_REQUEST
        assert _json(_run(cockpit.client.get("/api/machine")))["program"] == 0


NEGATIVE = "let n = 0 - 3\nprint(n)\n"
NEGATIVE_VALUE = -3
NEGATIVE_WORD = 0x10000 - 3
NEGATIVE_PRINT_LINE = 2
ADD_FUNCTION = "fn add(a, b) {\n    let c = a + b\n    return c\n}\nprint(add(2, 3))\n"
ADD_BODY_LINE = 2
ADD_A, ADD_B = 2, 3
ADD_A_OFFSET, ADD_B_OFFSET = 3, 2
RANGE_LOOP = "for i in range(3) {\n    print(i)\n}\n"
RANGE_PRINT_LINE = 2
RANGE_LIMIT = 3
LOADS_AFTER_THREE = 3
STORE_TO_N = "let n = 2\nn = n - 1\n"
STORE_LINE = 2
STORE_OLD, STORE_BETWEEN, STORE_NEW = 2, 3, 1


def _pebble_session(source: str) -> Session:
    """Build a 256-word session with `source` loaded and paused at its start."""
    session = Session(PEBBLE_BITS)
    session.load_pebble(source)
    return session


def _step_to_line(session: Session, line: int) -> dict[str, Any]:
    """Step one instruction at a time until the current instruction belongs to `line`."""
    picture = machine_picture(session)
    while cast("dict[str, Any]", picture["pebble"])["line"] != line:
        assert not picture["halted"]
        session.step(StepSize.INSTRUCTION)
        picture = machine_picture(session)
    return picture


class TestVariables:
    """The picture's `variables` shows each Pebble name at its real address."""

    def test_at_print_n_the_countdown_shows_n_about_to_be_printed(self) -> None:
        """At the start of `print(n)`, `n` sits just below r7 and holds the value printed next."""
        session = _pebble_session(COUNTDOWN)
        picture = _step_to_line(session, PRINT_LINE)
        variables = cast("dict[str, Any]", picture["variables"])
        top = PEBBLE_WORDS - 1
        assert variables["function"] is None
        assert variables["frame_pointer"] == top
        assert variables["names"] == [
            {
                "name": "n",
                "kind": "variable",
                "hidden": False,
                "address": top - 1,
                "word": 2,
                "value": 2,
                "part": f"ram.word{top - 1}",
            }
        ]
        session.run(MAX_RUN)
        assert str(machine_picture(session)["output"]).startswith("2\n")

    def test_inside_the_print_routine_there_are_none(self) -> None:
        """A runtime routine has no frame of its own, so `variables` is null."""
        session = _pebble_session(COUNTDOWN)
        _step_to_line(session, PRINT_LINE)
        picture = machine_picture(session)
        while cast("dict[str, Any]", picture["pebble"])["line"] is not None:
            session.step(StepSize.INSTRUCTION)
            picture = machine_picture(session)
        assert session.translated is not None
        address = cast("dict[str, Any]", picture["instruction"])["address"]
        assert address >= session.translated.program.labels["__mul"]
        assert picture["variables"] is None

    def test_the_prologue_has_none(self) -> None:
        """At the very first instruction the frame is still being built."""
        assert machine_picture(_pebble_session(COUNTDOWN))["variables"] is None

    def test_assembly_has_none(self) -> None:
        """An assembly program has no names at all."""
        assert machine_picture(Session(SMALL))["variables"] is None

    def test_while_playing_there_are_none(self) -> None:
        """Playing reads the fast engine, and `variables` is null."""
        session = _pebble_session(COUNTDOWN)
        _step_to_line(session, PRINT_LINE)
        session.playing = True
        assert machine_picture(session)["variables"] is None

    def test_a_negative_value_is_signed_and_its_word_is_raw(self) -> None:
        """`n = 0 - 3` shows a value of -3, stored as the word 65533."""
        picture = _step_to_line(_pebble_session(NEGATIVE), NEGATIVE_PRINT_LINE)
        (name,) = cast("dict[str, Any]", picture["variables"])["names"]
        assert name["value"] == NEGATIVE_VALUE
        assert name["word"] == NEGATIVE_WORD

    def test_a_function_shows_its_parameters_and_variables(self) -> None:
        """Inside `add(2, 3)`, `a` and `b` sit above r7 and `c` below, each part a real word."""
        session = _pebble_session(ADD_FUNCTION)
        picture = _step_to_line(session, ADD_BODY_LINE)
        assert picture["variables"] is None  # line 2 starts with add's prologue
        while picture["variables"] is None:
            session.step(StepSize.INSTRUCTION)
            picture = machine_picture(session)
        variables = cast("dict[str, Any]", picture["variables"])
        pointer = variables["frame_pointer"]
        assert variables["function"] == "add"
        assert pointer == cast("list[int]", picture["registers"])[FRAME_POINTER]
        found = {n["name"]: (n["kind"], n["address"], n["value"]) for n in variables["names"]}
        assert found == {
            "a": ("parameter", pointer + ADD_A_OFFSET, ADD_A),
            "b": ("parameter", pointer + ADD_B_OFFSET, ADD_B),
            "c": ("variable", pointer - 1, 0),
        }
        circuit = GateMachine(PEBBLE_BITS).simulator.circuit
        assert all(circuit.has_scope(n["part"]) for n in variables["names"])

    def test_the_for_loops_end_value_is_hidden(self) -> None:
        """The loop's own `$for_limit_0` holds 3 and is hidden; `i` is shown (as the docs say)."""
        picture = _step_to_line(_pebble_session(RANGE_LOOP), RANGE_PRINT_LINE)
        names = cast("dict[str, Any]", picture["variables"])["names"]
        assert [(n["name"], n["hidden"], n["value"]) for n in names] == [
            ("$for_limit_0", True, RANGE_LIMIT),
            ("i", False, 0),
        ]

    def test_an_address_outside_memory_is_left_out(self) -> None:
        """With r7 at the last word, `a` and `b` above it fall outside memory and are skipped."""
        session = _pebble_session(ADD_FUNCTION)
        translated = session.translated
        assert translated is not None
        body = next(
            a for a, f in enumerate(translated.frames) if f is not None and f.function == "add"
        )
        start = session.computer.instruction_start
        registers = list(start.registers)
        registers[FRAME_POINTER] = PEBBLE_WORDS - 1
        state = replace(start, pc=body, registers=tuple(registers))
        variables = variables_picture(translated, state)
        assert variables is not None
        assert [n["name"] for n in cast("list[dict[str, Any]]", variables["names"])] == ["c"]

    def test_a_pc_past_the_program_has_none(self) -> None:
        """A `pc` beyond the program's words has no frame."""
        session = _pebble_session(COUNTDOWN)
        start = replace(session.computer.instruction_start, pc=PEBBLE_WORDS - 1)
        assert variables_picture(session.translated, start) is None

    def test_part_way_through_a_store_the_variable_agrees_with_memory(self) -> None:
        """Gate-stepping the store to `n` updates `n`'s value as soon as its word changes."""
        session = _pebble_session(STORE_TO_N)
        picture = _step_to_line(session, STORE_LINE)
        while decode(cast("dict[str, Any]", picture["instruction"])["word"]).opcode != Opcode.STORE:
            session.step(StepSize.INSTRUCTION)
            picture = machine_picture(session)
        (n,) = cast("dict[str, Any]", picture["variables"])["names"]
        address: int = n["address"]
        assert n["word"] == STORE_OLD
        # The word's bits flip one gate at a time, so it passes through an in-between
        # value (3: bit 0 turns on before bit 1 turns off) before it settles on 1.
        # The variable must agree with memory both times.
        for expected in (STORE_BETWEEN, STORE_NEW):
            while session.computer.state().memory[address] in {STORE_OLD, STORE_BETWEEN} - {
                expected
            }:
                session.step(StepSize.GATE)
            picture = machine_picture(session)
            (n,) = cast("dict[str, Any]", picture["variables"])["names"]
            word = session.computer.state().memory[address]
            assert word == expected
            assert not picture["at_boundary"]  # still part-way through the store
            assert (n["address"], n["word"], n["value"]) == (address, word, word)
            assert address in cast("dict[str, Any]", picture["changed"])["memory"]

    def test_loading_another_program_shows_its_names(self) -> None:
        """After a reload nothing of the old program's names leaks through."""
        session = _pebble_session(ADD_FUNCTION)
        _step_to_line(session, ADD_BODY_LINE)
        session.load_assembly("halt\n")
        assert machine_picture(session)["variables"] is None
        session.load_pebble(NEGATIVE)
        picture = _step_to_line(session, NEGATIVE_PRINT_LINE)
        names = cast("dict[str, Any]", picture["variables"])["names"]
        assert [n["name"] for n in names] == ["n"]


EXAMPLE_ORDER = ["tour", "countdown", "times-table", "factorial", "greeting", "divide-by-zero"]
COUNTDOWN_TITLE = "Count down to lift off"
COUNTDOWN_FIRST_LINE = 2  # line 1 is the title comment
TOUR_BITS = 9  # 512 words: the tour needs 456
PAGE_IDS = (
    "walks",
    "walk-say",
    "walk-next",
    "walk-back",
    "try-task",
    "back-to-walk",
    "program",
    "glass",
    "trail",
    "step",
    "happened",
    "expert",
    "play",
    "pause",
    "examples",
    "source",
)
PLAYING_MESSAGE = "Pause to look inside the gates"
DOCS = Path(__file__).parent.parent / "docs" / "concepts"


def _page() -> str:
    """Fetch the Cockpit page's HTML."""
    return _run(Cockpit().client.get("/")).text


class TestExamples:
    """GET /api/examples and start_example: the programs the page offers to load."""

    def test_they_come_in_a_fixed_order_with_the_tour_first(self) -> None:
        """The names are in the page's order, each with its title and whole source."""
        examples = cast("list[dict[str, str]]", _run(Cockpit().client.get("/api/examples")).json())
        assert [e["name"] for e in examples] == EXAMPLE_ORDER
        countdown = examples[EXAMPLE_ORDER.index("countdown")]
        assert countdown["title"] == COUNTDOWN_TITLE
        assert countdown["source"].startswith(f"# {COUNTDOWN_TITLE}\n")

    def test_a_cockpit_can_start_with_an_example_paused_on_its_first_line(self) -> None:
        """create_cockpit(8, start_example="countdown") opens on its first line, nothing changed."""
        client = TestClient(create_cockpit(PEBBLE_BITS, start_example="countdown"))
        machine = _json(_run(client.get("/api/machine")))
        assert machine["pebble"]["line"] == COUNTDOWN_FIRST_LINE
        assert machine["pebble"]["source"][0] == f"# {COUNTDOWN_TITLE}"
        assert machine["pc"] == 0
        assert machine["paused"]
        assert machine["at_boundary"]
        assert machine["changed"] == {
            "registers": [],
            "pc": False,
            "sp": False,
            "flags": [],
            "memory": [],
        }

    def test_main_opens_the_full_size_cockpit_on_the_tour(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """open_cockpit asks for the tour (checked here on a smaller machine that fits it)."""
        asked: list[str | None] = []
        real = entry.create_cockpit

        def recording(address_bits: int, start_example: str | None = None) -> App:
            """Note which example was asked for, and build a Cockpit just big enough for it."""
            assert address_bits == RAM_ADDRESS_BITS
            asked.append(start_example)
            return real(TOUR_BITS, start_example)

        monkeypatch.setattr(entry, "create_cockpit", recording)

        async def body() -> None:
            server = await open_cockpit(0)
            await server.close()

        _run(body())
        assert asked == ["tour"]


PANES = ("program", "glass", "walks", "expert")
DEFINED_AND_CALLED_ONCE = 2  # drawChanged: its definition and its one call
GLASS_VIEWS = 2  # the part view and the gate view each number their requests
TRAIL_SIGN = "\u203a"  # the small arrow between the trail's crumbs
EXPERT_SIZES = [
    ("gate", "1"),
    ("gate", "100"),
    ("cycle", None),
    ("instruction", None),
    ("line", None),
    ("line_into", None),
]
WALK_NOT_FOUND = "Walk not found."
CHEER = "You did it! Pick another walk, or keep exploring."
EXPLORE = "Explore on my own"
WRITE_YOUR_OWN = "Write your own..."
STEP_INTO = "Step into ▸"
LAPTOP = "1280 by 720 dots"
REFERENCE = Path(__file__).parent.parent / "docs" / "reference" / "instruction-set.md"


def _script() -> str:
    """Return the page's own script, between its <script> tags."""
    match = re.search(r"<script>(.*?)</script>", _page(), flags=re.DOTALL)
    assert match is not None
    return match.group(1)


def _style() -> str:
    """Return the page's style sheet, between its <style> tags."""
    match = re.search(r"<style>(.*?)</style>", _page(), flags=re.DOTALL)
    assert match is not None
    return match.group(1)


def _media_block(style: str, query: str) -> str:
    """Return the body of the `@media` block with `query`, matching its braces."""
    start = style.index(f"@media {query}")
    opening = style.index("{", start)
    depth = 0
    for at in range(opening, len(style)):
        depth += {"{": 1, "}": -1}.get(style[at], 0)
        if depth == 0:
            return style[opening + 1 : at]
    msg = f"the @media {query} block never closes"
    raise AssertionError(msg)


def _top_rules(style: str) -> list[tuple[list[str], str]]:
    """List the style sheet's rules outside any @media block, as (selectors, body)."""
    flat = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)
    flat = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", flat)
    return [
        ([s.strip() for s in selectors.split(",")], body)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", flat)
    ]


def _js_json(name: str) -> Any:
    """Read the page's `const name = {...};`, written as JSON so a test can load it."""
    match = re.search(rf"const {name} = (\{{.*?\}});\n", _script(), flags=re.DOTALL)
    assert match is not None, name
    return json.loads(match.group(1))


def _flat(text: str) -> str:
    """Join a page's words onto one line, dropping the drawing's box edges."""
    return " ".join(text.replace("|", " ").split())


class TestThePage:
    """GET / serves layout C: every id its script uses, nothing from outside."""

    def test_it_has_every_id_the_script_uses(self) -> None:
        """Each pane and control the script looks up is on the page."""
        text = _page()
        for name in PAGE_IDS:
            assert f'id="{name}"' in text, name

    def test_it_loads_nothing_from_the_internet(self) -> None:
        """No src= or href= points at an http address, so the page works offline."""
        assert not re.search(r"""(src|href)\s*=\s*["']?\s*http""", _page(), flags=re.IGNORECASE)
        assert "innerHTML" not in _page()

    def test_it_has_a_dark_mode(self) -> None:
        """The colours change when the computer is in dark mode."""
        assert "@media (prefers-color-scheme: dark)" in _page()

    def test_it_listens_for_live_events(self) -> None:
        """The page opens an EventSource on /api/events and plays and pauses."""
        text = _page()
        for words in ("EventSource", "/api/events", "/api/play", "/api/pause", "/api/listing"):
            assert words in text

    def test_its_glass_waits_for_pause_while_playing(self) -> None:
        """The playing message sits inside the glass, and is the one the docs quote."""
        glass = re.search(r'<section[^>]*id="glass".*?</section>', _page(), flags=re.DOTALL)
        assert glass is not None
        assert PLAYING_MESSAGE in glass.group(0)
        for page in ("the-cockpit.md", "watching-it-run.md"):
            assert PLAYING_MESSAGE in (DOCS / page).read_text(encoding="utf-8")

    def test_it_marks_changes_in_words_and_explains_hidden_names(self) -> None:
        """Changed values get a "changed" tag; hidden names are dimmed with an explanation."""
        text = _page()
        assert 'const CHANGED = "changed";' in text
        assert 'node.append(el("span", CHANGED, "tag"));' in text
        assert "if (n.hidden) {" in text
        assert 'row.classList.add("dim");' in text
        assert "row.title = HIDDEN_TITLE;" in text
        assert "Pebble made this box for itself" in text

    def test_only_the_latest_pictures_changes_glow(self) -> None:
        """The page runs drawChanged once per picture; it clears old marks and reads `changed`."""
        script = _script()
        assert script.count("drawChanged(") == DEFINED_AND_CALLED_ONCE
        draw_text = script[script.index("function drawText(") :]
        draw_text = draw_text[: draw_text.index("\n}\n")]
        assert "drawChanged(m);" in draw_text
        body = script[script.index("function drawChanged(") :]
        body = body[: body.index("\n}\n")]
        assert 'querySelectorAll("." + CHANGED)' in body
        assert "m.changed" in body
        assert "latest" not in body

    def test_show_this_gate_is_offered_only_for_the_picture_that_named_it(self) -> None:
        """The button names last_gate, and a later picture without that gate drops the pick."""
        text = _page()
        assert '"show this gate (gate " + g.id' in text
        assert "g.id !== pickedGate.id || g.path !== pickedGate.path) pickedGate = null;" in text

    def test_a_gate_step_with_no_gate_shows_why(self) -> None:
        """The glass keeps the session's no-gate note for its gate spot."""
        text = _page()
        assert f'const NO_GATE = "{NO_GATE_ENDING}";' in text
        assert "m.note.endsWith(NO_GATE)" in text

    def test_no_sentence_is_shown_twice(self) -> None:
        """What just happened shows `happened`; `note` shows only when it says something else."""
        text = _page()
        assert (
            'document.getElementById("happened").textContent = m.happened || NOTHING_YET;' in text
        )
        assert 'const extra = m.note && m.note !== m.happened && !noGate ? m.note : "";' in text
        assert "&& m.note !== m.happened" in text.split('showGate.append(el("p", m.note')[0]
        assert text.count('showGate.append(el("p", m.note, "muted"));') == 1

    def test_the_expert_drawer_keeps_every_plan_4_step_size(self) -> None:
        """Gate, 100 gates, Cycle, Instruction, Line, Line into and Run sit in the drawer."""
        drawer = re.search(r'<aside[^>]*id="expert".*?</aside>', _page(), flags=re.DOTALL)
        assert drawer is not None
        found = re.findall(r'data-size="(\w+)"(?: data-count="(\d+)")?', drawer.group(0))
        assert [(size, count or None) for size, count in found] == EXPERT_SIZES
        for name in ("run", "count", "speed", "source", "load-pebble", "load"):
            assert f'id="{name}"' in drawer.group(0), name

    def test_the_line_buttons_have_the_names_the_docs_use(self) -> None:
        """The drawer's line buttons say Line and Line into, as every page that names them does."""
        labels = dict(re.findall(r'data-size="(line|line_into)"[^>]*>([^<]+)</button>', _page()))
        assert labels == {"line": "Line", "line_into": "Line into"}
        for page in ("the-cockpit.md", "stepping-a-pebble-line.md", "a-tour-of-the-cockpit.md"):
            text = (DOCS / page).read_text(encoding="utf-8")
            assert f"**{labels['line']}**" in text, page
        for page in ("the-cockpit.md", "stepping-a-pebble-line.md"):
            assert f"**{labels['line_into']}**" in (DOCS / page).read_text(encoding="utf-8")
        for page in DOCS.glob("*.md"):
            assert "**Next line**" not in page.read_text(encoding="utf-8"), page.name

    def test_the_step_into_button_follows_a_call_and_is_named_as_the_docs_say(self) -> None:
        """The try stage's second button sends line_into, and its label is the docs' one."""
        text = _page()
        assert f'id="step-into" hidden>{STEP_INTO}</button>' in text
        assert 'send("/api/step", { size: "line_into" })' in text
        assert 'w.step_kind === "into"' in text
        assert STEP_INTO in (DOCS / "the-cockpit.md").read_text(encoding="utf-8")

    def test_it_refetches_the_listing_whenever_the_program_number_changes(self) -> None:
        """The listing is stale when its `program` is not the picture's, and is re-checked."""
        text = _page()
        assert "return !listing || listing.program !== m.program;" in text
        assert "if (listingIsStale(m)) fetchListing(m); else drawProgram(m);" in text
        assert "if (latest.program !== askedFor) fetchListing(latest);" in text

    def test_only_the_newest_glass_answer_is_drawn(self) -> None:
        """Each glass request takes a number, and an answer that is not the newest is dropped."""
        script = _script()
        assert script.count("const mine = ++lensSeq;") == GLASS_VIEWS
        assert script.count("if (mine !== lensSeq) return;") >= GLASS_VIEWS

    def test_a_refused_button_catches_up_with_the_machine(self) -> None:
        """A refusal shows its message, then asks for the picture again."""
        script = _script()
        refused = script[script.index("if (!response.ok) {") :]
        assert refused.index("showError(message);") < refused.index("refresh();")

    def test_the_first_tour_quotes_the_demo_program_exactly(self) -> None:
        """The Cockpit page's first guided tour pastes DEMO_PROGRAM, word for word."""
        assert DEMO_PROGRAM in (DOCS / "the-cockpit.md").read_text(encoding="utf-8")


class TestOneScreen:
    """The page fits one screen: a grid as tall as the window, and panes that scroll."""

    def test_the_main_grid_is_as_tall_as_the_window(self) -> None:
        """`main` is `height: 100vh`, so the panes share the window and nothing hangs below."""
        rules = _top_rules(_style())
        assert any("main" in selectors and "height:100vh" in body for selectors, body in rules)

    def test_the_body_never_scrolls(self) -> None:
        """The page's body has `overflow: hidden`."""
        rules = _top_rules(_style())
        assert any("body" in selectors and "overflow:hidden" in body for selectors, body in rules)

    def test_every_pane_scrolls_inside_itself(self) -> None:
        """The program, the glass, the walks list and the Expert drawer each scroll on their own."""
        rules = _top_rules(_style())
        for pane in PANES:
            assert any(
                f"#{pane}" in selectors and "overflow:auto" in body for selectors, body in rules
            ), pane

    def test_on_a_phone_the_glass_sits_above_the_program(self) -> None:
        """Under 44rem the panes stack in one column, the glass first."""
        block = _media_block(_style(), "(max-width:44rem)")
        assert 'grid-template-areas:"glass" "program"' in block

    def test_the_docs_give_the_screen_the_page_is_built_for(self) -> None:
        """The Cockpit page names the laptop screen size the owner checks the page at."""
        assert LAPTOP in _flat((DOCS / "the-cockpit.md").read_text(encoding="utf-8"))


class TestTheStepButton:
    """The one Step button follows the glass's depth, and its words come from the picture."""

    def test_its_label_is_drawn_from_the_pictures_steps(self) -> None:
        """The label is `steps[look]`, and the script holds no label of its own."""
        script = _script()
        assert "step.textContent = m.steps[look];" in script
        assert "Step one" not in script

    def test_it_steps_at_the_glasss_depth(self) -> None:
        """Pressing it sends the glass's depth to /api/step."""
        assert 'send("/api/step", { depth: look })' in _script()


class TestWalksOnThePage:
    """The page opens on the walks, follows a walk's picture, and survives a stale link."""

    def test_it_opens_on_the_walks_unless_the_address_names_one(self) -> None:
        """The page reads `#walk=` and asks /api/walk; otherwise it shows the walks list."""
        script = _script()
        assert 'location.hash.startsWith("#walk=")' in script
        assert '"/api/walk"' in script
        assert '"/api/walks"' in script
        assert "else showWalks();" in script

    def test_a_walk_that_is_not_found_falls_back_to_the_list(self) -> None:
        """A failed /api/walk from a link shows the list with "Walk not found."."""
        script = _script()
        assert f'const WALK_NOT_FOUND = "{WALK_NOT_FOUND}";' in script
        assert "showWalks(WALK_NOT_FOUND);" in script
        assert WALK_NOT_FOUND in _cockpit_text()

    def test_the_server_answers_a_stale_link_with_a_404(self) -> None:
        """The answer the page falls back on: 404 with a plain sentence."""
        response = Cockpit().post("/api/walk", {"name": "nonsense", "step": 0})
        assert response.status == NOT_FOUND
        assert _json(response)["message"] == "There is no walk called nonsense."

    def test_next_and_back_move_one_step_and_back_to_the_walk_replays(self) -> None:
        """Next sends step + 1, Back step - 1, and Back to the walk the same step again."""
        script = _script()
        assert "openWalk(w.name, w.step + 1)" in script
        assert "openWalk(w.name, w.step - 1)" in script
        assert "openWalk(w.name, w.step)" in script
        assert '"/api/walk/leave"' in script

    def test_the_glass_follows_the_walks_look(self) -> None:
        """A new walk step sets the glass to its `look` and outlines its `show`."""
        script = _script()
        assert "look = w.look;" in script
        assert "outline(w.show" in script

    def test_the_page_words_the_docs_quote_are_the_pages_own(self) -> None:
        """The cheer, the explore button and the write-your-own choice match the docs."""
        text = _page()
        docs = _flat((DOCS / "the-cockpit.md").read_text(encoding="utf-8"))
        for words in (CHEER, EXPLORE, WRITE_YOUR_OWN, "Back to the walk", "Next ▸", "◂ Back"):
            assert words in text, words
            assert words in docs, words


def _tap_names() -> set[str]:
    """Collect every input and output name the CPU's parts have taps for."""
    gate = Session(SMALL).computer.gate
    return {name for taps in gate.taps.values() for name in taps}


class TestFriendlyLabels:
    """The glass shows plain words for wire names and instruction fields."""

    def test_every_tap_name_has_plain_words(self) -> None:
        """TAP_WORDS covers every name in GateMachine.taps, with no underscores left."""
        words = cast("dict[str, str]", _js_json("TAP_WORDS"))
        assert set(words) == _tap_names()
        for name, label in words.items():
            assert label, name
            assert "_" not in label, name

    def test_the_docs_quote_a_tap_label_as_the_page_writes_it(self) -> None:
        """The Cockpit page names sp_minus_1 by the page's own words for it."""
        label = cast("dict[str, str]", _js_json("TAP_WORDS"))["sp_minus_1"]
        assert f'"{label}" for `sp_minus_1`' in _flat(
            (DOCS / "the-cockpit.md").read_text(encoding="utf-8")
        )

    def test_every_part_has_the_name_the_step_button_uses(self) -> None:
        """PART_WORDS names each part exactly as PART_NAMES does for the Step button."""
        assert _js_json("PART_WORDS") == PART_NAMES

    def test_the_instruction_fields_match_the_instruction_set_page(self) -> None:
        """Each opcode's fields and each field's bits are the ones the reference page gives."""
        reference = REFERENCE.read_text(encoding="utf-8")
        bits = {
            name.strip("`"): [int(b) for b in span.split("-")]
            for name, span in re.findall(
                r"^\| (`\w+`)[^|]*\| (\d+-\d+) \|", reference, re.MULTILINE
            )
        }
        bits["cond"] = bits["rd"]  # the reference writes `rd` (or `cond`) on one row
        assert _js_json("FIELD_BITS") == bits
        fields: dict[str, list[str]] = {
            op: [] if listed == "none" else str(listed).split()
            for op, listed in re.findall(
                r"^\| (\d+) \| `\w+` \| ([\w ]+) \|", reference, re.MULTILINE
            )
        }
        assert _js_json("FIELDS") == fields
        assert sorted(int(op) for op in fields) == [int(op) for op in Opcode]


DRAWN_WALK = "many-instructions"
DRAWN_STEP = 2  # the drawing shows the walk just after its third step
WALK_BITS = 9  # 512 words: room for the countdown and its runtime routines
DRAWN_LINE = 5
DRAWN_ROWS = 3  # the drawing lists the first three of line 5's instructions
LINE_FIVE = (34, 43, 10)  # first address, last address, instructions
OPCODE_BITS = 4
RD_BITS = 3
REST_BITS = 9


def _cockpit_text() -> str:
    """Read the Cockpit concept page, its words joined onto one line."""
    return _flat((DOCS / "the-cockpit.md").read_text(encoding="utf-8"))


def _drawn_moment(address_bits: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Open the drawn walk at the drawn step; return its picture and the program's listing."""
    client = TestClient(create_cockpit(address_bits))
    body = {"name": DRAWN_WALK, "step": DRAWN_STEP}
    machine = _json(_run(client.post("/api/walk", json=body)))  # pyright: ignore[reportArgumentType]
    return machine, _json(_run(client.get("/api/listing")))


class TestTheDrawing:
    """Every figure in the Cockpit page's drawing of layout C, read from the real moment."""

    def test_the_walk_bar_step_button_and_trail(self) -> None:
        """The walk's title, place, sentence, the Step label and the trail are the drawn ones."""
        machine, _listing = _drawn_moment(WALK_BITS)
        walk = machine["walk"]
        text = _cockpit_text()
        assert f"{walk['title']} Step {walk['step'] + 1} of {walk['count']}" in text
        assert walk["say"] in text
        assert f"[{machine['steps'][walk['look']]}]" in text
        trail = f"Line {machine['pebble']['line']} {TRAIL_SIGN} {machine['instruction']['text']}"
        assert trail in text

    def test_the_program_pane_shows_line_five_and_its_instructions(self) -> None:
        """Line 5 is 10 instructions at 34 to 43; the first three are drawn, 35 marked next."""
        machine, listing = _drawn_moment(WALK_BITS)
        rows = [r for r in listing["rows"] if r["pebble_line"] == DRAWN_LINE]
        assert (rows[0]["address"], rows[-1]["address"], len(rows)) == LINE_FIVE
        text = _cockpit_text()
        assert "is 10 instructions, at addresses 34 to 43" in text
        for row in rows[:DRAWN_ROWS]:
            mark = "> " if row["address"] == machine["instruction"]["address"] else ""
            assert f"{mark}{row['address']} {' '.join(row['text'].split())}" in text
        assert machine["pebble"]["source"][DRAWN_LINE - 1].strip() == "n = n - 1"
        assert machine["output"] == "5\n"

    def test_only_r1_and_pc_glow(self) -> None:
        """The last move ran the line's first instruction, so only r1 (5) and pc (35) changed."""
        machine, listing = _drawn_moment(WALK_BITS)
        assert machine["changed"] == {
            "registers": [1],
            "pc": True,
            "sp": False,
            "flags": [],
            "memory": [],
        }
        before = listing["rows"][machine["pc"] - 1]["text"]
        assert before.startswith("load r1, [r7-1]")
        text = _cockpit_text()
        assert f"`r1` (now {machine['registers'][1]}) and `pc` (now {machine['pc']}) glow" in text
        assert f"[r1 {machine['registers'][1]} changed]" in text
        assert f"[pc {machine['pc']} changed]" in text

    def test_the_instruction_is_drawn_as_its_real_bits(self) -> None:
        """The word for push r1 is 1010 001 000000000: the job, rd, and nine bits it does not use."""
        machine, _listing = _drawn_moment(WALK_BITS)
        word = machine["instruction"]["word"]
        job = format(word >> (RD_BITS + REST_BITS), f"0{OPCODE_BITS}b")
        rd = format((word >> REST_BITS) & ((1 << RD_BITS) - 1), f"0{RD_BITS}b")
        rest = format(word & ((1 << REST_BITS) - 1), f"0{REST_BITS}b")
        raw = (DOCS / "the-cockpit.md").read_text(encoding="utf-8")
        for row in ((job, rd, rest), ("job", "rd", "not used"), ("push", "r1")):
            assert re.search(r"\|\s+" + r"\s+".join(row) + r"\s+\|", raw), row
        address = machine["instruction"]["address"]
        assert f"the instruction at address {address}, next to run" in _cockpit_text()

    @pytest.mark.slow
    def test_the_full_size_numbers(self) -> None:
        """On the real 4K Cockpit, the sentence, registers, variable and stack are as drawn."""
        machine, _listing = _drawn_moment(RAM_ADDRESS_BITS)
        text = _cockpit_text()
        assert f"What just happened: {machine['happened']}" in text
        r = machine["registers"]
        assert f"r0 {r[0]} [r1 {r[1]} changed] r2 {r[2]} r3 {r[3]} r4 {r[4]}" in text
        assert f"r5 {r[5]} r6 {r[6]} r7 {r[7]}" in text
        assert f"[pc {machine['pc']} changed] sp {machine['sp']}" in text
        f = machine["flags"]
        flags = f"zero {f['zero']} negative {f['negative']} carry {f['carry']}"
        assert f"{flags} overflow {f['overflow']}" in text
        (n,) = machine["variables"]["names"]
        stack = machine["stack"]
        assert f"{n['name']} {n['value']} at {n['address']} {stack[0]['address']}: " in text
        assert f"{stack[1]['address']}: {stack[1]['word']}" in text


class TestTheButtonTours:
    """The figures the Cockpit page's two button tours quote, read from a real Cockpit."""

    def test_the_first_tour_looks_at_the_alu_one_beat_into_the_add(self) -> None:
        """One ALU beat fetches the add; the ALU's inputs are 48 and 3 and its answer 51."""
        cockpit = Cockpit()
        cockpit.step("instruction")
        machine = cockpit.run(RUN_TO_ADD - 1)
        assert machine["steps"]["part"] == "Step one ALU beat ▸"
        machine = _json(cockpit.post("/api/step", {"depth": "part"}))
        text = _cockpit_text()
        assert f'What just happened says so: "{machine["happened"]}"' in text
        part = _json(_run(cockpit.client.get("/api/part", query={"path": "cpu.alu"})))
        a, b = (wire["value"] for wire in part["inputs"])
        result = part["outputs"][0]["value"]
        words = cast("dict[str, str]", _js_json("TAP_WORDS"))
        said = f"{words['a']} is {a}, {words['b']} is {b}, and the {words['result']} coming out"
        assert f"{said} is {result}." in text

    def test_the_first_tour_finishes_the_add_after_a_rewind(self) -> None:
        """Gates, a hundred gates, Rewind, then one instruction: r3 is 51, said in words."""
        cockpit = Cockpit()
        cockpit.run(RUN_TO_ADD)
        _json(cockpit.post("/api/step", {"depth": "part"}))
        _json(cockpit.post("/api/step", {"depth": "gate"}))
        cockpit.step("gate", HUNDRED)
        assert cockpit.post("/api/rewind", {}).status == OK
        machine = _json(cockpit.post("/api/step", {"depth": "instruction"}))
        assert machine["registers"][3] == ord("3")
        assert f'What just happened says "{machine["happened"]}"' in _cockpit_text()

    def test_the_second_tours_line_step_after_the_run(self) -> None:
        """After Run 180 the line step runs line 4's last instruction, the store into n."""
        cockpit = Cockpit(PEBBLE_BITS)
        machine = _json(cockpit.pebble(TOUR_COUNTDOWN))
        assert machine["instruction"] == {"address": 0, "word": 0xC200, "text": "getsp r1"}
        while machine["pebble"]["line"] is not None:
            machine = cockpit.step("instruction")
        machine = cockpit.run(TOUR_RUN)
        assert machine["instruction"]["text"] == "store r1, [r7-1]"
        machine = _json(cockpit.post("/api/step", {"depth": "line"}))
        text = _cockpit_text()
        assert f'What just happened says "{machine["happened"]}":' in text
        assert "the last instruction of line 4, `store r1, [r7-1]`" in text


CLOCK_NOTE = "That step moved the write clock wire, not a gate, so there is no gate to show."
MAIN_CLOCK_NOTE = "That step moved the clock wire, not a gate, so there is no gate to show."
TOUR_FIRST_WORDS = [(0xC200, True), (0x24B8, True), (0x3401, False)]
TOUR_FIRST_LINE = 18


class TestFreshTour:
    """The figures the Cockpit page's drawing and tour quote, read from a tour Cockpit."""

    def test_the_first_words_are_main_s_frame_on_line_18(self) -> None:
        """Words 0 to 2 are 0xC200, 0x24B8 and 0x3401, all on line 18; 1 and 2 share a `set`."""
        client = TestClient(create_cockpit(TOUR_BITS, start_example="tour"))
        rows = _json(_run(client.get("/api/listing")))["rows"][: len(TOUR_FIRST_WORDS)]
        assert [(row["word"], row["first"]) for row in rows] == TOUR_FIRST_WORDS
        assert {row["pebble_line"] for row in rows} == {TOUR_FIRST_LINE}
        assert rows[0]["text"].startswith("getsp r1")
        assert rows[1]["text"].startswith("set  r2, __end")
        assert f"the first line that runs is line {TOUR_FIRST_LINE}" in _cockpit_text()

    def test_the_first_gate_step_moves_a_clock_wire_and_says_so(self) -> None:
        """The very first 1 gate has no gate to show, and the note the docs quote says why."""
        client = TestClient(create_cockpit(TOUR_BITS, start_example="tour"))
        body: dict[str, object] = {"size": "gate"}
        machine = _json(_run(client.post("/api/step", json=body)))  # pyright: ignore[reportArgumentType]
        assert machine["last_gate"] is None
        assert machine["note"] == CLOCK_NOTE
        assert CLOCK_NOTE in (DOCS / "the-cockpit.md").read_text(encoding="utf-8")
        machine = _json(_run(client.post("/api/step", json=body)))  # pyright: ignore[reportArgumentType]
        assert machine["last_gate"] is not None
        assert machine["note"] is None

    def test_a_gate_step_ending_an_instruction_says_so(self) -> None:
        """A gate step whose last movement is an instruction's end names that instead."""
        counter = Session(SMALL)
        steps = 0
        while True:
            steps += 1
            micro = counter.computer.step(StepSize.GATE)
            assert micro is not None
            if micro.kind == "end":
                break
        session = Session(SMALL)
        session.step(StepSize.GATE, steps)
        assert session.last_gate is not None
        assert session.last_gate.kind == "end"
        assert session.note == END_NOTE

    def test_a_gate_step_ending_on_the_main_clock_calls_it_the_clock_wire(self) -> None:
        """The main clock, `clk`, is "the clock wire" in the note, never "the clk clock wire"."""
        counter = Session(SMALL)
        steps = 0
        while True:
            steps += 1
            micro = counter.computer.step(StepSize.GATE)
            assert micro is not None
            if micro.kind == "edge" and micro.wire == "clk":
                break
        session = Session(SMALL)
        session.step(StepSize.GATE, steps)
        assert session.note == MAIN_CLOCK_NOTE
        assert '`clk`, is just "the clock wire"' in (DOCS / "the-cockpit.md").read_text(
            encoding="utf-8"
        )

    def test_a_tour_too_big_for_the_memory_is_a_value_error(self) -> None:
        """Starting a 64-word Cockpit on the tour is refused as a ValueError, naming why."""
        with pytest.raises(ValueError, match="cannot start this Cockpit"):
            create_cockpit(SMALL, start_example="tour")


TOUR_GATE = 41226
TOUR_LINE_N = 5  # n = n - 1 in the countdown example
TOUR_N = 2
TOUR_GATE_STEPS = 2122
TOUR_ADDER = "cpu.alu.adder.bit0.full_adder"
XOR_GATES = 4
EXAMPLES = Path(__file__).parent.parent / "src" / "pycpu" / "cockpit" / "examples"


def _all_gates(circuit: Circuit, path: str) -> list[int]:
    """Collect every gate under `path`, in its own gates and every part nested inside."""
    gates = circuit.gates_in(path)
    for child in circuit.children(path):
        gates += _all_gates(circuit, f"{path}.{child}")
    return gates


def _wires_in_and_out(circuit: Circuit, path: str) -> tuple[set[int], set[int]]:
    """Return the wires a part takes in from outside, and the wires its own gates drive."""
    first, second, out = circuit.gate_wires
    gates = _all_gates(circuit, path)
    driven = {out[g] for g in gates}
    taken = {first[g] for g in gates} | {second[g] for g in gates}
    return taken - driven, driven - taken


class TestTheTourGate:
    """The XOR gate the tour page stops on, read straight from the real circuit."""

    def test_it_is_one_of_four_nands_fed_by_the_first_sum_and_the_carry_in(self) -> None:
        """Gate 41226 sits in the second half adder's 4-gate XOR, fed 0 (first sum) and 1 (carry)."""
        session = Session(PEBBLE_BITS)
        session.load_pebble((EXAMPLES / "countdown.pebble").read_text(encoding="utf-8"))
        picture = machine_picture(session)
        while not (
            cast("dict[str, Any]", picture["pebble"])["line"] == TOUR_LINE_N
            and cast("dict[str, Any]", picture["variables"])["names"][0]["value"] == TOUR_N
        ):
            session.step_line(into=False)
            picture = machine_picture(session)
        while not cast("dict[str, Any]", picture["instruction"])["text"].startswith("sub"):
            session.step(StepSize.INSTRUCTION)
            picture = machine_picture(session)
        steps = 0
        while not (cast("dict[str, Any] | None", picture["last_gate"]) or {"path": ""})[
            "path"
        ].startswith("cpu.alu.adder"):
            session.step(StepSize.GATE)
            steps += 1
            picture = machine_picture(session)
        gate = cast("dict[str, Any]", picture["last_gate"])
        assert (steps, gate["id"]) == (TOUR_GATE_STEPS, TOUR_GATE)

        simulator = session.computer.gate.simulator
        circuit = simulator.circuit
        xor = f"{TOUR_ADDER}.half_adder#1.xor"
        assert gate["path"] == xor
        assert len(circuit.gates_in(xor)) == XOR_GATES
        assert TOUR_GATE in circuit.gates_in(xor)
        first, second, _out = circuit.gate_wires
        inputs = {first[TOUR_GATE], second[TOUR_GATE]}
        assert inputs == _wires_in_and_out(circuit, xor)[0]  # the XOR's own two inputs
        (first_sum,) = _wires_in_and_out(circuit, f"{TOUR_ADDER}.half_adder.xor")[1]
        (carry_in,) = (
            _wires_in_and_out(circuit, TOUR_ADDER)[0]
            - _wires_in_and_out(circuit, f"{TOUR_ADDER}.half_adder")[0]
        )
        assert inputs == {first_sum, carry_in}
        assert (simulator.get(first_sum), simulator.get(carry_in)) == (0, 1)
        text = (DOCS / "a-tour-of-the-cockpit.md").read_text(encoding="utf-8")
        assert "one of the\nfour NANDs" in text
        assert f"{TOUR_GATE:,}" in text
