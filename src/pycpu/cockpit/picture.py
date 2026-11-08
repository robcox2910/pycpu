"""The Cockpit's picture: the dials the pilot reads, as plain JSON-ready data.

Think of the instrument panel in a cockpit: it does not fly the plane, it only shows
what the plane is doing right now. This module reads the paused computer in a
`Cockpit` session and lays its registers, memory, current instruction and Pebble
line out as a dictionary the page can draw. Everything is read, nothing is changed.
"""

from typing import cast

from pycpu.assembler import disassemble
from pycpu.cockpit.code import built_by, page_link
from pycpu.cockpit.session import BUSY_MESSAGE, Cockpit, CockpitBusy
from pycpu.cockpit.walks import walk_named
from pycpu.computer import Computer
from pycpu.cpu import GateMachine
from pycpu.isa import Fault, Opcode, decode
from pycpu.state import WORD_BITS, MachineState
from pycpu.translator import FRAME_POINTER, PebbleRun, TranslatedProgram

WINDOW_WORDS = 16  # how many words of memory the page shows
WINDOW_BEHIND = 4  # how many of them sit before pc
STACK_CELLS = 16  # how many words of the stack the page shows, from sp upwards
_SIGN_BIT = 1 << (WORD_BITS - 1)

# Which part of the circuit does the main work of each kind of instruction.
_PART_FOR_OPCODE = {
    Opcode.ALU: "cpu.alu",
    Opcode.CMP: "cpu.alu",
    Opcode.ADDI: "cpu.alu",
    Opcode.LI: "cpu.write_back",
    Opcode.LHI: "cpu.write_back",
    Opcode.LOAD: "cpu.address_mux",
    Opcode.STORE: "cpu.address_mux",
    Opcode.JMP: "cpu.next_pc",
    Opcode.BR: "cpu.next_pc",
    Opcode.CALL: "cpu.next_pc",
    Opcode.RET: "cpu.next_pc",
    Opcode.PUSH: "cpu.next_sp",
    Opcode.POP: "cpu.next_sp",
    Opcode.GETSP: "cpu.next_sp",
    Opcode.SETSP: "cpu.next_sp",
    Opcode.HALT: "cpu.halt",
}

# What the page calls each part in its Step button, for every part above and the whole CPU.
PART_NAMES = {
    "cpu.alu": "ALU",
    "cpu.write_back": "write-back",
    "cpu.address_mux": "memory address",
    "cpu.next_pc": "next-instruction",
    "cpu.next_sp": "stack pointer",
    "cpu.halt": "halt",
    "cpu.registers": "registers",
    "ram": "RAM",
    "cpu": "CPU",
}


def gate_path(gate: GateMachine, part: str) -> str:
    """Name the part of the circuit whose gates make `part`'s outputs, for the gate zoom.

    Like the label on a fuse box saying which room each switch lights: a part's name
    and the room its gates sit in are nearly always the same. The halt part is the odd
    one: its wires are made in the `fault` block, next to it (`cpu.fault`), while
    `cpu.halt` holds only the two registers that remember the answer. So when a part's
    builder recorded a block name, the gates are that block, beside the part.

    Args:
        gate: The gate machine whose builders were recorded as it was wired up.
        part: A part's scope path, such as `"cpu.halt"`, or any other path.

    Returns:
        The scope path to zoom to: `"cpu.fault"` for `"cpu.halt"`, else `part` itself.

    """
    _builder, scope = gate.builders.get(part, (None, None))
    if scope is None:
        return part
    parent = part.rpartition(".")[0]
    return f"{parent}.{scope}" if parent else scope


def part_picture(cockpit: Cockpit, path: str) -> dict[str, object]:
    """Describe one part of the CPU by what goes into it and what comes out, right now.

    Like a meter clipped onto the cables of a machine: each value is a row of the
    part's real wires (its tap in `GateMachine.taps`), read one wire at a time with
    `simulator.get` and added up, lowest bit first. Nothing is worked out here.

    Args:
        cockpit: The paused session to read.
        path: The part's scope path, such as `"cpu.alu"`.

    Returns:
        `path`, `name` (from `PART_NAMES`), and `inputs` and `outputs`, each a list
        of `{"name", "value"}` in the order the CPU's builder recorded them,
        `gates`: the scope that holds the gates making its outputs (see `gate_path`),
        and `built_by`: the live source of the code that built the part (see
        `code.built_by`).

    Raises:
        KeyError: If the part has no taps (an unknown path, or the whole `cpu`).
        CockpitBusy: If the session is playing: the gates stand still then, so
            there are no live wires to read.

    """
    gate = cockpit.computer.gate
    if path not in gate.taps:
        raise KeyError(path)
    if cockpit.playing:
        raise CockpitBusy(BUSY_MESSAGE)
    sim = gate.simulator
    outputs = gate.tap_outputs[path]
    inputs_seen: list[dict[str, object]] = []
    outputs_seen: list[dict[str, object]] = []
    for name, bus in gate.taps[path].items():
        value = sum(sim.get(wire) << bit for bit, wire in enumerate(bus))
        (outputs_seen if name in outputs else inputs_seen).append({"name": name, "value": value})
    return {
        "path": path,
        "name": PART_NAMES[path],
        "inputs": inputs_seen,
        "outputs": outputs_seen,
        "gates": gate_path(gate, path),
        "built_by": built_by(gate, path),
    }


def _cell(state: MachineState, address: int) -> dict[str, object]:
    """Describe one word of memory as its address, its number and its assembly text."""
    word = state.memory[address]
    return {
        "address": address,
        "word": word,
        "text": disassemble(word, address),
        "part": f"ram.word{address}",
    }


def part_for_instruction(word: int) -> str:
    """Name the part of the circuit that does the main work of the instruction `word`.

    Args:
        word: A 16-bit machine word. Every word decodes to some instruction.

    Returns:
        A scope path such as `"cpu.alu"` for an add, or `"cpu.next_pc"` for a jump.

    """
    return _PART_FOR_OPCODE[decode(word).opcode]


def _changed(before: MachineState, now: MachineState) -> dict[str, object]:
    """List what differs between two states: registers, pc, sp, flags and memory words.

    Memory is compared with a plain scan over both tuples. That is fine at 4K words
    (measured at about 0.3 ms; a slow test pins it under 0.05 s at full size), so there is
    no need for anything cleverer such as remembering which words were written.
    """
    registers = [
        i for i, (a, b) in enumerate(zip(before.registers, now.registers, strict=True)) if a != b
    ]
    flags = [
        name
        for name, a, b in zip(now.flags._fields, before.flags, now.flags, strict=True)
        if a != b
    ]
    memory = [i for i, (a, b) in enumerate(zip(before.memory, now.memory, strict=True)) if a != b]
    return {
        "registers": registers,
        "pc": before.pc != now.pc,
        "sp": before.sp != now.sp,
        "flags": flags,
        "memory": memory,
    }


def _stack(state: MachineState) -> list[dict[str, object]]:
    """Describe up to 16 words of the stack, from sp upwards (the top first)."""
    return [
        _cell(state, a) for a in range(state.sp, min(state.sp + STACK_CELLS, len(state.memory)))
    ]


def _signed(word: int) -> int:
    """Read a 16-bit word as a signed number, the way Pebble's code means it (65535 is -1)."""
    return word - (_SIGN_BIT << 1) if word & _SIGN_BIT else word


def variables_picture(
    translated: TranslatedProgram | None,
    start: MachineState,
    now: MachineState | None = None,
) -> dict[str, object] | None:
    """Describe the Pebble names of the running code: each one's address and value.

    The frame is the one of the instruction that started in `start` (its `pc`), found
    in `translated.frames`, and `r7` says where that frame sits. Each name lives at `r7`
    plus its slot's offset; a name whose address falls outside memory is left out.
    The frame and `r7` come from `start`, because part-way through an epilogue's
    `pop r7` the register has already moved on to the caller's frame. Each value is
    read from `now`, so that part-way through a store the variable agrees with the
    memory pane and its changed mark.

    Args:
        translated: The Pebble program, or None for assembly.
        start: The state at the start of the current instruction.
        now: The state to read each name's word from; `start` when None.

    Returns:
        `function` (None for the top level), `frame_pointer` and `names`, or None for
        assembly, or when the current word has no ready frame (a prologue, a return's
        `ret`, or a runtime routine).

    """
    if translated is None or not 0 <= start.pc < len(translated.frames):
        return None
    layout = translated.frames[start.pc]
    if layout is None:
        return None
    pointer = start.registers[FRAME_POINTER]
    memory = start.memory if now is None else now.memory
    names: list[dict[str, object]] = []
    for slot in layout.slots:
        address = pointer + slot.offset
        if not 0 <= address < len(memory):
            continue
        word = memory[address]
        names.append(
            {
                "name": slot.name,
                "kind": slot.kind,
                "hidden": slot.hidden,
                "address": address,
                "word": word,
                "value": _signed(word),
                "part": f"ram.word{address}",
            }
        )
    return {"function": layout.function, "frame_pointer": pointer, "names": names}


def _last_gate(cockpit: Cockpit) -> dict[str, object] | None:
    """Describe the last gate step: which gate, the part it lives in, and its new output.

    A clock edge or an instruction's end is not a gate thinking, so those give None.
    """
    micro = cockpit.last_gate
    if micro is None or micro.kind != "gate":
        return None
    circuit = cockpit.computer.gate.simulator.circuit
    return {"id": micro.gate, "path": circuit.scope_of(micro.gate), "value": micro.value}


def walk_picture(cockpit: Cockpit) -> dict[str, object] | None:
    """Describe the walk the learner is on, for the page to drive the glass and say its words.

    Returns:
        None with no walk, else `name`, `title`, `step`, `count` (how many steps it
        has), and for that step `say`, `look` and `show`. At the "Now you try" stage
        (`step == count`) `trying` is true, `say` is None, and `look` and `show` are
        the try's, and `step_kind` is the try's `step` (`"into"` when the page should
        offer Step into; None otherwise, and always None before the try). `task` is
        always the try's task, and `done` and `off_script` come from the session's
        `WalkProgress`. `see_also` is the `title` and `url` of the concept page that
        explains the walk's idea, on the docs server on your own computer.

    """
    progress = cockpit.walk
    walk = None if progress is None else walk_named(progress.name)
    if progress is None or walk is None:
        return None
    count = len(walk.steps)
    trying = progress.step >= count
    if trying:
        say, look, show, kind = None, walk.trial.look, walk.trial.show, walk.trial.step
    else:
        here = walk.steps[progress.step]
        say, look, show, kind = here.say, here.look, here.show, None
    return {
        "name": walk.name,
        "title": walk.title,
        "step": progress.step,
        "count": count,
        "say": say,
        "look": str(look),
        "show": show,
        "step_kind": kind,
        "trying": trying,
        "task": walk.trial.task,
        "done": progress.done,
        "off_script": progress.off_script,
        "see_also": page_link(walk.see_also),
    }


def listing(cockpit: Cockpit) -> dict[str, object]:
    """Describe the whole loaded program, one row for each word of machine code.

    Each row has its `address`, `word`, `text`, `first` (true for the first word that
    came from its source line, since a line such as `set` makes two), the `labels` that
    mark this address, and `pebble_line` (the Pebble line that made the word, or None
    for assembly and runtime words).
    The `text` is the source line the word came from, as the program was written
    (a word made by `set` shows the `set` line, not the `li` it became).

    Args:
        cockpit: The session whose program to list.

    Returns:
        `rows`; `pebble`, the Pebble source as a list of lines, or None for assembly;
        and `program`, the session's load count, which the picture carries too.

    """
    program, translated = cockpit.program, cockpit.translated
    source = cockpit.assembly.splitlines()
    names: dict[int, list[str]] = {}
    for name, address in program.labels.items():
        names.setdefault(address, []).append(name)
    rows: list[dict[str, object]] = []
    for address, (word, line) in enumerate(zip(program.words, program.lines, strict=True)):
        text = source[line - 1].strip() if 0 < line <= len(source) else ""
        rows.append(
            {
                "address": address,
                "word": word,
                "text": text,
                "first": address == 0 or program.lines[address - 1] != line,
                "labels": names.get(address, []),
                "pebble_line": None if translated is None else translated.line_at(address),
            }
        )
    pebble = None if translated is None else translated.source.splitlines()
    return {"rows": rows, "pebble": pebble, "program": cockpit.loads}


def pebble_picture(
    computer: Computer,
    translated: TranslatedProgram,
    *,
    state: MachineState | None = None,
    start_pc: int | None = None,
) -> dict[str, object]:
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
        state: The state to describe; the computer's own when None.
        start_pc: The address the current instruction started at; the computer's
            `instruction_start.pc` when None.

    Returns:
        `source` (a list of the Pebble lines), `line` and `message`.

    """
    state = computer.state() if state is None else state
    if start_pc is None:
        start_pc = computer.instruction_start.pc
    if state.halted:
        # steps=0 is not a count: the Cockpit does not count instructions, and a halted
        # run's sentence never mentions one.
        ended = PebbleRun.from_state(translated, state, steps=0)
        line, message = ended.line, ended.describe()
    else:
        line, message = translated.line_at(start_pc), None
    return {"source": translated.source.splitlines(), "line": line, "message": message}


def machine_picture(cockpit: Cockpit) -> dict[str, object]:
    """Describe the paused computer the way the Cockpit page draws it.

    Everything is read from the gate engine while paused (and from the fast engine
    while the session is playing, when `phase` is always `"fetch"` and `last_gate`
    is None). `changed` marks what differs from the state before the last move,
    `stack` lists up to 16 words from `sp` up, `last_gate` names the last gate step,
    and `parts` gives the circuit path to zoom to for each value. The current instruction
    is the one that started at `instruction_start.pc`, read from memory as it was
    then, because half way through an instruction `pc` has already moved on. When
    that address is outside memory (a fetch fault) its word is None and its text
    is empty. The memory window holds 16 words, starting 4 before `pc` (or at 0), and
    slides back so it never runs past the last word: a `pc` far outside memory still
    shows the final 16 words. `fault` is the name of the `Fault` (such as
    `"BAD_ADDRESS"`) when the machine has halted with one of those codes, else None;
    a program's own `halt 1` to `halt 3` shares those codes. `pebble` is the
    `pebble_picture` when the program came from Pebble, and None for assembly.
    `variables` is the `variables_picture` of the current instruction (None while
    playing). `steps` is the label of each Step depth, with the part's name taken from
    `PART_NAMES`. `happened` is the "What just happened" sentence for the last move
    (None before any move and after a load). `walk` is the `walk_picture` of the walk the
    learner is on, or None. `program` is the session's load count, so
    the page can tell whether its listing is of the program on the machine.
    `parts["gates"]` maps every part with a part view to the scope its gate zoom shows
    (see `gate_path`).

    Args:
        cockpit: The session to describe.

    Returns:
        A dictionary ready to send as JSON; the Cockpit's routes all answer with it.

    """
    computer = cockpit.computer
    state = computer.state()
    playing = cockpit.playing
    # While playing only the fast engine is live: the gate engine's phase and boundary
    # are stale, and the machine is always between two instructions, about to fetch.
    start = state if playing else computer.instruction_start
    start_pc = state.pc if playing else start.pc
    if start_pc < len(start.memory):
        # The instruction's zoom target is `parts["instruction"]`, so its cell has no `part`.
        instruction = {k: v for k, v in _cell(start, start_pc).items() if k != "part"}
    else:
        instruction = {"address": start_pc, "word": None, "text": ""}
    first = max(0, min(state.pc - WINDOW_BEHIND, len(state.memory) - WINDOW_WORDS))
    last = min(first + WINDOW_WORDS, len(state.memory))
    fault = Fault(state.halt_code).name if state.halted and state.halt_code in Fault else None
    translated = cockpit.translated
    word: int | None = cast("int | None", instruction["word"])
    pebble = None
    if translated is not None:
        pebble = pebble_picture(computer, translated, state=state, start_pc=start_pc)
    instruction_part = "cpu" if word is None else part_for_instruction(word)
    return {
        "paused": computer.paused,
        "running": playing,
        "phase": "fetch" if playing else computer.gate.phase.name.lower(),
        "at_boundary": True if playing else computer.gate.at_boundary,
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
        "pebble": pebble,
        "changed": _changed(cockpit.before, state),
        "stack": _stack(state),
        "variables": None if playing else variables_picture(translated, start, state),
        "last_gate": None if playing else _last_gate(cockpit),
        "note": cockpit.note,
        "happened": cockpit.happened,
        "program": cockpit.loads,
        "walk": walk_picture(cockpit),
        "parts": {
            "registers": [f"cpu.registers.r{i}" for i in range(len(state.registers))],
            "pc": "cpu.pc",
            "sp": "cpu.sp",
            "flags": "cpu.flags",
            "instruction": instruction_part,
            "gates": {part: gate_path(computer.gate, part) for part in computer.gate.taps},
        },
        "steps": {
            "line": "Step one line \u25b8",
            "instruction": "Step one instruction \u25b8",
            "part": f"Step one {PART_NAMES[instruction_part]} beat \u25b8",
            "gate": "Step one gate \u25b8",
        },
    }
