"""Check the multiply and divide routines by running them on the fast engine.

Each test builds a tiny caller (`call` the routine, then `halt`), appends the runtime
assembly, loads the numbers into registers and runs the real machine.
"""

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.assembler import assemble
from pycpu.fast import FastMachine
from pycpu.state import WORD_MASK, MachineState, program_state
from pycpu.translator import RUNTIME, RUNTIME_STACK_WORDS

RAM = 256
STEP_LIMIT = 5000
SIGN_BIT = 0x8000
INT_MIN = -0x8000
INT_MAX = 0x7FFF
R0, R1, R2, R7 = 0, 1, 2, 7


def _program(routine: str) -> tuple[int, ...]:
    """Assemble a caller of `routine` followed by the runtime."""
    return assemble(f"call {routine}\nhalt\n{RUNTIME}", words=RAM).words


MUL = _program("__mul")
DIVMOD = _program("__divmod")


def _start(words: tuple[int, ...], a: int, b: int) -> MachineState:
    """Return a powered-on state with `a` in r1, `b` in r2 and r7 set to a marker."""
    state = program_state(words, RAM)
    registers = list(state.registers)
    registers[R1] = a & WORD_MASK
    registers[R2] = b & WORD_MASK
    registers[R7] = 0x1234
    return replace(state, registers=tuple(registers))


def _run(words: tuple[int, ...], a: int, b: int) -> tuple[MachineState, int]:
    """Run to the halt; return the final state and the deepest stack use in words."""
    machine = FastMachine(words=RAM)
    machine.load_state(_start(words, a, b))
    deepest = 0
    while machine.step():
        deepest = max(deepest, RAM - machine.state().sp)
        if machine.state().halted:
            break
    return machine.state(), deepest


def _signed(value: int) -> int:
    """Read a 16-bit word as a signed number."""
    return value - (1 << 16) if value & SIGN_BIT else value


def _wrap(value: int) -> int:
    """Wrap any whole number to a signed 16-bit one."""
    return _signed(value & WORD_MASK)


def multiply(a: int, b: int) -> int:
    """Return the unsigned 16-bit product the machine computes."""
    final, _ = _run(MUL, a, b)
    assert final.halted
    assert final.halt_code == 0
    return final.registers[R1]


def divmod_(a: int, b: int) -> tuple[int, int]:
    """Return the signed (quotient, remainder) the machine computes."""
    final, _ = _run(DIVMOD, a, b)
    assert final.halted
    assert final.halt_code == 0
    return _signed(final.registers[R1]), _signed(final.registers[R2])


@settings(max_examples=500)
@given(st.integers(0, WORD_MASK), st.integers(0, WORD_MASK))
def test_multiply_matches_python_for_any_two_words(a: int, b: int) -> None:
    """Multiplying any two 16-bit words gives the product wrapped to 16 bits."""
    assert multiply(a, b) == (a * b) & WORD_MASK


def test_multiply_pinned_values() -> None:
    """300 times 300 wraps to 24464, and 65535 times 65535 wraps to 1."""
    assert multiply(300, 300) == 24464  # noqa: PLR2004
    assert multiply(0xFFFF, 0xFFFF) == 1


@settings(max_examples=500)
@given(st.integers(INT_MIN, INT_MAX), st.integers(INT_MIN, INT_MAX).filter(bool))
def test_divmod_matches_python_floor_division(a: int, b: int) -> None:
    """Quotient and remainder match Python's // and %, wrapped to 16 bits."""
    assert divmod_(a, b) == (_wrap(a // b), _wrap(a % b))


def test_divmod_pinned_values() -> None:
    """Negative numbers round down: the worked examples from the docs."""
    assert divmod_(-7, 2) == (-4, 1)
    assert divmod_(7, -2) == (-4, -1)
    assert divmod_(-7, -2) == (3, -1)
    assert divmod_(7, 2) == (3, 1)
    assert divmod_(-32768, -1) == (-32768, 0)
    assert divmod_(-32768, 1) == (-32768, 0)
    assert divmod_(32767, -32768) == (-1, -1)
    assert divmod_(-32768, -32768) == (1, 0)


def test_routines_keep_r0_and_r7() -> None:
    """r0 stays 0 and r7 (the frame pointer) is untouched by both routines."""
    for words, a, b in [(MUL, 1234, 567), (DIVMOD, -1234, 57), (DIVMOD, 99, -7)]:
        final, _ = _run(words, a, b)
        assert final.registers[R0] == 0
        assert final.registers[R7] == 0x1234  # noqa: PLR2004


def test_routines_leave_the_stack_as_they_found_it() -> None:
    """After a routine returns, sp is back where it was before the call."""
    for words in (MUL, DIVMOD):
        final, _ = _run(words, -9, 4)
        assert final.sp == RAM


def test_runtime_stack_words_covers_the_deepest_use() -> None:
    """The constant is at least the deepest stack measured, and exactly it for divmod."""
    deepest = max(
        _run(words, a, b)[1]
        for words in (MUL, DIVMOD)
        for a, b in [(1, 1), (-7, 2), (7, -2), (-32768, -1), (0, 5)]
    )
    assert deepest <= RUNTIME_STACK_WORDS
    assert deepest == RUNTIME_STACK_WORDS


def test_runtime_labels_all_start_with_two_underscores() -> None:
    """Runtime labels never clash with generated ones."""
    labels = assemble(f"halt\n{RUNTIME}", words=RAM).labels
    assert labels
    assert all(name.startswith("__") for name in labels)
