# The ALU

## A Kitchen Multi-Tool With a Dial

Picture a kitchen gadget with two slots on top and a dial on the side. You drop
two ingredients into the slots, turn the dial to "chop", "mix", "blend" or
"squeeze" and out comes one result. Whatever the dial says, there is only one
machine: the same motor and the same box, doing one job at a time. Along the
front are some little indicator lights: one for "empty", one for "overflowing".

A processor has one of these. It is called the **ALU**, short for *arithmetic
logic unit* (arithmetic is sums, logic is things like AND and OR). Two numbers
go in, a **dial** (a few wires that spell a number) chooses the operation, and
one number comes out. Along with the result come four **flags**: single wires
that each answer a yes/no question about the result. A flag is just a lamp the
ALU switches on or off.

The four flags are:

- **zero**: is the result all zeros?
- **negative**: is the top bit (the sign bit from
  [Negative Numbers](negative-numbers.md)) on?
- **carry**: did a 1 fall off the end? For adding, that is the carry out of the
  top column. For subtracting, it is 1 when no borrow was needed. For a shift,
  it is the bit that was pushed out.
- **overflow**: did a signed add or subtract give an answer that does not fit?

| The kitchen gadget | In PyCPU |
|--------------------|----------|
| The two slots | The buses `a` and `b` |
| The dial | The 3-wire bus `op`, one of the eight `AluOp` values |
| The dish that comes out | `AluOutput.result` |
| The indicator lights | The flags `zero`, `negative`, `carry` and `overflow` |
| One motor, shared by every setting | One adder, in the part `alu.adder` |
| Picking the dish from the dial | A tree of choosers (muxes) steered by `op` |

The eight dial settings are `AluOp.ADD`, `SUB`, `AND`, `OR`, `XOR`, `SHL`,
`SHR` and `PASS_B`. A shift moves every bit one place along. `SHL` (shift left)
moves them towards the top, which doubles the number. `SHR` (shift right) moves
them towards the bottom, which halves it. A 0 is shifted in at the empty end.

## Try It

Build one ALU, then turn its dial through every setting with the same two
inputs, 12 and 5. The flags are printed after each result.

```python
from pycpu.arithmetic import AluOp, alu
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

c = Circuit()
a = c.bus_input("a", 16)
b = c.bus_input("b", 16)
op = c.bus_input("op", 3)
out = alu(c, a, b, op)
sim = Simulator(c)
sim.set_bus(a, 12)
sim.set_bus(b, 5)
for setting in AluOp:
    sim.set_bus(op, setting)
    sim.settle()
    print(
        f"{setting.name:<6} result {sim.get_bus(out.result):>5}",
        "zero",
        sim.get(out.zero),
        "negative",
        sim.get(out.negative),
        "carry",
        sim.get(out.carry),
        "overflow",
        sim.get(out.overflow),
    )

# The flags tell stories: each case below lights a different lamp.
cases = [
    (AluOp.ADD, 0xFFFF, 1),  # wraps to 0: zero and carry
    (AluOp.ADD, 0x7FFF, 1),  # 32767 + 1 does not fit: negative and overflow
    (AluOp.SUB, 5, 5),  # equal numbers: zero, and no borrow so carry
    (AluOp.SUB, 0, 1),  # had to borrow: negative, and carry is 0
]
for setting, x, y in cases:
    sim.set_bus(a, x)
    sim.set_bus(b, y)
    sim.set_bus(op, setting)
    sim.settle()
    print(
        f"{setting.name} {x:#06x}, {y:#06x} -> {sim.get_bus(out.result):#06x}:",
        "zero",
        sim.get(out.zero),
        "negative",
        sim.get(out.negative),
        "carry",
        sim.get(out.carry),
        "overflow",
        sim.get(out.overflow),
    )

# Zoom in on the real thing.
print("the ALU holds", c.children("alu"))
print("the adder holds", c.children("alu.adder")[:3], "...")
print("the whole ALU costs", c.gate_count, "NAND gates")
print("the adder alone costs", c.gate_count_in("alu.adder"), "of them")
# Output:
# ADD    result    17 zero 0 negative 0 carry 0 overflow 0
# SUB    result     7 zero 0 negative 0 carry 1 overflow 0
# AND    result     4 zero 0 negative 0 carry 0 overflow 0
# OR     result    13 zero 0 negative 0 carry 0 overflow 0
# XOR    result     9 zero 0 negative 0 carry 0 overflow 0
# SHL    result    24 zero 0 negative 0 carry 0 overflow 0
# SHR    result     6 zero 0 negative 0 carry 0 overflow 0
# PASS_B result     5 zero 0 negative 0 carry 0 overflow 0
# ADD 0xffff, 0x0001 -> 0x0000: zero 1 negative 0 carry 1 overflow 0
# ADD 0x7fff, 0x0001 -> 0x8000: zero 0 negative 1 carry 0 overflow 1
# SUB 0x0005, 0x0005 -> 0x0000: zero 1 negative 0 carry 1 overflow 0
# SUB 0x0000, 0x0001 -> 0xffff: zero 0 negative 1 carry 0 overflow 0
# the ALU holds ['control', 'operand', 'adder', 'overflow', 'and_bus', 'or_bus', 'xor_bus', 'select', 'flags']
# the adder holds ['bit0', 'bit1', 'bit2'] ...
# the whole ALU costs 896 NAND gates
# the adder alone costs 240 of them
```

## How It Works

The ALU is in `src/pycpu/arithmetic.py`, the same file as the adders, and is
built entirely from the gates and the adder below it. The big idea is to build
every answer, all the time, and then use the dial to pick one. Every setting's
answer is always being worked out; the dial just chooses which wire to listen to.

**1. One adder does both ADD and SUB.** As [Negative Numbers](negative-numbers.md)
showed, `a - b` is `a + NOT b + 1`. A flip is just an XOR with 1: XOR-ing a bit
with 0 leaves it alone, XOR-ing with 1 flips it. So we XOR every wire of `b`
with a wire called `sub`, which is 1 only when the dial says SUB. The same
wire `sub` is the adder's carry in. One adder, in the part `alu.adder`, serves
both settings, and costs 240 gates only once.

```
 dial ──► is it SUB? ──► sub ──┬──────────────────────┐
                               │                      │
  b ──► [XOR each bit with sub]┴─► ┌───────────────┐   │
  a ──────────────────────────────►│  16-bit adder │◄──┘ carry in
                                   └───┬───────┬───┘
                                       │       │
                                     sum    carry out
```

**2. The other answers come from `logic.py`.** `and_bus`, `or_bus` and
`xor_bus` give AND, OR and XOR for all sixteen bits at once. A shift is only
re-wiring, with no gates at all: for `SHL` the result is `low` followed by
bits 0 to 14 of `a`, and for `SHR` it is bits 1 to 15 followed by `low`. The bit
that fell out (bit 15 or bit 0) goes to the carry flag. `PASS_B` is just `b`.

**3. Eight answers, one dial: a tree of choosers.** A chooser (a *mux*, from
[Choosing and Decoding](choosing-and-decoding.md)) picks one of two. To choose
one of eight we use three layers of them, one layer per dial wire:

```
 layer 1 (dial bit 0)   ADD | SUB  -> m0      AND | OR      -> m1
                        XOR | SHL  -> m2      SHR | PASS_B  -> m3
 layer 2 (dial bit 1)   m0 | m1    -> n0      m2 | m3       -> n1
 layer 3 (dial bit 2)   n0 | n1    -> the result
```

That is 4 + 2 + 1 = 7 choosers, each one 18 wires wide.

The 18 wires are the sixteen result wires plus the carry and overflow flags
riding along, so each setting brings its own flags with it. `AND`, `OR`, `XOR` and `PASS_B` have `carry` and `overflow` held at 0.

**4. Where everything lives.** Zoom into `alu` and these are the parts, with
gate counts measured on the real circuit:

| Part | Gates | What it does |
|------|-------|--------------|
| `control` | 6 | Works out "is the dial on SUB?" |
| `operand` | 64 | Flips `b` when subtracting (16 XORs) |
| `adder` | 240 | The one ripple adder, columns `bit0` to `bit15` |
| `overflow` | 11 | The overflow check |
| `and_bus`, `or_bus`, `xor_bus` | 32, 48, 64 | The logic settings |
| `select` | 385 | The tree of choosers |
| `flags` | 46 | The zero check |

All together that is 896 NAND gates.

**5. The flags are small circuits on the result.** `zero` is `is_zero` from
`logic.py`, which ORs every bit together and then flips the answer (an OR followed by a
NOT is called a **NOR**, "not or"), so it is 1 only when no bit is on.
`negative` is simply bit 15 of the *wrapped* 16-bit result, with no gates,
so it is the sign of what the wires hold, not of the true answer. For a sum
that overflowed, the two can disagree, which is what the overflow lamp is for. `carry` is chosen as above. `overflow` fires when the two numbers
being added (after the flip for SUB) had the same sign bit and the answer has
a different one. Remember: two numbers on the same side of the circle landed
on the other side.

## Why Does This Matter?

Every arithmetic or logic step a computer ever takes goes through an ALU: adding
a score, comparing two numbers, masking bits, moving a position. The flags are
how programs make decisions. After `SUB a b`, the flags answer every question about how `a` and `b` compare:

| The question | The flags to read |
|--------------|-------------------|
| Is `a` equal to `b`? | `zero` is 1 |
| Is `a` smaller than `b`, as plain counting numbers? | `carry` is 0 (a borrow was needed) |
| Is `a` smaller than `b`, as numbers that may be negative? | `negative` differs from `overflow` |

The last row is because `negative` is the sign of the wrapped answer. If the
subtraction did not overflow, that sign is the truth. If it did overflow, the
sign is wrong, so we flip it.

And you have just seen what it is: 896 NAND gates, of which
240 are the one shared adder and 385 are the choosers that pick the answer.

**See it in the Cockpit.** The Cockpit has a guided walk about this page's idea, a subtraction worked out by gates. Start the Cockpit first with `uv run pycpu` (or `uvx --from fromscratch-pycpu pycpu` with no clone), then open [the walk](http://127.0.0.1:8765/#walk=subtracting-with-gates).

## What's Next

We can now calculate, but we cannot *remember*. Every answer vanishes the
moment the inputs change. The next page, [Remembering](remembering.md), shows
how two gates that listen to each other can hold on to a bit, and from there
the climb goes to [The Clock](the-clock.md) and [Registers](registers.md).
