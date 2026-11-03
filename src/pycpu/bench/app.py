"""The Bench's web app: one real running computer, a page to watch it, and a few small routes.

Think of a workshop with a single radio on the bench, switched on, its lid off.
Visitors can freeze it, nudge it forward (`/api/step`), wind it back (`/api/rewind`),
let it play (`/api/run`), put a new song on (`/api/program`, or `/api/pebble` for a
song that comes with its lyric sheet), read its dials (`/api/machine`) and ask what
any part is carrying (`/api/view`). The radio is always the same real one. Here it is
a `Computer` whose paused gate engine is the CPU and RAM built from NAND gates, and
every answer is read from it, never from a copy.
"""

from collections.abc import Mapping
from importlib import resources

from pebble import PebbleError
from pyweb.app import App
from pyweb.messages import HTTPError, HttpRequest, HttpResponse, JsonValue, html, json

from pycpu.assembler import AssemblyError, assemble, disassemble
from pycpu.computer import Computer, StepSize
from pycpu.isa import Fault
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.state import MachineState
from pycpu.translator import PebbleRun, TranslatedProgram, UnsupportedFeature, translate
from pycpu.view import circuit_view

BAD_REQUEST = 400
NOT_FOUND = 404
MAX_RUN = 10_000  # the most instructions one press of Run may ask for
MAX_GATE_STEPS = 100_000  # the most gate steps one request may ask for
MAX_PEBBLE_CHARACTERS = 65_536  # far more Pebble than fits in 4K words once translated
WINDOW_WORDS = 16  # how many words of memory the page shows
WINDOW_BEHIND = 4  # how many of them sit before pc

DEMO_PROGRAM = """\
    set r1, 0xFFFF    ; the output port's address
    li r2, 3          ; count down from 3
loop:
    call show         ; print the digit for r2
    addi r2, -1
    br ne, loop       ; again, until r2 reaches 0
    halt
show:
    li r3, 48         ; 48 is the character '0'
    add r3, r3, r2    ; '0' + r2 is the digit for r2
    store r3, [r1]    ; send it to the screen
    ret
"""


def _whole_number(body: Mapping[str, object], name: str, largest: int, default: int | None) -> int:
    """Return `body[name]` as a whole number from 1 to `largest`, or raise a 400.

    A missing value takes `default` when there is one. Booleans are refused even
    though Python counts them as numbers, because `true` is not what anyone means
    by "run 1 instruction".
    """
    value = body.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= largest:
        msg = f"{name} must be a whole number from 1 to {largest}"
        raise HTTPError(BAD_REQUEST, msg)
    return value


def _object(request: HttpRequest, what: str) -> Mapping[str, object]:
    """Return the request's JSON body as an object, or raise a 400 saying what to send."""
    body = request.json()
    if not isinstance(body, dict):
        raise HTTPError(BAD_REQUEST, f"send a JSON object with {what}")
    return body


def _cell(state: MachineState, address: int) -> dict[str, object]:
    """Describe one word of memory as its address, its number and its assembly text."""
    word = state.memory[address]
    return {"address": address, "word": word, "text": disassemble(word, address)}


def pebble_picture(computer: Computer, translated: TranslatedProgram) -> dict[str, object]:
    """Describe the Pebble program on the Bench: its lines and the one running now.

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
        # steps=0 is not a count: the Bench does not count instructions, and a halted
        # run's sentence never mentions one.
        ended = PebbleRun.from_state(translated, state, steps=0)
        line, message = ended.line, ended.describe()
    else:
        line, message = translated.line_at(computer.instruction_start.pc), None
    return {"source": translated.source.splitlines(), "line": line, "message": message}


def machine_picture(
    computer: Computer, translated: TranslatedProgram | None = None
) -> dict[str, object]:
    """Describe the paused computer the way the Bench page draws it.

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
        computer: The computer to describe.
        translated: The Pebble program it is running, or None for an assembly program.

    Returns:
        A dictionary ready to send as JSON; the Bench page's routes all answer with it.

    """
    state = computer.state()
    start = computer.instruction_start
    if start.pc < len(start.memory):
        instruction = _cell(start, start.pc)
    else:
        instruction = {"address": start.pc, "word": None, "text": ""}
    first = max(0, min(state.pc - WINDOW_BEHIND, len(state.memory) - WINDOW_WORDS))
    last = min(first + WINDOW_WORDS, len(state.memory))
    fault = Fault(state.halt_code).name if state.halted and state.halt_code in Fault else None
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


def step_paused(computer: Computer, body: Mapping[str, object]) -> None:
    """Step the paused computer as a `POST /api/step` body asks, or raise a 400.

    `size` is `"gate"`, `"cycle"` or `"instruction"`. A gate step may carry a
    `count` from 1 to `MAX_GATE_STEPS`, because one instruction is thousands of
    gate steps; the steps stop early if the machine halts. A cycle or instruction
    step may only say `count` 1.

    Args:
        computer: The paused computer to move.
        body: The request's JSON object.

    """
    size = body.get("size")
    if size not in tuple(StepSize):
        sizes = ", ".join(f'"{s}"' for s in StepSize)
        raise HTTPError(BAD_REQUEST, f"size must be one of {sizes}")
    size = StepSize(str(size))
    count = _whole_number(body, "count", MAX_GATE_STEPS, 1)
    if size != StepSize.GATE and count != 1:
        raise HTTPError(BAD_REQUEST, "count is only for gate steps")
    for _ in range(count):
        micro = computer.step(size)
        # Only an instruction's end can leave the machine halted, so look only there.
        if micro is not None and micro.kind == "end" and computer.state().halted:
            break


def load_source(computer: Computer, source: object) -> None:
    """Assemble `source`, load it and pause at its start, or raise a 400 naming the line.

    Args:
        computer: The computer to load; it is left as it was when the text is wrong.
        source: The assembly text from the request.

    """
    if not isinstance(source, str):
        raise HTTPError(BAD_REQUEST, "source must be the assembly text")
    try:
        assembled = assemble(source, words=computer.gate.words)
    except AssemblyError as error:
        raise HTTPError(BAD_REQUEST, str(error)) from None
    computer.load_program(assembled)
    computer.pause()


def load_pebble(computer: Computer, source: object) -> TranslatedProgram:
    """Translate a Pebble program, load it and pause at its start, or refuse it.

    Args:
        computer: The computer to load; it is left as it was when the program is refused.
        source: The Pebble text from the request.

    Returns:
        The translated program, whose source map the machine picture reads.

    Raises:
        HTTPError: 400 if `source` is not text, is longer than
            `MAX_PEBBLE_CHARACTERS`, or the program (with room for its stack) needs more words than
            this Bench's memory has (only a small Bench; the full 4K is what the
            translator itself checks against).
        PebbleError: If Pebble itself finds a mistake in the program.
        UnsupportedFeature: If the program uses something PyCPU cannot do yet.

    """
    if not isinstance(source, str):
        raise HTTPError(BAD_REQUEST, "source must be the Pebble program's text")
    # Refuse a huge text before Pebble's compiler spends time on it: anything this long
    # could never fit in memory once translated.
    if len(source) > MAX_PEBBLE_CHARACTERS:
        msg = f"a Pebble program may be at most {MAX_PEBBLE_CHARACTERS:,} characters long"
        raise HTTPError(BAD_REQUEST, msg)
    translated = translate(source)
    needed, words = len(translated.program.words), computer.gate.words
    if needed > words:
        msg = f"this program needs {needed} words, but this Bench's memory has only {words}"
        raise HTTPError(BAD_REQUEST, msg)
    # Main's first frame sits just past the program; without room it would stop at once.
    if translated.memory_needed > words:
        msg = (
            f"this program needs room for its stack too ({translated.memory_needed} words in all), "
            f"but this Bench's memory has only {words}"
        )
        raise HTTPError(BAD_REQUEST, msg)
    computer.load_program(translated.program)
    computer.pause()
    return translated


def refusal(error: PebbleError | UnsupportedFeature) -> HttpResponse:
    """Answer 400 with the error's message and the line and column it points at.

    The body has the same `error` and `message` as every other 400 from the Bench,
    plus `line` and `column` (1-based, or null when nobody knows) so the page could
    point at the place.
    """
    body: dict[str, JsonValue] = {
        "error": "Bad Request",
        "message": str(error),
        "line": error.line,
        "column": error.column,
    }
    return json(body, BAD_REQUEST)


def create_bench(address_bits: int = RAM_ADDRESS_BITS) -> App:
    """Build the Bench app around one `Computer` running `DEMO_PROGRAM`, paused at its start.

    Args:
        address_bits: How many address wires the RAM has. The real Bench uses the
            full 12 (4,096 words), which takes a few seconds to build; tests and the
            docs use 6 (64 words).

    Returns:
        A PyWeb `App` with the routes `GET /` (the page), `GET /api/machine`,
        `GET /api/view`, `POST /api/step`, `POST /api/rewind`, `POST /api/run`,
        `POST /api/program` and `POST /api/pebble`. See the Bench page in the docs
        for each one.

    """
    computer = Computer(assemble(DEMO_PROGRAM, words=1 << address_bits), address_bits)
    computer.pause()
    page = resources.files("pycpu.bench").joinpath("page.html").read_text(encoding="utf-8")
    app = App()
    # The Pebble program on the Bench, if the program came from Pebble; a dict so the
    # routes below can change it.
    loaded: dict[str, TranslatedProgram] = {}

    def answer() -> HttpResponse:
        """Answer with the machine picture, as every route that moves the machine does."""
        picture = machine_picture(computer, loaded.get("pebble"))
        return json(picture)  # pyright: ignore[reportArgumentType]

    @app.get("/")
    def front_page(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Serve the Bench page."""
        return html(page)

    @app.get("/api/machine")
    def machine(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the computer as it is now."""
        return answer()

    @app.get("/api/view")
    def view(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the part named by `?path=`, or the whole circuit with no path."""
        path = request.query.get("path", "") or ""
        try:
            described = circuit_view(computer.gate.simulator, path)
        except KeyError:
            raise HTTPError(NOT_FOUND, f"No part called {path}") from None
        return json(described)  # pyright: ignore[reportArgumentType]

    @app.post("/api/step")
    def step(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Step by a gate (`count` of them), a clock beat or an instruction."""
        step_paused(computer, _object(request, "a size"))
        return answer()

    @app.post("/api/rewind")
    def rewind(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Go back to the start of the current instruction."""
        computer.rewind()
        return answer()

    @app.post("/api/run")
    def run(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Resume, run some instructions on the fast engine, and pause again."""
        body = _object(request, "a number of instructions")
        instructions = _whole_number(body, "instructions", MAX_RUN, None)
        computer.resume()
        computer.run(instructions)
        computer.pause()
        return answer()

    @app.post("/api/program")
    def program(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Assemble new source and load it, or answer 400 naming the faulty line."""
        load_source(computer, _object(request, "the assembly text as source").get("source"))
        loaded.clear()
        return answer()

    @app.post("/api/pebble")
    def pebble(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Translate a Pebble program and load it, or answer 400 naming the line and column."""
        source = _object(request, "the Pebble program as source").get("source")
        try:
            loaded["pebble"] = load_pebble(computer, source)
        except (PebbleError, UnsupportedFeature) as error:
            return refusal(error)
        return answer()

    return app
