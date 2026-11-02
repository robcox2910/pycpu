"""Tests for the assembler: words in, numbers out, and friendly errors for mistakes.

The expected words were worked out by hand from the field positions in `isa.py`, so a
bug in the assembler cannot hide behind the same bug in `encode`.
"""

import contextlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.arithmetic import AluOp
from pycpu.assembler import AssemblyError, Program, assemble, disassemble
from pycpu.fast import FastMachine
from pycpu.isa import Condition, Instruction, Opcode, decode, encode
from pycpu.memory import RAM_WORDS

COUNTDOWN = "li r1, 3\nloop: addi r1, -1\nbr ne, loop\nhalt\n"
HELLO = """
    set r1, msg
    set r2, 0xFFFF
next:
    load r3, [r1]
    cmp r3, r0
    br eq, done
    store r3, [r2]
    addi r1, 1
    jmp next
done:
    halt
msg:
    .string "Hi"
"""
RUN_LIMIT = 10_000
HELLO_MESSAGE_ADDRESS = 11
MAX_ADDRESS = 300
MNEMONICS = [
    "add", "sub", "and", "or", "xor", "shl", "shr", "mov", "cmp", "li", "lhi", "load",
    "store", "jmp", "call", "br", "ret", "push", "pop", "getsp", "setsp", "addi", "halt",
    "set", ".word", ".string",
]  # fmt: skip
PIECES = [
    "r1",
    "r8",
    "[r2+3]",
    "[r2",
    "eq",
    "loop",
    "loop:",
    "0x1F",
    "-5",
    "'A'",
    '"hi"',
    '"',
    ",",
    ";",
    " ",
]


def test_the_countdown_assembles_to_the_words_worked_out_by_hand() -> None:
    """The countdown from the machine code page becomes four known words."""
    program = assemble(COUNTDOWN)
    assert program.words == (0x2203, 0xE2FF, 0x83FE, 0xF000)
    assert program.labels == {"loop": 1}
    assert program.lines == (1, 2, 3, 4)


def test_the_hello_program_prints_hi_when_run() -> None:
    """The hello program lays out as expected, and running it prints Hi."""
    program = assemble(HELLO)
    assert program.labels["msg"] == HELLO_MESSAGE_ADDRESS
    assert program.words[HELLO_MESSAGE_ADDRESS:] == (ord("H"), ord("i"), 0)
    machine = FastMachine(words=64)
    machine.load_program(program.words)
    machine.run(RUN_LIMIT)
    assert machine.state().output_text == "Hi"
    assert machine.state().halt_code == 0


def test_set_is_two_words_and_each_line_remembers_its_source_line() -> None:
    """`set` is a `li` then a `lhi`, and both words point at their one source line."""
    program = assemble("\n; a comment\nset r4, 0x1234\nhalt")
    assert program.words == (
        encode(Opcode.LI, rd=4, imm=0x34),
        encode(Opcode.LHI, rd=4, imm=0x12),
        0xF000,
    )
    assert program.lines == (3, 3, 4)


def test_every_instruction_form_assembles_to_the_hand_checked_word() -> None:
    """Each mnemonic, with its odd operand shapes, gives the word worked out by hand."""
    cases = {
        "add r3, r1, r2": 0x0650,
        "shl r3, r1": encode(Opcode.ALU, rd=3, ra=1, fn=AluOp.SHL),
        "shr r3, r1": encode(Opcode.ALU, rd=3, ra=1, fn=AluOp.SHR),
        "mov r3, r2": encode(Opcode.ALU, rd=3, rb=2, fn=AluOp.PASS_B),
        "cmp r1, r2": 0x1050,
        "lhi r1, 0x12": 0x3212,
        "load r1, [r2]": encode(Opcode.LOAD, rd=1, ra=2),
        "load r1, [r2-1]": 0x42BF,
        "store r1, [r2+1]": 0x5281,
        "jmp 100": 0x6064,
        "call 100": 0x7064,
        "ret": 0x9000,
        "push r1": 0xA200,
        "pop r1": 0xB200,
        "getsp r1": 0xC200,
        "setsp r1": 0xD200,
        "halt": 0xF000,
        "halt 3": 0xF003,
    }
    for source, word in cases.items():
        assert assemble(source).words == (word,), source


def test_case_spaces_and_number_styles_do_not_matter() -> None:
    """`ADDI R1, -1`, spaces inside brackets, hex and character literals all work."""
    assert assemble("ADDI R1, -1").words == (0xE2FF,)
    assert assemble("  load   r1 ,[ r2 - 1 ]  ").words == (0x42BF,)
    assert assemble("li r1, 'A'").words == assemble("li r1, 65").words
    assert assemble("li r1, 0x1f").words == assemble("li r1, 31").words
    assert assemble("li r1, ';' ; a comment").words == assemble("li r1, 59").words
    assert assemble("li r1, ','").words == assemble("li r1, 44").words


def test_directives_make_raw_words() -> None:
    """`.word` takes numbers and labels, and `.string` adds a 0 and understands escapes."""
    program = assemble('start: .word 7, start\n.word -1\n.string "a;\\n"\n.string ""')
    assert program.words == (7, 0, 0xFFFF, ord("a"), ord(";"), 10, 0, 0)


def test_a_label_can_share_a_line_or_stand_alone_and_may_be_forward() -> None:
    """Labels work before an instruction, alone, and referenced from further up."""
    program = assemble("jmp end\nstart: end2: halt\nend:\nhalt")
    assert program.labels == {"start": 1, "end2": 1, "end": 2}
    assert program.words[0] == encode(Opcode.JMP, imm=2)


def test_a_backward_and_a_forward_branch_get_the_right_offsets() -> None:
    """The offset is the target minus the address after the branch."""
    program = assemble("br eq, 3\nhalt\nhalt\nhalt\nbr gt, 0")
    assert decode(program.words[0]) == Instruction(Opcode.BR, rd=Condition.EQ, imm=2)
    assert decode(program.words[4]) == Instruction(Opcode.BR, rd=Condition.GT, imm=-5)


def test_a_branch_at_the_edge_of_its_range_works_and_one_more_is_refused() -> None:
    """A branch reaches -256 to 255 words from the next address, no further."""
    padding = "halt\n" * 255
    assert decode(assemble(f"br eq, far\n{padding}far: halt").words[0]).imm == 255  # noqa: PLR2004
    with pytest.raises(AssemblyError, match="too far for br: branch over a jmp instead"):
        assemble(f"br eq, far\n{padding}halt\nfar: halt")


@pytest.mark.parametrize(
    ("source", "line", "fragment"),
    [
        ("halt\nfrobnicate r1", 2, "frobnicate"),
        ("halt\n\nli r8, 1", 3, "r8"),
        ("li r1, 256", 1, "256"),
        ("addi r1, 128", 1, "128"),
        ("load r1, [r2+32]", 1, "32"),
        ("a: halt\na: halt", 2, "already"),
        ("jmp nowhere", 1, "nowhere"),
        ("li r1", 1, "li"),
        ("li r1, 2, 3", 1, "li"),
        ("halt\nli r1,", 2, "li"),
        ('.string "oops', 1, "quote"),
        ("jmp 5000", 1, "5000"),
        ("br maybe, 0", 1, "maybe"),
        ("li r1, banana", 1, "banana"),
        ("load r1, r2", 1, "["),
        ("1abc: halt", 1, "1abc"),
        ("r1: halt", 1, "r1"),
    ],
)
def test_mistakes_give_a_friendly_error_naming_the_line(
    source: str, line: int, fragment: str
) -> None:
    """Each kind of mistake raises an AssemblyError starting `line N:` and naming the problem."""
    with pytest.raises(AssemblyError) as caught:
        assemble(source)
    assert caught.value.line == line
    assert str(caught.value).startswith(f"line {line}: ")
    assert fragment in str(caught.value)
    assert isinstance(caught.value, ValueError)


def test_a_program_longer_than_memory_is_refused_at_the_line_that_overflows() -> None:
    """The error names the line where the program ran out of room."""
    with pytest.raises(AssemblyError) as caught:
        assemble("halt\nhalt\nhalt\nhalt", words=3)
    assert caught.value.line == 4  # noqa: PLR2004
    assert "3" in str(caught.value)
    assert len(assemble("halt\nhalt\nhalt", words=3).words) == 3  # noqa: PLR2004


def test_the_default_memory_size_is_the_ram_size() -> None:
    """Without `words`, a program of exactly RAM_WORDS words fits and one more does not."""
    assert isinstance(assemble(".word 0\n" * RAM_WORDS), Program)
    with pytest.raises(AssemblyError):
        assemble(".word 0\n" * (RAM_WORDS + 1))


def test_disassemble_prints_the_canonical_text() -> None:
    """Disassembly uses lower case, absolute branch targets and tidy memory operands."""
    assert disassemble(0x2203, 0) == "li r1, 3"
    assert disassemble(0x83FE, 3) == "br ne, 2"
    assert disassemble(0x42BF, 0) == "load r1, [r2-1]"
    assert disassemble(0x5281, 0) == "store r1, [r2+1]"
    assert disassemble(encode(Opcode.LOAD, rd=1, ra=2), 0) == "load r1, [r2]"
    assert disassemble(encode(Opcode.ALU, rd=3, ra=1, fn=AluOp.SHL), 0) == "shl r3, r1"
    assert disassemble(encode(Opcode.ALU, rd=3, rb=2, fn=AluOp.PASS_B), 0) == "mov r3, r2"
    assert disassemble(0xF000, 0) == "halt"
    assert disassemble(0xF003, 0) == "halt 3"
    assert disassemble(0x9000, 0) == "ret"


@given(st.text(max_size=200))
def test_random_text_gives_a_program_or_an_assembly_error_and_nothing_else(text: str) -> None:
    """No text at all can make the assembler raise anything but AssemblyError."""
    with contextlib.suppress(AssemblyError):
        assert isinstance(assemble(text, words=64), Program)


@given(
    st.lists(
        st.tuples(
            st.sampled_from(MNEMONICS),
            st.lists(st.sampled_from(PIECES), max_size=4),
            st.booleans(),
        ),
        max_size=8,
    )
)
def test_random_lines_built_from_real_mnemonics_and_junk_never_crash(
    lines: list[tuple[str, list[str], bool]],
) -> None:
    """Lines that look almost right are the likeliest to find a crash, so try many."""
    text = "\n".join(
        name + " " + (", " if comma else " ").join(pieces) for name, pieces, comma in lines
    )
    with contextlib.suppress(AssemblyError):
        assemble(text, words=64)


def _instructions() -> st.SearchStrategy[Instruction]:
    """Build every valid instruction, leaving unused fields 0 as the assembler writes them."""
    reg = st.integers(min_value=0, max_value=7)
    imm8 = st.integers(min_value=0, max_value=255)
    alu = st.one_of(
        st.builds(
            Instruction,
            st.just(Opcode.ALU),
            reg,
            reg,
            reg,
            st.sampled_from([AluOp.ADD, AluOp.SUB, AluOp.AND, AluOp.OR, AluOp.XOR]),
        ),
        st.builds(
            Instruction,
            st.just(Opcode.ALU),
            reg,
            reg,
            st.just(0),
            st.sampled_from([AluOp.SHL, AluOp.SHR]),
        ),
        st.builds(Instruction, st.just(Opcode.ALU), reg, st.just(0), reg, st.just(AluOp.PASS_B)),
    )
    off6 = st.integers(min_value=-32, max_value=31)
    return st.one_of(
        alu,
        st.builds(Instruction, st.just(Opcode.CMP), ra=reg, rb=reg),
        st.builds(Instruction, st.sampled_from([Opcode.LI, Opcode.LHI]), rd=reg, imm=imm8),
        st.builds(
            Instruction, st.sampled_from([Opcode.LOAD, Opcode.STORE]), rd=reg, ra=reg, imm=off6
        ),
        st.builds(
            Instruction,
            st.sampled_from([Opcode.JMP, Opcode.CALL]),
            imm=st.integers(min_value=0, max_value=4095),
        ),
        st.builds(
            Instruction,
            st.just(Opcode.BR),
            rd=st.sampled_from(list(Condition)),
            imm=st.integers(min_value=-256, max_value=255),
        ),
        st.just(Instruction(Opcode.RET)),
        st.builds(
            Instruction,
            st.sampled_from([Opcode.PUSH, Opcode.POP, Opcode.GETSP, Opcode.SETSP]),
            rd=reg,
        ),
        st.builds(
            Instruction,
            st.just(Opcode.ADDI),
            rd=reg,
            imm=st.integers(min_value=-128, max_value=127),
        ),
        st.builds(Instruction, st.just(Opcode.HALT), imm=imm8),
    )


@given(_instructions(), st.integers(min_value=0, max_value=MAX_ADDRESS))
def test_disassembly_assembles_back_to_the_same_word_at_the_same_address(
    instruction: Instruction, address: int
) -> None:
    """Printing a word and assembling the text at the same address gives the word back."""
    word = encode(
        instruction.opcode,
        rd=instruction.rd,
        ra=instruction.ra,
        rb=instruction.rb,
        fn=instruction.fn,
        imm=instruction.imm,
    )
    text = disassemble(word, address)
    program = assemble(".word 0\n" * address + text)
    assert program.words[address] == word, text
