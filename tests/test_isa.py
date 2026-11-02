"""Tests for the instruction set: encoding, decoding, conditions and the reference page.

The pinned words were worked out by hand from the field positions, so a wrong
shift in `encode` cannot hide behind a matching wrong shift in `decode`.
"""

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.arithmetic import AluOp
from pycpu.assembler import assemble
from pycpu.fast import alu_model
from pycpu.isa import Condition, Instruction, Opcode, condition_holds, decode, encode

ROOT = Path(__file__).parent.parent
REFERENCE_PAGE = ROOT / "docs" / "reference" / "instruction-set.md"
WORD_MAX = 0xFFFF
SIGN = 0x8000
REGISTER_COUNT = 8
LAST_OPCODE = 15
words = st.integers(min_value=0, max_value=WORD_MAX)
registers = st.integers(min_value=0, max_value=REGISTER_COUNT - 1)


def _signed(value: int) -> int:
    """Read a 16-bit pattern as a signed number."""
    return value - 0x10000 if value & SIGN else value


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        (encode(Opcode.ALU, rd=3, ra=1, rb=2, fn=AluOp.ADD), 0x0650),
        (encode(Opcode.LI, rd=1, imm=5), 0x2205),
        (encode(Opcode.LOAD, rd=1, ra=2, imm=-1), 0x42BF),
        (encode(Opcode.ADDI, rd=1, imm=-1), 0xE2FF),
        (encode(Opcode.BR, rd=Condition.NE, imm=-2), 0x83FE),
        (encode(Opcode.HALT), 0xF000),
        (encode(Opcode.CMP, ra=1, rb=2), 0x1050),
        (encode(Opcode.LHI, rd=1, imm=0x12), 0x3212),
        (encode(Opcode.STORE, rd=1, ra=2, imm=1), 0x5281),
        (encode(Opcode.JMP, imm=100), 0x6064),
        (encode(Opcode.CALL, imm=100), 0x7064),
        (encode(Opcode.RET), 0x9000),
        (encode(Opcode.PUSH, rd=1), 0xA200),
        (encode(Opcode.POP, rd=1), 0xB200),
        (encode(Opcode.GETSP, rd=1), 0xC200),
        (encode(Opcode.SETSP, rd=1), 0xD200),
        (encode(Opcode.HALT, imm=3), 0xF003),
    ],
)
def test_encode_gives_the_pinned_word(word: int, expected: int) -> None:
    """Each instruction encodes to the word worked out by hand."""
    assert word == expected


@pytest.mark.parametrize(
    ("opcode", "field", "value"),
    [
        (Opcode.LI, "imm", 256),
        (Opcode.LI, "imm", -1),
        (Opcode.ADDI, "imm", 128),
        (Opcode.ADDI, "imm", -129),
        (Opcode.LOAD, "imm", 32),
        (Opcode.LOAD, "imm", -33),
        (Opcode.BR, "imm", 256),
        (Opcode.BR, "imm", -257),
        (Opcode.JMP, "imm", 4096),
        (Opcode.JMP, "imm", -1),
        (Opcode.LI, "rd", 8),
        (Opcode.ALU, "ra", 8),
        (Opcode.ALU, "rb", -1),
        (Opcode.ALU, "fn", 8),
    ],
)
def test_encode_refuses_a_value_that_does_not_fit_and_names_the_field(
    opcode: Opcode, field: str, value: int
) -> None:
    """A value too big for its box raises a ValueError naming the box."""
    with pytest.raises(ValueError, match=field):
        encode(opcode, **{field: value})


def test_the_opcodes_are_numbered_zero_to_fifteen() -> None:
    """The opcode numbers are the ones in the table, in order."""
    assert [int(op) for op in Opcode] == list(range(16))
    assert Opcode.ALU == 0
    assert Opcode.HALT == LAST_OPCODE


@given(
    rd=registers,
    ra=registers,
    rb=registers,
    fn=st.integers(min_value=0, max_value=7),
    imm8=st.integers(min_value=0, max_value=255),
    signed8=st.integers(min_value=-128, max_value=127),
    off6=st.integers(min_value=-32, max_value=31),
    off9=st.integers(min_value=-256, max_value=255),
    addr12=st.integers(min_value=0, max_value=4095),
)
def test_decode_gives_back_what_encode_was_given(
    rd: int, ra: int, rb: int, fn: int, imm8: int, signed8: int, off6: int, off9: int, addr12: int
) -> None:
    """For every opcode, the fields it uses survive a round trip."""
    expected = {
        Opcode.ALU: Instruction(Opcode.ALU, rd=rd, ra=ra, rb=rb, fn=fn),
        Opcode.CMP: Instruction(Opcode.CMP, ra=ra, rb=rb),
        Opcode.LI: Instruction(Opcode.LI, rd=rd, imm=imm8),
        Opcode.LHI: Instruction(Opcode.LHI, rd=rd, imm=imm8),
        Opcode.LOAD: Instruction(Opcode.LOAD, rd=rd, ra=ra, imm=off6),
        Opcode.STORE: Instruction(Opcode.STORE, rd=rd, ra=ra, imm=off6),
        Opcode.JMP: Instruction(Opcode.JMP, imm=addr12),
        Opcode.CALL: Instruction(Opcode.CALL, imm=addr12),
        Opcode.BR: Instruction(Opcode.BR, rd=rd, imm=off9),
        Opcode.RET: Instruction(Opcode.RET),
        Opcode.PUSH: Instruction(Opcode.PUSH, rd=rd),
        Opcode.POP: Instruction(Opcode.POP, rd=rd),
        Opcode.GETSP: Instruction(Opcode.GETSP, rd=rd),
        Opcode.SETSP: Instruction(Opcode.SETSP, rd=rd),
        Opcode.ADDI: Instruction(Opcode.ADDI, rd=rd, imm=signed8),
        Opcode.HALT: Instruction(Opcode.HALT, imm=imm8),
    }
    for opcode, instruction in expected.items():
        word = encode(
            opcode,
            rd=instruction.rd,
            ra=instruction.ra,
            rb=instruction.rb,
            fn=instruction.fn,
            imm=instruction.imm,
        )
        assert decode(word) == instruction


@given(words)
def test_decode_accepts_every_word_and_encode_reads_it_back(word: int) -> None:
    """Every 16-bit word is an instruction; re-encoding it only clears unused bits."""
    instruction = decode(word)
    again = encode(
        instruction.opcode,
        rd=instruction.rd,
        ra=instruction.ra,
        rb=instruction.rb,
        fn=instruction.fn,
        imm=instruction.imm,
    )
    assert decode(again) == instruction
    assert again >> 12 == word >> 12


def test_every_opcode_is_in_the_reference_page() -> None:
    """Each opcode name appears in a table row of the reference page."""
    rows = [
        line
        for line in REFERENCE_PAGE.read_text(encoding="utf-8").splitlines()
        if line.startswith("|")
    ]
    for opcode in Opcode:
        pattern = re.compile(rf"^\|\s*{int(opcode)}\s*\|\s*`{opcode.name}`")
        assert any(pattern.match(row) for row in rows), f"{opcode.name} has no row"


@given(words, words)
def test_conditions_agree_with_python_comparisons_after_a_subtraction(a: int, b: int) -> None:
    """After `a - b`, each of the eight conditions matches a plain comparison."""
    _, flags = alu_model(a, b, AluOp.SUB)
    sa, sb = _signed(a), _signed(b)
    expected = {
        Condition.EQ: a == b,
        Condition.NE: a != b,
        Condition.LT: sa < sb,
        Condition.GE: sa >= sb,
        Condition.LE: sa <= sb,
        Condition.GT: sa > sb,
        Condition.LTU: a < b,
        Condition.GEU: a >= b,
    }
    for condition in Condition:
        assert condition_holds(condition, flags) == expected[condition], condition.name


def test_every_worked_example_on_the_reference_page_matches_the_assembler() -> None:
    """Each `instruction` = `0xWORD` example in the table is what `assemble` really gives."""
    text = REFERENCE_PAGE.read_text(encoding="utf-8")
    examples = re.findall(r"`([a-z][^`]*)` = `0x([0-9A-Fa-f]{4})`", text)
    assert len(examples) == len(Opcode)
    for source, word in examples:
        assert assemble(source).words == (int(word, 16),), source
