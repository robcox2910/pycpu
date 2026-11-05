"""Tests for the "What just happened" sentence: one plain sentence after every move."""

import re
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.arithmetic import AluOp
from pycpu.assembler import assemble
from pycpu.cockpit.app import example_programs
from pycpu.cockpit.explain import (
    ALU_TEMPLATES,
    FINISHED_NOTE,
    OPCODE_TEMPLATES,
    Depth,
    describe_line,
    describe_move,
    describe_rewind,
    describe_run,
    gate_place,
    gate_words,
)
from pycpu.cockpit.picture import machine_picture, variables_picture
from pycpu.cockpit.session import END_NOTE, NO_LINES_NOTE, Cockpit
from pycpu.computer import StepSize
from pycpu.cpu import GateMachine, MicroStep, Phase
from pycpu.fast import FastMachine
from pycpu.isa import Opcode, decode, encode
from pycpu.state import WORD_MASK, Flags

BITS = 8
WORDS = 1 << BITS
SUB_PROGRAM = "li r1, 2\nli r2, 1\nsub r1, r1, r2\nhalt\n"
SUB_SENTENCE = "The ALU took 1 away from 2. The answer, 1, went into r1."
SUB_ADDRESS = 2  # where the `sub` sits in SUB_PROGRAM
SOME_GATES = 5
LINE_N_MINUS_1 = 5  # `n = n - 1` in the countdown example
N_BEFORE = 2
LINE_INSTRUCTIONS = 10  # measured: the translator makes 10 instructions for `n = n - 1`
TOUR_GATE = 41226  # the adder gate A Tour of the Cockpit reaches
TOUR_LINE_STEPS = 12
TOUR_INSTRUCTION_STEPS = 6
FAR_ADDRESS = 300  # outside a 256-word memory
HIDDEN = "$"
ANSWER = re.compile(r"The answer, (\d+), went into r(\d)\.$")
ZERO_FLAG = Flags(1, 0, 0, 0)
NEGATIVE_FLAG = Flags(0, 1, 0, 0)
NEXT_ANYWAY = "li r1, 0\naddi r1, 0\nbr eq, next\nnext:\n    halt\n"
TOUR_GATE_SENTENCE = f"Gate {TOUR_GATE}, a NAND inside an XOR in the ALU, worked out a 1."
MID_LINE_SENTENCE = (
    "Line 5 finished the instruction you were in, then ran 9 more. n changed from 2 to 1."
)


def _countdown() -> str:
    """Return the source of the countdown example."""
    return next(e["source"] for e in example_programs() if e["name"] == "countdown")


def _first(
    source: str,
    *,
    registers: dict[int, int] | None = None,
    memory: dict[int, int] | None = None,
    sp: int | None = None,
    flags: Flags | None = None,
    pc: int = 0,
) -> str:
    """Run the first instruction of `source` on the fast engine and describe it.

    The registers, memory words, sp and flags given are set before it runs, so each
    sentence is built from numbers the test knows.
    """
    program = assemble(source, words=WORDS)
    fast = FastMachine(WORDS)
    fast.load_program(program.words)
    start = fast.state()
    regs = list(start.registers)
    for index, value in (registers or {}).items():
        regs[index] = value
    cells = list(start.memory)
    for address, value in (memory or {}).items():
        cells[address] = value
    start = replace(
        start,
        registers=tuple(regs),
        memory=tuple(cells),
        sp=start.sp if sp is None else sp,
        flags=start.flags if flags is None else flags,
        pc=pc,
    )
    fast.load_state(start)
    fast.step()
    return describe_move(Depth.INSTRUCTION, start, fast.state(), None, None, 1)


# Every opcode and every ALU function, each run once with known numbers.
CASES: list[tuple[str, dict[str, object], str]] = [
    (
        "add r3, r1, r2",
        {"registers": {1: 2, 2: 3}},
        "The ALU added 2 and 3. The answer, 5, went into r3.",
    ),
    ("sub r1, r1, r2", {"registers": {1: 2, 2: 1}}, SUB_SENTENCE),
    (
        "and r3, r1, r2",
        {"registers": {1: 12, 2: 10}},
        "The ALU kept only the bits that are 1 in both 12 and 10. The answer, 8, went into r3.",
    ),
    (
        "or r3, r1, r2",
        {"registers": {1: 12, 2: 10}},
        "The ALU kept the bits that are 1 in 12 or in 10. The answer, 14, went into r3.",
    ),
    (
        "xor r3, r1, r2",
        {"registers": {1: 12, 2: 10}},
        (
            "The ALU kept the bits that are 1 in 12 or in 10, but not in both. "
            "The answer, 6, went into r3."
        ),
    ),
    (
        "shl r3, r1",
        {"registers": {1: 5}},
        "The ALU slid every bit of 5 one place to the left. The answer, 10, went into r3.",
    ),
    (
        "shr r3, r1",
        {"registers": {1: 5}},
        "The ALU slid every bit of 5 one place to the right. The answer, 2, went into r3.",
    ),
    (
        "mov r3, r2",
        {"registers": {2: 7}},
        "The ALU let 7 straight through. The answer, 7, went into r3.",
    ),
    (
        "cmp r1, r2",
        {"registers": {1: 2, 2: 1}},
        (
            "The ALU compared 2 with 1 by taking 1 away from 2. It kept no answer, only the "
            "flag lamps: zero lamp off, negative lamp off, carry lamp on (nothing had to be "
            "borrowed), overflow lamp off."
        ),
    ),
    (
        "cmp r1, r2",
        {"registers": {1: 1, 2: 2}},
        (
            "The ALU compared 1 with 2 by taking 2 away from 1. It kept no answer, only the "
            "flag lamps: zero lamp off, negative lamp on, carry lamp off (it had to borrow), "
            "overflow lamp off."
        ),
    ),
    ("li r1, 5", {}, "The CPU put the number 5 into r1."),
    (
        "lhi r1, 2",
        {"registers": {1: 3}},
        "The CPU put 2 into the top half of r1, so r1 is now 515.",
    ),
    (
        "load r1, [r2+1]",
        {"registers": {2: 100}, "memory": {101: 42}},
        "The CPU copied 42 from memory address 101 into r1.",
    ),
    (
        "store r1, [r2-1]",
        {"registers": {1: 9, 2: 100}},
        "The CPU copied 9 from r1 into memory address 99.",
    ),
    (
        "store r1, [r2]",
        {"registers": {1: 53, 2: WORD_MASK}},
        'The CPU sent 53 from r1 to the screen, which showed "5".',
    ),
    (
        "store r1, [r2]",
        {"registers": {1: 10, 2: WORD_MASK}},
        "The CPU sent 10 from r1 to the screen, which started a new line.",
    ),
    (
        "store r1, [r2]",
        {"registers": {1: 0, 2: WORD_MASK}},
        "The CPU sent 0 from r1 to the screen.",
    ),
    ("jmp 7", {}, "The CPU jumped to address 7."),
    ("call 7", {}, "The CPU pushed the return address, 1, onto the stack and jumped to address 7."),
    (
        "br eq, 5",
        {"flags": ZERO_FLAG},
        (
            'The branch asked "is the zero lamp on?" The answer was yes, so the CPU '
            "jumped to address 5."
        ),
    ),
    (
        "br lt, 5",
        {"flags": NEGATIVE_FLAG},
        (
            'The branch asked "was the first number in the last compare less than the '
            'second?" The answer was yes, so the CPU jumped to address 5.'
        ),
    ),
    (
        "br eq, 5",
        {},
        (
            'The branch asked "is the zero lamp on?" The answer was no, so the CPU '
            "went on to address 1."
        ),
    ),
    (
        "ret",
        {"sp": 200, "memory": {200: 42}},
        "The CPU popped the return address, 42, off the stack and went back there.",
    ),
    ("push r1", {"registers": {1: 9}}, "The CPU pushed 9 from r1 onto the stack, at address 255."),
    ("pop r2", {"sp": 200, "memory": {200: 42}}, "The CPU popped 42 off the stack into r2."),
    ("getsp r1", {}, "The CPU copied the stack pointer, 256, into r1."),
    (
        "setsp r1",
        {"registers": {1: 200}},
        "The CPU set the stack pointer to 200, the number in r1.",
    ),
    ("addi r1, 3", {"registers": {1: 2}}, "The ALU added 3 to 2. The answer, 5, went into r1."),
    (
        "addi r1, -1",
        {"registers": {1: 2}},
        "The ALU took 1 away from 2. The answer, 1, went into r1.",
    ),
    ("halt", {}, "The program finished, so the CPU stopped."),
    ("halt 3", {}, "The CPU stopped with code 3, which means a division by zero."),
    ("halt 9", {}, "The program stopped itself with code 9."),
    (
        "load r1, [r2]",
        {"registers": {2: FAR_ADDRESS}},
        "The CPU stopped: load r1, [r2] tried to use an address outside memory.",
    ),
]


class TestInstructionSentences:
    """Every opcode and every ALU function has a sentence filled with the real numbers."""

    @pytest.mark.parametrize(("source", "setup", "sentence"), CASES, ids=[c[2][:40] for c in CASES])
    def test_each_instruction_says_exactly_what_it_did(
        self, source: str, setup: dict[str, object], sentence: str
    ) -> None:
        """The first instruction of each one-line program gives its pinned sentence."""
        assert _first(f"{source}\n", **setup) == sentence  # pyright: ignore[reportArgumentType]

    def test_the_cases_cover_every_opcode_and_every_alu_function(self) -> None:
        """Between them the cases use all 16 opcodes and all 8 ALU functions."""
        words = [assemble(f"{source}\n", words=WORDS).words[0] for source, _, _ in CASES]
        instructions = [decode(word) for word in words]
        assert {i.opcode for i in instructions} == set(Opcode)
        assert {AluOp(i.fn) for i in instructions if i.opcode == Opcode.ALU} == set(AluOp)

    def test_every_template_is_filled_in(self) -> None:
        """No sentence still shows a `{` placeholder, and the tables cover every kind."""
        assert all("{" not in sentence for _, _, sentence in CASES)
        assert set(OPCODE_TEMPLATES) == set(Opcode)
        assert set(ALU_TEMPLATES) == set(AluOp)

    def test_a_fetch_outside_memory_is_described(self) -> None:
        """A pc outside memory stops the machine at the fetch, and the sentence says where."""
        assert _first("halt\n", pc=FAR_ADDRESS) == (
            "The CPU stopped: it tried to fetch an instruction from address 300, which is "
            "outside memory."
        )

    def test_a_machine_that_had_already_stopped_says_so(self) -> None:
        """Describing a move from a halted start gives the finished note."""
        fast = FastMachine(WORDS)
        fast.load_program(assemble("halt\n", words=WORDS).words)
        fast.step()
        done = fast.state()
        assert describe_move(Depth.INSTRUCTION, done, done, None, None, 0) == FINISHED_NOTE


@given(
    function=st.sampled_from(list(AluOp)),
    values=st.lists(st.integers(0, WORD_MASK), min_size=8, max_size=8),
    rd=st.integers(0, 7),
    ra=st.integers(0, 7),
    rb=st.integers(0, 7),
)
def test_the_answer_in_the_sentence_is_the_real_register(
    function: AluOp, values: list[int], rd: int, ra: int, rb: int
) -> None:
    """For any registers and any ALU function, the answer said is the answer in `rd`."""
    fast = FastMachine(WORDS)
    fast.load_program([encode(Opcode.ALU, rd=rd, ra=ra, rb=rb, fn=function)])
    start = replace(fast.state(), registers=tuple(values))
    fast.load_state(start)
    fast.step()
    after = fast.state()
    sentence = describe_move(Depth.INSTRUCTION, start, after, None, None, 1)
    match = ANSWER.search(sentence)
    assert match is not None, sentence
    assert int(match.group(1)) == after.registers[rd]
    assert int(match.group(2)) == rd
    assert "{" not in sentence


def _sub_cockpit() -> Cockpit:
    """Return a small Cockpit paused just before the `sub` of SUB_PROGRAM."""
    cockpit = Cockpit(BITS)
    cockpit.load_assembly(SUB_PROGRAM)
    cockpit.step_at(Depth.INSTRUCTION)
    cockpit.step_at(Depth.INSTRUCTION)
    return cockpit


def _n(cockpit: Cockpit) -> int:
    """Read the countdown's `n` from the current frame."""
    picture = variables_picture(cockpit.translated, cockpit.computer.instruction_start)
    assert picture is not None
    names = picture["names"]
    assert isinstance(names, list)
    return next(int(v["value"]) for v in names if v["name"] == "n")  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


def _countdown_at_line_5() -> Cockpit:
    """Return the countdown paused just before `n = n - 1`, with n holding 2."""
    cockpit = Cockpit(BITS)
    cockpit.load_pebble(_countdown())
    translated = cockpit.translated
    assert translated is not None
    while not (
        translated.line_at(cockpit.computer.instruction_start.pc) == LINE_N_MINUS_1
        and _n(cockpit) == N_BEFORE
    ):
        cockpit.step_at(Depth.LINE)
    return cockpit


class TestSession:
    """The Cockpit keeps the sentence for the last move, and the picture carries it."""

    def test_the_contract_sentence_for_a_sub(self) -> None:
        """An instruction step over `sub r1, r1, r2` gives the contract's exact sentence."""
        cockpit = _sub_cockpit()
        cockpit.step_at(Depth.INSTRUCTION)
        assert cockpit.happened == SUB_SENTENCE
        assert machine_picture(cockpit)["happened"] == SUB_SENTENCE

    def test_nothing_has_happened_after_a_load(self) -> None:
        """A new Cockpit and a fresh load both have no sentence."""
        cockpit = Cockpit(BITS)
        assert cockpit.happened is None
        cockpit.step_at(Depth.INSTRUCTION)
        assert cockpit.happened is not None
        cockpit.load_assembly(SUB_PROGRAM)
        assert cockpit.happened is None
        assert machine_picture(cockpit)["happened"] is None
        cockpit.load_pebble(_countdown())
        assert cockpit.happened is None

    @pytest.mark.parametrize("depth", list(Depth))
    def test_every_depth_leaves_a_sentence(self, depth: Depth) -> None:
        """A step at any depth that moves the machine sets `happened`."""
        cockpit = Cockpit(BITS)
        cockpit.load_pebble(_countdown())
        cockpit.step_at(depth)
        assert cockpit.happened

    def test_a_step_that_cannot_move_leaves_no_sentence(self) -> None:
        """Nothing happened, so `happened` is None and `note` says why."""
        cockpit = Cockpit(BITS)
        cockpit.load_assembly("halt\n")
        cockpit.step_at(Depth.LINE)
        assert (cockpit.happened, cockpit.note) == (None, NO_LINES_NOTE)
        cockpit.step_at(Depth.INSTRUCTION)
        assert cockpit.happened == "The program finished, so the CPU stopped."
        cockpit.step_at(Depth.PART)
        assert (cockpit.happened, cockpit.note) == (None, FINISHED_NOTE)

    def test_part_steps_say_fetch_then_execute(self) -> None:
        """The fetch beat names the word it read; the execute beat gives the whole sentence."""
        cockpit = _sub_cockpit()
        cockpit.step_at(Depth.PART)
        assert cockpit.happened == (
            "Fetch: the CPU read the word at address 2, which says sub r1, r1, r2."
        )
        cockpit.step_at(Depth.PART)
        assert cockpit.happened == SUB_SENTENCE

    @pytest.mark.parametrize("depth", [Depth.INSTRUCTION, Depth.PART])
    def test_a_deeper_step_started_mid_instruction_describes_all_of_it(self, depth: Depth) -> None:
        """Gate steps, then a bigger step: the sentence is the whole `sub`, from its start."""
        cockpit = _sub_cockpit()
        for _ in range(SOME_GATES):
            cockpit.step_at(Depth.GATE)
        cockpit.step_at(depth)
        if depth == Depth.PART:  # the gates were inside the fetch beat; finish the execute
            cockpit.step_at(Depth.PART)
        assert cockpit.happened == SUB_SENTENCE

    def test_the_countdown_line_sentence(self) -> None:
        """`n = n - 1` ran 10 instructions and changed n from 2 to 1."""
        cockpit = _countdown_at_line_5()
        step = cockpit.step_line(into=False)  # what `step_at(Depth.LINE)` runs
        assert step.instructions == LINE_INSTRUCTIONS
        assert cockpit.happened == "Line 5 ran 10 instructions. n changed from 2 to 1."
        again = _countdown_at_line_5()
        again.step_at(Depth.LINE)
        assert again.happened == cockpit.happened

    def test_a_line_step_started_mid_instruction_says_the_finish_apart(self) -> None:
        """Gate steps into the line's first instruction, then Line: 1 finished, 9 more."""
        cockpit = _countdown_at_line_5()
        for _ in range(SOME_GATES):
            cockpit.step_at(Depth.GATE)
        step = cockpit.step_line(into=False)
        assert step.instructions == LINE_INSTRUCTIONS - 1
        assert cockpit.happened == MID_LINE_SENTENCE

    def test_a_branch_to_the_next_word_does_not_guess_the_answer(self) -> None:
        """With the zero lamp on, `br eq` to the very next word says either answer leads there."""
        cockpit = Cockpit(BITS)
        cockpit.load_assembly(NEXT_ANYWAY)
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.step_at(Depth.INSTRUCTION)
        assert cockpit.computer.state().flags.zero == 1
        cockpit.step_at(Depth.INSTRUCTION)
        assert cockpit.happened == (
            'The branch asked "is the zero lamp on?" Either answer leads to the next '
            "address, so the CPU went on to address 3."
        )

    def test_hidden_variables_never_appear(self) -> None:
        """A `for` loop's made-up `$for_limit_0` never reaches a sentence; `i` does."""
        cockpit = Cockpit(BITS)
        cockpit.load_pebble("let s = 0\nfor i in range(3) {\n    s = s + i\n}\n")
        sentences: list[str] = []
        while not cockpit.computer.state().halted:
            cockpit.step_at(Depth.LINE)
            assert cockpit.happened is not None
            sentences.append(cockpit.happened)
        assert all(HIDDEN not in sentence for sentence in sentences)
        assert any("i changed from" in sentence for sentence in sentences)
        assert "and then the program stopped." in sentences[-1]

    def test_the_tour_gate(self) -> None:
        """The adder gate the Tour reaches is described as an XOR working out a 1."""
        cockpit = Cockpit(BITS)
        cockpit.load_pebble(_countdown())
        for _ in range(TOUR_LINE_STEPS):
            cockpit.step_at(Depth.LINE)
        for _ in range(TOUR_INSTRUCTION_STEPS):
            cockpit.step_at(Depth.INSTRUCTION)
        circuit = cockpit.computer.gate.simulator.circuit
        while True:
            cockpit.step_at(Depth.GATE)
            last = cockpit.last_gate
            if (
                last
                and last.kind == "gate"
                and circuit.scope_of(last.gate).startswith("cpu.alu.adder")
            ):
                break
        assert cockpit.happened == TOUR_GATE_SENTENCE

    def test_a_clock_step_and_an_end_step_give_the_no_gate_notes(self) -> None:
        """A step that moved a clock wire, or ended the instruction, says there is no gate."""
        cockpit = _sub_cockpit()
        kinds: set[str] = set()
        while "end" not in kinds:
            cockpit.step_at(Depth.GATE)
            last = cockpit.last_gate
            assert last is not None
            if last.kind == "edge" and last.kind not in kinds:
                assert cockpit.happened == cockpit.note
                assert cockpit.happened is not None
                assert cockpit.happened.startswith("That step moved the ")
            kinds.add(last.kind)
        assert cockpit.happened == END_NOTE

    def test_many_gate_steps_at_once_count_them(self) -> None:
        """An older gate step with a count says how many it took, then describes the last."""
        cockpit = _sub_cockpit()
        cockpit.step(StepSize.GATE, 3)
        assert cockpit.happened is not None
        assert cockpit.happened.startswith("Took 3 gate steps. ")

    def test_run_says_how_many_instructions_ran(self) -> None:
        """Run counts its instructions, and says apart one the gates finish first."""
        cockpit = Cockpit(BITS)
        cockpit.load_assembly(SUB_PROGRAM)
        cockpit.run(1)
        assert cockpit.happened == "Ran 1 instruction."
        cockpit.step_at(Depth.GATE)
        cockpit.run(1)
        assert cockpit.happened == "Finished the instruction you were in, then ran 1 more."
        cockpit.run(10)
        assert cockpit.happened == "Ran 1 instruction, and then the program stopped."
        cockpit.run(1)
        assert cockpit.happened == "Nothing ran, because the program has already finished."

    def test_rewind_says_where_it_went(self) -> None:
        """Rewind part-way through goes back; at the start there is nothing to undo."""
        cockpit = _sub_cockpit()
        cockpit.rewind()
        assert cockpit.happened == (
            "You were already at the start of this instruction, so nothing changed."
        )
        cockpit.step_at(Depth.GATE)
        cockpit.rewind()
        assert cockpit.happened == "Went back to the start of this instruction."

    def test_play_clears_the_sentence(self) -> None:
        """Play is not one move, so while playing there is no sentence."""
        cockpit = _sub_cockpit()
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.start_playing()
        assert cockpit.happened is None
        cockpit.stop_playing()


class TestHelpers:
    """The small sentence helpers say real numbers in plain words."""

    def test_run_and_rewind_helpers(self) -> None:
        """The run sentence counts in words, with thousands written with a comma."""
        start = Cockpit(BITS).computer.state()
        assert describe_run(1_234, start) == "Ran 1,234 instructions."
        stopped = replace(start, halted=True)
        assert describe_run(0, stopped, finishing=1) == (
            "Finished the instruction you were in, and then the program stopped."
        )
        assert describe_rewind(moved=True) == "Went back to the start of this instruction."

    @pytest.mark.parametrize(
        ("path", "words"),
        [
            ("cpu.alu.adder.bit0.full_adder.half_adder#1.xor", "XOR"),
            ("cpu.registers.r1.bit3.master", "master latch"),
            ("cpu.registers.r1", "register r1"),
            ("ram.word12.bit3", "bit 3 of memory word 12"),
            ("ram.word12", "memory word 12"),
            ("cpu.write_back", "write-back part"),
            ("cpu.something_new", "something new"),
            ("", "circuit"),
        ],
    )
    def test_gate_words(self, path: str, words: str) -> None:
        """The deepest scope name becomes plain words."""
        assert gate_words(path) == words

    @pytest.mark.parametrize(
        ("path", "place"),
        [
            ("cpu.alu.adder.bit0.full_adder.half_adder#1.xor", "an XOR in the ALU"),
            ("ram.and", "an AND in the memory"),
            ("cpu.registers.r1.bit3.master", "a master latch in register r1"),
            ("cpu.registers.read_a.mux_bus", "a chooser in the registers"),
            ("cpu.operand.mux_bus.choose", "the operand chooser"),
            ("cpu.pc", "the program counter"),
            ("ram.word12.bit3", "bit 3 of memory word 12"),
            ("cpu.decode.decoder.not_bus", "a row of NOT gates in the instruction decoder"),
            ("cpu", "the CPU"),
            ("other.thing", "the thing"),
            ("", "the circuit"),
        ],
    )
    def test_gate_place(self, path: str, place: str) -> None:
        """A gate's place names its small part and the big part it sits in."""
        assert gate_place(path) == place

    def test_every_gate_has_plain_words(self) -> None:
        """No gate in the whole machine is named with an underscore or a `#`."""
        circuit = GateMachine(BITS).simulator.circuit
        paths = {circuit.scope_of(gate) for gate in range(circuit.gate_count)}
        names = {gate_words(path) for path in paths} | {gate_place(path) for path in paths}
        assert all("_" not in name and "#" not in name for name in names)

    def test_a_line_step_from_a_routine_says_where_it_started(self) -> None:
        """A line step begun inside a built-in routine, which has no line, says so."""
        cockpit = _countdown_at_line_5()
        translated = cockpit.translated
        assert translated is not None
        start = replace(cockpit.computer.instruction_start, pc=len(translated.frames) - 1)
        assert translated.line_at(start.pc) is None
        after = replace(start, pc=FAR_ADDRESS)  # no frame here or there, so no variables
        assert describe_line(translated, start, after, 1) == (
            "Ran 1 instruction, starting inside a built-in routine (such as the one print "
            "uses), which has no Pebble line."
        )

    def test_a_gate_with_no_path_is_still_described(self) -> None:
        """Without its path a gate step still names the gate and its output."""
        state = Cockpit(BITS).computer.state()
        micro = MicroStep("gate", 7, "", 1, Phase.FETCH)
        assert describe_move(Depth.GATE, state, state, micro, None, 0) == "Gate 7 worked out a 1."


FACTORIAL = next(e["source"] for e in example_programs() if e["name"] == "factorial")
TWO_FUNCTION = (
    "fn add(a, b) {\n    let s = a + b\n    return s\n}\nlet x = 5\nlet y = add(x, 2)\nprint(y)\n"
)


def _line_sentences(source: str, *, into: bool, presses: int) -> list[str | None]:
    """Load `source` and press Step (into or over) at line depth, keeping each sentence."""
    cockpit = Cockpit(BITS)
    cockpit.load_pebble(source)
    said: list[str | None] = []
    for _ in range(presses):
        cockpit.step_line(into=into)
        said.append(cockpit.happened)
    return said


BACK = "and came back to the copy of fact that called it, "


class TestLinesThatChangeFrame:
    """A line step that ends in another frame says where it went, never "changed from"."""

    def test_stepping_into_fact_and_into_new_copies(self) -> None:
        """Into a call from the main program, then into a new copy of the same function."""
        said = _line_sentences(FACTORIAL, into=True, presses=3)
        assert said == [
            "Line 8 ran 21 instructions and went into fact, where n is 5.",
            "Line 3 ran 15 instructions.",
            "Line 6 ran 20 instructions and went into a new copy of fact, where n is 4.",
        ]

    def test_coming_back_out_to_each_caller_and_to_main(self) -> None:
        """Out of a copy of fact to the copy that called it, and at last to the main program."""
        said = _line_sentences(FACTORIAL, into=True, presses=15)[10:]
        assert said == [
            f"Line 4 ran 6 instructions {BACK}where n is 2.",
            f"Line 6 ran 26 instructions {BACK}where n is 3.",
            f"Line 6 ran 33 instructions {BACK}where n is 4.",
            f"Line 6 ran 41 instructions {BACK}where n is 5.",
            "Line 6 ran 55 instructions and came back to the main program.",
        ]

    def test_into_and_out_of_another_function_lists_its_names(self) -> None:
        """A call names every variable it finds there; the way back names the caller's."""
        said = _line_sentences(TWO_FUNCTION, into=True, presses=5)
        assert said == [
            "Line 5 ran 15 instructions. x changed from 0 to 5.",
            "Line 6 ran 15 instructions and went into add, where a is 5, b is 2 and s is 0.",
            "Line 2 ran 10 instructions. s changed from 0 to 7.",
            "Line 3 ran 6 instructions and came back to the main program, where x is 5 and y is 0.",
            "Line 6 ran 6 instructions. y changed from 0 to 7.",
        ]

    def test_stepping_over_a_call_stays_in_the_same_frame(self) -> None:
        """A step over runs the whole call and keeps the plain "changed from" sentence."""
        said = _line_sentences(TWO_FUNCTION, into=False, presses=2)
        assert said == [
            "Line 5 ran 15 instructions. x changed from 0 to 5.",
            "Line 6 ran 37 instructions. y changed from 0 to 7.",
        ]
