# Choosing and Decoding

## Railway Points and a Hotel Panel

Two everyday pictures.

**Railway points.** Where a railway line splits, a lever decides which track
the train takes. Pull it one way and the train goes left; pull it the other
and it goes right. The train is not changed at all, the lever just *chooses*
which route it follows. A part that picks one of two inputs is called a
**mux** (short for *multiplexer*, a long word for "chooser").

**A hotel receptionist's panel.** Imagine a panel with one lamp for every room
in the hotel. A guest says "room 5" and exactly one lamp, number 5, lights
up. The other lamps stay dark. A part that takes a number and lights exactly
one line out of many is called a **decoder**. (It *decodes* the number into a
single line.)

| The story | In PyCPU |
|-----------|----------|
| The lever | The `select` wire |
| The track for lever-left, the track for lever-right | `when_0` and `when_1` |
| Where the train ends up | The wire `mux(c, select, when_0, when_1)` returns |
| A whole 16-bit train taking one route | `mux_bus(c, select, when_0, when_1)` |
| The room number the guest says | The `select` bus given to `decoder(c, select)` |
| One lamp per room | The bus of `2 ** len(select)` lines it returns |

## Try It

A mux with `when_0 = 1` and `when_1 = 0`. The lever picks which one comes
out:

```python
from pycpu.circuit import Circuit
from pycpu.logic import mux
from pycpu.simulator import Simulator

c = Circuit()
select = c.input("select")
chosen = mux(c, select, c.high, c.low)  # when_0 is always 1, when_1 is always 0
sim = Simulator(c)
for lever in (0, 1):
    sim.set(select, lever)
    sim.settle()
    print("select", lever, "-> output", sim.get(chosen))
print("a mux costs", c.gate_count, "NAND gates")
# Output:
# select 0 -> output 1
# select 1 -> output 0
# a mux costs 4 NAND gates
```

The same lever can steer a whole 16-bit number at once, and a decoder can
turn a 3-bit room number into one lit lamp out of eight:

```python
from pycpu.circuit import Circuit
from pycpu.logic import decoder, mux_bus
from pycpu.simulator import Simulator

c = Circuit()
lever = c.input("lever")
left = c.bus_input("left", 16)
right = c.bus_input("right", 16)
picked = mux_bus(c, lever, left, right)
sim = Simulator(c)
sim.set_bus(left, 0x1234)
sim.set_bus(right, 0xABCD)
for value in (0, 1):
    sim.set(lever, value)
    sim.settle()
    print(f"lever {value} -> {sim.get_bus(picked):#06x}")

panel = Circuit()
room = panel.bus_input("room", 3)
lamps = decoder(panel, room)
panel_sim = Simulator(panel)
panel_sim.set_bus(room, 5)
panel_sim.settle()
print("room 5 lamps:", [panel_sim.get(lamp) for lamp in lamps])
print("the decoder costs", panel.gate_count, "NAND gates")
# Output:
# lever 0 -> 0x1234
# lever 1 -> 0xabcd
# room 5 lamps: [0, 0, 0, 0, 0, 1, 0, 0]
# the decoder costs 35 NAND gates
```

## How It Works

Both parts are made from the gates on the [previous page](gates.md), which
are themselves made of NAND. Both live in `src/pycpu/logic.py`.

**The mux: let one answer through, block the other.** An AND gate with one
input held at 1 simply passes the other input along; with it held at 0 it
always says 0, so it *blocks*. A mux uses two such doors and opens exactly
one of them. The lever opens the `when_1` door directly, and a NOT of the
lever opens the `when_0` door. Whichever door is open lets its value
through, and an OR joins the two doors' outputs back into one wire:

```
   when_0 ───────[AND]──┐
                  │     [OR]── output
   when_1 ───────[AND]──┘
                  │
   door control:  top door  open when select = 0   (it gets NOT select)
                  lower door open when select = 1  (it gets select)
```

Written straight in NAND, the AND-then-OR collapses (two flips cancel out)
into just four gates: one NOT, and three NANDs.

```
not_select = NAND(select, select)
top    = NAND(when_0, not_select)
bottom = NAND(when_1, select)
output = NAND(top, bottom)
```

**The 16-bit mux.** `mux_bus` makes the NOT of the lever once and then gives
every bit its own three NANDs, so all sixteen bits follow the same lever.

**The decoder: one AND per room.** Room 5 is `101` in binary. The lamp for
room 5 should light only when bit 0 is **1**, bit 1 is **0** and bit 2 is
**1**. So we make the NOT of each bit, then for each room pick either the bit
or its NOT and AND them all together. That is 3 NOTs plus an AND of three
wires for each of the eight rooms. A NAND gate has only two inputs, so a
three-wire AND is built as two 2-input ANDs in a row, and each of those costs
2 NANDs (a NAND and a NOT): 2 x 2 = 4 NANDs. Hence the measured 35 gates
(3 + 8 x 4). Only the lamp whose pattern matches can be on, so exactly one is.

Here is just the wiring for lamp 5:

```
   bit 0 ────────────────────┐
                             [AND]──┐
   bit 1 ──[NOT]── not bit 1 ┘      [AND]── lamp 5
   bit 2 ───────────────────────────┘
```

Lamp 5 is on only if bit 0 is 1, bit 1 is 0 (so its NOT is 1) and bit 2 is 1.

## Why Does This Matter?

Choosing is how a computer makes decisions without a brain. The ALU will use
muxes to pick which result to send out; registers will use them to decide
between keeping an old value and taking a new one. Decoders are how the
computer turns an address, like "word number 2,731", into the one place in
memory to read or write. Without these two parts a computer could calculate
but never choose and never find anything.

## What's Next

You now have every everyday gate, the chooser and the decoder. Next, we
start doing arithmetic: wiring XOR and AND together into an adder that can add
two numbers. (That page comes next in the climb.)
