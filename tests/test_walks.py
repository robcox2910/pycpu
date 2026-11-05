"""Tests for the guided walks: the files, the replay, the checks and the routes."""

import re
import time
from importlib import resources
from pathlib import Path
from typing import Any, cast

import pytest
from pynet.loop import run as run_loop
from pynet.loop import sleep
from pyweb.testing import TestClient, TestResponse

from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.picture import machine_picture
from pycpu.cockpit.session import (
    FINISHED_NOTE,
    MAX_RUN,
    Cockpit,
    CockpitBusy,
    CockpitRefusal,
    Depth,
    NoSuchWalk,
)
from pycpu.cockpit.walks import (
    WALK_ORDER,
    Halted,
    LineIs,
    OutputContains,
    RegisterIs,
    RunInstructions,
    RunToLine,
    Start,
    StepAt,
    StepGateUntil,
    StepLineInto,
    VariableIs,
    Walk,
    WalkError,
    example_source,
    load_walk,
    load_walks,
    parse_action,
    parse_check,
    parse_walk,
    passes,
    walk_named,
)
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.translator import FRAME_POINTER

BITS = 8
OK = 200
BAD_REQUEST = 400
NOT_FOUND = 404
FEWEST_STEPS = 4
MOST_STEPS = 8
FULL_SIZE_SECONDS = 5.0
CONCEPTS = Path(__file__).parent.parent / "docs" / "concepts"
SOME_GATES = 5
THIRTEEN = 13
FAST_TICK = 0.01
QUICK_PLAY = 1_000

GOOD = """
title = "A test walk"
example = "countdown"
see_also = "the-clock"

[[steps]]
say = "Here we start."
do = "start"
look = "line"

[[steps]]
say = "One line on."
do = "step line"
look = "line"
show = "variables"

[try]
task = "Press Step until n is 0."
look = "line"
check = "variable n == 0"
solution = ["step line"]
"""


def _walks() -> tuple[Walk, ...]:
    """Return the five walks, as the session reads them."""
    return load_walks()


def _walk(name: str) -> Walk:
    """Return the walk called `name`, which must exist."""
    walk = walk_named(name)
    assert walk is not None
    return walk


def _walk_picture(cockpit: Cockpit) -> dict[str, Any]:
    """Return the picture's `walk` key, which must be there."""
    picture = cast("dict[str, Any] | None", machine_picture(cockpit)["walk"])
    assert picture is not None
    return picture


def _variables(cockpit: Cockpit) -> dict[str, int]:
    """Return the variables pane as a name-to-value table (empty with no ready frame)."""
    variables = cast("dict[str, Any] | None", machine_picture(cockpit)["variables"])
    if variables is None:
        return {}
    return {name["name"]: name["value"] for name in variables["names"]}


def _key(picture: dict[str, Any], path: str) -> bool:
    """Say whether the dotted `path` names a key in the picture."""
    here: Any = picture
    for part in path.split("."):
        if not isinstance(here, dict) or part not in here:
            return False
        here = cast("dict[str, Any]", here)[part]
    return True


@pytest.fixture(scope="module")
def cockpit() -> Cockpit:
    """Build one small Cockpit for the module; every walk replays from a clean load."""
    return Cockpit(BITS)


class TestTheFiles:
    """The five walk files load, in order, and each follows the house rules."""

    def test_all_five_load_in_walk_order(self) -> None:
        """`load_walks` gives the five walks in `WALK_ORDER`."""
        assert tuple(walk.name for walk in _walks()) == WALK_ORDER

    def test_the_folder_holds_exactly_the_five(self) -> None:
        """There is no walk file outside `WALK_ORDER`, so none is forgotten."""
        folder = resources.files("pycpu.cockpit").joinpath("walks")
        names = {p.name.removesuffix(".toml") for p in folder.iterdir() if p.name.endswith(".toml")}
        assert names == set(WALK_ORDER)

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_each_walk_has_four_to_eight_steps(self, name: str) -> None:
        """A walk is short: 4 to 8 steps, then its Now you try."""
        assert FEWEST_STEPS <= len(_walk(name).steps) <= MOST_STEPS

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_each_sentence_is_one_sentence(self, name: str) -> None:
        """Every say and the task is one sentence, ending in a full stop."""
        walk = _walk(name)
        for text in (*(step.say for step in walk.steps), walk.trial.task):
            assert text.endswith(".")
            assert re.search(r"[.!?] [A-Z]", text) is None, text

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_each_see_also_page_exists(self, name: str) -> None:
        """A walk's `see_also` is a real concept page."""
        assert (CONCEPTS / f"{_walk(name).see_also}.md").is_file()

    def test_subtracting_reaches_the_alu_with_a_gate_step(self) -> None:
        """The subtracting walk uses `step gate until cpu.alu`."""
        actions = [step.action for step in _walk("subtracting-with-gates").steps]
        assert StepGateUntil("cpu.alu") in actions

    def test_the_call_walk_uses_factorial(self) -> None:
        """The call walk runs the factorial example."""
        assert _walk("a-call-and-the-stack").source == example_source("factorial")


class TestGoingToEveryStep:
    """Every step of every walk can be reached, and the picture says the file's words."""

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_every_step_says_its_sentence(self, cockpit: Cockpit, name: str) -> None:
        """For each step, `walk.say`, `look` and `show` are the file's own."""
        walk = _walk(name)
        for number, step in enumerate(walk.steps):
            cockpit.go_to_walk(name, number)
            picture = _walk_picture(cockpit)
            assert picture == {
                "name": name,
                "title": walk.title,
                "step": number,
                "count": len(walk.steps),
                "say": step.say,
                "look": step.look.value,
                "show": step.show,
                "step_kind": None,
                "trying": False,
                "task": walk.trial.task,
                "done": False,
                "off_script": False,
            }

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_every_show_is_a_key_of_the_picture(self, cockpit: Cockpit, name: str) -> None:
        """What a step highlights is really in the picture at that step."""
        walk = _walk(name)
        for number, step in enumerate(walk.steps):
            if step.show is not None:
                cockpit.go_to_walk(name, number)
                assert _key(machine_picture(cockpit), step.show), (name, number, step.show)

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_the_try_stage_shows_the_task(self, cockpit: Cockpit, name: str) -> None:
        """At `step == count` the picture is trying, with no say and the try's look."""
        walk = _walk(name)
        cockpit.go_to_walk(name, len(walk.steps))
        picture = _walk_picture(cockpit)
        assert picture["trying"] is True
        assert picture["say"] is None
        assert picture["look"] == walk.trial.look.value
        assert picture["task"] == walk.trial.task
        assert picture["step_kind"] == walk.trial.step

    def test_the_call_walk_offers_step_into(self) -> None:
        """Only the call walk's try asks the page for Step into."""
        kinds = {walk.name: walk.trial.step for walk in _walks()}
        assert kinds == {name: "into" if name == "a-call-and-the-stack" else None for name in kinds}

    def test_the_clock_try_takes_two_beats_an_instruction(self, cockpit: Cockpit) -> None:
        """Each instruction is a fetch beat then an execute beat, and li r3, 13 is the third."""
        walk = _walk("why-the-clock-ticks")
        cockpit.go_to_walk(walk.name, len(walk.steps))
        assert "li r3, 13" in walk.trial.task
        assert "every instruction takes two" in walk.trial.task
        beats: list[tuple[str, bool, str]] = []
        for _ in walk.trial.solution:
            cockpit.step_at(Depth.PART)
            picture = machine_picture(cockpit)
            text = cast("dict[str, Any]", picture["instruction"])["text"]
            beats.append(
                (cast("str", picture["phase"]), cast("bool", picture["at_boundary"]), text)
            )
        assert beats == [
            ("fetch", True, "li r2, 157"),  # the first beat finishes getsp r1
            ("execute", False, "li r2, 157"),
            ("fetch", True, "lhi r2, 0"),
            ("execute", False, "lhi r2, 0"),
            ("fetch", True, "li r3, 13"),
            ("execute", False, "li r3, 13"),
            ("fetch", True, "add r2, r2, r3"),
        ]
        assert cockpit.computer.state().registers[3] == THIRTEEN


# The "What just happened" sentence at each step of each walk, on the 256-word machine.
# Each walk sentence that names a number is backed by these, or by the checks below.
HAPPENED: dict[str, list[str | None]] = {
    "many-instructions": [
        None,
        "Ran 202 instructions to reach line 5.",
        "The CPU copied 5 from memory address 254 into r1.",
        "The CPU pushed 5 from r1 onto the stack, at address 253.",
        "Line 5 ran 8 instructions. n changed from 5 to 4.",
    ],
    "where-n-lives": [
        None,
        "Line 2 ran 14 instructions. n changed from 0 to 5.",
        "Ran 188 instructions to reach line 5.",
        "The CPU copied 5 from memory address 254 into r1.",
        "Line 5 ran 9 instructions. n changed from 5 to 4.",
    ],
    "subtracting-with-gates": [
        None,
        "Ran 202 instructions to reach line 5.",
        "Ran 6 instructions.",
        "Took 1,328 gate steps. Gate 41152, a NAND inside an AND in the ALU, worked out a 0.",
        "The ALU took 1 away from 5. The answer, 4, went into r1.",
    ],
    "a-call-and-the-stack": [
        None,
        "Ran 21 instructions to reach line 3.",
        "Ran 35 instructions to reach line 3.",
        "Ran 118 instructions to reach line 4.",
        "Line 4 ran 6 instructions.",
        "Ran 659 instructions to reach line 9.",
    ],
    "why-the-clock-ticks": [
        None,
        "That step moved the write clock wire, not a gate, so there is no gate to show.",
        "Gate 0, a NAND inside an AND in the memory, worked out a 1.",
        "That step moved the write clock wire, not a gate, so there is no gate to show.",
        "Gate 0, a NAND inside an AND in the memory, worked out a 1.",
        "That step moved the clock wire, not a gate, so there is no gate to show.",
        "Fetch: the CPU read the word at address 0, which says getsp r1.",
    ],
}


# The numbers each walk sentence names, step by step: n's value, a register, a line,
# the screen. They hold at any memory size, so the slow test checks them at full size.
N = "n"
CLAIMS: dict[tuple[str, int], dict[str, object]] = {
    ("many-instructions", 1): {"line": 5, N: 5},
    ("many-instructions", 2): {"r1": 5, N: 5},
    ("many-instructions", 3): {"stack top": 5},
    ("many-instructions", 4): {N: 4, "words on line 5": 10},
    ("where-n-lives", 1): {N: 5},
    ("where-n-lives", 2): {"line": 5, N: 5},
    ("where-n-lives", 3): {"r1": 5},
    ("where-n-lives", 4): {N: 4},
    ("subtracting-with-gates", 1): {"line": 5, N: 5},
    ("subtracting-with-gates", 2): {"r1": 5, "r2": 1, "next": "sub"},
    ("subtracting-with-gates", 3): {"gate in": "cpu.alu.", "next": "sub", "phase": "execute"},
    ("subtracting-with-gates", 4): {"r1": 4},
    ("a-call-and-the-stack", 1): {
        "line": 3,
        N: 5,
        "sp": "falls",
        "frames": [5],
        "return to line": 8,
    },
    ("a-call-and-the-stack", 2): {"line": 3, N: 4, "sp": "falls", "frames": [4, 5]},
    ("a-call-and-the-stack", 3): {"line": 4, N: 1, "sp": "falls", "frames": [1, 2, 3, 4, 5]},
    ("a-call-and-the-stack", 4): {"line": 6, N: 2, "sp": "rises", "frames": [2, 3, 4, 5]},
    ("a-call-and-the-stack", 5): {"output": "120\n", "sp": "rises", "frames": []},
    ("why-the-clock-ticks", 2): {"listens to write": True},
    ("why-the-clock-ticks", 4): {"listens to write": True},
    ("why-the-clock-ticks", 6): {"next": "getsp r1", "phase": "execute"},
}


def _frames(cockpit: Cockpit) -> list[int]:
    """List the `n` of every frame of fact on the stack, the running one first.

    Each frame keeps the caller's `r7` at `[r7]`, the return address at `[r7+1]`
    and the argument `n` at `[r7+2]`. The chain ends at the main program's frame,
    which sits at the top of memory.
    """
    state = cockpit.computer.state()
    memory, top = state.memory, len(state.memory) - 1
    pointer, found = state.registers[FRAME_POINTER], list[int]()
    while pointer != top and len(found) < len(memory):
        found.append(memory[pointer + 2])
        pointer = memory[pointer]
    return found


def _seen(cockpit: Cockpit, claim: str) -> object:
    """Read from the machine the one thing a claim is about."""
    picture = machine_picture(cockpit)
    state = cockpit.computer.state()
    translated = cockpit.translated
    assert translated is not None
    registers = cast("list[int]", picture["registers"])
    text = cast("dict[str, Any]", picture["instruction"])["text"]
    last_gate = cast("dict[str, Any] | None", picture["last_gate"])
    path = "" if last_gate is None else last_gate["path"]
    stack = cast("list[dict[str, Any]]", picture["stack"])
    seen: dict[str, object] = {
        "line": cast("dict[str, Any]", picture["pebble"])["line"],
        "r1": registers[1],
        "r2": registers[2],
        "stack top": stack[0]["word"] if stack else None,
        "next": "sub" if text.startswith("sub ") else text,
        "gate in": "cpu.alu." if path.startswith("cpu.alu.") else path,
        "phase": picture["phase"],
        "output": picture["output"],
        "listens to write": last_gate is not None and _listens_to_write(cockpit),
        "words on line 5": sum(
            1
            for a in range(len(translated.frames))
            if translated.line_at(a) == 5  # noqa: PLR2004
        ),
        "frames": _frames(cockpit) if "fact" in translated.source else None,
        "return to line": translated.line_at(
            state.memory[(state.registers[FRAME_POINTER] + 1) % len(state.memory)]
        ),
    }
    return seen[claim] if claim in seen else _variables(cockpit).get(claim)


# What differs in the sentences on the 4K machine: memory addresses near the top of
# memory, and gate ids (the bigger RAM is built first, so later gates are numbered higher).
FULL_SIZE_CHANGES = {
    "memory address 254": "memory address 4094",
    "address 253": "address 4093",
    "Gate 41152": "Gate 610564",
}


def check_the_numbers(cockpit: Cockpit, name: str) -> None:
    """Replay every step of the walk `name` and check each claim in `CLAIMS` there."""
    sp = None
    for number in range(len(_walk(name).steps)):
        cockpit.go_to_walk(name, number)
        now = cockpit.computer.state().sp
        for claim, expected in CLAIMS.get((name, number), {}).items():
            if claim == "sp":
                assert sp is not None
                assert ("falls" if now < sp else "rises") == expected, (name, number)
            else:
                assert _seen(cockpit, claim) == expected, (name, number, claim)
        sp = now


def _listens_to_write(cockpit: Cockpit) -> bool:
    """Say whether the last gate step's gate is a memory gate with the write wire as an input."""
    gate = cockpit.computer.gate
    micro = cockpit.last_gate
    assert micro is not None
    first, second, _ = gate.simulator.circuit.gate_wires
    write = gate._clock.write  # pyright: ignore[reportPrivateUsage]
    in_memory = gate.simulator.circuit.scope_of(micro.gate).startswith("ram.")
    return in_memory and write in (first[micro.gate], second[micro.gate])


class TestTheNumbersAreReal:
    """Every number a walk sentence says is the number the machine shows."""

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_what_just_happened_at_each_step(self, cockpit: Cockpit, name: str) -> None:
        """The sentence after each step's move is the one pinned here."""
        said: list[str | None] = []
        for number in range(len(_walk(name).steps)):
            cockpit.go_to_walk(name, number)
            said.append(cockpit.happened)
        assert said == HAPPENED[name]

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_the_numbers_in_the_sentences(self, cockpit: Cockpit, name: str) -> None:
        """The registers, variables, lines and output each sentence names are there."""
        check_the_numbers(cockpit, name)


class TestNowYouTry:
    """The check starts false, the solution passes it, and a pass is latched."""

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_the_check_is_false_before_any_move(self, cockpit: Cockpit, name: str) -> None:
        """A fresh try is never already done."""
        walk = _walk(name)
        cockpit.go_to_walk(name, len(walk.steps))
        assert cockpit.walk is not None
        assert cockpit.walk.done is False
        start = cockpit.computer.instruction_start
        assert not passes(walk.trial.check, cockpit.computer.state(), start, cockpit.translated)

    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_the_solution_passes_the_check(self, cockpit: Cockpit, name: str) -> None:
        """Playing the walk's own solution makes `done` true, and the picture says so."""
        walk = _walk(name)
        cockpit.go_to_walk(name, len(walk.steps))
        for action in walk.trial.solution:
            cockpit.act(action)
        assert cockpit.walk is not None
        assert cockpit.walk.done is True
        assert cockpit.walk.off_script is False
        assert _walk_picture(cockpit)["done"] is True

    def test_a_passed_check_stays_passed_past_the_halt(self, cockpit: Cockpit) -> None:
        """After n reaches 0, stepping on to the halt leaves the countdown's try done."""
        walk = _walk("many-instructions")
        cockpit.go_to_walk(walk.name, len(walk.steps))
        for action in walk.trial.solution:
            cockpit.act(action)
        while not cockpit.computer.state().halted:
            cockpit.step_at(Depth.LINE)
            assert _variables(cockpit).get("n", 0) == 0
        cockpit.step_at(Depth.LINE)  # one press too many: the program has finished
        start = cockpit.computer.instruction_start
        assert not passes(walk.trial.check, cockpit.computer.state(), start, cockpit.translated)
        assert cockpit.walk is not None
        assert cockpit.walk.done is True

    def test_steps_at_the_try_stage_are_not_off_script(self, cockpit: Cockpit) -> None:
        """Pressing Step is the task, so it does not take the learner off the walk."""
        walk = _walk("where-n-lives")
        cockpit.go_to_walk(walk.name, len(walk.steps))
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.rewind()
        cockpit.run(1)
        assert cockpit.walk is not None
        assert cockpit.walk.off_script is False

    def test_a_load_at_the_try_stage_is_off_script_and_judges_nothing(self) -> None:
        """Loading a program leaves the walk, and its check is no longer judged."""
        cockpit = Cockpit(BITS)
        cockpit.go_to_walk("many-instructions", len(_walk("many-instructions").steps))
        cockpit.load_pebble("let n = 0\nprint(n)\n")
        cockpit.step_at(Depth.LINE)
        assert cockpit.walk is not None
        assert cockpit.walk.off_script is True
        assert cockpit.walk.done is False

    def test_a_walk_move_needs_a_walk(self) -> None:
        """`act` with no walk open is refused in plain words."""
        with pytest.raises(CockpitRefusal, match="no walk open"):
            Cockpit(BITS).act(StepAt(Depth.LINE))


class TestReplay:
    """Opening a walk stops play, loads cleanly and leaves nothing from before."""

    def _first_picture(self, cockpit: Cockpit) -> dict[str, object]:
        """Open the first walk at step 0 and return its picture without the load count."""
        cockpit.go_to_walk("many-instructions", 0)
        picture = machine_picture(cockpit)
        del picture["program"]  # every load counts up, so the page refetches the listing
        return picture

    def test_opening_a_walk_while_playing_stops_play_first(self) -> None:
        """`go_to_walk` while playing pauses, then replays."""
        cockpit = Cockpit(BITS)
        cockpit.start_playing()
        cockpit.play_tick(SOME_GATES)
        cockpit.go_to_walk("many-instructions", 1)
        assert cockpit.playing is False
        assert cockpit.computer.paused
        assert cockpit.happened == HAPPENED["many-instructions"][1]

    def test_nothing_leaks_from_the_learners_own_program(self) -> None:
        """After loading their own Pebble, the walk's first picture is a fresh one."""
        fresh = self._first_picture(Cockpit(BITS))
        cockpit = Cockpit(BITS)
        cockpit.load_pebble("let x = 7\nprint(x * 3)\n")
        cockpit.step_at(Depth.LINE)
        assert self._first_picture(cockpit) == fresh

    def test_nothing_leaks_from_mid_instruction(self) -> None:
        """After some gate steps into an instruction, the first picture is a fresh one."""
        fresh = self._first_picture(Cockpit(BITS))
        cockpit = Cockpit(BITS)
        cockpit.go_to_walk("subtracting-with-gates", 3)
        for _ in range(SOME_GATES):
            cockpit.step_at(Depth.GATE)
        assert not cockpit.computer.gate.at_boundary
        assert self._first_picture(cockpit) == fresh

    def test_nothing_leaks_from_play(self) -> None:
        """After play, the first picture is a fresh one."""
        fresh = self._first_picture(Cockpit(BITS))
        cockpit = Cockpit(BITS)
        cockpit.load_assembly("loop:\n    addi r1, 1\n    jmp loop\n")
        cockpit.start_playing()
        cockpit.play_tick(SOME_GATES)
        assert self._first_picture(cockpit) == fresh

    def test_replay_lands_on_the_same_machine_every_time(self, cockpit: Cockpit) -> None:
        """Going to a step twice, with wandering between, gives the same state."""
        cockpit.go_to_walk("a-call-and-the-stack", 4)
        first = cockpit.computer.state()
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.go_to_walk("a-call-and-the-stack", 2)
        cockpit.go_to_walk("a-call-and-the-stack", 4)
        assert cockpit.computer.state() == first

    def test_a_move_of_your_own_is_off_script_until_you_go_back(self, cockpit: Cockpit) -> None:
        """Any non-walk move during the steps sets `off_script`; `go_to_walk` clears it."""
        moves = [
            lambda: cockpit.step_at(Depth.GATE),
            lambda: cockpit.run(1),
            cockpit.rewind,
            lambda: cockpit.step_line(into=True),
            lambda: cockpit.load_pebble("print(1)\n"),
            lambda: cockpit.load_assembly("halt\n"),
        ]
        for move in moves:
            cockpit.go_to_walk("where-n-lives", 1)
            assert cockpit.walk is not None
            assert cockpit.walk.off_script is False
            move()
            assert cockpit.walk.off_script is True
            assert _walk_picture(cockpit)["off_script"] is True
        cockpit.go_to_walk("where-n-lives", 1)
        assert cockpit.walk is not None
        assert cockpit.walk.off_script is False

    def test_leave_walk_clears_it(self, cockpit: Cockpit) -> None:
        """Leaving puts the guide away and leaves the machine where it is."""
        cockpit.go_to_walk("where-n-lives", 2)
        state = cockpit.computer.state()
        cockpit.leave_walk()
        assert cockpit.walk is None
        assert machine_picture(cockpit)["walk"] is None
        assert cockpit.computer.state() == state

    def test_an_unknown_walk_or_step_is_refused(self, cockpit: Cockpit) -> None:
        """No such walk, or a step outside 0 to the count, is refused in plain words."""
        with pytest.raises(NoSuchWalk, match=r"^There is no walk called nonsense\.$"):
            cockpit.go_to_walk("nonsense", 0)
        count = len(_walk("where-n-lives").steps)
        for step in (-1, count + 1):
            with pytest.raises(CockpitRefusal, match=f"from 0 to {count}"):
                cockpit.go_to_walk("where-n-lives", step)

    def test_a_fast_forward_that_never_arrives_is_a_walk_error(self) -> None:
        """A run to a line the program never reaches fails loudly, and closes the walk."""
        cockpit = Cockpit(BITS)
        cockpit.go_to_walk("many-instructions", 0)
        with pytest.raises(WalkError, match="never reached line 99"):
            cockpit.act(RunToLine(99))
        with pytest.raises(WalkError, match="step gate until nowhere never reached a gate in it"):
            cockpit.act(StepGateUntil("nowhere"))


class TestTheNewMoves:
    """Run to a line and gate steps until a part, as moves of their own."""

    def test_run_to_the_line_you_are_on_goes_round_the_loop(self) -> None:
        """A run to the current line runs once round the loop, not nowhere."""
        cockpit = Cockpit(BITS)
        cockpit.go_to_walk("many-instructions", 1)
        cockpit.run_to_line(5)
        assert _variables(cockpit) == {"n": 4}
        assert machine_picture(cockpit)["pebble"] == {
            "source": example_source("countdown").splitlines(),  # pyright: ignore[reportOptionalMemberAccess]
            "line": 5,
            "message": None,
        }

    def test_run_to_line_on_assembly_or_a_halt(self) -> None:
        """Assembly has no lines to run to, and a halted machine says it has finished."""
        cockpit = Cockpit(BITS)
        with pytest.raises(CockpitRefusal, match="Pebble"):
            cockpit.run_to_line(1)
        cockpit.load_pebble("print(1)\n")
        cockpit.run(MAX_RUN)
        assert cockpit.run_to_line(1).stopped == "halted"
        assert cockpit.step_gate_until("cpu") is False
        assert cockpit.note == FINISHED_NOTE

    def test_run_to_line_that_halts_says_so(self) -> None:
        """A run that ends with the program stopping says it stopped, not that it arrived."""
        cockpit = Cockpit(BITS)
        cockpit.load_pebble("print(1)\n")
        assert cockpit.run_to_line(9).stopped == "halted"
        assert cockpit.happened is not None
        assert cockpit.happened.endswith("and then the program stopped.")

    def test_step_gate_until_while_playing_is_busy(self) -> None:
        """Like every move, the gate steps are refused while playing."""
        cockpit = Cockpit(BITS)
        cockpit.start_playing()
        with pytest.raises(CockpitBusy):
            cockpit.step_gate_until("cpu.alu")
        cockpit.stop_playing()


class TestGrammar:
    """Actions and checks are read by small explicit grammars, never run as code."""

    @pytest.mark.parametrize(
        ("text", "action"),
        [
            ("start", Start()),
            ("step line", StepAt(Depth.LINE)),
            ("step gate", StepAt(Depth.GATE)),
            ("run to line 5", RunToLine(5)),
            ("run 6 instructions", RunInstructions(6)),
            ("run 1 instruction", RunInstructions(1)),
            ("step gate until cpu.alu", StepGateUntil("cpu.alu")),
            ("step line into", StepLineInto()),
        ],
    )
    def test_each_action(self, text: str, action: object) -> None:
        """Each action shape reads as its value."""
        assert parse_action(text) == action

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("jump about", "unknown action"),
            ("step sideways", "must be one of line, instruction, part, gate"),
            ("run to line five", "whole number"),
            ("run to line 0", "from 1 up"),
            ("run 0 instructions", "at least 1"),
            ("__import__('os')", "unknown action"),
        ],
    )
    def test_a_bad_action(self, text: str, problem: str) -> None:
        """A bad action is a `WalkError` saying what is wrong."""
        with pytest.raises(WalkError, match=re.escape(problem)):
            parse_action(text)

    @pytest.mark.parametrize(
        ("text", "check"),
        [
            ("variable n == 0", VariableIs("n", 0)),
            ("variable n == -3", VariableIs("n", -3)),
            ("line == 6", LineIs(6)),
            ("register r3 == 13", RegisterIs(3, 13)),
            ('output contains "Lift off!"', OutputContains("Lift off!")),
            ("halted", Halted()),
        ],
    )
    def test_each_check(self, text: str, check: object) -> None:
        """Each check shape reads as its value."""
        assert parse_check(text) == check

    @pytest.mark.parametrize(
        "text",
        ["n == 0", "variable 1n == 0", "register x3 == 1", "output contains 120", "line = 6"],
    )
    def test_a_bad_check(self, text: str) -> None:
        """A check of no known shape is a `WalkError`."""
        with pytest.raises(WalkError, match="unknown check"):
            parse_check(text)

    def test_a_check_value_must_be_a_number(self) -> None:
        """`variable n == lots` says the value must be a whole number."""
        with pytest.raises(WalkError, match="whole number"):
            parse_check("variable n == lots")

    def test_checks_on_the_machine(self) -> None:
        """Each kind of check reads the real machine: register, output, line, halt."""
        cockpit = Cockpit(BITS)
        cockpit.load_pebble("let n = 3\nprint(n)\n")
        cockpit.step_at(Depth.LINE)
        here = cockpit.computer.state(), cockpit.computer.instruction_start, cockpit.translated
        assert passes(VariableIs("n", 3), *here)
        assert not passes(VariableIs("m", 3), *here)
        assert passes(LineIs(2), *here)
        assert not passes(Halted(), *here)
        assert not passes(RegisterIs(99, 0), *here)
        cockpit.run(MAX_RUN)
        here = cockpit.computer.state(), cockpit.computer.instruction_start, cockpit.translated
        assert passes(OutputContains("3"), *here)
        assert passes(Halted(), *here)
        assert not passes(LineIs(2), *here)
        assert not passes(VariableIs("n", 3), *here)

    def test_checks_on_assembly(self) -> None:
        """Assembly has no lines or variables, so those checks never pass."""
        cockpit = Cockpit(BITS)
        cockpit.load_assembly("li r1, 4\nhalt\n")
        cockpit.run(1)
        here = cockpit.computer.state(), cockpit.computer.instruction_start, None
        assert passes(RegisterIs(1, 4), *here)
        assert not passes(LineIs(1), *here)
        assert not passes(VariableIs("n", 4), *here)


def _bad(text: str, problem: str) -> None:
    """Fail unless the walk text is refused with a message naming the file and `problem`."""
    with pytest.raises(WalkError, match=r"^bad-walk\.toml: .*" + re.escape(problem)):
        parse_walk("bad-walk", text)


class TestBadFiles:
    """A bad walk file is a `WalkError` naming the file and the problem."""

    def test_a_good_file_reads(self) -> None:
        """The sample file reads, with its example's program and its steps."""
        walk = parse_walk("good", GOOD)
        assert walk.source == example_source("countdown")
        assert [step.action for step in walk.steps] == [Start(), StepAt(Depth.LINE)]
        assert walk.steps[1].show == "variables"
        assert walk.trial.check == VariableIs("n", 0)

    def test_an_unknown_action(self) -> None:
        """A step whose `do` is no action names the action."""
        _bad(GOOD.replace('do = "step line"', 'do = "jump about"'), "unknown action 'jump about'")

    def test_an_unknown_check(self) -> None:
        """A try whose check is no check names the check."""
        _bad(GOOD.replace("variable n == 0", "n is zero"), "unknown check 'n is zero'")

    def test_a_missing_try(self) -> None:
        """A walk with no `[try]` says it needs one."""
        _bad(GOOD[: GOOD.index("[try]")], "the walk needs a [try] table")

    def test_a_bad_example_name(self) -> None:
        """An example that does not exist is named."""
        _bad(GOOD.replace('"countdown"', '"nonsense"'), "there is no example called 'nonsense'")

    def test_more_mistakes(self) -> None:
        """Other mistakes each get a plain message."""
        _bad(GOOD.replace("title", "titel"), "the walk has unknown keys: titel")
        _bad(GOOD.replace('example = "countdown"', ""), "an example or a source, and not both")
        _bad(GOOD.replace('example = "countdown"', 'source = "  "'), "source must be")
        _bad(GOOD.replace('say = "Here we start."', ""), "step 1 needs say as some text")
        _bad(GOOD.replace('look = "line"', 'look = "far"', 1), "step 1's look must be one of")
        _bad(GOOD.replace('show = "variables"', 'show = "wires"'), "show 'wires'")
        _bad(GOOD.replace('do = "start"', 'do = "step line"'), "the first step must do start")
        _bad(GOOD.replace('solution = ["step line"]', "solution = []"), "[try] needs a solution")
        into = 'step = "into"\nsolution'
        _bad(GOOD.replace("solution", 'step = "over"\nsolution'), 'step may only be "into"')
        _bad(
            GOOD.replace("solution", into).replace('look = "line"\ncheck', 'look = "part"\ncheck'),
            'with look = "line"',
        )
        assert parse_walk("into", GOOD.replace("solution", into)).trial.step == "into"
        _bad(GOOD.replace('solution = ["step line"]', "solution = [1]"), "list of actions")
        _bad(GOOD.replace("[[steps]]", "[steps]", 1), "")  # TOML refuses a table then an array
        _bad(
            GOOD[: GOOD.index("[[steps]]")] + GOOD[GOOD.index("[try]") :], "at least one [[steps]]"
        )
        header, trial = GOOD[: GOOD.index("[[steps]]")], GOOD[GOOD.index("[try]") :]
        _bad("steps = [1]\n" + header + trial, "step 1 must be a table")
        _bad("try = 1\n" + GOOD[: GOOD.index("[try]")], "the walk needs a [try] table")

    def test_a_walk_with_its_own_source(self) -> None:
        """A walk may carry its own Pebble instead of naming an example."""
        walk = parse_walk("own", GOOD.replace('example = "countdown"', 'source = "print(1)\\n"'))
        assert walk.source == "print(1)\n"

    def test_a_missing_file(self) -> None:
        """`load_walk` of a name with no file says so."""
        with pytest.raises(WalkError, match=r"nonsense\.toml: there is no walk file"):
            load_walk("nonsense")


def _post(client: TestClient, path: str, body: object) -> TestResponse:
    """Post a JSON body to `path`."""
    return run_loop(client.post(path, json=body))  # pyright: ignore[reportArgumentType]


def _json(response: TestResponse) -> Any:
    """Read a response body as JSON."""
    return response.json()


class TestRoutes:
    """`/api/walks`, `/api/walk` and `/api/walk/leave`."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Give a small Cockpit app to call."""
        return TestClient(create_cockpit(address_bits=BITS))

    def test_the_list_is_in_walk_order(self, client: TestClient) -> None:
        """The list names each walk, its title and its page."""
        response = run_loop(client.get("/api/walks"))
        assert response.status == OK
        assert _json(response) == [
            {"name": w.name, "title": w.title, "see_also": w.see_also} for w in _walks()
        ]

    def test_opening_a_walk_answers_the_picture(self, client: TestClient) -> None:
        """`POST /api/walk` answers the picture with its `walk`."""
        response = _post(client, "/api/walk", {"name": "where-n-lives", "step": 1})
        assert response.status == OK
        walk = _json(response)["walk"]
        assert walk["name"] == "where-n-lives"
        assert walk["say"] == _walk("where-n-lives").steps[1].say

    def test_an_unknown_name_is_a_404_in_plain_words(self, client: TestClient) -> None:
        """A stale link gets 404 and "There is no walk called <name>."."""
        response = _post(client, "/api/walk", {"name": "nonsense", "step": 0})
        assert response.status == NOT_FOUND
        assert _json(response)["message"] == "There is no walk called nonsense."

    def test_a_bad_step_or_body_is_a_400(self, client: TestClient) -> None:
        """A step out of range, or a body of the wrong shape, is refused with 400."""
        count = len(_walk("where-n-lives").steps)
        bodies: list[object] = [
            {"name": "where-n-lives", "step": count + 1},
            {"name": "where-n-lives", "step": -1},
            {"name": "where-n-lives", "step": True},
            {"name": "where-n-lives", "step": "1"},
            {"name": "where-n-lives"},
            {"name": 3, "step": 0},
            [],
        ]
        for body in bodies:
            assert _post(client, "/api/walk", body).status == BAD_REQUEST, body

    def test_leave_clears_walk(self, client: TestClient) -> None:
        """After leave, the picture's `walk` is null."""
        _post(client, "/api/walk", {"name": "where-n-lives", "step": 0})
        response = _post(client, "/api/walk/leave", {})
        assert response.status == OK
        assert _json(response)["walk"] is None

    def test_opening_a_walk_while_playing_stops_play(self, client: TestClient) -> None:
        """A walk opened while playing pauses first and answers a paused picture."""
        assert _post(client, "/api/play", {"speed": 1}).status == OK
        response = _post(client, "/api/walk", {"name": "many-instructions", "step": 0})
        assert response.status == OK
        assert _json(response)["running"] is False
        assert _json(response)["paused"] is True


class TestPlay:
    """A walk and play together: refusals leave play alone, and checks read the live state."""

    def test_a_refused_walk_leaves_play_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bad walk name or step while playing is refused, and play keeps moving."""
        sessions: list[Cockpit] = []

        class RecordingCockpit(Cockpit):
            """A Cockpit that tells the test about itself."""

            def __init__(self, address_bits: int) -> None:
                """Build as usual and record this session."""
                super().__init__(address_bits)
                sessions.append(self)

        monkeypatch.setattr("pycpu.cockpit.app.Cockpit", RecordingCockpit)
        client = TestClient(create_cockpit(BITS, tick_seconds=FAST_TICK))
        session = sessions[-1]

        async def main() -> tuple[list[int], int, int]:
            """Play a counting loop, send two bad walks, then see that it still counts."""
            await client.post("/api/program", json={"source": "loop:\n addi r1, 1\n jmp loop\n"})
            await client.post("/api/play", json={"speed": QUICK_PLAY})
            refused = [
                (await client.post("/api/walk", json={"name": "nonsense", "step": 0})).status,
                (await client.post("/api/walk", json={"name": "where-n-lives", "step": 99})).status,
            ]
            before = session.computer.state().registers[1]
            await sleep(FAST_TICK * 10)
            after = session.computer.state().registers[1]
            await client.post("/api/pause", json={})
            return refused, before, after

        refused, before, after = run_loop(main())
        assert refused == [NOT_FOUND, BAD_REQUEST]
        assert after > before

    def test_a_line_check_is_judged_on_the_live_state_while_playing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Playing at the try stage passes a `line == n` check on the line really running."""
        walk = parse_walk("line-check", GOOD.replace("variable n == 0", "line == 4"))

        def only_this_walk(_name: str) -> Walk:
            """Stand in for `walk_named`: every name is this one test walk."""
            return walk

        monkeypatch.setattr("pycpu.cockpit.session.walk_named", only_this_walk)
        cockpit = Cockpit(BITS)
        cockpit.go_to_walk(walk.name, len(walk.steps))
        assert cockpit.walk is not None
        assert cockpit.walk.done is False
        cockpit.start_playing()
        while cockpit.play_tick(1) and not cockpit.walk.done:
            pass
        cockpit.stop_playing()
        assert cockpit.walk.done is True


class TestFullSize:
    """The real Cockpit: every walk at 12 address bits."""

    @pytest.fixture(scope="class")
    def full(self) -> Cockpit:
        """Build one full-size Cockpit (about 3 s) for every walk."""
        return Cockpit(RAM_ADDRESS_BITS)

    @pytest.mark.slow
    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_each_walk_reaches_its_last_step_quickly(self, full: Cockpit, name: str) -> None:
        """Replaying to the last step takes under 5 s, and the try's solution still works."""
        walk = _walk(name)
        began = time.perf_counter()
        full.go_to_walk(name, len(walk.steps) - 1)
        assert time.perf_counter() - began < FULL_SIZE_SECONDS
        full.go_to_walk(name, len(walk.steps))
        for action in walk.trial.solution:
            full.act(action)
        assert full.walk is not None
        assert full.walk.done is True

    @pytest.mark.slow
    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_the_numbers_hold_at_full_size(self, full: Cockpit, name: str) -> None:
        """Every number a walk sentence claims is the same on the 4K machine."""
        check_the_numbers(full, name)

    @pytest.mark.slow
    @pytest.mark.parametrize("name", WALK_ORDER)
    def test_what_just_happened_at_full_size(self, full: Cockpit, name: str) -> None:
        """The sentences are the small machine's, but for addresses and gate ids."""
        said: list[str | None] = []
        for number in range(len(_walk(name).steps)):
            full.go_to_walk(name, number)
            said.append(full.happened)
        expected = HAPPENED[name]
        for small, large in FULL_SIZE_CHANGES.items():
            expected = [None if s is None else s.replace(small, large) for s in expected]
        assert said == expected
