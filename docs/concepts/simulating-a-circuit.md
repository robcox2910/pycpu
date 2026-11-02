# Simulating a Circuit

## The Dominoes

Set up a long line of dominoes. Push the first one and it knocks the second,
which knocks the third, and so on down the line. Now notice something: the
dominoes that nobody touched, and that nothing falling ever reaches, **just
stand there**. A domino only moves when something pushes it.

That is exactly how PyCPU pretends to be electricity. There is no electricity
in Python. Instead we keep the value of every wire in a list, and when a wire
changes we ask only the gates connected to it to think again. If their answer
changes, *their* output wire changes, and we ask the gates connected to that
wire, and so on. The wave stops by itself when nothing more changes.

Each time a wire changes, we call it an **event** (something happened). When a
push has finished rippling through and everything is still, we say the circuit
has **settled**, like dominoes that have all fallen and gone quiet.

| The dominoes | In PyCPU |
|--------------|----------|
| A domino | A gate |
| Pushing the first one | `sim.set(wire, value)` |
| A domino knocking the next | A wire changing, which is an **event** |
| Waiting for everything to stop moving | `sim.settle()` |
| How many dominoes fell | The number `settle()` returns |
| A domino nobody touched | A gate that is never asked to think |
| The list of who touches whom | The **netlist**, turned into a fanout table |

## Try It

Two groups of gates: a chain of five NOT gates (each one is a NAND with both
inputs joined) driven by `a`, and a thousand other gates that depend only on
`b`. We flip `a` and count how many gates had to think. Then we build a ring
that can never stop:

```python
from pycpu.circuit import Circuit
from pycpu.simulator import OscillationError, Simulator

circuit = Circuit()
a = circuit.input("a")
b = circuit.input("b")
wire = a
for _ in range(5):
    wire = circuit.nand(wire, wire)  # a NOT gate: NAND with its inputs joined
for _ in range(1000):
    circuit.nand(b, b)

sim = Simulator(circuit)
print("gates in the circuit:", circuit.gate_count)
sim.set(a, 1)
print("flip a, gates that thought:", sim.settle())
sim.set(a, 1)  # it is already 1, so nothing changes
print("set a to 1 again, gates that thought:", sim.settle())

ring = Circuit()
loop = ring.wire_placeholder()  # a wire we will connect up afterwards
ring.nand_into(loop, loop, loop)  # a NOT gate that feeds itself
try:
    Simulator(ring, max_events=1000)
except OscillationError as error:
    print("the ring never stopped:", error)
# Output:
# gates in the circuit: 1005
# flip a, gates that thought: 5
# set a to 1 again, gates that thought: 0
# the ring never stopped: circuit did not settle within 1000 gate evaluations
```

A thousand and five gates, yet flipping `a` woke exactly five. The thousand
that depend on `b` never stirred. Setting `a` to a value it already had woke
none at all.

## How It Works

The simulator lives in `src/pycpu/simulator.py` and is built from three small
ideas.

**1. Keep a value for every wire, and a list of who is listening.** When the
`Simulator` is created it reads the netlist from the `Circuit` and builds a
*fanout* table: for each wire, the gates that use it as an input. "Fanout"
just means "where the wire fans out to". It is stored as two flat lists
instead of a small list for every wire, because a big circuit has hundreds of
thousands of wires and tiny lists would waste a lot of memory.

**2. A queue of gates that need to think again.** Setting an input puts the
gates listening to it in a waiting line (a *queue*). Then `settle()` repeats:

```
 take the gate at the front of the queue
 work out NAND of its two inputs, right now
 if its output changed:
     write the new value
     put every gate listening to that wire at the back of the queue
 until the queue is empty
```

Each trip round the loop is one gate evaluation. The number `settle()`
returns is how many there were. The outputs are written **immediately**, one
gate at a time, rather than all at once. That matters for circuits that
remember (later in the climb): two gates facing each other need to be
processed one after the other, or they would flip together forever.

**3. A safety fuse.** Some circuits never settle. The ring in the example is
a NOT gate whose output is fed back into its own input. If its output is `0`
it becomes `1`, which makes it `0`, which makes it `1`, and so on, like a
circle of dominoes that is always falling. A circuit that never rests like
this **oscillates** (swings back and forth). The simulator counts evaluations
and, if one `settle()` passes `max_events`, raises `OscillationError` instead
of hanging forever. By default the fuse is ten million evaluations.

When the `Simulator` is first made it queues every gate once, in order, and
settles. That gives every circuit the same starting values every time.

## Why Does This Matter?

A real processor has millions of gates, but in any one moment almost all of
them are doing nothing. A simulator that re-checked every gate on every step
would be hopelessly slow. By waking only the gates whose inputs changed, the
cost of a step grows with how much *happens*, not with how much *exists*.
Real chip designers use this very idea, called *event-driven simulation*,
when they test chips before building them. It is also what lets
us simulate the big memory we build at the top of this part of the climb:
most of its gates sit still at any moment, and the simulator never visits them.

## What's Next

You can now build a circuit from NAND gates and watch it settle. Next, we use
that machinery to build the other everyday gates: NOT, AND, OR and XOR, each
made of nothing but NAND. (That page comes next in the climb.)
