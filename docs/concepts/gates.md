# Logic Gates from NAND

## One Lamp, Many Questions

Picture a lamp wired to some light switches in a hallway. Depending on how
you wire the switches, the lamp answers a different yes-or-no question:

- "Is the switch **off**?" (one switch, lamp does the opposite)
- "Are **both** switches on?"
- "Is **at least one** switch on?"
- "Are the two switches **different** from each other?"

Each of those questions is a **logic gate**. They have names: **NOT**, **AND**,
**OR** and **XOR** (say "ex-or", short for "exclusive or"). On the last page,
[Switches and NAND](switches-and-nand.md), you met NAND, the lamp that is on unless *both* buttons are pressed. Here is
the big surprise: you do not need to buy four more kinds of part. You can make
all four from NAND alone, just by wiring NANDs together in clever ways. That
is why NAND is called a **universal gate**.

Every gate has a **truth table**: a list of every possible input with the
answer beside it. Here are all five side by side (`a` and `b` are the two
inputs; NOT only looks at `a`):

| a | b | NOT a | NAND | AND | OR | XOR |
|:-:|:-:|:-----:|:----:|:---:|:--:|:---:|
| 0 | 0 | 1 | 1 | 0 | 0 | 0 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1 |
| 1 | 0 | 0 | 1 | 0 | 1 | 1 |
| 1 | 1 | 0 | 0 | 1 | 1 | 0 |

And how the story maps onto PyCPU (all of these live in `src/pycpu/logic.py`):

| The hallway story | In PyCPU |
|-------------------|----------|
| "Is the switch off?" | `not_(c, a)` |
| "Are both on?" | `and_(c, a, b)` |
| "Is at least one on?" | `or_(c, a, b)` |
| "Are they different?" | `xor(c, a, b)` |
| A row of 16 switches sharing one question | `not_bus`, `and_bus`, `or_bus`, `xor_bus` |
| "Is any switch in this crowd on?" | `or_many(c, wires)` |
| "Is every switch in this row off?" | `is_zero(c, bus)` |

(Here `c` is the `Circuit` you are drawing on. Each function adds NAND gates
to it and hands back the wire where the answer will appear. The names `not_`
and `and_` end in an underscore only because Python already uses plain `not`
and `and` for something else.)

## Try It

First, build every gate and press every combination of `a` and `b`. The
answers come from the real NAND wiring, not from Python's own `and` and `or`:

```python
from pycpu.circuit import Circuit
from pycpu.logic import and_, or_, not_, xor
from pycpu.simulator import Simulator

c = Circuit()
a = c.input("a")
b = c.input("b")
outputs = [not_(c, a), c.nand(a, b), and_(c, a, b), or_(c, a, b), xor(c, a, b)]

sim = Simulator(c)
print("a b | not_a nand and or xor")
for a_value in (0, 1):
    for b_value in (0, 1):
        sim.set(a, a_value)
        sim.set(b, b_value)
        sim.settle()
        print(a_value, b_value, "|", *(sim.get(wire) for wire in outputs))
# Output:
# a b | not_a nand and or xor
# 0 0 | 1 1 0 0 0
# 0 1 | 1 1 0 1 1
# 1 0 | 0 1 0 1 1
# 1 1 | 0 0 1 1 0
```

It matches the table. Now the part that proves NAND is enough: count how many
NAND gates each one needed. Every gate is a fresh little circuit, and the
only part that circuit can contain is a NAND:

```python
from pycpu.circuit import Circuit
from pycpu.logic import and_, or_, not_, xor

for name, build in [("not_", not_), ("and_", and_), ("or_", or_), ("xor", xor)]:
    c = Circuit()
    a = c.input("a")
    if build is not_:
        build(c, a)
    else:
        build(c, a, c.input("b"))
    print(f"{name} used {c.gate_count} NAND gates")
# Output:
# not_ used 1 NAND gates
# and_ used 2 NAND gates
# or_ used 3 NAND gates
# xor used 4 NAND gates
```

## How It Works

Each gate below is a small recipe. In the pictures, `[N]` is one NAND gate and
the lines are wires. Where a wire splits in two, both halves carry the same
value.

**NOT: join the two inputs of a NAND.** NAND is only off when *both* inputs are
on. If both inputs are the *same* wire, they are always the same, so the gate
is off when that wire is on and on when it is off. That is NOT. One gate.

```
   a ──┬──[N]── not a
       └──┘
```

**AND: a NAND, then a NOT.** NAND is the opposite of AND (it is literally "not
and"). So flip NAND's answer and you have AND. Two gates.

```
   a ──┐
       [N]──┬──[N]── a AND b
   b ──┘    └──┘
```

**OR: flip each input first, then NAND.** Read NAND as "on, unless both are
pressed". Flip both inputs first and it becomes "on, unless both are *not*
pressed", which says the same thing as "on if at least one is pressed". That
is OR. (Mathematicians call this trick *De Morgan's law*.) Three gates.

```
   a ──┬──[N]──┐
       └──┘    [N]── a OR b
   b ──┬──[N]──┘
       └──┘
```

**XOR: the classic four.** XOR must be on when the inputs *differ*. Start with
`n = NAND(a, b)`, which is off only when both are on. Then NAND `a` with `n`,
and `b` with `n`, and NAND those two results together. Four gates.

```
   inputs        gate      output wire

   a, b     ──►  [N1]  ──►  n
   a, n     ──►  [N2]  ──►  p
   b, n     ──►  [N3]  ──►  q
   p, q     ──►  [N4]  ──►  a XOR b
```

How to read it: each row is one NAND gate. Its inputs are on the left and
the wire it drives is on the right. Wire `n` comes out of the first gate and
goes into the next two (it fans out), and `p` and `q` meet in the last gate.
Use it to trace any input by hand.

The same four gates, written as a list:

```
n   = NAND(a, b)      off only if both are on
p   = NAND(a, n)
q   = NAND(b, n)
out = NAND(p, q)
```

Check `a=1, b=1`: `n` is 0, so `p` and `q` are both 1, so `out` is 0. XOR says
"no, they are the same". Check `a=1, b=0`: `n` is 1, `p` is 0, `q` is 1, so
`out` is 1. XOR says "yes, different".

**Buses: do it sixteen times.** A word is 16 wires side by side (a *bus*).
`and_bus(c, a, b)` just builds one `and_` for each pair of matching wires and
returns the 16 answers as a new bus. If the buses are different widths there
is nothing sensible to pair up, so it raises a `ValueError`.

**Is any wire on?** `or_many` answers that question for a crowd of wires. You
could chain the ORs in a line, but then a change at the far end would have to
travel through every gate. Instead `or_many` arranges them as a tree, pairing
wires up, then pairing the pairs, and so on. Seven wires need only three
levels, so a change travels through three OR levels, not six. `is_zero` is
`or_many` followed by a NOT: a number is zero when *no* bit is on.

## Why Does This Matter?

This is the moment the project's big promise becomes real. A processor does
arithmetic, compares numbers and makes decisions, and every one of those is
built from AND, OR, NOT and XOR. Now you have seen each of them made of
nothing but NAND. There is no hidden trick: later pages that add numbers or
store them are just more wiring of the same one brick. This has been done for
real: the Apollo Guidance Computer, which helped steer the Apollo spacecraft to
the Moon, had its logic built from one type of gate (NOR, NAND's twin).

## What's Next

You have gates that answer yes-or-no questions. Next, [Choosing and Decoding](choosing-and-decoding.md)
uses them to build parts that *choose*: a switch that picks between two
numbers, and a panel that lights exactly one lamp out of many.
