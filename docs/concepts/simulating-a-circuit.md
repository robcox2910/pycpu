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
# the ring never stopped: circuit did not settle within 1000 gate evaluations (still changing at the top level)
```

A thousand and five gates, yet flipping `a` woke exactly five. The thousand
that depend on `b` never stirred. Setting `a` to a value it already had woke
none at all.

`settle()` lets the whole line of dominoes fall in one go. Sometimes you want
to watch them fall **one at a time**, like a slow-motion replay. `step()` does
exactly one gate's thinking, then stops so you can look. It returns the number
of the gate it just thought about (every gate gets a number, counting up from
0 in the order it was added), or `-1` if no gate is waiting. Here is a *half
adder*, a tiny circuit that adds two single bits and gives a sum and a carry,
with both inputs switched on. We step through it and print each gate, the wire
it drives (wires are numbered too), and the value that wire holds afterwards.

Two things to know first. The half adder is built from six gates, numbered 0
to 5 in the order they were added: gates 0 to 3 work out the **sum** (this is
called an XOR, "one or the other but not both") and gates 4 and 5 work out the
**carry** (an AND, "both at once"). And `circuit.gate_wires` hands back three
lists, one entry per gate: the wire each gate reads first, the wire it reads
second, and the wire it drives. We only want the last list, the driven wires,
so the other two are thrown away with `_`:

```python
from pycpu.arithmetic import half_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

circuit = Circuit()
a = circuit.input("a")
b = circuit.input("b")
total, carry = half_adder(circuit, a, b)
_, _, gate_outputs = circuit.gate_wires

sim = Simulator(circuit)
sim.set(a, 1)
sim.set(b, 1)
print("gates waiting:", sim.pending)
steps = 0
while (gate := sim.step()) != -1:
    steps += 1
    wire = gate_outputs[gate]
    held = sim.get(wire)
    print(f"step {steps}: gate {gate} drives wire {wire}, which now holds {held}")
print("sum:", sim.get(total), "carry:", sim.get(carry))
# Output:
# gates waiting: 4
# step 1: gate 0 drives wire 4, which now holds 0
# step 2: gate 1 drives wire 5, which now holds 1
# step 3: gate 4 drives wire 8, which now holds 0
# step 4: gate 2 drives wire 6, which now holds 1
# step 5: gate 5 drives wire 9, which now holds 1
# sum: 0 carry: 1
```

Watch the dominoes. Four gates were waiting at the start, but there were five
steps, because gate 4 changed its wire and so woke gate 5 (the carry's second
gate), which had not been waiting. Some steps changed nothing: wire 5 held 1
before gate 1 looked at it and 1 after, so the ripple stopped there.

Now look for gate 3, the last gate of the sum. It never ran at all! It reads
wires 5 and 6, and neither of them changed (both held 1 all along), so
nothing ever woke it. That is the whole idea of this page in one picture: a
gate only thinks when something it listens to changes. One push, a little
ripple, then stillness.

Once the queue is empty the circuit is exactly where `settle()` would have
left it, and `step()` took exactly as many steps as `settle()` would have
counted.

## How It Works

The simulator lives in `src/pycpu/simulator.py` and is built from five small
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
of hanging forever. By default the fuse is ten million evaluations. The error
also says *where* the trouble is. Our ring was built in no named part, so it
says "at the top level". Later in the climb, circuits are filed into named
parts, and then the error names the part instead.

**4. One gate at a time.** `step()` is the loop above with the "repeat" cut
off: it takes the gate at the front of the queue, works out its NAND, writes
the answer straight away, queues the listeners, and stops. It follows the very
same rule as `settle()`, so stepping until nothing is waiting always ends with
the same wire values. `settle()` keeps its own copy of the loop only so that it
stays as fast as it can be. `sim.pending` says how many gates are waiting.

**5. Saving what a circuit remembers.** Later in the climb we build circuits
that remember a bit (latches, registers, memory). `sim.storage()` copies out
every remembered bit as a row of bytes, and `sim.restore_storage(bits)` writes
them back and settles. That is how a computer can be paused and wound back to
an earlier moment. Before restoring, switch the clock wires off and settle, so
nothing is half way through a pulse.

After an `OscillationError` the wire values are left half way through a ripple
and cannot be trusted, so that simulator is **dead**: every later call raises
`RuntimeError` and you build a new one.

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
made of nothing but NAND. Read on to [Logic Gates from NAND](gates.md).
