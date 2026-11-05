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

The depths nest inside each other, like boxes inside boxes:

```text
  one line      |  n = n - 1                                                   |
                |                                                              |
  instructions  |  [load] [push] [li] [push] [pop] [pop] [sub] [push] ...      |
                |                                                              |
  beats         |  one instruction = [fetch beat] [execute beat]               |
                |                                                              |
  gates         |  one beat = hundreds of NAND gates, worked out one by one    |
```

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

## Why Does This Matter?

A beginner should not have to learn four different buttons. One Step button that is
as big as the glass is deep means you choose how closely to look, and the button
always does the sensible thing. Real debuggers do the same: "step over", "step into"
and "step one instruction" are the same idea at different depths.

## What's Next

To see the whole climb in one go, go back to
[A Tour of the Cockpit](a-tour-of-the-cockpit.md), which follows one line from Pebble
down to a single gate. A later page, What Just Happened, will explain the sentence the
page shows after each step.
