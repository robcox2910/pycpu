# Two Engines

## A Flip-Book and a Slow-Motion Camera

Imagine filming a juggler with two cameras at once. The first is a flip-book camera:
it snaps one picture each time a ball changes hands, and it is so quick that you can
flick through a whole minute of juggling in a second. The second is a slow-motion
camera: it films every tiny movement of every finger, so you can pause it and see
exactly how a catch happens. It is wonderful to watch, and it takes ages.

Most of the time you want the flip-book, because you want to see the whole act. But
why should you trust it? It skips everything between the pictures. The answer is to
check: lay the two films side by side and look at them **frame by frame**. If every
flip-book picture matches the slow-motion film at the same moment, then the flip-book
is telling the truth, even about the parts it skips.

PyCPU has two cameras like that, called **engines** (an engine is the part that
actually runs the program). The **gate engine** is the computer we built from NAND
gates: every add, every choice and every stored bit is real gates working. The **fast
engine** follows exactly the same rules with ordinary Python arithmetic, the way you
would work a sum out in your head instead of with a pile of switches. Running the two
side by side and comparing them after every single instruction is called running them
in **lockstep**, like soldiers marching so close together that their feet hit the
ground at the same moment.

| The two cameras | In PyCPU |
|-----------------|----------|
| The slow-motion camera | The **gate engine**: `GateMachine` in `src/pycpu/cpu.py` |
| The flip-book camera | The **fast engine**: `FastMachine` in `src/pycpu/fast.py` |
| One picture of the juggler | A `MachineState`: every register, flag and word of memory |
| Laying the films side by side, frame by frame | The **lockstep** tests in `tests/test_lockstep.py` |
| Starting the juggler mid-throw | Loading a random state with `load_state` |
| Timing each camera | `measure_engines` in `src/pycpu/proof.py` |

## Try It

This program counts down from 3 and sends each digit to the output port (the computer's
screen, from [Fetch, Decode, Execute](fetch-decode-execute.md)). We load it into both
engines, step them together, and after every step check that the two whole machines
are equal: every register, every flag, every word of memory and everything printed.

```python
from pycpu.assembler import assemble
from pycpu.cpu import GateMachine
from pycpu.fast import FastMachine

source = """
    set r1, 0xFFFF    ; the output port's address
    li r2, 3          ; count down from 3
loop:
    li r3, 48         ; 48 is the character '0'
    add r3, r3, r2    ; '0' + r2 is the digit for r2
    store r3, [r1]    ; send it to the screen
    addi r2, -1
    br ne, loop       ; again, until r2 reaches 0
    halt
"""
gate = GateMachine(address_bits=6)
fast = FastMachine(gate.words)
program = assemble(source, words=gate.words).words
gate.load_program(program)
fast.load_program(program)

steps = matching = 0
while fast.step():
    gate.step()
    steps += 1
    if gate.state() == fast.state():
        matching += 1
print("steps:", steps, "matching:", matching)
print("fast engine printed:", fast.state().output_text)
print("gate engine printed:", gate.state().output_text)
print("gates in the CPU:", gate.circuit.gate_count_in("cpu"))
print("gates in the whole machine:", gate.circuit.gate_count)
# Output:
# steps: 19 matching: 19
# fast engine printed: 321
# gate engine printed: 321
# gates in the CPU: 6029
# gates in the whole machine: 15525
```

Nineteen instructions, nineteen matching frames. The fast engine got there by doing
sums; the gate engine got there by sending signals through 15,525 NAND gates. The
fast engine has no gates at all, which is the whole point of it.

We print gate counts but no timings, because the counts are the same on every computer
and the timings are not. To time both engines at full size on your own computer, run
this in a terminal:

```text
uv run python scripts/measure_engines.py
```

## How It Works

**Two engines, one rule book.** Both engines follow the
[instruction set](../reference/instruction-set.md), and they are built from very
different layers.

```
          one instruction, say  add r3, r3, r2
                    │
       ┌────────────┴─────────────┐
       ▼                          ▼
  FAST ENGINE                GATE ENGINE
  fast.py                    cpu.py
  decode(word)               instruction register, opcode lines
  alu_model(a, b, ADD)       alu(): 16 full adders of NAND gates
  registers[3] = result      register r3 loads at the clock's rise
  (a few lines of Python)    (thousands of gates settle, two beats)
       │                          │
       ▼                          ▼
  MachineState  ───── equal? ─────  MachineState
```

The fast engine's `alu_model` works out an `add` with Python's `+`, and its flags with
a few comparisons. The gate engine's `alu` is the one from [The ALU](the-alu.md): the
same answer arrives after the carries ripple through the adders. Both engines can write
their whole state onto the same sheet of paper, a `MachineState` (see
`src/pycpu/state.py`), and two sheets can be compared with `==` in one go.

**Lockstep.** `tests/test_lockstep.py` loads the same state into both engines, steps
both, and compares the two sheets after *every* step, not just at the end. Comparing
only at the end would miss two mistakes that cancel out, like a film that drops a frame
and then doubles the next one.

**Starting mid-throw.** A test that only ran sensible programs would only check the
sensible paths. So the first lockstep test makes up whole machines at random: random
memory, random registers, random `pc` and `sp`, random flags. Every 16-bit word means
*something* to this CPU, so random memory is a random program, full of strange jumps,
loads from far outside memory and stack pointers in silly places. The random states are
made by a library called **Hypothesis**, which invents test cases for you and, when one
fails, shrinks it to the smallest example that still fails. It tries 200 random machines,
each for up to 30 steps. A second test does the same with 200 random programs written in
real assembly language, and a third pins one tricky case: an instruction that overwrites
the very next instruction in memory. Both engines must then fetch the *new* word.

**Does the checking really catch anything?** To find out, we broke the fast engine on
purpose: we made `shr` forget the bit it shifts out. The random-state test found a
machine where the two engines' carry flags differed, and failed, as it should. Then we
put the fast engine back.

**Timing them.** `measure_engines` in `src/pycpu/proof.py` builds the full-size
computer, with all 4,096 words of RAM made of real gates, and runs one mixed program on
both engines. The program loops forever through sums, a store and a load, a push and a
pop, a call and a return, and a branch. The memory after the program is filled with
mixed-up numbers, as on [How Big Is Our Memory?](how-big-is-our-memory.md), so the
gates have real work to do. Before any figure counts, the gate engine's state after its
timed instructions must equal the fast engine's after the same number of steps: a quick
camera that films the wrong juggler proves nothing.

Measured on 2 November 2026, on one laptop: an Intel Core i7-9750H at 2.60 GHz with
16 GB of memory, running macOS 26.5 and Python 3.14.3.

| Test | Measured | Limit | Passed? |
|------|----------|-------|---------|
| Gates in the CPU (outside the RAM) | 6,023 | (no limit) | |
| Gates in the whole machine | 613,477 | (no limit) | |
| Build the gate machine and its simulator | 2.83 seconds | under 30 | yes |
| Peak memory | 113 MiB | under 1,024 | yes |
| Load a whole state into the gates (`load_state`) | 0.106 seconds | under 2 | yes |
| Read a whole state back out (`state()`) | 0.013 seconds | under 2 | yes |
| One instruction on the gate engine | 0.0236 seconds | under 0.5 | yes |
| Instructions per second on the fast engine | 176,811 | over 50,000 | yes |

The times for loading, reading and one instruction are **medians** (line the times up
from fastest to slowest and take the middle one), of 5, 5 and 60 tries. The fast
engine's figure comes from one run of 300,000 instructions. Five fresh runs on the same
laptop gave between 153,618 and 176,811 instructions per second for the fast engine, and
between 0.0233 and 0.0251 seconds per instruction for the gate engine. Your computer
will give different times; the gate counts will not change. (The full-size CPU has 6,023
gates, six fewer than the 6,029 in the Try It. Checking whether an address is outside a
bigger RAM needs fewer gates, because fewer address bits are left over to check: 9 gates
instead of 27. But the bigger RAM has six more address wires to connect, which costs 12
gates. 18 saved, 12 spent: 6 fewer.)

**How much faster is the flip-book?** 0.0236 seconds per instruction means the gate
engine manages about 42 instructions a second. The fast engine does 176,811. That makes
the fast engine roughly **4,000 times** quicker. A program that takes the fast engine one
second would keep the gate engine busy for over an hour.

## Why Does This Matter?

Without a fast engine, every program would crawl along at about 42 instructions a
second. A program that runs a million instructions would take the gate engine more than
six hours, and the fast engine under six seconds. Without the gate engine, there would be nothing real to
look inside: no gates to zoom into, no wires lighting up. We want both, and lockstep is
what lets us have both honestly. Because the two engines are checked frame by frame,
the fast engine can do the running and the gate engine can do the showing, and they are
telling the same story.

Real chip makers do this too. Before a new processor is made, its designers describe it
in a hardware language and run that description in a simulator, gate by gate, which is
very slow. Alongside it they keep a quick model written as ordinary software, often
called a *reference model*, and they run the two together on huge numbers of random
programs, comparing them instruction by instruction. Any difference is a bug, found
before anything is made in silicon, when fixing it is cheap. Game console emulators,
which let a laptop pretend to be an old games machine, are fast engines of the same kind.

## What's Next

The fast engine runs and the gate engine shows. Next we want to switch between them in
the middle of a program: run quickly, freeze, look at the gates, then carry on. The
page for that is still being written. For now, look inside the parts we have built,
gate by gate, with [The Bench](the-bench.md).
