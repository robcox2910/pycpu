# Pausing and Rewinding

## Pause, Replay, Back to Live

Imagine watching a football match on television. The game races along, live. Then
something amazing happens near the goal, and you press **pause**. The picture freezes
just before the move starts. Now the channel switches you over to the **slow-motion
replay camera**, which filmed every tiny movement: you can nudge it forward a fraction
of a second at a time and watch exactly how the ball curled past the keeper. Missed
something? **Rewind** the replay to the start of the move and watch it again. When you
have seen enough, you press play: the replay finishes the move, and the television
jumps you back to the live match, which carries on from exactly where the replay
ended.

PyCPU can do the same with a running program. The live match is the **fast engine**,
which runs the program quickly with plain arithmetic. The slow-motion camera is the
**gate engine**, the computer built from NAND gates, where you can watch every gate
think (both engines are on [Two Engines](two-engines.md)). A `Computer` holds one of
each. It runs on the fast engine and, when you **pause**, it copies the whole machine
into the gates, so you can step forward one gate at a time, **rewind** to the start of
the instruction, and **resume** at full speed.

| The football match | In PyCPU |
|--------------------|----------|
| The live match | The fast engine, `computer.fast` (a `FastMachine`) |
| The slow-motion replay camera | The gate engine, `computer.gate` (a `GateMachine`) |
| The television, with its remote control | `Computer` in `src/pycpu/computer.py` |
| Pressing pause just before a move | `pause()`: stop between two instructions and copy the state into the gates |
| One move in the match | One instruction |
| Nudging the replay forward | `step(StepSize.GATE)`, `step(StepSize.CYCLE)`, `step(StepSize.INSTRUCTION)` |
| The frame where the move began | `instruction_start`: the saved `MachineState` at the start of the instruction |
| Rewinding the replay to that frame | `rewind()` |
| Pressing play to go back to live | `resume()`: finish the instruction in the gates, copy back, carry on fast |
| Whatever is on the screen right now | `state()`: the gate engine's state while paused, the fast engine's otherwise |

## Try It

This is the countdown from [Two Engines](two-engines.md). We run three instructions on
the fast engine, pause, and take 20 steps through the gates, printing a few of them.
Then we finish the current clock beat, which moves the program counter (`pc`, the
address of the next instruction, from [What Is a CPU?](what-is-a-cpu.md)) on by one.
We rewind, check that the machine is exactly back at the start of the instruction, and
resume to run the rest of the program fast.

```python
from pycpu.assembler import assemble
from pycpu.computer import Computer, StepSize

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
computer = Computer(assemble(source, words=64), address_bits=6)
computer.run(3)
computer.pause()
start = computer.instruction_start
print("paused before the instruction at address", start.pc)

for number in range(1, 21):
    micro = computer.step(StepSize.GATE)
    if number in (1, 3, 5, 10, 20):
        where = computer.gate.circuit.scope_of(micro.gate) if micro.kind == "gate" else micro.wire
        print("step", number, micro.kind, where, "is now", micro.value)
print("after 20 gate steps, any different?", computer.state() != start)

computer.step(StepSize.CYCLE)
print("after the fetch beat, pc is", computer.state().pc)
computer.rewind()
print("after rewind, pc is", computer.state().pc)
print("back at the very start?", computer.state() == start)

computer.resume()
computer.run(100)
print("printed:", computer.state().output_text)
# Output:
# paused before the instruction at address 3
# step 1 edge write is now 1
# step 3 edge write is now 0
# step 5 edge clk is now 1
# step 10 gate cpu.ir.bit0.slave is now 1
# step 20 gate cpu.ir.bit5.slave is now 0
# after 20 gate steps, any different? False
# after the fetch beat, pc is 4
# after rewind, pc is 3
# back at the very start? True
# printed: 321
```

Read the steps in order. First the `write` clock wire pulses up and down; this beat
writes nothing to memory, so only a gate in the RAM (`ram.and`) checks it and nothing
changes. At step 5 the `clk` wire rises, and the gates inside the **instruction
register** (`cpu.ir`, which holds the instruction being worked on) start to copy in the
fetched word: each bit's flip-flop has a *slave* latch, the second half that opens when
`clk` rises (see [The Clock](the-clock.md)). After 20 tiny steps, nothing that
`state()` reports has changed yet, because the instruction register is not part of the
saved state and the gates that hold `pc` have not had their turn yet. Finishing the
beat moved `pc` from 3 to 4. Rewinding put everything back, and the program still
printed `321`, exactly as if we had never paused.

## How It Works

**Pausing lands between two instructions.** The fast engine does a whole instruction
in one go, with plain Python: it never has a "half-way through" moment to show. So the
only moments it can pause at are the gaps *between* instructions, which we call
**instruction boundaries**. That is the frame just before the move. `pause()` asks the
fast engine for its `MachineState` (the sheet of paper holding every register, flag
and word of memory, from [Two Engines](two-engines.md)) and writes it into the gate
engine with `load_state`. `load_state` drops both clock wires to 0 and then writes each
value straight into the gates' storage cells (`poke`, from
[Registers](registers.md)), so the gate machine starts at the beginning of a fetch beat
holding exactly what the fast machine held. The same sheet is kept as
`instruction_start`, the frame to rewind to.

```
    running                   paused                        running
 ┌──────────────┐  pause()  ┌────────────────────────┐  resume()  ┌─────────────┐
 │ FAST ENGINE  │ ────────▶ │ GATE ENGINE            │ ─────────▶ │ FAST ENGINE │
 │ fast.py      │  state    │ cpu.py                 │  state     │ fast.py     │
 │ whole        │  copied   │ step: GATE, CYCLE,     │  copied    │ carries on  │
 │ instructions │  in       │       INSTRUCTION      │  back      │             │
 └──────────────┘           │ rewind(): reload       │            └─────────────┘
                            │   instruction_start    │
                            └────────────────────────┘
                 copies happen only at instruction boundaries
```

**Three sizes of step.** While paused, `step` moves the gate engine forward by one of
three sizes, `StepSize.GATE`, `StepSize.CYCLE` or `StepSize.INSTRUCTION`:

- **`GATE`** does the smallest thing there is: one gate works out its new output, or
  one clock wire moves up or down. It is `GateMachine.micro_step`, and `step` hands
  back the `MicroStep` that says what happened: its `kind` is `"gate"` (with the gate's
  number and its new value), `"edge"` (with the clock wire's name, `write` or `clk`,
  and its new value) or `"end"`, meaning the instruction has just finished. Each step
  also says which beat it belongs to, `FETCH` or `EXECUTE` (from
  [Fetch, Decode, Execute](fetch-decode-execute.md)). In the countdown, one
  instruction took between 6,313 and 13,403 of these tiny steps.
- **`CYCLE`** finishes the clock beat you are in. If you have not started one, it plays
  a whole beat.
- **`INSTRUCTION`** finishes the instruction you are in. If you are half-way through
  one, it completes *that* instruction; it does not run a whole extra one. If you are
  at a boundary, it plays one whole instruction.

Whenever a step reaches the end of an instruction, the machine is at a new boundary, so
`instruction_start` moves forward to the new state: the next rewind goes back to the
start of the *next* instruction. A halted machine (one that has run `HALT` or
faulted) stays where it is; every `GATE` step on it gives `"end"`.

**Rewinding is loading the saved frame.** `rewind()` simply loads `instruction_start`
into the gate engine again, the same way `pause()` did. It does not matter that you
might have stopped half-way through a beat with the `clk` wire up: `load_state` drops
the clock wires first, then writes every storage cell, so no half-finished beat is left
behind. The gate engine never runs backwards; it jumps back to a saved picture, the way
a replay jumps back to a recorded frame.

**Resuming finishes the move first.** The fast engine can only start at an instruction
boundary, because it has nowhere to keep "half an instruction". So `resume()` first
finishes the current instruction on the gate engine, then reads its state and loads it
into the fast engine with `load_state`, and the program runs on fast. If you paused at
a boundary and took no steps, there is nothing to finish, and the state is copied back
as it is. Because the two engines are checked to agree after every instruction
([Two Engines](two-engines.md)), finishing an instruction on the gates gives the same
state the fast engine would have reached: no drift (a tiny difference that builds up
over time). `tests/test_computer.py` checks this by pausing at random places, taking a
random number of gate steps, sometimes rewinding and stepping again, resuming, and
comparing the final state with a straight fast run.

**Who is in charge?** `state()` reads whichever engine is live: the gate engine while
paused, the fast engine otherwise. Some calls only make sense for one engine, so the
computer refuses the others: Python stops with an error called a `RuntimeError` (an
error that means "you can't do that right now"). It refuses:

- `run` while paused, because the fast engine is not live;
- `step`, `rewind` or `resume` while running, because there is nothing paused to step,
  rewind or resume;
- `pause` while already paused, because pausing again would copy the fast engine's old
  state over the gates and throw away the steps you have taken.

## Why Does This Matter?

Without pausing, you would have to choose: run a program fast and never see inside it,
or run it all on gates and wait over an hour for what the fast engine does in a second.
Pausing gives both. You let the fast engine race to the interesting part, then look at
it in as much detail as you like, down to a single gate. And rewinding means you can
look again and again at the one instruction that puzzles you, without starting the
whole program over.

Programmers use exactly this every day. A **debugger** is a tool that lets you pause a
program, step through it one line at a time and look at its values; every big
programming tool has one. Some debuggers can even run backwards, like the `rr` tool on
Linux (an operating system, the program that runs a computer's other programs), which
records a program as it runs so that you can rewind to the moment a bug happened. Chip
designers do the same with their slow gate-level simulators: run fast to just before the
problem, then switch to the slow, detailed view.

## What's Next

Now you can freeze the computer and creep through an instruction one gate at a time.
Next, do all of this with buttons, and watch the whole running computer, on
[The Bench](the-bench.md).
