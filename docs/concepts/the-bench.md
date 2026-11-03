# The Bench

## A Workbench With the Lid Off

Imagine a radio on a workbench. Normally you only see the box: a dial, a speaker,
a smooth lid. But someone has taken the lid off, and now you can lean over and
see every wire and every part inside. Better still, the radio is switched on and
playing. You can freeze it in the middle of a note, nudge it forward a tiny bit at a
time, point at any part and say, "That one is carrying a signal *right now*."

The **Bench** is a web page on your own computer that does this for the whole
computer we have built. On it sits a real program, already loaded and paused at its
very first instruction. You can see the eight **registers** (the computer's small
named boxes for numbers, from [What Is a CPU?](what-is-a-cpu.md)), the program
counter, the stack pointer, the flags, a window onto memory with the current
instruction marked, and whatever the program has printed. Buttons move the machine
forward by one **gate**, a hundred gates, one clock beat or one whole
**instruction**; another button rewinds to the start of the instruction. And the zoom
panel lets you **zoom** (move from a big part into the smaller parts it is made of)
from the whole CPU down to a single NAND gate, with the real 0s and 1s on its wires.
Nothing on it is drawn from memory or faked.

| The workbench | In PyCPU |
|---------------|----------|
| The radio with its lid off | The Bench page, served by `python -m pycpu` |
| The radio, switched on and playing | A `Computer` (from [Pausing and Rewinding](pausing-and-rewinding.md)) running `DEMO_PROGRAM` |
| The dials on the front | `registers`, `pc`, `sp`, `flags` and `output`, read from `GET /api/machine` |
| The song sheet, with your place marked | The memory window: 16 words of memory, the current instruction highlighted |
| Nudging the music forward | `POST /api/step` with `"gate"`, `"cycle"` or `"instruction"` |
| Going back to the start of the note | `POST /api/rewind` |
| Letting it play for a while | `POST /api/run` |
| Putting a new song on | `POST /api/program`, with assembly text |
| A part you point at | A **scope**, such as `cpu.alu.adder` (see [Looking Inside a Circuit](looking-inside.md)) |
| The smallest part you can find | One NAND gate, with its two inputs and one output |
| The workshop door | `create_bench()` in `src/pycpu/bench/app.py` |

## Try It

The Bench is a small web app, but you can talk to it without opening a browser.
Python has a pretend browser for this, called `TestClient` (it sends requests
straight to the app, with no network). We open a small Bench, with 64 words of memory
so it builds quickly, and drive it the way the page's buttons do.

Three small words appear that you may not have met. A web request is a message that
has to wait for its reply, so the code that sends one is written as `async def` ("this
function may wait"), and each wait is marked `await` ("pause here until the answer
arrives"). `run(...)` is the starter button: it starts the waiting machinery and runs
our function to the end.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.bench.app import create_bench


async def visit() -> None:
    client = TestClient(create_bench(address_bits=6))
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
to its end, printing `321`, and asking for a step size the Bench does not know gets a
400.

To open the real thing, run this in a terminal, then visit the address it prints:

```text
uv run python -m pycpu
```

It serves the page at `http://127.0.0.1:8765`. The address `127.0.0.1` means "this
computer only", so nobody else on your network can see it. The real Bench has the full
4K words of memory, more than 600,000 NAND gates, so it says `Building the computer
from NAND gates...` and takes about 3 seconds (on the computer this page was written on)
before the address appears.

## How It Works

The Bench has three small parts, all in `src/pycpu/bench/`.

```
   your browser                               your computer
 ┌───────────────┐   GET /              ┌────────────────────────────────┐
 │  page.html    │ <─────────────────── │  app.py: create_bench()        │
 │               │                      │                                │
 │  registers    │   GET /api/machine   │  one Computer, paused:         │
 │  memory       │ <─────────────────── │   a fast engine and a gate     │
 │  buttons      │   POST /api/step     │   engine of real NAND gates    │
 │  load box     │   POST /api/rewind   │                                │
 │               │   POST /api/run      │  assemble / disassemble        │
 │  zoom panel   │   POST /api/program  │                                │
 │               │ ───────────────────> │  circuit_view reads the gates' │
 │               │   GET /api/view      │  own wires                     │
 └───────────────┘ <─────────────────── └────────────────────────────────┘
```

**`create_bench()`** assembles `DEMO_PROGRAM`, a short countdown written in assembly at
the top of `app.py`, builds a `Computer` with it and pauses it at once, so the machine
sits in the gate engine before its first instruction. It takes `address_bits`, the
number of memory address wires, just like `Computer` does; the real Bench uses the full
12 (4,096 words), and the Try It uses 6 (64 words) to build quickly. Every route
answers with the same picture of the machine, which the page redraws:

- `GET /api/machine` reads the paused gate engine's state: the eight `registers`, `pc`,
  `sp`, the four `flags`, `halted` and `halt_code`, the `output` printed so far, which
  beat is next (`phase`, `"fetch"` or `"execute"`) and whether the machine is between
  two instructions (`at_boundary`). `instruction` is the **current instruction**: the
  one at the address where it started, with its `word` and its `text`, turned back into
  assembly by `disassemble`. `memory` is 16 words starting 4 before `pc` (or at 0), so
  you can see a little behind and ahead; near the end of memory the window stops at the
  last word.
- `POST /api/step` takes `{"size": "gate"}`, `{"size": "cycle"}` or
  `{"size": "instruction"}` and calls `Computer.step` with that size (the three sizes
  from [Pausing and Rewinding](pausing-and-rewinding.md)). One instruction is thousands
  of gate steps: running the demo program on the full-size Bench, the quickest took
  6,988 and the slowest 43,045. The slow ones write to memory, because each data wire
  that changes wakes one gate in every one of the 4,096 words (on the small 64-word
  Bench the same program's instructions take 6,736 to 15,213). Clicking one gate at a
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
- `GET /api/view?path=cpu.alu` answers with `circuit_view` for that scope of the gate
  engine's circuit, exactly as before. A scope that does not exist, such as `cpu.nope`,
  gets a friendly 404 ("not found") answer that says `No part called cpu.nope`.

**The page** is plain HTML, CSS and JavaScript in one file, with nothing fetched from
anywhere else. Across the top are the step buttons (**1 gate**, **100 gates**,
**1 cycle**, **1 instruction**), **Rewind**, and **Run** with a box for how many
instructions. Below them are the registers and flags, the program's printed output, and
the memory window, where each word is shown as a number and as assembly, with the
current instruction highlighted. A text box takes your own assembly, and **Load**
sends it. Under all that is the zoom panel: it opens on `cpu`, lists the parts inside
with their gate counts, and draws each gate with its two inputs and its output, a wire
holding a 1 highlighted. Each level is labelled in one plain sentence, with the name of
the page that explains it. After every button the page reloads the part you are looking
at, so you can watch its wires change.

**Why can the page look inside at all?** Back in
[Looking Inside a Circuit](looking-inside.md), every gate was filed under the name of
the part it belongs to as it was built. `circuit_view` looks up that filing and reads
each gate's three wires from the gate engine's simulator. The Bench does no logic of
its own: it only asks the gate engine what is on each wire and what is in each
register, and shows you.

### A guided tour: from an instruction down to a gate

This is the Try It, done with the buttons. The RAM is built before the CPU, so on the
full-size Bench, with its much bigger RAM, the same two gates have bigger numbers than
the small Bench's 12678 and 12679: they are gates 610636 and 610637.

1. Open the Bench. The memory window highlights address 0, `li r1, 255`, and every
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

## Why Does This Matter?

Without the Bench, a wrong answer from a program is a mystery: it prints 5 where you
expected 4 and you have no way to ask *where did it go wrong?* With the lid off you can
stop at the instruction that misbehaved, see which register held what, step through it
a beat or a gate at a time, and follow the 1 down to the single gate that got it wrong.
That is how engineers debug real chips, with probes and logic analysers that show
which wire is high right now, and how programmers debug programs, with a **debugger**
that pauses and steps through code.

It matters for teaching too. The promise of this project is "nothing is faked", and the
Bench is where you check that promise yourself. Every number on the page is read from
the gate engine, the computer made of NAND gates.

## What's Next

That finishes the second climb: from RAM up to a whole computer that fetches, decodes
and executes instructions, with an assembler to write programs in and a Bench to watch
them run, all the way down to the gates. What we do not have yet is a friendly language
to write programs in: typing `li`, `add` and `store` by hand is slow. The next climb
builds **Pebble**, a small programming language, and a compiler that turns it into the
assembly you have just been reading. The Bench will grow into the **Cockpit**, where you
can pause a Pebble program and drop from a line of code down to the gates.
