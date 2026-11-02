# Looking Inside a Circuit

## A Map You Can Zoom

Open a map app and you see a whole country. Tap a town and the map zooms in
to its streets. Tap a street and you see its houses. Tap a house and you see
the rooms. Nothing on the screen was drawn to look pretty: it is the real
place, shown at a different size each time you zoom.

We want to do the same with a circuit. A computer is millions of NAND gates,
far too many to look at in one go. But the gates are built in groups: a few
gates make an XOR, some XORs make an adder, some adders make a calculator. If
we **label each group with a name**, we can start with the biggest groups and
**zoom** into any of them, all the way down to single gates.

A named group of gates is called a **scope** (the part of the circuit a name
covers). Scopes sit inside each other like countries, towns and streets, so we
write one as a path with dots between the names, like `alu.adder.bit1`. The
empty path `""` means the whole circuit.

| The map | In PyCPU |
|---------|----------|
| The country, town, street, house | Scopes, one inside the next |
| The address "Main Street, Springfield" | A dotted path such as `"alu.adder"` |
| The whole country | The empty path `""` |
| Tapping a town to zoom in | Asking `circuit_view` for a longer path |
| A house | One NAND gate |
| Seeing who is home right now | The 0 or 1 on each of the gate's wires |
| A map that shows the real place | A view that reads the simulator's own values (**real**) |
| A map someone drew from memory | A **faking** view, which PyCPU never makes |

## Try It

We build an XOR gate inside a part called `half_adder`, switch both inputs
on, and then zoom in twice: first to the part, then to the XOR inside it.

```python
from pycpu.circuit import Circuit
from pycpu.logic import xor
from pycpu.simulator import OscillationError, Simulator
from pycpu.view import circuit_view

c = Circuit()
a = c.input("a")
b = c.input("b")
with c.scope("half_adder"):
    total = xor(c, a, b)

sim = Simulator(c)
sim.set(a, 1)
sim.set(b, 1)
sim.settle()

top = circuit_view(sim, "")
print("the whole circuit holds:", top["children"])
inside = circuit_view(sim, "half_adder")
print("half_adder holds:", inside["children"])
zoomed = circuit_view(sim, "half_adder.xor")
for gate in zoomed["gates"]:
    print(gate)
print("the xor answer wire", total, "holds", sim.get(total))

# A ring that never settles, built inside two nested parts. A gate cannot read a
# wire that does not exist yet, so we make the wire first (`wire_placeholder`)
# and then connect the gate that drives it (`nand_into`).
ring = Circuit()
with ring.scope("clock"), ring.scope("ring"):
    loop = ring.wire_placeholder()
    ring.nand_into(loop, loop, loop)  # a NOT gate that feeds itself
try:
    Simulator(ring, max_events=1000)
except OscillationError as error:
    print(error)
# Output:
# the whole circuit holds: [{'name': 'half_adder', 'gate_count': 4}]
# half_adder holds: [{'name': 'xor', 'gate_count': 4}]
# {'id': 0, 'a': 2, 'b': 3, 'out': 4, 'value_a': 1, 'value_b': 1, 'value_out': 0}
# {'id': 1, 'a': 2, 'b': 4, 'out': 5, 'value_a': 1, 'value_b': 0, 'value_out': 1}
# {'id': 2, 'a': 3, 'b': 4, 'out': 6, 'value_a': 1, 'value_b': 0, 'value_out': 1}
# {'id': 3, 'a': 5, 'b': 6, 'out': 7, 'value_a': 1, 'value_b': 1, 'value_out': 0}
# the xor answer wire 7 holds 0
# circuit did not settle within 1000 gate evaluations (still changing in part 'clock.ring')
```

Each line of the last four is one NAND gate. `a` and `b` are the numbers of
its two input wires and `out` is its output wire. The three `value_` entries
are what those wires hold *right now*. Gate 0 has both inputs at 1, so its
output is 0, which is what a NAND does. The last gate's output, wire 7, is the
XOR's answer: 1 XOR 1 is 0.

The last message is the "fuse" from
[Simulating a Circuit](simulating-a-circuit.md). Now that the ring lives in
named parts, the error says *which* part kept changing, so you know where to
look.

## How It Works

Two files do the work: `src/pycpu/circuit.py` remembers the names, and
`src/pycpu/view.py` shows them.

**1. Every gate remembers which part it belongs to.** Each part gets a number,
and a gate stores just the number of its part: one whole number, 4 bytes. The
parts themselves cost more, because each one has a name, a parent and counts of
its gates, about 200 bytes a part. We measured a circuit of 500,010 gates (a
12-bit decoder plus a few thousand 16-bit XOR, AND, chooser and zero-check
units) that held 197,229 parts. The whole circuit took about 59 MB, and the
parts' bookkeeping was under 40 MB of that. Each part also keeps its total
gate count up to date as gates are added, so asking "how big is this part?"
is instant however big it is. A `with c.scope("half_adder"):` block says "every
gate made until the block ends goes in this part". Blocks can sit inside
blocks, which gives the dotted paths.

**2. The gate functions label themselves.** Every function in `logic.py`
that builds more than one gate (`xor`, `mux`, `decoder` and the rest) opens a
scope named after itself. That is why `xor` made a part called `xor` all by
itself. The exception is `not_`, which is a single NAND: a part holding one
gate would cost more than it tells you, so its gate just sits in whatever part
called it. If one part uses the same
gate twice, the repeats are numbered: `xor`, `xor#1`, `xor#2`. The gate counts
do not change; the labels are extra, not extra gates.

```
 the whole circuit  ""
 └── half_adder
     └── xor              4 gates
         gate 0  NAND(a, b)        -> n
         gate 1  NAND(a, n)        -> p
         gate 2  NAND(b, n)        -> q
         gate 3  NAND(p, q)        -> answer
```

**3. The view reads, and only reads.** `circuit_view(sim, path)` asks the
circuit for the parts and gates at that path, then asks the *simulator* for
the value on each gate's wires with `sim.get`. It keeps no copy of any value
and works none out. The simulator is the one place that ever computes a
result, so whatever the view shows is, by construction, what the simulator
holds. The view is **real**: it cannot show you a value the circuit does not
have. A **faking** view, one that worked out its own idea of the answers, could
drift apart from the circuit and show you something comforting but false. We
never build one, because the whole point of looking inside is to be able to
trust what you see.

The view is plain dictionaries of numbers and words, so a web page can draw it
without knowing anything about circuits.

## Why Does This Matter?

Nobody can understand a computer by staring at half a million gates. People
understand big things by zooming: country, town, street, house. Chip designers
name the parts of their designs for exactly this reason, and so do programmers
when they use functions. Later in this climb the Cockpit, our control panel,
will use this very view to let you click from a whole computer down to one
gate and watch real values flicker. And when a circuit refuses to settle, the
name of the part tells you where to look instead of leaving you to hunt through
a haystack.

## What's Next

You can now find any gate by name and see the real value on its wires. Next
we use those gates to do arithmetic, starting with how a computer adds two
numbers by carrying the one, just like you do on paper. Read on to
[Adding](adding.md).
