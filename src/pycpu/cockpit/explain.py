"""What just happened: one plain sentence about the last move, written from the real change.

Think of a radio commentator at a football match. You cannot see the pitch, so after
every play they tell you what happened, with the real names and the real score, and
never what might have happened. This module is the Cockpit's commentator. It is given
two snapshots of the machine, `start` (the state at the start of the instruction, before
the move) and `after`, and fills a set phrase with the numbers it reads from them: the
numbers going into an instruction come from `start`'s registers, and the answer comes
from `after`. Instructions are taken apart by `isa.decode`, never by hand.

It also holds `Depth`, how closely the glass looks, because every sentence is shaped by
the depth of the move it describes.
"""

import re
from enum import StrEnum

from pycpu.arithmetic import AluOp
from pycpu.assembler import disassemble
from pycpu.cpu import MicroStep
from pycpu.isa import OUTPUT_PORT, Condition, Fault, Instruction, Opcode, decode
from pycpu.memory import WORD_BITS
from pycpu.state import BYTE_MASK, WORD_MASK, MachineState
from pycpu.translator import FRAME_POINTER, TranslatedProgram

FINISHED_NOTE = "The program has finished, so there is no next line."
MAIN_CLOCK = "clk"  # the CPU's main clock wire, named plainly in notes
NO_GATE_ENDING = "so there is no gate to show."  # the page looks for these words
END_NOTE = f"That step finished the instruction, not a gate, {NO_GATE_ENDING}"

NEW_LINE = 10  # the character code that starts a new line on the screen
FIRST_PRINTABLE = 32  # a space: the first character code the screen shows as a letter
LAST_PRINTABLE = 126  # "~": the last one
_SIGN_BIT = 1 << (WORD_BITS - 1)

# One sentence for each ALU function: `a` and `b` are the numbers going in, from `start`.
ALU_TEMPLATES: dict[AluOp, str] = {
    AluOp.ADD: "The ALU added {a} and {b}.",
    AluOp.SUB: "The ALU took {b} away from {a}.",
    AluOp.AND: "The ALU kept only the bits that are 1 in both {a} and {b}.",
    AluOp.OR: "The ALU kept the bits that are 1 in {a} or in {b}.",
    AluOp.XOR: "The ALU kept the bits that are 1 in {a} or in {b}, but not in both.",
    AluOp.SHL: "The ALU slid every bit of {a} one place to the left.",
    AluOp.SHR: "The ALU slid every bit of {a} one place to the right.",
    AluOp.PASS_B: "The ALU let {b} straight through.",
}

# One sentence for each opcode. Numbers going in come from `start`; `answer`, `pc`, `sp`
# and `top` (the word on top of the stack) are read from `after`.
OPCODE_TEMPLATES: dict[Opcode, str] = {
    Opcode.ALU: "{alu} The answer, {answer}, went into r{rd}.",
    Opcode.CMP: (
        "The ALU compared {a} with {b} by taking {b} away from {a}. It kept no answer, "
        "only the flag lamps: zero {zero}, negative {negative}, carry {carry}, "
        "overflow {overflow}."
    ),
    Opcode.LI: "The CPU put the number {answer} into r{rd}.",
    Opcode.LHI: "The CPU put {imm} into the top half of r{rd}, so r{rd} is now {answer}.",
    Opcode.LOAD: "The CPU copied {answer} from memory address {address} into r{rd}.",
    Opcode.STORE: "The CPU copied {stored} from r{rd} into memory address {address}.",
    Opcode.JMP: "The CPU jumped to address {pc}.",
    Opcode.CALL: (
        "The CPU pushed the return address, {top}, onto the stack and jumped to address {pc}."
    ),
    Opcode.BR: 'The branch asked "{question}?" {outcome}',
    Opcode.RET: "The CPU popped the return address, {pc}, off the stack and went back there.",
    Opcode.PUSH: "The CPU pushed {top} from r{rd} onto the stack, at address {sp}.",
    Opcode.POP: "The CPU popped {answer} off the stack into r{rd}.",
    Opcode.GETSP: "The CPU copied the stack pointer, {answer}, into r{rd}.",
    Opcode.SETSP: "The CPU set the stack pointer to {sp}, the number in r{rd}.",
    Opcode.ADDI: "The ALU added {imm} to {value}. The answer, {answer}, went into r{rd}.",
    Opcode.HALT: "The program finished, so the CPU stopped.",
}

# The few instructions whose sentence depends on what really happened.
ADDI_DOWN_TEMPLATE = "The ALU took {down} away from {value}. The answer, {answer}, went into r{rd}."
SCREEN_TEMPLATE = "The CPU sent {stored} from r{rd} to the screen{shown}."
TAKEN_TEMPLATE = "The answer was yes, so the CPU jumped to address {pc}."
NOT_TAKEN_TEMPLATE = "The answer was no, so the CPU went on to address {pc}."
HALT_CODE_TEMPLATE = "The CPU stopped with code {code}, which means {meaning}."
OWN_CODE_TEMPLATE = "The program stopped itself with code {code}."
FAULT_TEMPLATE = "The CPU stopped: {text} tried to use an address outside memory."
FETCH_FAULT_TEMPLATE = (
    "The CPU stopped: it tried to fetch an instruction from address {pc}, which is outside memory."
)
FETCH_TEMPLATE = "Fetch: the CPU read the word at address {pc}, which says {text}."
GATE_TEMPLATE = "Gate {gate} in the {words} worked out a {value}."
BARE_GATE_TEMPLATE = "Gate {gate} worked out a {value}."
LINE_TEMPLATE = "Line {line} ran {count}."
ROUTINE_TEMPLATE = (
    "Ran {count}, starting inside a built-in routine (such as the one print uses), "
    "which has no Pebble line."
)
CHANGED_TEMPLATE = " {name} changed from {old} to {new}."
STOPPED_ENDING = ", and then the program stopped."
SCREEN_SHOWED_TEMPLATE = ' The screen showed "{text}".'
GATE_STEPS_TEMPLATE = "Took {count:,} gate steps. {last}"
RUN_TEMPLATE = "Ran {count}."
NOTHING_RAN = "Nothing ran, because the program has already finished."
REWOUND = "Went back to the start of this instruction."
ALREADY_AT_START = "You were already at the start of this instruction, so nothing changed."

# The question each branch asks the flag lamps. `eq` and `ne` only look at the zero lamp,
# so they are asked that way: they often follow an `addi`, not a compare. The others
# follow a compare in Pebble's code, so they ask about its two numbers.
BRANCH_QUESTIONS: dict[Condition, str] = {
    Condition.EQ: "is the zero lamp on",
    Condition.NE: "is the zero lamp off",
    Condition.LT: "was the first number less than the second",
    Condition.GE: "was the first number at least the second",
    Condition.LE: "was the first number at most the second",
    Condition.GT: "was the first number more than the second",
    Condition.LTU: "was the first number less than the second, counting without signs",
    Condition.GEU: "was the first number at least the second, counting without signs",
}

# What each fault code means, for a `halt` that uses one.
FAULT_MEANINGS: dict[Fault, str] = {
    Fault.BAD_ADDRESS: "an address outside memory",
    Fault.STACK_OVERFLOW: "the stack ran out of room",
    Fault.DIVIDE_BY_ZERO: "a division by zero",
}

# Plain words for the last name in a gate's scope path. Numbered names are handled apart.
GATE_PART_WORDS: dict[str, str] = {
    "and": "AND",
    "or": "OR",
    "xor": "XOR",
    "not_bus": "row of NOT gates",
    "mux_bus": "chooser",
    "choose": "chooser",
    "master": "master latch",
    "slave": "slave latch",
    "condition": "branch checker",
    "control": "control unit",
    "fault": "fault checker",
    "flags": "flag register",
    "halt_code": "halt-code register",
    "halted": "halted register",
    "ir": "instruction register",
    "is_zero": "zero checker",
    "next_pc": "next-instruction part",
    "next_sp": "stack pointer part",
    "overflow": "overflow checker",
    "pc": "program counter",
    "phase": "phase register",
    "ram_data": "memory data chooser",
    "ram_wires": "memory wires",
    "sp": "stack pointer",
    "write_back": "write-back part",
}
_COPY_NUMBER = re.compile(r"#\d+$")  # `half_adder#1` is the second half adder in its part
_NUMBERED = re.compile(r"^(bit|word|r)(\d+)$")


class Depth(StrEnum):
    """How closely the glass looks, and so how big one press of Step is.

    Attributes:
        LINE: One line of Pebble.
        INSTRUCTION: One machine instruction.
        PART: One clock beat of the CPU part that does the instruction's work.
        GATE: One NAND gate.

    """

    LINE = "line"
    INSTRUCTION = "instruction"
    PART = "part"
    GATE = "gate"


def count_instructions(count: int) -> str:
    """Say `count` instructions in words, with "instruction" singular for 1."""
    return "1 instruction" if count == 1 else f"{count:,} instructions"


def no_gate_note(micro: MicroStep) -> str:
    """Say why a gate step whose last movement was not a gate has no gate to show."""
    if micro.kind == "edge":
        # The main clock is simply "the clock"; "the clk clock wire" would say it twice.
        wire = "the clock wire" if micro.wire == MAIN_CLOCK else f"the {micro.wire} clock wire"
        return f"That step moved {wire}, not a gate, {NO_GATE_ENDING}"
    return END_NOTE


def gate_words(path: str) -> str:
    """Turn a gate's scope path into plain words for the part it lives in.

    Only the last name counts, without its copy number: the gate in
    `cpu.alu.adder.bit0.full_adder.half_adder#1.xor` lives in an "XOR". A register
    or memory word keeps its number, and a memory bit says which word it belongs to.

    Args:
        path: A dotted scope path from `Circuit.scope_of`; `""` for the top level.

    """
    parent, _, last = path.rpartition(".")
    last = _COPY_NUMBER.sub("", last)
    if not last:
        return "circuit"
    numbered = _NUMBERED.match(last)
    if numbered is not None:
        kind, number = numbered.groups()
        if kind == "r":
            return f"register r{number}"
        if kind == "word":
            return f"memory word {number}"
        return f"bit {number} of {gate_words(parent)}"
    return GATE_PART_WORDS.get(last, last.replace("_", " "))


def _signed(word: int) -> int:
    """Read a 16-bit word as a signed number, the way Pebble's code means it (65535 is -1)."""
    return word - (_SIGN_BIT << 1) if word & _SIGN_BIT else word


def _screen_words(word: int) -> str:
    """Say what the screen did with a word sent to it, or nothing for a code it cannot show."""
    code = word & BYTE_MASK
    if code == NEW_LINE:
        return ", which started a new line"
    if FIRST_PRINTABLE <= code <= LAST_PRINTABLE:
        return f', which showed "{chr(code)}"'
    return ""


def _halt_sentence(code: int) -> str:
    """Say why a `halt` stopped the machine, from its code."""
    if code == 0:
        return OPCODE_TEMPLATES[Opcode.HALT]
    if code in Fault:
        return HALT_CODE_TEMPLATE.format(code=code, meaning=FAULT_MEANINGS[Fault(code)])
    return OWN_CODE_TEMPLATE.format(code=code)


def describe_instruction(start: MachineState, after: MachineState) -> str:
    """Say what the instruction that started in `start` did, ending in `after`.

    The word is read from `start`'s memory at `start.pc` and taken apart by `decode`.
    The numbers going in are `start`'s registers; the answer and every other result
    are read from `after`, so the sentence says what really happened.

    Args:
        start: The state at the start of the instruction.
        after: The state once the instruction has finished.

    """
    if start.pc >= len(start.memory):
        return FETCH_FAULT_TEMPLATE.format(pc=start.pc)
    word = start.memory[start.pc]
    i: Instruction = decode(word)
    if i.opcode == Opcode.HALT:
        return _halt_sentence(after.halt_code)
    if after.halted:
        return FAULT_TEMPLATE.format(text=disassemble(word, start.pc))
    return _fill(i, start, after)


def _fill(i: Instruction, start: MachineState, after: MachineState) -> str:
    """Fill the opcode's template for an instruction that finished normally."""
    a, b, value = start.registers[i.ra], start.registers[i.rb], start.registers[i.rd]
    answer = after.registers[i.rd]
    address = (start.registers[i.ra] + i.imm) & WORD_MASK
    top = after.memory[after.sp] if after.sp < len(after.memory) else 0
    fields: dict[str, object] = {
        "a": a,
        "b": b,
        "rd": i.rd,
        "imm": i.imm,
        "value": value,
        "answer": answer,
        "address": address,
        "pc": after.pc,
        "sp": after.sp,
        "top": top,
        **after.flags._asdict(),
    }
    match i.opcode:
        case Opcode.ALU:
            fields["alu"] = ALU_TEMPLATES[AluOp(i.fn)].format(a=a, b=b)
        case Opcode.STORE if address == OUTPUT_PORT:
            sent = after.output[-1]  # the word the screen really took
            return SCREEN_TEMPLATE.format(stored=sent, rd=i.rd, shown=_screen_words(sent))
        case Opcode.STORE:
            fields["stored"] = after.memory[address]
        case Opcode.BR:
            fields["question"] = BRANCH_QUESTIONS[Condition(i.rd)]
            jumped = after.pc != (start.pc + 1) & WORD_MASK
            fields["outcome"] = (TAKEN_TEMPLATE if jumped else NOT_TAKEN_TEMPLATE).format(
                pc=after.pc
            )
        case Opcode.ADDI if i.imm < 0:
            return ADDI_DOWN_TEMPLATE.format(down=-i.imm, value=value, answer=answer, rd=i.rd)
        case _:
            pass
    return OPCODE_TEMPLATES[i.opcode].format(**fields)


def _frame_names(
    translated: TranslatedProgram, state: MachineState
) -> list[tuple[str, int]] | None:
    """List the visible Pebble names of `state`'s frame with their addresses, or None.

    None means `state`'s word has no ready frame (a prologue, a return or a routine).
    Hidden names the translator made up, such as `$for_limit_0`, are left out.
    """
    if not 0 <= state.pc < len(translated.frames):
        return None
    layout = translated.frames[state.pc]
    if layout is None:
        return None
    pointer = state.registers[FRAME_POINTER]
    return [
        (slot.name, pointer + slot.offset)
        for slot in layout.slots
        if not slot.hidden and 0 <= pointer + slot.offset < len(state.memory)
    ]


def describe_line(
    translated: TranslatedProgram, start: MachineState, after: MachineState, ran: int
) -> str:
    """Say what one Pebble line step did: the line, how many instructions, what changed.

    Each visible variable is compared between `start`'s memory and `after`'s. The
    frame is `after`'s when it has one (so a line that makes a variable, such as the
    first, still sees it), else `start`'s.

    Args:
        translated: The Pebble program, with its source map and frames.
        start: The state at the start of the instruction the step began in.
        after: The state where the step stopped.
        ran: How many whole instructions the step ran, counting one the gates finished.

    """
    line = translated.line_at(start.pc)
    count = count_instructions(ran)
    if line is None:
        sentence = ROUTINE_TEMPLATE.format(count=count)
    else:
        sentence = LINE_TEMPLATE.format(line=line, count=count)
    if after.halted:
        sentence = sentence.removesuffix(".") + STOPPED_ENDING
    names = _frame_names(translated, after) or _frame_names(translated, start) or []
    for name, address in names:
        old, new = _signed(start.memory[address]), _signed(after.memory[address])
        if old != new:
            sentence += CHANGED_TEMPLATE.format(name=name, old=old, new=new)
    shown = "".join(chr(w & BYTE_MASK) for w in after.output[len(start.output) :]).strip()
    if shown:
        sentence += SCREEN_SHOWED_TEMPLATE.format(text=" ".join(shown.split()))
    return sentence


def describe_move(
    depth: Depth,
    start: MachineState,
    after: MachineState,
    micro: MicroStep | None,
    translated: TranslatedProgram | None,
    ran: int,
    *,
    gate_path: str | None = None,
) -> str:
    """Say in one plain sentence what a step at `depth` really did.

    - **LINE**: "Line 5 ran 10 instructions. n changed from 2 to 1."
    - **INSTRUCTION**: the opcode's template filled with real numbers, such as
      "The ALU took 1 away from 2. The answer, 1, went into r1."
    - **PART**: a fetch beat ("Fetch: the CPU read the word at address 2, which says
      sub r1, r1, r2.") or, when the beat finished the instruction, its sentence.
    - **GATE**: "Gate 41226 in the XOR worked out a 1.", or the no-gate note for a
      clock wire or an instruction's end.

    Args:
        depth: How big the step was.
        start: The state at the start of the current instruction before the step
            (`instruction_start`), so a step begun part-way through an instruction
            describes all of it.
        after: The state after the step.
        micro: The last gate step's micro step, for GATE; else None.
        translated: The Pebble program, needed for LINE; None for assembly.
        ran: How many whole instructions the step finished: a line's count, 1 for
            an instruction, and 0 or 1 for a beat (0 means it was a fetch).
        gate_path: The scope path of the gate in `micro`, for its part's words.

    """
    if start.halted:
        return FINISHED_NOTE
    match depth:
        case Depth.LINE if translated is not None:
            return describe_line(translated, start, after, ran)
        case Depth.PART if ran == 0 and start.pc < len(start.memory):
            word = start.memory[start.pc]
            return FETCH_TEMPLATE.format(pc=start.pc, text=disassemble(word, start.pc))
        case Depth.GATE if micro is not None:
            return _describe_gate(micro, gate_path)
        case _:
            return describe_instruction(start, after)


def _describe_gate(micro: MicroStep, path: str | None) -> str:
    """Say which gate one gate step worked out, or why it had no gate to show."""
    if micro.kind != "gate":
        return no_gate_note(micro)
    if path is None:
        return BARE_GATE_TEMPLATE.format(gate=micro.gate, value=micro.value)
    return GATE_TEMPLATE.format(gate=micro.gate, words=gate_words(path), value=micro.value)


def describe_gate_steps(count: int, last: str) -> str:
    """Say how many gate steps one request took, then what the last one did."""
    return GATE_STEPS_TEMPLATE.format(count=count, last=last)


def describe_run(ran: int, after: MachineState) -> str:
    """Say how many instructions a press of Run ran, and whether the program stopped.

    Args:
        ran: Every whole instruction that ran, counting one the gates finished first.
        after: The state once the run paused again.

    """
    if ran == 0:
        return NOTHING_RAN
    sentence = RUN_TEMPLATE.format(count=count_instructions(ran))
    return sentence.removesuffix(".") + STOPPED_ENDING if after.halted else sentence


def describe_rewind(*, moved: bool) -> str:
    """Say what Rewind did: went back, or found nothing to undo.

    Args:
        moved: True when the instruction was part-way through, so rewinding changed it.

    """
    return REWOUND if moved else ALREADY_AT_START
