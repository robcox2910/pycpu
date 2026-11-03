"""Tests for the Bench: the local page for watching the running computer."""

from collections.abc import Coroutine
from typing import Any, cast

import pytest
from pynet.loop import run
from pyweb.aserver import AsyncServer
from pyweb.testing import TestClient, TestResponse

from pycpu import __main__ as entry
from pycpu.__main__ import HOST, banner, open_bench
from pycpu.assembler import assemble
from pycpu.bench.app import (
    DEMO_PROGRAM,
    MAX_GATE_STEPS,
    MAX_PEBBLE_CHARACTERS,
    MAX_RUN,
    create_bench,
)
from pycpu.computer import Computer, StepSize
from pycpu.fast import FastMachine
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.state import REGISTER_COUNT
from pycpu.translator import translate

OK = 200
BAD_REQUEST = 400
NOT_FOUND = 404
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


class Bench:
    """A small Bench (64 words of memory) with plain, waiting-free helpers for each route."""

    def __init__(self, address_bits: int = SMALL) -> None:
        """Build the Bench (64 words unless told otherwise) and a pretend browser for it."""
        self.client = TestClient(create_bench(address_bits=address_bits))

    def machine(self) -> dict[str, Any]:
        """Return the machine picture from GET /api/machine."""
        return _json(_run(self.client.get("/api/machine")))

    def post(self, path: str, body: object) -> TestResponse:
        """Send a JSON body to `path` and return the raw response."""
        return _run(self.client.post(path, json=body))  # pyright: ignore[reportArgumentType]

    def step(self, size: str, count: int | None = None) -> dict[str, Any]:
        """Step by `size` (and `count`, if given), insisting the Bench agrees."""
        body: dict[str, object] = {"size": size}
        if count is not None:
            body["count"] = count
        response = self.post("/api/step", body)
        assert response.status == OK, response.text
        return _json(response)

    def run(self, instructions: int) -> dict[str, Any]:
        """Run `instructions` instructions, insisting the Bench agrees."""
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

    def test_the_bench_opens_paused_before_the_first_instruction(self) -> None:
        """At the start every register is 0, sp is the RAM size and pc points at address 0."""
        machine = Bench().machine()
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
        instruction = Bench().machine()["instruction"]
        first = assemble(DEMO_PROGRAM, words=WORDS).words[0]
        assert instruction == {"address": 0, "word": first, "text": "li r1, 255"}

    def test_the_memory_window_is_sixteen_words_from_zero_at_the_start(self) -> None:
        """With pc at 0 the window cannot start 4 behind, so it starts at 0."""
        memory = Bench().machine()["memory"]
        words = assemble(DEMO_PROGRAM, words=WORDS).words
        assert [cell["address"] for cell in memory] == list(range(WINDOW))
        assert memory[1] == {"address": 1, "word": words[1], "text": "lhi r1, 255"}

    def test_the_memory_window_starts_four_words_behind_pc(self) -> None:
        """Paused before the add at address 8, the window shows addresses 4 to 19."""
        machine = Bench().run(RUN_TO_ADD)
        assert machine["pc"] == ADD_ADDRESS
        assert machine["memory"][0]["address"] == ADD_ADDRESS - BEHIND
        assert len(machine["memory"]) == WINDOW
        assert machine["instruction"]["text"] == "add r3, r3, r2"

    def test_the_memory_window_slides_back_to_end_at_the_last_word(self) -> None:
        """Near the end of memory the window still holds 16 words, the last 16."""
        bench = Bench()
        assert bench.load(f".word {JUMP_NEAR_END}").status == OK
        machine = bench.step("instruction")
        assert machine["pc"] == NEAR_END
        assert [cell["address"] for cell in machine["memory"]] == list(range(WORDS - WINDOW, WORDS))

    def test_a_pc_outside_memory_shows_no_word_and_a_fault(self) -> None:
        """Jumping past the end faults on the next fetch; the instruction has no word."""
        bench = Bench()
        assert bench.load(f".word {JUMP_OUTSIDE}").status == OK
        bench.step("instruction")
        machine = bench.step("instruction")
        assert machine["halted"] is True
        assert machine["halt_code"] == 1
        assert machine["instruction"] == {"address": OUTSIDE, "word": None, "text": ""}
        assert machine["fault"] == "BAD_ADDRESS"
        assert [cell["address"] for cell in machine["memory"]] == list(range(WORDS - WINDOW, WORDS))

    def test_a_normal_halt_names_no_fault(self) -> None:
        """A program that halts with 0, or with a code that is no `Fault`, has `fault` null."""
        bench = Bench()
        assert bench.machine()["fault"] is None
        assert bench.load("halt").status == OK
        machine = bench.step("instruction")
        assert (machine["halted"], machine["halt_code"], machine["fault"]) == (True, 0, None)
        assert bench.load("halt 7").status == OK
        machine = bench.step("instruction")
        assert (machine["halt_code"], machine["fault"]) == (SEVEN, None)

    def test_a_programs_own_halt_one_to_three_shares_the_fault_names(self) -> None:
        """`halt 2` is indistinguishable from a stack overflow, so it is named as one."""
        bench = Bench()
        assert bench.load("halt 2").status == OK
        assert bench.step("instruction")["fault"] == "STACK_OVERFLOW"


class TestStepping:
    """POST /api/step moves the gate engine by a gate, a beat or an instruction."""

    def test_one_instruction_moves_the_machine_as_the_fast_engine_predicts(self) -> None:
        """After each instruction, the registers, pc, sp and output match a fast run."""
        bench = Bench()
        for done in range(1, RUN_TO_ADD + 2):
            machine = bench.step("instruction")
            predicted = _fast_after(done).state()
            assert machine["registers"] == list(predicted.registers)
            assert machine["pc"] == predicted.pc
            assert machine["sp"] == predicted.sp
            assert machine["output"] == predicted.output_text

    def test_a_cycle_step_leaves_the_add_fetched_but_not_obeyed(self) -> None:
        """Half way through the add, pc has moved on but the instruction is still the add."""
        bench = Bench()
        bench.run(RUN_TO_ADD)
        machine = bench.step("cycle")
        assert machine["phase"] == "execute"
        assert machine["at_boundary"] is False
        assert machine["pc"] == ADD_ADDRESS + 1
        assert machine["instruction"]["address"] == ADD_ADDRESS
        assert machine["instruction"]["text"] == "add r3, r3, r2"

    def test_gate_steps_change_the_phase_and_the_wires_over_one_instruction(self) -> None:
        """Stepping 500 gates at a time through an instruction, both beats appear and wires move."""
        bench = Bench()
        bench.run(RUN_TO_ADD)
        phases: set[str] = set()
        pictures = [bench.wires("cpu.pc.bit0")]
        machine = bench.step("gate", GATE_BATCH)
        while machine["instruction"]["address"] == ADD_ADDRESS:
            phases.add(machine["phase"])
            pictures.append(bench.wires("cpu.pc.bit0"))
            machine = bench.step("gate", GATE_BATCH)
        assert phases == {"fetch", "execute"}
        assert len({tuple(picture) for picture in pictures}) > 1
        assert machine["registers"][3] == ord("3")

    def test_a_count_of_a_hundred_is_the_same_as_a_hundred_single_gates(self) -> None:
        """The 100 gates button is a shortcut, not a different kind of step."""
        one_by_one, at_once = Bench(), Bench()
        for _ in range(HUNDRED):
            one_by_one.step("gate")
        assert at_once.step("gate", HUNDRED) == one_by_one.machine()
        assert at_once.wires("cpu") == one_by_one.wires("cpu")

    def test_gate_steps_stop_when_the_machine_halts(self) -> None:
        """A huge count on a program that halts at once finishes quickly and halts."""
        bench = Bench()
        assert bench.load("halt 7").status == OK
        machine = bench.step("gate", MAX_GATE_STEPS)
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
        bench = Bench()
        assert [bench.post("/api/step", item).status for item in bad] == [BAD_REQUEST] * len(bad)
        assert bench.machine()["pc"] == 0

    def test_a_cycle_or_instruction_step_may_say_count_one(self) -> None:
        """A count of 1 is what those steps already mean, so it is allowed."""
        bench = Bench()
        assert bench.step("cycle", 1)["phase"] == "execute"
        assert bench.step("instruction", 1)["at_boundary"] is True


class TestBrokenBodies:
    """A body that is not JSON at all, or is empty, is refused rather than crashing."""

    @pytest.mark.parametrize("path", ["/api/step", "/api/run", "/api/program", "/api/pebble"])
    @pytest.mark.parametrize("body", [b"{nope", b""], ids=["broken", "empty"])
    def test_a_broken_or_empty_body_is_a_400(self, path: str, body: bytes) -> None:
        """Broken JSON and an empty body both get 400, and the machine does not move."""
        bench = Bench()
        response = _run(bench.client.post(path, body=body))
        assert response.status == BAD_REQUEST
        assert bench.machine()["pc"] == 0


class TestRewindAndRun:
    """POST /api/rewind goes back to the instruction's start; POST /api/run runs fast."""

    def test_rewind_goes_back_to_the_start_of_the_instruction(self) -> None:
        """After some gates and a beat, rewind shows exactly the starting picture again."""
        bench = Bench()
        start = bench.machine()
        bench.step("gate", HUNDRED)
        bench.step("cycle")
        response = bench.post("/api/rewind", {})
        assert response.status == OK
        assert _json(response) == start

    def test_running_to_the_end_prints_the_countdown(self) -> None:
        """The demo program counts 3, 2, 1 and halts normally."""
        machine = Bench().run(MAX_RUN)
        assert machine["output"] == "321"
        assert machine["halted"] is True
        assert machine["halt_code"] == 0
        assert machine["paused"] is True

    def test_run_finishes_a_half_done_instruction_first(self) -> None:
        """Run 1 from half way through the add finishes the add and runs one more."""
        bench = Bench()
        bench.run(RUN_TO_ADD)
        bench.step("cycle")
        machine = bench.run(1)
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
        bench = Bench()
        assert [bench.post("/api/run", item).status for item in bad] == [BAD_REQUEST] * len(bad)


class TestLoadingAProgram:
    """POST /api/program puts new assembly into the computer, or says which line is wrong."""

    def test_a_new_program_starts_paused_at_its_first_instruction(self) -> None:
        """Loading `li r0, 7` and running it leaves 7 in r0."""
        bench = Bench()
        bench.run(RUN_TO_ADD)
        response = bench.load("li r0, 7\nhalt")
        assert response.status == OK
        machine = _json(response)
        assert machine["pc"] == 0
        assert machine["paused"] is True
        assert machine["sp"] == WORDS
        assert machine["instruction"]["text"] == "li r0, 7"
        assert bench.run(MAX_RUN)["registers"][0] == SEVEN

    def test_a_mistake_is_a_400_naming_the_line(self) -> None:
        """The assembler's own message, with its line number, comes back."""
        bench = Bench()
        response = bench.load("li r0, 7\nfly r1")
        assert response.status == BAD_REQUEST
        assert _json(response)["message"].startswith("line 2:")
        assert bench.machine()["instruction"]["text"] == "li r1, 255"

    def test_a_program_too_big_for_memory_is_a_400(self) -> None:
        """65 words do not fit in 64."""
        assert Bench().load(TOO_MANY_WORDS).status == BAD_REQUEST

    def test_source_that_is_not_text_is_a_400(self) -> None:
        """A number, nothing at all, or a list is not assembly."""
        bench = Bench()
        statuses = [bench.post("/api/program", item).status for item in ({"source": 5}, {}, [1])]
        assert statuses == [BAD_REQUEST] * len(statuses)


class TestPebbleOnTheBench:
    """POST /api/pebble translates a Pebble program, loads it, and the picture names its line."""

    def _bench(self) -> Bench:
        """Build a 256-word Bench with the countdown loaded, insisting the Bench agrees."""
        bench = Bench(PEBBLE_BITS)
        response = bench.pebble(COUNTDOWN)
        assert response.status == OK, response.text
        return bench

    def test_an_assembly_program_has_no_pebble(self) -> None:
        """The demo program is assembly, so `pebble` is null."""
        assert Bench().machine()["pebble"] is None

    def test_a_pebble_program_starts_paused_on_its_first_line(self) -> None:
        """The source comes back line by line, and line 1 runs first."""
        machine = self._bench().machine()
        assert machine["pc"] == 0
        assert machine["paused"] is True
        assert machine["sp"] == PEBBLE_WORDS
        assert machine["pebble"] == {"source": COUNTDOWN.splitlines(), "line": 1, "message": None}
        assert len(machine["pebble"]["source"]) == COUNTDOWN_LINES
        assert machine["instruction"]["word"] == translate(COUNTDOWN).program.words[0]

    def test_each_instruction_shows_the_line_that_made_it(self) -> None:
        """Stepping to the end, the line is always the source map's line for the instruction."""
        bench = self._bench()
        translated = translate(COUNTDOWN)
        machine = bench.machine()
        seen: set[int | None] = set()
        while not machine["halted"]:
            line = machine["pebble"]["line"]
            assert line == translated.line_at(machine["instruction"]["address"])
            seen.add(line)
            machine = bench.step("instruction")
        assert seen == {1, 2, PRINT_LINE, 4, None}

    def test_half_way_through_an_instruction_the_line_is_still_its_line(self) -> None:
        """The fetch moves `pc` on, but the line stays with the instruction being obeyed."""
        bench = self._bench()
        translated = translate(COUNTDOWN)
        machine = bench.machine()
        while translated.line_at(machine["pc"] + 1) == translated.line_at(machine["pc"]):
            machine = bench.step("instruction")
        here = translated.line_at(machine["pc"])
        machine = bench.step("cycle")
        assert translated.line_at(machine["pc"]) != here
        assert machine["pebble"]["line"] == here

    def test_running_to_the_end_says_the_program_finished(self) -> None:
        """The countdown prints 2 then 1, each on its own line; once halted no line is marked."""
        machine = self._bench().run(MAX_RUN)
        assert machine["output"] == "2\n1\n"
        assert machine["halted"] is True
        assert machine["pebble"]["line"] is None
        assert machine["pebble"]["message"] == "The program finished"

    def test_a_fault_names_its_pebble_line(self) -> None:
        """Dividing by zero halts on line 2, and the message says so."""
        bench = Bench(PEBBLE_BITS)
        assert bench.pebble(DIVIDE_BY_ZERO).status == OK
        machine = bench.run(MAX_RUN)
        assert machine["fault"] == "DIVIDE_BY_ZERO"
        assert machine["pebble"]["line"] == DIVIDE_LINE
        assert machine["pebble"]["message"] == f"Division by zero at line {DIVIDE_LINE}"

    def test_loading_assembly_afterwards_clears_the_pebble(self) -> None:
        """An assembly program has no Pebble source, so the pane empties."""
        bench = self._bench()
        assert bench.load("halt").status == OK
        assert bench.machine()["pebble"] is None

    def test_rewind_keeps_the_pebble_line(self) -> None:
        """Rewinding half an instruction shows exactly the picture from its start."""
        bench = self._bench()
        start = bench.step("instruction")
        bench.step("cycle")
        assert _json(bench.post("/api/rewind", {})) == start

    def test_an_unsupported_feature_is_a_400_with_its_line_and_column(self) -> None:
        """`/` is refused with the translator's message, line and column; nothing is loaded."""
        bench = self._bench()
        response = bench.pebble(DECIMAL_DIVIDE)
        assert response.status == BAD_REQUEST
        body = _json(response)
        assert body["message"].startswith("the / operator")
        assert (body["line"], body["column"]) == (DIVIDE_LINE, DIVIDE_COLUMN)
        assert bench.machine()["pebble"]["source"] == COUNTDOWN.splitlines()

    def test_a_pebble_mistake_is_a_400_with_its_line_and_column(self) -> None:
        """Pebble's own errors, such as a missing value, come back with their place."""
        bench = Bench(PEBBLE_BITS)
        response = bench.pebble(NOT_PEBBLE)
        assert response.status == BAD_REQUEST
        body = _json(response)
        assert "at line 1" in body["message"]
        assert (body["line"], body["column"]) == (1, NOT_PEBBLE_COLUMN)
        assert bench.machine()["pebble"] is None

    def test_a_program_whose_stack_has_no_room_is_a_400(self) -> None:
        """Three prints fit in 128 words, but main's first frame after them would not."""
        bench = Bench(address_bits=PEBBLE_STACK_BITS)
        source = "print(1)\n" * PEBBLE_STACK_PRINTS
        translated = translate(source)
        assert len(translated.program.words) <= (1 << PEBBLE_STACK_BITS)
        response = bench.pebble(source)
        assert response.status == BAD_REQUEST
        assert "room for its stack" in _json(response)["message"]
        assert bench.machine()["pebble"] is None

    def test_a_program_too_big_for_this_benchs_memory_is_a_400(self) -> None:
        """The countdown and its routines need more than the 64-word Bench has."""
        bench = Bench()
        response = bench.pebble(COUNTDOWN)
        assert response.status == BAD_REQUEST
        words = len(translate(COUNTDOWN).program.words)
        assert _json(response)["message"] == (
            f"this program needs {words} words, but this Bench's memory has only {WORDS}"
        )
        assert bench.machine()["instruction"]["text"] == "li r1, 255"

    def test_the_second_tour_comes_out_of_the_print_routine_on_line_four(self) -> None:
        """Stepping into the print routine, then running 180, has printed 3 and is on line 4."""
        bench = Bench(PEBBLE_BITS)
        machine = _json(bench.pebble(TOUR_COUNTDOWN))
        while machine["pebble"]["line"] is not None:
            machine = bench.step("instruction")
        machine = bench.run(TOUR_RUN)
        assert machine["output"] == "3\n"
        assert machine["pebble"]["line"] == TOUR_LINE_AFTER_PRINT
        machine = bench.run(MAX_RUN)
        assert machine["output"] == "3\n2\n1\n"
        assert machine["pebble"]["message"] == "The program finished"

    def test_the_second_tours_divide_by_zero_prints_twice_then_names_line_three(self) -> None:
        """10 // 2 and 10 // 1 print, then 10 // 0 halts on line 3."""
        bench = Bench(PEBBLE_BITS)
        assert bench.pebble(TOUR_DIVIDE).status == OK
        machine = bench.run(MAX_RUN)
        assert machine["output"] == "5\n10\n"
        assert machine["pebble"]["line"] == PRINT_LINE
        assert machine["pebble"]["message"] == f"Division by zero at line {PRINT_LINE}"

    def test_a_text_too_long_to_ever_fit_is_a_400_before_translating(self) -> None:
        """One character over the limit is refused with a friendly message; nothing loads."""
        bench = Bench(PEBBLE_BITS)
        response = bench.pebble("#" * (MAX_PEBBLE_CHARACTERS + 1))
        assert response.status == BAD_REQUEST
        assert "at most 65,536 characters" in _json(response)["message"]
        assert bench.machine()["pebble"] is None

    def test_a_text_just_at_the_limit_is_translated(self) -> None:
        """A comment padded to exactly the limit is still a Pebble program."""
        source = "print(7)\n#"
        source += "x" * (MAX_PEBBLE_CHARACTERS - len(source))
        assert Bench(PEBBLE_BITS).pebble(source).status == OK

    def test_source_that_is_not_text_is_a_400(self) -> None:
        """A number, nothing at all, or a list is not a Pebble program."""
        bench = Bench(PEBBLE_BITS)
        statuses = [bench.post("/api/pebble", item).status for item in ({"source": 5}, {}, [1])]
        assert statuses == [BAD_REQUEST] * len(statuses)


class TestTheViewAndThePage:
    """GET /api/view looks into the gate engine's circuit; GET / serves the page."""

    def test_the_whole_circuit_holds_the_cpu_and_the_ram(self) -> None:
        """With no path the view is the top of the circuit."""
        view = _json(Bench().view(""))
        assert sorted(child["name"] for child in view["children"]) == ["cpu", "ram"]

    def test_the_alu_is_one_click_down_from_the_cpu(self) -> None:
        """`cpu` lists `alu` among its parts."""
        view = _json(Bench().view("cpu"))
        assert "alu" in [child["name"] for child in view["children"]]

    def test_the_tour_gates_show_forty_eight_plus_three_in_the_first_column(self) -> None:
        """After fetching the add, the first column's and sees a 0 and a 1, so nothing carries."""
        bench = Bench()
        bench.run(RUN_TO_ADD)
        bench.step("cycle")
        gates = _json(bench.view(ALU_GATE))["gates"]
        assert sorted((g["value_a"], g["value_b"]) for g in gates) == [(0, 1), (1, 1)]
        assert gates[-1]["value_out"] == 0

    def test_an_unknown_part_is_a_friendly_404(self) -> None:
        """Asking for a scope that does not exist says so, rather than crashing."""
        response = Bench().view("cpu.nope")
        assert response.status == NOT_FOUND
        assert "No part called cpu.nope" in response.text

    def test_the_front_page_has_the_machine_and_its_buttons(self) -> None:
        """GET / serves HTML with the step buttons, rewind, run and the load box."""
        response = _run(Bench().client.get("/"))
        assert response.status == OK
        assert "text/html" in (response.headers.get("Content-Type") or "")
        for words in ("Bench", "1 gate", "100 gates", "1 cycle", "1 instruction", "Rewind"):
            assert words in response.text
        assert "<script src" not in response.text

    def test_the_front_page_has_a_pebble_pane_that_never_injects_html(self) -> None:
        """The page loads Pebble and draws it with textContent, never innerHTML."""
        text = _run(Bench().client.get("/")).text
        for words in ("Pebble", "/api/pebble", "Load Pebble", TOUR_COUNTDOWN):
            assert words in text
        assert "innerHTML" not in text


def test_the_bench_opens_on_this_computer_only() -> None:
    """open_bench listens on 127.0.0.1, and the banner names the real address."""

    async def body() -> tuple[str, int]:
        server = await open_bench(0, address_bits=SMALL)
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
    """Serve opens the Bench, prints where it is, and closes it when serving ends."""

    async def finish(_self: AsyncServer) -> None:
        """Stand in for serving forever by returning at once."""

    monkeypatch.setattr(AsyncServer, "serve_forever", finish)
    monkeypatch.setattr(entry, "PORT", 0)
    monkeypatch.setattr(entry, "ADDRESS_BITS", SMALL)
    _run(entry.serve())
    out = capsys.readouterr().out
    assert "Building the computer" in out
    assert "The Bench is open at http://127.0.0.1:" in out


FULL_SIZE_TOUR_GATES = [610636, 610637]


@pytest.mark.slow
def test_the_full_size_tour_finds_the_gates_the_bench_page_names() -> None:
    """On the real 4K Bench, the tour's two gates are the numbers the docs give."""

    async def body() -> list[int]:
        client = TestClient(create_bench())
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
def test_the_bench_page_gives_the_real_gate_steps_per_instruction(address_bits: int) -> None:
    """The quickest and slowest demo instructions take the gate steps the docs give."""
    counts = _gate_steps_per_instruction(address_bits)
    assert (min(counts), max(counts)) == DEMO_GATE_STEPS[address_bits]
