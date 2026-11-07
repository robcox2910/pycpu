# The Magnifying Glass

## A Magnifying Glass Over a Map

Spread a big map of a country on the table. Your finger rests on the town you are
visiting. Hold a **magnifying glass** over it and you see one street. Move the glass
closer and you see one house; closer still, one brick. Your finger never moved. Only
the glass did, and the trail of where you zoomed is how you get back up.

The Cockpit works like that. The program on the left is the map, and the place it
will run next is your finger. The glass can look at **four depths**, and the one Step
button takes a step as big as the glass is deep.

| On the map | In the Cockpit | What Step does there |
|------------|----------------|----------------------|
| A street | **line**: one line of Pebble | Runs the whole line, then stops before the next one |
| A house | **instruction**: one machine instruction | Runs one instruction |
| A room | **part**: the piece of the CPU doing the instruction's work, such as the ALU | Runs one clock beat |
| A brick | **gate**: one NAND gate | Works out one gate |
| The trail back up | The page's own trail of depths | Nothing: climbing never moves the machine |

In code the depths are `Depth.LINE`, `Depth.INSTRUCTION`, `Depth.PART` and
`Depth.GATE`, and `Cockpit.step_at(depth)` takes the matching step.

## Try It

We load the `countdown` example on a small machine (8 address bits) and print where it
starts. Then we send one step at each depth, from the top down, and print `pc`, the
instruction waiting to run, and the Step button's label from the picture's `steps` key.
At the end we load an assembly program (machine code written as words) and ask for a
line step. It has no Pebble lines, so it cannot do one.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def look() -> None:
    client = TestClient(create_cockpit(address_bits=8, start_example="countdown"))
    machine = (await client.get("/api/machine")).json()
    print(f"start: pc {machine['pc']}, next instruction '{machine['instruction']['text']}'")
    for depth in ("line", "instruction", "part", "gate"):
        machine = (await client.post("/api/step", json={"depth": depth})).json()
        print(
            f"{depth}: pc {machine['pc']}, next '{machine['instruction']['text']}', "
            f"button '{machine['steps'][depth]}'"
        )
    await client.post("/api/program", json={"source": "li r1, 1\nhalt\n"})
    machine = (await client.post("/api/step", json={"depth": "line"})).json()
    print(machine["note"])


run(look())
# Output:
# start: pc 0, next instruction 'getsp r1'
# line: pc 15, next 'load r1, [r7-1]', button 'Step one line ▸'
# instruction: pc 16, next 'push r1', button 'Step one instruction ▸'
# part: pc 17, next 'push r1', button 'Step one stack pointer beat ▸'
# gate: pc 17, next 'push r1', button 'Step one gate ▸'
# This program is machine code, so it has no Pebble lines to step. Look closer to step an instruction.
```

Read it line by line:

- The line step ran the whole first line, many instructions, and `pc` jumped from 0 to 15.
- The instruction step ran one instruction, so `pc` moved from 15 to 16.
- The part step ran one clock beat of the `push` that was waiting. `pc` went to 17
  because the beat that fetches an instruction also moves `pc` on to the next word.
- The gate step worked out a single gate inside the next beat. A gate is only a tiny
  piece of a beat, and `pc` changes only when a fetch beat finishes, so `pc` stayed at 17.
- The part button says "stack pointer" because the waiting instruction is a `push`, and a
  `push` works by moving the stack pointer (see [The Stack](the-stack.md)).
- The last message is not an error. The machine was left alone, and the page says in
  plain words what to do instead.

## How It Works

Each depth is one of the moves from the pages before this one. The mapping lives in
`Cockpit.step_at` in `src/pycpu/cockpit/session.py`:

```text
  Depth        Step does                          Older name
  line         step_line(into=False)              size "line"
  instruction  step(StepSize.INSTRUCTION)         size "instruction"
  part         step(StepSize.CYCLE)               size "cycle"
  gate         step(StepSize.GATE)                size "gate"
```

`POST /api/step` takes either `{"depth": ...}` or the older `{"size": ...}`, never
both. A depth the Cockpit has never heard of is a 400, and so is a count: a depth step
always takes exactly one step.

The depths nest inside each other, like boxes inside boxes. This block measures the
real thing for the Pebble line `n = n - 1`: the instructions the translator made for
it, and how many gates the first one works out in each of its two beats. (The CPU has
exactly two phases, `Phase.FETCH` and `Phase.EXECUTE`, so every instruction is one
fetch beat and one execute beat.)

```python
from pycpu.assembler import disassemble
from pycpu.cockpit.session import Cockpit
from pycpu.computer import StepSize
from pycpu.cpu import Phase

cockpit = Cockpit(8)
cockpit.load_pebble("let n = 2\nn = n - 1\n")
translated = cockpit.translated
assert translated is not None
# Line 2 is `n = n - 1`; the `halt` the translator adds at the end belongs to no line we care about.
words = [
    disassemble(word, address)
    for address, word in enumerate(translated.program.words)
    if translated.line_at(address) == 2
]
words = [text for text in words if text != "halt"]
print(f"{len(words)} instructions:", ", ".join(words))
print("phases:", ", ".join(phase.name for phase in Phase))

computer = cockpit.computer
for _ in Phase:
    phase = computer.gate.phase
    gates = 0
    while True:
        micro = computer.step(StepSize.GATE)
        gates += micro.kind == "gate"
        if computer.gate.phase != phase or (micro.kind == "end" and computer.gate.at_boundary):
            break
    print(f"{phase.name} beat of the first instruction: {gates} gates")
# Output:
# 10 instructions: load r1, [r7-1], push r1, li r1, 1, push r1, pop r2, pop r1, sub r1, r1, r2, push r1, pop r1, store r1, [r7-1]
# phases: FETCH, EXECUTE
# FETCH beat of the first instruction: 400 gates
# EXECUTE beat of the first instruction: 3551 gates
```

Drawn with those exact figures (only the first two instructions are drawn in full):

```text
+- one line: n = n - 1 ---------------------------------------------------+
|                                                                         |
|  +- instruction: load r1, [r7-1] -----------------------------------+   |
|  |                                                                  |   |
|  |  +- FETCH beat ----------+   +- EXECUTE beat -----------------+  |   |
|  |  | 400 gates, one by one |   | 3551 gates, one by one         |  |   |
|  |  +-----------------------+   +--------------------------------+  |   |
|  |                                                                  |   |
|  +------------------------------------------------------------------+   |
|                                                                         |
|  +- instruction: push r1 --+   ... then li, push, pop, pop, sub,        |
|  |  FETCH beat, EXECUTE    |   push, pop and store: 10 instructions     |
|  +-------------------------+   in all                                   |
|                                                                         |
+-------------------------------------------------------------------------+
```

The picture's gate counts belong to the first instruction on a 256-word machine; other
instructions have their own counts.

**A bigger step pressed part-way through a smaller one finishes the smaller one first.**
Say you press Gate five times and then Line. The machine is part-way through an
instruction: five gates of a beat are done and the rest are not. Look at the diagram.
The line is made of instructions, so the line step first finishes that instruction in
the gates and then runs on to the next line, as
[Stepping a Pebble Line](stepping-a-pebble-line.md) describes. Nothing is skipped, and
the machine is always left on a clean boundary.

**A step that cannot move does not break.** A line step on an assembly program has no
lines to step, and nothing can step once the program has halted. In both cases the
machine stays exactly as it was and `note` holds one plain sentence.

**Climbing never moves the machine.** The trail of depths is kept by the page, not by
the computer. Going back up only changes how closely the glass looks.

**The part button is named for the part at work.** The picture's `steps["part"]` uses
`PART_NAMES` in `src/pycpu/cockpit/picture.py` to name the part that does the work of
the current instruction: "ALU" for a `sub`, "memory address" for a `store`, and "CPU"
when there is no instruction to name.

### Looking at a Part

At the part depth the glass can do more than step. It can show you what goes **into**
the part and what comes **out**, like holding a meter to the cables of a machine in a
factory. The meter clips onto cables that are already there. It never adds a cable and
never changes what flows down one.

Each cable here is a **bus**: a row of wires that carry one number together, lowest bit
first (see [Bits and Binary](bits-and-binary.md)).

| At the factory | In the Cockpit |
|----------------|----------------|
| A cable going into the machine | An input bus, such as the ALU's `a` and `b` |
| A cable coming out | An output bus, such as the ALU's `result` |
| The meter clipped onto a cable | A **tap**: a name for wires the CPU already has |
| The list of where you may clip | `GateMachine.taps` in `src/pycpu/cpu.py` |
| Reading the meter | `GET /api/part?path=cpu.alu` |

Here we load the countdown and run it, one instruction at a time, until the next
instruction is its `sub` and `n` (held in `r1`) is 2. Then we step one beat. That beat
is the fetch: the CPU picks up the `sub`, and the execute beat comes next. Now the ALU's
wires already carry the subtraction, so we read the part.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def look_at_the_alu() -> None:
    client = TestClient(create_cockpit(address_bits=8, start_example="countdown"))
    machine = (await client.get("/api/machine")).json()
    while not (machine["instruction"]["text"].startswith("sub") and machine["registers"][1] == 2):
        machine = (await client.post("/api/step", json={"depth": "instruction"})).json()
    print(f"waiting: '{machine['instruction']['text']}', r1 {machine['registers'][1]}")
    machine = (await client.post("/api/step", json={"depth": "part"})).json()
    print(f"after one beat the next beat is: {machine['phase']}")
    part = (await client.get("/api/part?path=cpu.alu")).json()
    print(f"looking at the {part['name']}")
    for bus in part["inputs"]:
        print(f"  in:  {bus['name']} = {bus['value']}")
    for bus in part["outputs"]:
        print(f"  out: {bus['name']} = {bus['value']}")


run(look_at_the_alu())
# Output:
# waiting: 'sub r1, r1, r2', r1 2
# after one beat the next beat is: execute
# looking at the ALU
#   in:  a = 2
#   in:  b = 1
#   out: result = 1
#   out: flags = 4
```

The ALU is being asked to work out `2 - 1`, and its `result` wires already say 1. When
the execute beat runs, that 1 is what goes into `r1`. `flags` is the ALU's four lamps
read as one number: the zero lamp counts 1, negative 2, carry 4 and overflow 8. Each lamp
is worth double the one before, like the bits of any number, so 4 is the third bit. Only
the carry lamp is lit, so it reads 4. (A subtraction that does not need to borrow
lights carry, see [The ALU](the-alu.md).)

**These numbers are read from the real wires.** A tap is only a name for a row of wires
the CPU was already built with, the same wires the gate view reads. To show a value,
the Cockpit asks the simulator for each wire, one bit at a time, and adds the bits up.
Nothing works out `2 - 1` in Python; the gates did that.

```text
  register r1 --- a (16 wires) ---+
                                  |      +-----+
                                  +----->|     |--- result (16 wires) ---> write-back
                                         | ALU |
  register r2 --- b (16 wires) --------->|     |--- flags (4 wires) -----> flags register
                                         +-----+
       each tap is a name for one of these rows of wires;
       the meter reads every wire with simulator.get
```

Every part the part button can name has taps, except the whole `cpu`, which is too big
to have one set of inputs and outputs. Asking for a part with no taps answers 404.

**While playing there is nothing to read.** When the computer plays, the fast engine
runs it and the gates stand still, so their wires are not live. `/api/part` then
answers 409 with "the computer is running: press pause first". That is stricter than
`/api/view`, which while playing shows the gates as they were when last paused: a
drawing of the gates can be old, but a meter reading must be the real value now.

## Why Does This Matter?

A beginner should not have to learn four different buttons. One Step button that is
as big as the glass is deep means you choose how closely to look, and the button
always does the sensible thing. Real debuggers do the same: "step over", "step into"
and "step one instruction" are the same idea at different depths.

## What's Next

Every Step, at every depth, ends with one plain sentence saying what the machine just
did. Read [What Just Happened](what-just-happened.md) to see how that sentence is
written from the real numbers.
