# The Cockpit

## A Cockpit With Every Dial in View

Imagine the cockpit of an aeroplane. Every dial is in view at once: speed, height,
fuel, heading. Now imagine a pilot who can *freeze the flight* in the middle of the
sky, look at every dial, and nudge time forward a tiny bit at a time to see what each
one does. That is what this page does for the computer we have built.

The **Cockpit** is a web page on your own computer that shows the whole computer. It
began life as the Bench, a workbench with the lid off a radio, and it has grown into
the Cockpit: the routes work exactly as they did, and the name now says what the page
is for. On it sits a real program, already loaded and paused at its
very first instruction. You can see the eight **registers** (the computer's small
named boxes for numbers, from [What Is a CPU?](what-is-a-cpu.md)), the program
counter, the stack pointer, the flags, a window onto memory with the current
instruction marked, and whatever the program has printed. Buttons move the machine
forward by one **gate**, a hundred gates, one clock beat or one whole
**instruction**; another button rewinds to the start of the instruction. And the zoom
panel lets you **zoom** (move from a big part into the smaller parts it is made of)
from the whole CPU down to a single NAND gate, with the real 0s and 1s on its wires.
Nothing on it is drawn from memory or faked.

You can also put a **Pebble** program in the Cockpit. Then the page shows your Pebble
code next to the machine code it was translated into, with the line that is running
right now marked. Step one instruction at a time and you can watch that mark sit still
for a while, then jump: one line of Pebble is many machine instructions, and the Cockpit
lets you count them.

The page in your browser and the Cockpit app behind it talk by sending each other short
messages, like notes passed through a hatch. Each kind of note goes to its own address,
called a **route**, such as `/api/machine` ("tell me about the machine") or `/api/step`
("move it forward"). A note marked **GET** asks for something and changes nothing; a
note marked **POST** sends something, such as which button you pressed. The answers
travel as **JSON**, a plain text way of writing numbers, words and lists that both
Python and the browser can read, like `{"pc": 1, "halted": false}`. When a note makes
no sense, the answer is a number instead: **400** means "bad request, I can't do
that", and **404** means "not found, there is no such thing".

| The cockpit | In PyCPU |
|---------------|----------|
| The whole instrument panel | The Cockpit page, served by `python -m pycpu` |
| The aeroplane in flight, frozen | A `Computer` (from [Pausing and Rewinding](pausing-and-rewinding.md)) running `DEMO_PROGRAM` |
| The dials in front of the pilot | `registers`, `pc`, `sp`, `flags` and `output`, read from `GET /api/machine` |
| The flight plan, with your place marked | The memory window: 16 words of memory, the current instruction highlighted |
| Nudging time forward | `POST /api/step` with `"gate"`, `"cycle"` or `"instruction"` |
| Going back to the start of the manoeuvre | `POST /api/rewind` |
| Letting the flight go on for a while | `POST /api/run` |
| Loading a new flight plan | `POST /api/program`, with assembly text |
| Loading a plan that comes with a written briefing | `POST /api/pebble`, with a Pebble program that the translator turns into machine code |
| The briefing, held up beside the plan | The Pebble pane, next to the memory window |
| The line of the briefing being flown right now | `pebble.line`: the Pebble line of the current instruction |
| The program, in full | `GET /api/listing`: one row for each word, with its source line, labels and Pebble line |
| Circled differences | `changed`: what the last move altered |
| A part you point at | A **scope**, such as `cpu.alu.adder` (see [Looking Inside a Circuit](looking-inside.md)) |
| The smallest part you can find | One NAND gate, with its two inputs and one output |
| The cockpit door | `create_cockpit()` in `src/pycpu/cockpit/app.py` |

## Try It

The Cockpit is a small web app, but you can talk to it without opening a browser.
Python has a pretend browser for this, called `TestClient` (it sends requests
straight to the app, with no network). We open a small Cockpit, with 64 words of memory
so it builds quickly, and drive it the way the page's buttons do.

Three small words appear that you may not have met. A web request is a message that
has to wait for its reply, so the code that sends one is written as `async def` ("this
function may wait"), and each wait is marked `await` ("pause here until the answer
arrives"). `run(...)` is the starter button: it starts the waiting machinery and runs
our function to the end.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def visit() -> None:
    client = TestClient(create_cockpit(address_bits=6))
    machine = (await client.get("/api/machine")).json()
    print("pc", machine["pc"], "next:", machine["instruction"]["text"])

    machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    print("pc", machine["pc"], "r1 is", machine["registers"][1])
    print("next:", machine["instruction"]["text"])

    machine = (await client.post("/api/run", json={"instructions": 4})).json()
    print("pc", machine["pc"], "next:", machine["instruction"]["text"])
    print("r2 is", machine["registers"][2], "and r3 is", machine["registers"][3])

    machine = (await client.post("/api/step", json={"size": "cycle"})).json()
    print("after one beat:", machine["phase"], "beat next; at a boundary?", machine["at_boundary"])
    where = "cpu.alu.adder.bit0.full_adder.half_adder.and"
    seen = (await client.get("/api/view", query={"path": where})).json()
    for gate in seen["gates"]:
        print("gate", gate["id"], "in", gate["value_a"], gate["value_b"], "out", gate["value_out"])

    machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    print("r3 is now", machine["registers"][3])

    machine = (await client.post("/api/run", json={"instructions": 100})).json()
    print("printed", machine["output"], "halted?", machine["halted"])

    wrong = await client.post("/api/step", json={"size": "giant"})
    print(wrong.status)


run(visit())
# Output:
# pc 0 next: li r1, 255
# pc 1 r1 is 255
# next: lhi r1, 255
# pc 8 next: add r3, r3, r2
# r2 is 3 and r3 is 48
# after one beat: execute beat next; at a boundary? False
# gate 12678 in 0 1 out 1
# gate 12679 in 1 1 out 0
# r3 is now 51
# printed 321 halted? True
# 400
```

Follow it line by line. The program starts with `set r1, 0xFFFF`, but `set` is a
shortcut that the assembler turns into *two* real instructions (see
[Assembly Language](assembly-language.md)): `li r1, 255` puts 255 in the low half, then
`lhi r1, 255` puts 255 in the high half. One instruction step ran only the first, so
`r1` is 255 and the second is next. Running four more instructions brings us inside the
`show` function, just before `add r3, r3, r2`, with `r3` holding 48 (the character `0`)
and `r2` holding 3. One beat later the add has been **fetched** into the CPU but not yet
**executed** (the two beats from [Fetch, Decode, Execute](fetch-decode-execute.md)), and
the ALU's gates are already working on 48 + 3. In the very first column of the sum,
48 ends in a 0 and 3 ends in a 1, so the half adder's `and` sees a 0 and a 1: gate
12678 outputs 1, gate 12679 turns it into 0, and nothing carries. Finishing the
instruction stores the answer, 51 (the character `3`), in `r3`. Then the program runs
to its end, printing `321`, and asking for a step size the Cockpit does not know gets a
400.

Now the same countdown, written in Pebble instead. This Cockpit gets 256 words of memory
(`address_bits=8`), because a translated program also carries the ready-made routines
for multiplying, dividing and printing from
[Multiply and Divide](multiply-and-divide.md) and [Printing a Number](printing-a-number.md).
We step one instruction at a time and keep a **trail**: each time the Pebble line
changes, we start a new entry and count how many instructions it lasts. `None` means
"no Pebble line": the machine is inside one of those ready-made routines.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit

COUNTDOWN = """\
let n = 2
while n > 0 {
    print(n)
    n = n - 1
}
"""
DIVIDE_BY_ZERO = "let a = 7\nprint(a // 0)\n"
DECIMAL = "let a = 7\nprint(a / 2)\n"


async def visit_pebble() -> None:
    client = TestClient(create_cockpit(address_bits=8))
    machine = (await client.post("/api/pebble", json={"source": COUNTDOWN})).json()
    pebble = machine["pebble"]
    print(len(pebble["source"]), "lines of Pebble; line", pebble["line"], "runs first")
    print("its first instruction:", machine["instruction"]["text"])

    trail = []
    while len(trail) < 6:
        line = machine["pebble"]["line"]
        if trail and trail[-1][0] == line:
            trail[-1][1] += 1
        else:
            trail.append([line, 1])
        machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    for line, instructions in trail[:5]:
        print("line", line, "lasted", instructions, "instructions")

    machine = (await client.post("/api/run", json={"instructions": 1000})).json()
    print("printed", repr(machine["output"]), "-", machine["pebble"]["message"])

    await client.post("/api/pebble", json={"source": DIVIDE_BY_ZERO})
    machine = (await client.post("/api/run", json={"instructions": 1000})).json()
    print(machine["pebble"]["message"], "- the page marks line", machine["pebble"]["line"])

    wrong = await client.post("/api/pebble", json={"source": DECIMAL})
    print(wrong.status, "at line", wrong.json()["line"], "column", wrong.json()["column"])
    print(wrong.json()["message"])


run(visit_pebble())
# Output:
# 5 lines of Pebble; line 1 runs first
# its first instruction: getsp r1
# line 1 lasted 14 instructions
# line 2 lasted 13 instructions
# line 3 lasted 4 instructions
# line None lasted 170 instructions
# line 4 lasted 10 instructions
# printed '2\n1\n' - The program finished
# Division by zero at line 2 - the page marks line 2
# 400 at line 2 column 9
# the / operator (it always makes a decimal number; use // for whole numbers) is not supported on PyCPU yet at line 2, column 9
```

The first instruction is `getsp r1`, not anything to do with `n`: it starts main's
**frame**, the room checked and made for its variables (see
[Variables in Memory](variables-in-memory.md)), and the translator files those words
under line 1. So `let n = 2` lasts 14 instructions, frame and all. The check
`while n > 0` takes 13. `print(n)` takes only 4 of its own (fetch `n`, put it on the
stack, take it off again, call the printing routine), and then the mark leaves the
Pebble program altogether for 170 instructions: that is the ready-made routine turning
2 into the digit `2` and a new line, one division at a time. Then `n = n - 1` takes 10.
The trail's sixth entry is cut off by the loop, so we print only five.

Running to the end prints `'2\n1\n'`. `repr` shows text with its invisible characters
written out, and `\n` is the "new line" character `print` puts after each number. The
second program divides by zero; the Cockpit marks line 2 and says why, in the same words
as [What Happens When Things Go Wrong](what-happens-when-things-go-wrong.md). The last
program uses `/`, which PyCPU cannot do, so nothing is loaded and the answer is a 400
naming the exact line and column.

To open the real thing, run this in a terminal, then visit the address it prints:

```text
uv run python -m pycpu
```

It serves the page at `http://127.0.0.1:8765`. The address `127.0.0.1` means "this
computer only", so nobody else on your network can see it. The real Cockpit has the full
4K words of memory, more than 600,000 NAND gates, so it says `Building the computer
from NAND gates...` and takes about 3 seconds (on the computer this page was written on)
before the address appears.

## How It Works

The Cockpit is split into a session, a picture and an app, all in `src/pycpu/cockpit/`:
`session.py` holds the `Cockpit` (the one running computer and every rule about moving
it), `picture.py` turns it into the JSON the page draws, and `app.py` only reads requests,
calls the session and answers.

```
   your browser                               your computer
 ┌───────────────┐   GET /              ┌────────────────────────────────┐
 │  page.html    │ <─────────────────── │  app.py: create_cockpit()      │
 │               │                      │                                │
 │  registers    │   GET /api/machine   │  one Computer, paused:         │
 │  Pebble pane  │ <─────────────────── │   a fast engine and a gate     │
 │  memory       │   POST /api/step     │   engine of real NAND gates    │
 │  buttons      │   POST /api/rewind   │                                │
 │  load box     │   POST /api/run      │  assemble / disassemble        │
 │               │   POST /api/program  │  translate (Pebble -> words,   │
 │  zoom panel   │   POST /api/pebble   │   plus a line for each word)   │
 │               │ ───────────────────> │                                │
 │               │   GET /api/view      │  circuit_view reads the gates' │
 │               │ <─────────────────── │  own wires                     │
 └───────────────┘                      └────────────────────────────────┘
```

**`create_cockpit()`** builds a `Cockpit` session, which assembles `DEMO_PROGRAM`, a short countdown written in
assembly at the top of `session.py`, builds a `Computer` with it and pauses it at once, so the machine
sits in the gate engine before its first instruction. It takes `address_bits`, the
number of memory address wires, just like `Computer` does; the real Cockpit uses the full
12 (4,096 words), and the Try It uses 6 (64 words) to build quickly, or 8 (256 words)
when it needs room for a Pebble program. Every route answers with the same picture of
the machine, which the page redraws:

- `GET /api/machine` reads the paused gate engine's state: the eight `registers`, `pc`,
  `sp`, the four `flags`, `halted` and `halt_code`, the `output` printed so far, which
  beat is next (`phase`, `"fetch"` or `"execute"`) and whether the machine is between
  two instructions (`at_boundary`). `instruction` is the **current instruction**: the
  one at the address where it started, with its `word` and its `text`, turned back into
  assembly by `disassemble`. `memory` is always 16 words, starting 4 before `pc` (or at
  0), so you can see a little behind and ahead; near the end of memory the window slides
  back so it still shows the last 16 words, even when `pc` has run off the end. `fault`
  names why the machine stopped when `halt_code` is one of the `Fault` codes
  (`BAD_ADDRESS`, `STACK_OVERFLOW` or `DIVIDE_BY_ZERO`, which are 1, 2 and 3) and is
  `null` otherwise; the page then says, for example, "halted: bad address (code 1)".
  A program's own `halt 1`, `halt 2` or `halt 3` shares those codes, so the page cannot
  tell a program that chose to stop that way from a real fault.
  `pebble` is `null` for an assembly program. For a Pebble program it is
  `{"source": [...], "line": 3, "message": null}`: `source` is the program as a list of
  lines, and `line` is the Pebble line of the current instruction, looked up in the
  translator's **source map** (the list that says, for every word of machine code,
  which Pebble line made it; see [What Happens When Things Go Wrong](what-happens-when-things-go-wrong.md)).
  It is `null` while a ready-made routine runs, because those words belong to no line.
  Once the machine halts, `message` says how the run ended, such as
  `"Division by zero at line 2"` or `"The program finished"`, and `line` is the line
  to blame (`null` after a normal finish).
- `POST /api/step` takes `{"size": "gate"}`, `{"size": "cycle"}` or
  `{"size": "instruction"}` and calls `Computer.step` with that size (the three sizes
  from [Pausing and Rewinding](pausing-and-rewinding.md)). One instruction is thousands
  of gate steps: running the demo program on the full-size Cockpit, the quickest took
  6,988 and the slowest 43,045. The slow ones write to memory, because each data wire
  that changes wakes one gate in every one of the 4,096 words (on the small 64-word
  Cockpit the same program's instructions take 6,736 to 15,213). Clicking one gate at a
  time would take all day.
  A gate step can therefore carry a `count`, a whole number from 1 to 100,000, such as
  `{"size": "gate", "count": 100}`: that is the page's **100 gates** button. The steps
  stop early if the machine halts. Any other size, a count outside 1 to 100,000, or a
  count with a cycle or instruction step gets a 400 ("bad request") answer.
- `POST /api/rewind` goes back to the start of the current instruction.
- `POST /api/run` takes `{"instructions": 25}` (from 1 to 10,000). The computer
  resumes, which finishes any half-done instruction in the gates, runs that many more
  instructions on the fast engine, and pauses again at the next boundary. A number out
  of range gets a 400.
- `POST /api/program` takes `{"source": "..."}`, some assembly text. If it assembles,
  the computer is switched on again with the new program in memory and paused at its
  start. If it does not, the answer is a 400 carrying the assembler's own message, which
  starts with the line number of the mistake, such as `line 2: ...`.
- `POST /api/pebble` takes `{"source": "..."}`, a Pebble program. `load_pebble` hands it
  to `translate` (from [From Pebble to Machine Code](from-pebble-to-machine-code.md)),
  loads the machine code exactly as `/api/program` does, keeps the translated program
  so later pictures can look up lines, and pauses at the start. If Pebble finds a
  mistake, or the program uses something PyCPU cannot do yet, nothing is loaded and the
  answer is a 400 whose `message` is the error's own words, with `line` and `column`
  saying where. A small Cockpit also refuses a program bigger than its memory. Loading
  assembly afterwards forgets the Pebble program, so `pebble` goes back to `null`.
- `GET /api/view?path=cpu.alu` answers with `circuit_view` for that scope of the gate
  engine's circuit, exactly as before. A scope that does not exist, such as `cpu.nope`,
  gets a friendly 404 ("not found") answer that says `No part called cpu.nope`.

**The page** is plain HTML, CSS and JavaScript in one file, with nothing fetched from
anywhere else. Across the top are the step buttons (**1 gate**, **100 gates**,
**1 cycle**, **1 instruction**), **Rewind**, and **Run** with a box for how many
instructions. Below them are the registers and flags, the program's printed output, and
the memory window, where each word is shown as a number and as assembly, with the
current instruction highlighted. Once the machine has halted, no row is highlighted,
because nothing runs next. Beside the memory window is the **Pebble pane**: the Pebble
program, one numbered line per row, with the running line highlighted and a sentence
above it saying what is happening ("Running line 2", "Inside a ready-made routine", or,
once halted, how the run ended). For an assembly program the pane says there is no
Pebble to show. A text box below takes your own program; **Load Pebble** sends it to
`/api/pebble` and **Load assembly** to `/api/program`. The page writes every piece of
text it shows with `textContent`, which puts words on the page as plain words, so a
program containing something like `<b>` shows those three characters instead of
changing the page. Under all that is the zoom panel: it opens on `cpu`, lists the parts inside
with their gate counts, and draws each gate with its two inputs and its output, a wire
holding a 1 highlighted. Each level is labelled in one plain sentence, with the name of
the page that explains it. After every button the page reloads the part you are looking
at, so you can watch its wires change.

**Why can the page look inside at all?** Back in
[Looking Inside a Circuit](looking-inside.md), every gate was filed under the name of
the part it belongs to as it was built. `circuit_view` looks up that filing and reads
each gate's three wires from the gate engine's simulator. The Cockpit does no logic of
its own: it only asks the gate engine what is on each wire and what is in each
register, and shows you.

### A guided tour: from an instruction down to a gate

This is the Try It, done with the buttons. The RAM is built before the CPU, so on the
full-size Cockpit, with its much bigger RAM, the same two gates have bigger numbers than
the small Cockpit's 12678 and 12679: they are gates 610636 and 610637.

1. Open the Cockpit. The memory window highlights address 0, `li r1, 255`, and every
   register is 0. Press **1 instruction**. `r1` becomes 255 and the highlight moves to
   address 1. `pc` is 1.
2. Type 4 in the Run box and press **Run**. The highlight is now on
   `add r3, r3, r2` at address 8, inside the `show` function. `sp` is one less than
   before, because the `call` pushed the address to come back to (see
   [Calling and Returning](calling-and-returning.md)).
3. Press **1 cycle**. The phase now says `execute`: the add has been fetched into the
   instruction register (`ir`) and is waiting to be obeyed. Notice `pc` already says 9.
4. In the zoom panel you are looking at `cpu`. Click **alu**, then **adder**, then
   **bit0**, then **full_adder**, then the first **half_adder**, then **and**. Here are
   the two gates that decide whether the first column of 48 + 3 carries: one input
   holds a 0 and the other a 1, so nothing carries.
5. Press **1 gate** a few times, then **100 gates**, and watch the phase, the boundary
   flag and the wires. Press **Rewind** and you are back at the start of the add, with
   the phase saying `fetch` again.
6. Press **1 instruction**: `r3` turns from 48 into 51, the code for the character
   `3`. Press **Run** with 100 and the output says `321`.

### A second tour: one Pebble line, many instructions

1. The box under the memory window already holds a Pebble countdown from 3. Press
   **Load Pebble**. The Pebble pane highlights line 1, `let n = 3`, and the memory
   window highlights `getsp r1` at address 0: the start of main's frame.
2. Press **1 instruction** again and again. The memory highlight moves every time; the
   Pebble highlight sits on line 1 until the frame is made and `n` is stored, then
   jumps to line 2, `while n > 0`.
3. Keep going until line 3, `print(n)`, and on until the `call`. One more press and the
   Pebble pane says you are inside a ready-made routine: no line is highlighted, and
   the memory window shows the printing routine's own instructions. Press **Run** with
   180 and you come out the other side, on line 4, with `3` printed.
4. Whatever line is highlighted, press **1 cycle** and click down through the zoom
   panel as in the first tour. The gates you reach are working on that Pebble line,
   right now.
5. Press **Run** with 1000. The output says `3`, `2`, `1`, and the Pebble pane says
   "The program finished."
6. Change line 3 to `print(10 // (n - 1))` and press **Load Pebble**, then **Run**.
   It prints `5` and `10`, then `n - 1` reaches 0 and the pane says
   "Division by zero at line 3", with line 3 highlighted as the one to blame.

### The levels, in plain words

The page shows a one-line explanation and a pointer to the matching concept page at
every level you visit. These are the main ones.

| Level | What the page says | Read more |
|-------|--------------------|-----------|
| The whole circuit | The CPU and the RAM, as named parts | [Looking Inside a Circuit](looking-inside.md) |
| `ram` | 4K words of memory, every bit a latch of gates | [RAM](ram.md) |
| `cpu` | The processor: registers, the control unit, the ALU and the wires between | [What Is a CPU?](what-is-a-cpu.md) |
| `ir`, `pc`, `sp`, `phase`, `halt` | One register of the CPU | [Registers](registers.md) |
| `registers` | The register file, `r0` to `r7` | [The Control Unit](the-control-unit.md) |
| `decode`, `control`, `condition` | The control unit lighting the right wires | [The Control Unit](the-control-unit.md) |
| `sp_minus_1`, `sp_plus_1` | The stack pointer's adders | [The Stack](the-stack.md) |
| `alu` | Two numbers go in, a dial picks the job, a result comes out | [The ALU](the-alu.md) |
| `adder`, `bit0`, `full_adder`, `half_adder` | Adding, one column at a time | [Adding](adding.md) |
| `xor`, `and`, `or` | A gate built from NANDs | [Logic Gates from NAND](gates.md) |
| A gate | One NAND: its output is 0 only if both inputs are 1 | [Switches and NAND](switches-and-nand.md) |

### What Just Changed

Imagine a spot-the-difference puzzle: two photographs of the same room, one taken just
before you moved and one after. Circle everything that is different and the answer
leaps out. The Cockpit does this after every move. Before it moves the machine it
keeps a copy of the whole state (the session's `before`). Afterwards it compares
`before` with the machine as it is now, field by field, and the picture carries the
answer in a key called `changed`:

| Key in `changed` | What it lists |
|------------------|---------------|
| `registers` | The numbers of the registers whose value differs, such as `[1]` for `r1` |
| `pc`, `sp` | `true` if the program counter or the stack pointer moved |
| `flags` | The names of the flag lamps that differ: `zero`, `negative`, `carry`, `overflow` |
| `memory` | The addresses of the words of memory that differ |

The page uses these to mark the changed values, so your eye goes straight to what the
last button did. The marks always compare with the state *before the last move*,
whatever that move was: after a rewind they show what the rewind undid, and after you
load a new program they show how the new machine differs from the old one.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def what_changed() -> None:
    client = TestClient(create_cockpit(address_bits=6))
    machine = (await client.get("/api/machine")).json()
    print("at the start:", machine["changed"])
    machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    print("after one instruction:", machine["changed"])


run(what_changed())
# Output:
# at the start: {'registers': [], 'pc': False, 'sp': False, 'flags': [], 'memory': []}
# after one instruction: {'registers': [1], 'pc': True, 'sp': False, 'flags': [], 'memory': []}
```

The demo program's first instruction is `li r1, 255`. It changes `r1` and moves `pc`
on to the next instruction, and nothing else: the stack pointer, the flags and memory
are untouched, so those lists are empty. At the very start nothing has moved yet, so
nothing is marked.

**The stack window.** The page also shows the top of the **stack**, the pile of words
that `push` and `call` add to (see [The Stack](the-stack.md)). The picture's `stack`
holds up to 16 words, starting at `sp` (the top) and going up through memory, so the
newest word comes first. It is `[]` when `sp` is at the very end of memory, which is
where it starts: nothing has been pushed. Like every word, a stack word is only a
number: its `text` is that number read as if it were an instruction, which is rarely
meaningful, so look at its `word`.

### The Whole Program

The memory window shows 16 words at a time, which is a keyhole. `GET /api/listing`
shows the whole loaded program at once. It answers with `rows`, one for each word of
machine code the program was turned into, and `pebble`, which is the Pebble program as
a list of lines (or `null` for an assembly program). Each row has:

- `address` and `word`: where the word sits and its number.
- `text`: the line of source the word came from, as it was written. A shortcut such as
  `set r1, 0xFFFF` becomes *two* words, so both rows show the same line.
- `first`: `true` for the first word of its source line, `false` for the rest, so the
  page can show each line once.
- `labels`: the names of the **labels** (named bookmarks for an address, such as
  `loop`) that mark this address.
- `pebble_line`: the Pebble line that made this word, or `null` for assembly and for
  the ready-made routines.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit

COUNTDOWN = """\
let n = 2
while n > 0 {
    print(n)
    n = n - 1
}
"""


async def whole_program() -> None:
    client = TestClient(create_cockpit(address_bits=8))
    await client.post("/api/pebble", json={"source": COUNTDOWN})
    listing = (await client.get("/api/listing")).json()
    print(len(listing["rows"]), "words from", len(listing["pebble"]), "lines of Pebble")
    for row in listing["rows"][:3]:
        print(row["address"], row["word"], row["pebble_line"], row["labels"])
    print(listing["rows"][0]["text"])

    demo = TestClient(create_cockpit(address_bits=6))
    for row in (await demo.get("/api/listing")).json()["rows"][:4]:
        print(row["address"], row["first"], row["labels"])


run(whole_program())
# Output:
# 142 words from 5 lines of Pebble
# 0 49664 1 ['__main']
# 1 9358 1 []
# 2 13312 1 []
# getsp r1                ; r1 = the top of the stack, where the frame starts
# 0 True []
# 1 False []
# 2 True []
# 3 True ['loop']
```

Five lines of Pebble became 142 words, and the first three words all belong to line 1
(the frame, as in the Try It above). The translator's own label `__main` marks address 0.
In the demo, the two words at addresses 0 and 1 come from one `set` line, so `first` is
`true` and then `false`, and the word at address 3 carries the label `loop`.

### Zooming From Anything

Every value on the page is a number that lives somewhere real in the circuit, so every
value can be a doorway to it. The picture's `parts` key says where each one lives, as
a **scope** path that `/api/view` understands:

| Value | Where it lives |
|-------|----------------|
| Register `i` | `parts["registers"][i]`, such as `cpu.registers.r1` |
| `pc`, `sp`, the flags | `parts["pc"]` is `cpu.pc`, `parts["sp"]` is `cpu.sp`, `parts["flags"]` is `cpu.flags` |
| A word of memory or of the stack | The cell's own `part`, such as `ram.word4` |
| The current instruction | `parts["instruction"]`, chosen by what the instruction does (below) |

An instruction does not live in one place, so the Cockpit picks the part that does its
main work, using `part_for_instruction(word)` in `src/pycpu/cockpit/picture.py`:

| Instruction | Part |
|-------------|------|
| `add` and its cousins, `cmp`, `addi` | `cpu.alu`, which does the sums |
| `li`, `lhi` | `cpu.write_back`, which chooses what goes into the register |
| `load`, `store` | `cpu.address_mux`, which chooses the memory address |
| `jmp`, `br`, `call`, `ret` | `cpu.next_pc`, which works out where to go next |
| `push`, `pop`, `getsp`, `setsp` | `cpu.next_sp`, which works out the new stack pointer |
| `halt` | `cpu.halt`, the lamp that stops the machine |

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def zoom() -> None:
    client = TestClient(create_cockpit(address_bits=6))
    for _ in range(5):
        machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    print(machine["instruction"]["text"], "is zoomed to", machine["parts"]["instruction"])
    seen = (await client.get("/api/view", query={"path": machine["parts"]["instruction"]})).json()
    print([part["name"] for part in seen["children"]])
    print(machine["parts"]["registers"][1], machine["memory"][0]["part"])


run(zoom())
# Output:
# add r3, r3, r2 is zoomed to cpu.alu
# ['control', 'operand', 'adder', 'overflow', 'and_bus']
# cpu.registers.r1 ram.word4
```

Five instructions in, the demo is about to run `add r3, r3, r2`, so its zoom target is
the ALU, and `/api/view` shows the parts inside it. The test suite checks that every
path the picture can name is a real scope of the circuit, so a doorway never opens on
a wall.

### Following a Gate

When you step by a single gate, the picture says which gate just thought, in
`last_gate`: its `id`, its `value` (the new output) and its `path`, the part of the
circuit it belongs to, read from the circuit's own filing (`Circuit.scope_of`). Paste
the `path` into `/api/view` and you are standing at that gate. A move that is not one
gate thinking, such as an instruction step or a clock wire moving, leaves `last_gate`
as `null`, because nothing is faked.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def follow() -> None:
    client = TestClient(create_cockpit(address_bits=6))
    machine = (await client.post("/api/step", json={"size": "gate", "count": 100})).json()
    print(machine["last_gate"])
    machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    print(machine["last_gate"])


run(follow())
# Output:
# {'id': 10016, 'path': 'cpu.sp.bit12.slave', 'value': 0}
# None
```

After 100 gate steps the last gate to think was number 10,016 (a number that belongs to this small
6-bit machine and is different on a machine of another size), a part of the stack
pointer's own wiring, and it settled on 0. Then an instruction step ran many gates at
once, so there is no single last one to name and the answer goes back to `null`. The
picture also carries a `note`, one sentence about the last move, which is `null` for
now; later pages use it to say why a line step stopped.

### Variables

For a Pebble program, the picture's `variables` names the boxes of the code that is
running: `function` (the function's name, or `null` for the top level), `frame_pointer`
(the value of `r7`) and `names`. Each name has its `address`, its raw `word`, its `value`
read as a signed number (so the word 65535 shows as -1), its `kind` (`"parameter"` or
`"variable"`), the `part` to zoom to, and `hidden`. How the Cockpit finds them is on
[Variables in Memory](variables-in-memory.md). For an assembly program, inside a
ready-made routine, while a frame is still being built, and while the computer is
playing, `variables` is `null`.

`hidden` marks the compiler's own helpers. A `for` loop needs to remember where to stop,
so Pebble quietly makes a variable for the loop's end value and gives it a name that
starts with `$`, which no Pebble program could ever write. It is a real box in the frame,
so the Cockpit shows it, but marks it `hidden` so the page can keep it out of the way.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit

LOOP = """\
for i in range(3) {
    print(i)
}
"""


async def variables() -> None:
    client = TestClient(create_cockpit(address_bits=8))
    machine = (await client.post("/api/pebble", json={"source": LOOP})).json()
    while machine["pebble"]["line"] != 2:  # line 2 is print(i)
        machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    for name in machine["variables"]["names"]:
        print(name["name"], name["kind"], "hidden" if name["hidden"] else "shown", name["value"])


run(variables())
# Output:
# $for_limit_0 variable hidden 3
# i variable shown 0
```

The loop's end value, 3, sits in a box named `$for_limit_0`, and `i` is 0 on the first
time round.

## Why Does This Matter?

Without the Cockpit, a wrong answer from a program is a mystery: it prints 5 where you
expected 4 and you have no way to ask *where did it go wrong?* With the lid off you can
stop at the instruction that misbehaved, see which register held what, step through it
a beat or a gate at a time, and follow the 1 down to the single gate that got it wrong.
That is how engineers debug real chips, with probes and logic analysers that show
which wire is high right now, and how programmers debug programs, with a **debugger**
that pauses and steps through code.

The Pebble pane is the trick every real debugger plays. When you pause a Python or C
program on a line, the debugger is doing what the Cockpit does: the processor only knows
which machine instruction it is on, and a table made by the compiler, like our source
map, turns that address back into a line of your code. Without that table, the
computer could tell you only the address of an instruction, and nothing more.

It matters for teaching too. The promise of this project is "nothing is faked", and the
Cockpit is where you check that promise yourself. Every number on the page is read from
the gate engine, the computer made of NAND gates.

## What's Next

That finishes the third climb. You started with one NAND gate, built memory and a whole
computer from it, and now a program written in Pebble, a real programming language,
runs on that computer: translated into machine code, with its own frames, jumps,
routines and faults, and with every instruction traceable back to the line that made
it. Only part of Pebble runs on PyCPU so far: whole numbers, variables, `if`, `while`,
`for` over a range, functions and `print`. Lists, text in variables and the rest are
refused with a friendly message.

What comes next is the rest of the Cockpit: the Pebble pane becomes the left side of
the screen and you can step one *Pebble line* at a time, then drop from that line all
the way down to the gates. Until then, go back to
[the start of the story](../index.md) and see how far you have climbed.
