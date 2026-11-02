# Registers

## A Row of Sticky Notes

Picture a row of sixteen sticky notes on a desk, each with a 0 or a 1 written
on it, and a label on the desk: "the score". You can read the whole row at any
time. To change the score you do not erase just one note; you wait for the
signal "update now", and if the signal says *yes, load the new score*, you
rewrite all sixteen at once. If it says *no*, the notes stay as they are.

That row is a **register**: a group of flip-flops, one for each bit of a
number, that all step on the same clock beat. The signal that says "update now"
is called **load**. If `load` is 1 when the beat comes, the register takes a
new number; if it is 0, it **holds** its old one. Wire a register to an adder
that adds 1, and each beat bumps the number up: that is a **counter**, the same
as the click-counter a doorman holds in his hand.

| The sticky notes | In PyCPU |
|------------------|----------|
| One note | One flip-flop, with a chooser in front |
| The row of sixteen | `Register(c, 16, data, load, clock, "score")` |
| Reading the score | `reg.q` (wires) or `reg.peek(sim)` (a number) |
| "Update now? Yes or no" | The `load` wire |
| The new score to copy | The `data` bus |
| The click-counter | A register fed by an adder that adds 1 |

## Try It

A register with `load` and 16 data wires: it holds, then loads. Then the
counter, which is a register whose data is "my own value, plus one". A wire
cannot be both a gate's output and an input to something built earlier, so we
make the data wires first, then connect them with `buffer_into`, which is two NOTs in a row (a NOT of
a NOT is the same value as the one you started with).

```python
from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.logic import buffer_into
from pycpu.memory import Register, make_clock
from pycpu.simulator import Simulator

c = Circuit()
clock = make_clock(c)
data = c.bus_input("data", 16)
load = c.input("load")
reg = Register(c, 16, data, load, clock, "score")
sim = Simulator(c)

reg.poke(sim, 0x1234)
print("poked:", hex(reg.peek(sim)))
sim.set_bus(data, 0xBEEF)
sim.tick(clock)
print("load=0, after tick:", hex(reg.peek(sim)))
sim.set(load, 1)
sim.tick(clock)
print("load=1, after tick:", hex(reg.peek(sim)))
print("register gates:", c.gate_count)

# A counter: 8 bits, always loading "my value plus one".
c = Circuit()
clock = make_clock(c)
next_value = tuple(c.wire_placeholder() for _ in range(8))
counter = Register(c, 8, next_value, c.high, clock, "counter")
one = (c.high, *([c.low] * 7))
total, _ = ripple_adder(c, counter.q, one, c.low)
for wire, bit in zip(next_value, total, strict=True):
    buffer_into(c, bit, wire)
sim = Simulator(c)
for beat in range(1, 301):
    sim.tick(clock)
    if beat in (1, 2, 3, 255, 256, 300):
        print("beat", beat, "counter =", counter.peek(sim))
# Output:
# poked: 0x1234
# load=0, after tick: 0x1234
# load=1, after tick: 0xbeef
# register gates: 178
# beat 1 counter = 1
# beat 2 counter = 2
# beat 3 counter = 3
# beat 255 counter = 255
# beat 256 counter = 0
# beat 300 counter = 44
```

## How It Works

`Register` is in `src/pycpu/memory.py`, built from the flip-flop on
[The Clock](the-clock.md) and the chooser (mux) from
[Choosing and Decoding](choosing-and-decoding.md).

**1. One bit.** Each bit is a flip-flop with a chooser in front of its data wire:

```
              ┌──────────────┐
   q ────────►│ 0            │
              │   chooser    ├──► [ flip-flop ] ──► q
   data ─────►│ 1  (by load) │        ▲
              └──────▲───────┘        │
                     │               clk
                    load
```

If `load` is 0 the chooser passes `q` itself back round, so on the beat the
flip-flop copies its own value: nothing changes. If `load` is 1 it passes the
new `data` bit. A register is sixteen of these side by side, sharing one `load`
and one `clk`. Each bit sits in its own part, `bit0` to `bit15`, so you can
zoom into any of them.

**2. The wire that is made early.** `q` is needed by the chooser before the
flip-flop that makes it exists, so we use `wire_placeholder`, exactly as in
the loop on the [Remembering](remembering.md) page.

**3. The counter.** Add 1 to `q`, send the answer back to the data wires, and
keep `load` at 1: each beat the register becomes its old value plus 1. An
8-bit counter has only 256 values, so after 255 it wraps round to 0, just like
the car odometer rolling over.

**4. Poke and peek.** `peek` reads the sixteen wires as a number. `poke` writes a
number straight into the flip-flops, with no beat, which is useful for setting
up an experiment. Each flip-flop has two latches inside it (master and slave),
so `poke` writes both; otherwise the master would still hold the old bit and
undo your number on the next beat. The pairs are registered with
`Circuit.state_pair` so that they can be found and written fast.

## Why Does This Matter?

The processor's own notebook is made of registers: where it is in the program,
the numbers it is adding right now. A counter that adds 1 each beat is the
heart of "step to the next instruction". Everything the machine remembers for
less than a blink lives in registers. Everything it remembers for longer
lives in the next page's big grid of the same bits.

## What's Next

A register holds one number. A computer needs thousands. On the next page we
stack up thousands of words and add an address to choose between them: RAM.
