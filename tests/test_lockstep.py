"""Lockstep: the fast engine and the gate engine must agree after every single step.

Think of two cameras filming the same juggler, one a quick flip-book and one a
slow-motion camera. If the frames ever differ, one camera is lying. These tests
load the same state into both engines, step them side by side, and compare the
whole machine after every instruction. Any difference is a bug in one engine,
and is fixed there; the test is never loosened.
"""

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.assembler import assemble
from pycpu.cpu import GateMachine
from pycpu.fast import FastMachine
from pycpu.isa import OUTPUT_PORT, WORD_MASK, Condition, Opcode, encode
from pycpu.state import HALT_CODE_MAX, REGISTER_COUNT, Flags, MachineState

ADDRESS_BITS = 6
WORDS = 1 << ADDRESS_BITS
MAX_STEPS = 30
MAX_OUTPUT = 3
PROGRAM_MIN = 1
PROGRAM_MAX = 20
BYTE_MAX = 255
SIGNED_BYTE_LIMIT = 128
SELF_MODIFIED_CODE = 7
ORIGINAL_CODE = 2

ALU_NAMES = ("add", "sub", "and", "or", "xor")
REGISTERS = [f"r{n}" for n in range(REGISTER_COUNT)]
CONDITIONS = [c.name.lower() for c in Condition]


@pytest.fixture(scope="module")
def gate() -> GateMachine:
    """Build one small gate computer for the whole module; `load_state` resets it each time."""
    return GateMachine(address_bits=ADDRESS_BITS)


def _word_near(edges: list[int]) -> st.SearchStrategy[int]:
    """Pick any 16-bit word, often one of `edges` or an address inside the small RAM.

    Fully random words are nearly always far outside 64 words of RAM, so a run
    would fault on its first step; leaning towards real addresses and the edges
    keeps the engines busy for longer, while every value can still turn up.
    """
    return st.one_of(
        st.integers(0, WORDS - 1),
        st.sampled_from(edges),
        st.integers(0, WORD_MASK),
    )


EDGES = [0, 1, WORDS - 1, WORDS, WORDS + 1, OUTPUT_PORT - 1, OUTPUT_PORT]

states = st.builds(
    MachineState,
    pc=_word_near(EDGES),
    sp=_word_near(EDGES),
    registers=st.tuples(*[_word_near(EDGES)] * REGISTER_COUNT),
    flags=st.builds(Flags, *[st.integers(0, 1)] * len(Flags._fields)),
    memory=st.tuples(*[st.integers(0, WORD_MASK)] * WORDS),
    halted=st.booleans(),
    halt_code=st.integers(0, HALT_CODE_MAX),
    output=st.lists(st.integers(0, WORD_MASK), max_size=MAX_OUTPUT).map(tuple),
)


def _run_side_by_side(gate: GateMachine, start: MachineState) -> MachineState:
    """Load `start` into both engines, step both, and fail at the first step they differ.

    Return the final state, so a caller can check where the run ended.
    """
    fast = FastMachine(WORDS)
    fast.load_state(start)
    gate.load_state(start)
    assert gate.state() == fast.state()
    for step in range(MAX_STEPS):
        fast_moved = fast.step()
        gate_moved = gate.step()
        assert gate_moved == fast_moved, f"step {step}: one engine had already halted"
        assert gate.state() == fast.state(), f"the engines differ after step {step + 1}"
        if not fast_moved:
            break
    return fast.state()


@settings(max_examples=200, deadline=None)
@given(start=states)
def test_both_engines_agree_from_any_state(gate: GateMachine, start: MachineState) -> None:
    """From any loadable state, halted or not, both engines stay equal; a halted one stays put."""
    _run_side_by_side(gate, start)


# Pieces a line of assembly is made from, each drawn fresh every time it appears.
PIECES: dict[str, st.SearchStrategy[str]] = {
    "r": st.sampled_from(REGISTERS),
    "alu": st.sampled_from(ALU_NAMES),
    "shift": st.sampled_from(("shl", "shr")),
    "cond": st.sampled_from(CONDITIONS),
    "byte": st.integers(0, BYTE_MAX).map(str),
    "signed": st.integers(-SIGNED_BYTE_LIMIT, SIGNED_BYTE_LIMIT - 1).map(str),
    "offset": st.integers(0, WORDS // 2 - 1).map(str),
    "address": st.integers(0, WORDS - 1).map(str),
    "code": st.integers(0, HALT_CODE_MAX).map(str),
}

# One template for every kind of instruction; each `<name>` is filled from PIECES.
TEMPLATES = (
    "<alu> <r>, <r>, <r>",
    "<shift> <r>, <r>",
    "mov <r>, <r>",
    "cmp <r>, <r>",
    "li <r>, <byte>",
    "lhi <r>, <byte>",
    "addi <r>, <signed>",
    "load <r>, [<r>+<offset>]",
    "store <r>, [<r>+<offset>]",
    "jmp <address>",
    "call <address>",
    "br <cond>, <address>",
    "ret",
    "push <r>",
    "pop <r>",
    "getsp <r>",
    "setsp <r>",
    "halt <code>",
)


@st.composite
def programs(draw: st.DrawFn) -> str:
    """Build a short program from random real instructions, as assembly text."""
    chosen = draw(st.lists(st.sampled_from(TEMPLATES), min_size=PROGRAM_MIN, max_size=PROGRAM_MAX))
    return "\n".join(
        re.sub(r"<(\w+)>", lambda piece: draw(PIECES[piece[1]]), template) for template in chosen
    )


@settings(max_examples=200, deadline=None)
@given(source=programs())
def test_both_engines_agree_on_assembled_programs(gate: GateMachine, source: str) -> None:
    """A random program written in assembly runs the same, step for step, on both engines."""
    fast = FastMachine(WORDS)
    fast.load_program(assemble(source, words=WORDS).words)
    _run_side_by_side(gate, fast.state())


def test_self_modifying_code_fetches_the_new_word(gate: GateMachine) -> None:
    """A STORE that overwrites the very next instruction makes both engines obey the new word."""
    halt_seven = encode(Opcode.HALT, imm=SELF_MODIFIED_CODE)
    source = f"""
        set r1, {halt_seven}
        set r2, next
        store r1, [r2]      ; write `halt 7` over the instruction below
    next:
        halt {ORIGINAL_CODE}
    """
    fast = FastMachine(WORDS)
    fast.load_program(assemble(source, words=WORDS).words)
    end = _run_side_by_side(gate, fast.state())
    assert end.halted
    assert end.halt_code == SELF_MODIFIED_CODE
