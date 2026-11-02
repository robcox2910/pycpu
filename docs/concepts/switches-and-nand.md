# Switches and NAND

## The Lamp With Two Switches

Imagine a lamp wired up a slightly odd way. There are two push-button
switches, and the lamp is **on all the time**, except when you press **both**
buttons at once. Press just one, or neither: lamp on. Press both: lamp off.

That odd little lamp is the most important thing in this whole project. It is
called a **NAND gate**. "NAND" is short for "NOT AND": the ordinary "AND"
would switch the lamp on only when *both* buttons are pressed, and NAND does
the exact opposite.

A **gate** is a small part with some inputs (the buttons) and an output (the
lamp) that follows a fixed rule. A **wire** is the thing that carries one bit,
on or off, from where it is made to where it is used. The rule of a gate can
be written as a **truth table**: a list of every possible input, with the
answer next to it. NAND's truth table has only four rows:

| left button | right button | lamp |
|:-----------:|:------------:|:----:|
| 0 | 0 | 1 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | **0** |

Here is how the story maps onto PyCPU:

| The lamp story | In PyCPU |
|----------------|----------|
| A wire carrying on or off | A `Wire`, which is just a whole number naming it |
| A button you can press | `circuit.input("left")` |
| The lamp-and-two-buttons part | `circuit.nand(left, right)` |
| The whole pile of parts and wires | A `Circuit` (the **netlist**) |
| Someone who presses buttons and looks at lamps | A `Simulator` |
| Wire that is always off, wire that is always on | `circuit.low`, `circuit.high` |

## Try It

Build the lamp circuit, then press every combination of buttons and write
down what the lamp does. We have just made the truth table above, with a real
circuit:

```python
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

circuit = Circuit()
left = circuit.input("left")
right = circuit.input("right")
lamp = circuit.nand(left, right)

sim = Simulator(circuit)
print("left right lamp")
for left_value in (0, 1):
    for right_value in (0, 1):
        sim.set(left, left_value)
        sim.set(right, right_value)
        sim.settle()
        print(f"  {left_value}     {right_value}     {sim.get(lamp)}")
print("gates:", circuit.gate_count, "wires:", circuit.wire_count)
# Output:
# left right lamp
#   0     0     1
#   0     1     1
#   1     0     1
#   1     1     0
# gates: 1 wires: 5
```

Why five wires? Two are the buttons, one is the lamp, and two more are
built in to every circuit: `circuit.low` (a wire that is always `0`) and
`circuit.high` (always `1`). You will want them later.

## How It Works

**One brick for everything.** NAND looks too simple to matter, but here is
the secret: you can build *every* other logic part out of NAND gates. If you
join the two inputs of a NAND together, it flips: on becomes off, off becomes
on. That is a NOT. Chain a NAND and a NOT and you get an AND. A few more and
you get OR, then adders, then memory, then a processor. Each is just NAND
gates joined by wires. So PyCPU has exactly one primitive, and the rest of
the climb builds on it.

```
   left  ──┐
           ├──[ NAND ]──── lamp
   right ──┘
```

**A circuit is a list.** A `Circuit` (in `src/pycpu/circuit.py`) is not
anything magical. It is a numbered list of wires and a list of gates. Each
gate is written as three numbers: which wire is its first input, which is its
second input, and which wire it drives. For our lamp:

```
wire 0 = low   wire 1 = high   wire 2 = left   wire 3 = right   wire 4 = lamp
gate 0: inputs (2, 3), output 4
```

That list is called a **netlist**. A real chip designer's netlist is just a
much longer list of the same kind. Notice that the `Circuit` only *describes*
the wiring. It never works out a lamp's value. That is the `Simulator`'s job,
which the next page explains.

## Why Does This Matter?

Every computer you have ever used, from a pocket calculator to the biggest
supercomputer, is at the bottom a huge collection of tiny switches that obey
rules like this one. Chip makers really do build whole processors from a
single repeated kind of gate. Understanding that one humble gate is the key
that unlocks the rest of this project: if NAND is enough to build everything,
then there is no magic anywhere, only more NAND.

## What's Next

You can describe a circuit, but who works out what the lamps do? The next page,
[Simulating a Circuit](simulating-a-circuit.md), shows how Python pretends to
be electricity, using a clever trick that only does work where something
changed.
