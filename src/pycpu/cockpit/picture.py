"""The Cockpit's picture: the dials the pilot reads, as plain JSON-ready data.

Think of the instrument panel in a cockpit: it does not fly the plane, it only shows
what the plane is doing right now. This module reads the paused computer in a
`Cockpit` session and lays its registers, memory, current instruction and Pebble
line out as a dictionary the page can draw. Everything is read, nothing is changed.
"""

from pycpu.assembler import disassemble
from pycpu.cockpit.session import Cockpit
from pycpu.computer import Computer
from pycpu.isa import Fault
from pycpu.state import MachineState
from pycpu.translator import PebbleRun, TranslatedProgram

WINDOW_WORDS = 16  # how many words of memory the page shows
WINDOW_BEHIND = 4  # how many of them sit before pc


def _cell(state: MachineState, address: int) -> dict[str, object]:
    """Describe one word of memory as its address, its number and its assembly text."""
    word = state.memory[address]
    return {"address": address, "word": word, "text": disassemble(word, address)}


def pebble_picture(computer: Computer, translated: TranslatedProgram) -> dict[str, object]:
    """Describe the Pebble program on the Cockpit: its lines and the one running now.

    The running line is the Pebble line of the current instruction, the one that
    started at `instruction_start.pc` (half way through an instruction `pc` has moved
    on). It is None inside the ready-made runtime routines, which belong to no line.
    Once the machine has halted nothing runs next, so the line is the one a fault is
    blamed on (None after a normal finish), and `message` says how the run ended in
    one sentence, such as "Division by zero at line 2". Before that `message` is None.

    Args:
        computer: The paused computer running the program.
        translated: The program it is running, with its source map.

    Returns:
        `source` (a list of the Pebble lines), `line` and `message`.

    """
    state = computer.state()
    if state.halted:
        # steps=0 is not a count: the Cockpit does not count instructions, and a halted
        # run's sentence never mentions one.
        ended = PebbleRun.from_state(translated, state, steps=0)
        line, message = ended.line, ended.describe()
    else:
        line, message = translated.line_at(computer.instruction_start.pc), None
    return {"source": translated.source.splitlines(), "line": line, "message": message}


def machine_picture(cockpit: Cockpit) -> dict[str, object]:
    """Describe the paused computer the way the Cockpit page draws it.

    Everything is read from the gate engine while paused. The current instruction
    is the one that started at `instruction_start.pc`, read from memory as it was
    then, because half way through an instruction `pc` has already moved on. When
    that address is outside memory (a fetch fault) its word is None and its text
    is empty. The memory window holds 16 words, starting 4 before `pc` (or at 0), and
    slides back so it never runs past the last word: a `pc` far outside memory still
    shows the final 16 words. `fault` is the name of the `Fault` (such as
    `"BAD_ADDRESS"`) when the machine has halted with one of those codes, else None;
    a program's own `halt 1` to `halt 3` shares those codes. `pebble` is the
    `pebble_picture` when the program came from Pebble, and None for assembly.

    Args:
        cockpit: The session to describe.

    Returns:
        A dictionary ready to send as JSON; the Cockpit's routes all answer with it.

    """
    computer = cockpit.computer
    state = computer.state()
    start = computer.instruction_start
    if start.pc < len(start.memory):
        instruction = _cell(start, start.pc)
    else:
        instruction = {"address": start.pc, "word": None, "text": ""}
    first = max(0, min(state.pc - WINDOW_BEHIND, len(state.memory) - WINDOW_WORDS))
    last = min(first + WINDOW_WORDS, len(state.memory))
    fault = Fault(state.halt_code).name if state.halted and state.halt_code in Fault else None
    translated = cockpit.translated
    return {
        "paused": computer.paused,
        "phase": computer.gate.phase.name.lower(),
        "at_boundary": computer.gate.at_boundary,
        "registers": list(state.registers),
        "pc": state.pc,
        "sp": state.sp,
        "flags": state.flags._asdict(),
        "halted": state.halted,
        "halt_code": state.halt_code,
        "fault": fault,
        "output": state.output_text,
        "instruction": instruction,
        "memory": [_cell(state, address) for address in range(first, last)],
        "pebble": None if translated is None else pebble_picture(computer, translated),
    }
