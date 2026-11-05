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

We load the `countdown` example on a small machine (8 address bits) and send one step
at each depth, from the top down. The Step label comes back in the picture's `steps`
key, and the part button is named after the part that is working. Then we load machine
code and ask for a line step, which it cannot do.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def look() -> None:
    client = TestClient(create_cockpit(address_bits=8, start_example="countdown"))
    for depth in ("line", "instruction", "part", "gate"):
        machine = (await client.post("/api/step", json={"depth": depth})).json()
        print(f"{depth}: now at pc {machine['pc']}, button says '{machine['steps'][depth]}'")
    await client.post("/api/program", json={"source": "li r1, 1\nhalt\n"})
    machine = (await client.post("/api/step", json={"depth": "line"})).json()
    print(machine["note"])


run(look())
# Output:
# line: now at pc 15, button says 'Step one line ▸'
# instruction: now at pc 16, button says 'Step one instruction ▸'
# part: now at pc 17, button says 'Step one stack pointer beat ▸'
# gate: now at pc 17, button says 'Step one gate ▸'
# This program is machine code, so it has no Pebble lines to step. Look closer to step an instruction.
```

The line step ran several instructions at once and `pc` jumped. The instruction step
moved it by one. The part step ran a clock beat, which started the next instruction
(`pc` moved by one as the CPU fetched it), and the gate step worked out one gate
inside it. The last message is not an error: the machine was left alone and the page
says, in plain words, what to do instead.

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
both; a depth the Cockpit has never heard of is a 400.

**A deeper step started mid-move finishes the smaller move first.** If you press Gate
five times and then Line, the machine is half way through an instruction. The line
step first finishes that instruction in the gates, then runs on to the next line, as
[Stepping a Pebble Line](stepping-a-pebble-line.md) describes. Nothing is skipped.

**A step that cannot move does not break.** A line step on machine code has no lines to
step, and nothing can step once the program has halted. In both cases the machine stays
exactly as it was and `note` holds one plain sentence.

**Climbing never moves the machine.** The trail of depths is kept by the page, not by
the computer. Going back up only changes how closely the glass looks.

**The part button is named for the part at work.** The picture's `steps["part"]` uses
`PART_NAMES` in `src/pycpu/cockpit/picture.py` to name the part that does the work of
the current instruction: "ALU" for a `sub`, "memory address" for a `store`.

## Why Does This Matter?

A beginner should not have to learn four different buttons. One Step button that is
as big as the glass is deep means you choose how closely to look, and the button
always does the sensible thing. Real debuggers do the same: "step over", "step into"
and "step one instruction" are the same idea at different depths.

## What's Next

Next, see how the Cockpit's whole picture fits together in
[A Tour of the Cockpit](a-tour-of-the-cockpit.md), following one line from Pebble all
the way down to a gate. A later page, What Just Happened, will explain the sentence the
page shows after each step.
