# The Control Unit

## A Railway Signal Box

Picture a railway signal box, the little hut beside the tracks. Inside is a row of
levers, and each lever has a number. When the signaller pulls lever 7, exactly the
right signals turn green and exactly the right points click over for *route 7*. Pull
lever 3 and a different set of signals change. The signaller does not think about
trains. The wiring does the work: one lever number goes in, and the right set of
wires lights up.

A CPU has a signal box too. It is called the **control unit**: the part that looks at
an instruction and switches on the wires that make the rest of the machine do the
right job. The lever number is the **opcode**, the top four bits of every instruction
(see [Machine Code](machine-code.md)). Turning an opcode into "this one line is lit"
is called **decoding**, and you already met the gate pattern for it, the **decoder**,
in [Choosing and Decoding](choosing-and-decoding.md).

The control unit also needs somewhere to keep the numbers it is working on. That is
the **register file**: a row of eight lockers, `r0` to `r7`, each holding one 16-bit
number (a [register](registers.md)). The lockers have two **read windows** (you can
peek into any two lockers at the same moment) and one **slot** to post a new number
into one locker.

| The signal box and lockers | In PyCPU |
|----------------------------|----------|
| The lever number | The 4-bit opcode, in bits 15 to 12 of the instruction |
| Signals for one route lighting up | `opcode_lines(c, opcode)`: 16 wires, exactly one high |
| A signaller's question, "may the train go?" | `condition_met(c, cond, zero, negative, carry, overflow)` |
| The row of eight lockers | `RegisterFile`, with eight `Register`s named `r0` to `r7` |
| The two read windows | `bank.a` and `bank.b` |
| The slot and the locker number | `write` and `write_select` |
| A short number stretched to a long one | `sign_extend(c, bits, width)` |
| "Is this address off the end of the map?" | `outside_ram(c, address, ram_bits)` |

## Try It

Signals take a moment to travel through gates, so after we change an input we call
`sim.settle()`, which lets them finish travelling before we look at the answer.

We build a decoder and a "may we branch?" checker, then feed them. Each opcode lights
its own line, and each condition answers yes or no for the flags left behind by
`3 - 5` (negative, no carry, not zero).

```python
from pycpu.circuit import Circuit
from pycpu.cpu_parts import RegisterFile, condition_met, opcode_lines
from pycpu.isa import Condition, Opcode
from pycpu.memory import make_clock
from pycpu.simulator import Simulator

c = Circuit()
instruction = c.bus_input("instruction", 16)
lines = opcode_lines(c, instruction[12:])  # the top four bits
sim = Simulator(c)
for opcode in (Opcode.ALU, Opcode.LOAD, Opcode.BR, Opcode.HALT):
    sim.set_bus(instruction, (opcode << 12) | 0x0ABC)
    sim.settle()
    lit = [n for n, line in enumerate(lines) if sim.get(line)]
    print(f"{opcode.name:<5} lights line {lit}")
print("decoder gates:", c.gate_count)

c = Circuit()
cond = c.bus_input("cond", 3)
zero, negative, carry, overflow = (c.input(name) for name in ("z", "n", "c", "v"))
met = condition_met(c, cond, zero, negative, carry, overflow)
sim = Simulator(c)
sim.set(negative, 1)  # the flags after 3 - 5: negative, no carry
holding = []
for condition in Condition:
    sim.set_bus(cond, condition)
    sim.settle()
    if sim.get(met):
        holding.append(condition.name)
print("after 3 - 5 these hold:", ", ".join(holding))
print("condition gates:", c.gate_count)

c = Circuit()
clock = make_clock(c)
bank = RegisterFile(
    c,
    data=c.bus_input("data", 16),
    write=c.input("write_enable"),
    write_select=c.bus_input("write_select", 3),
    read_a=c.bus_input("read_a", 3),
    read_b=c.bus_input("read_b", 3),
    clock=clock,
)
print("register file gates:", c.gate_count)
# Output:
# ALU   lights line [0]
# LOAD  lights line [4]
# BR    lights line [8]
# HALT  lights line [15]
# decoder gates: 100
# after 3 - 5 these hold: NE, LT, LE, LTU
# condition gates: 24
# register file gates: 2161
```

## How It Works

All four parts live in `src/pycpu/cpu_parts.py`, and every one is built from the gates
on earlier pages. Each opens its own part (a *scope*) with a name, so the
[Bench](the-bench.md) can zoom in on it.

**1. Decoding the opcode.** `opcode_lines` is a decoder with four inputs. A decoder
makes sixteen AND gates, one for each possible opcode. Line 8 is "bit 3 is 1 AND bits 2,
1, 0 are 0", so it is high only for opcode 8 (`BR`). Exactly one line is ever high, and
that line is the lit signal for "this is a branch". It lives in the part `decode`.

```
 opcode bits       decoder         lit line
  1 0 0 0   ──►  [ 16 ANDs ]  ──►  0 0 0 0 0 0 0 0 1 0 0 0 0 0 0 0
 (bit3..bit0)                      line 8 (BR) is the one that is high
```

**2. Asking a condition.** A branch says *if this, jump*, where "this" is one of eight
questions about the four flag lamps. Look at the table of conditions on the
[instruction set](../reference/instruction-set.md) page: they come in pairs that are
opposites. `EQ`/`NE`, `LT`/`GE`, `LE`/`GT`, `LTU`/`GEU`. So we build only four
answers and let the lowest bit of `cond` flip the result when it is 1. The flipping is
done by an **XOR** gate, which gives 1 when its two inputs differ (see
[Logic Gates from NAND](gates.md)): XOR with 0 changes nothing, XOR with 1 flips.

Picking one of the four answers is a job for a **mux** (short for multiplexer): a
**chooser** that passes one of two inputs along, depending on a select wire (see
[Choosing and Decoding](choosing-and-decoding.md)). Two layers of muxes, a *chooser
tree*, pick one of four, steered by the top two bits of `cond`. It is the same kind of
tree the ALU uses to pick its answer.

```
 zero ────────────────────────┐
 negative XOR overflow (LT) ──┤  chooser tree      ┌─────┐
 zero OR LT (LE) ─────────────┼─ steered by ──────►│ XOR ├──► met
 NOT carry (LTU) ─────────────┘  cond bits 2,1     └──▲──┘
                                                       │
                                                  cond bit 0
```

"Less than" for signed numbers is `negative XOR overflow`: the answer is negative,
unless the sum overflowed and lied. It lives in the part `condition`.

**3. The register file.** `RegisterFile` makes eight `Register`s, named `r0` to `r7`,
all sharing one data bus. A register needs its `load` wire high to take the data. We
give register `n` the wire *`write` AND decoder line `n`*, where the decoder reads
`write_select`. So when `write` is 0 nobody loads; when `write` is 1 only the register
whose number is spelled by `write_select` loads, on the next beat of the clock.

To read, each of the two windows is a tree of choosers: eight registers, three
selecting wires. The first level picks between neighbouring pairs using bit 0, the next
level uses bit 1, and the last uses bit 2, leaving one register's value. We could have
used a decoder with an AND per bit and a big OR, but the tree is the same shape the ALU
already uses, so there is less new to learn, and it needs only 7 choosers per bit.
Both windows work at once because they are two separate trees. They live in the parts
`registers.read_a` and `registers.read_b`. The whole register file, measured by the
Try It above, is 2161 NAND gates.

**4. Two tiny helpers.** `sign_extend` stretches a short signed number (like the 6-bit
offset in `LOAD`) to 16 bits by copying its top bit into the new places, exactly the
idea from [Negative Numbers](negative-numbers.md). It builds no gates at all: it just
runs the same wire to several places. `outside_ram` ORs together every address bit at
or above the RAM size; if any is 1, the address is off the end of memory. It lives in
the part `address_check`.

## Why Does This Matter?

Without decoding, an instruction would be just sixteen meaningless bits. The control
unit is what gives them meaning: one lit line says "this is a branch" and the rest of
the machine obeys. Real processors have exactly this shape. The decoder is the
machine's reading comprehension, and the register file is its short-term memory. The
next page uses these parts to wire up a whole CPU.

## What's Next

You now have every part the CPU needs, built from gates. On the next page we wire them
to the RAM and a clock and watch the computer run a program by itself: read
[Fetch, Decode, Execute](fetch-decode-execute.md).
