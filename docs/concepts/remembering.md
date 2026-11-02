# Remembering

## Two Friends Who Keep Repeating

Imagine two friends standing at opposite ends of a long corridor. A teacher
runs up to one of them and whispers "banana", then leaves. Friend A shouts
"banana!" down the corridor. Friend B hears it and shouts "banana!" right back.
Friend A hears that and shouts it again. Nobody is holding the word. It is not
written down anywhere. Yet the word stays alive for as long as the two friends
keep listening and repeating, and you could walk in a week later and still hear
"banana" bouncing along the corridor.

That is how a circuit remembers. Every gate in the last few pages gave its
answer from its inputs *right now*: change the inputs and the answer vanishes.
To make a gate remember, we do something sneaky. We take the output of one gate
and wire it back into the input of another, and the output of that one back
into the first. Sending an answer round to listen to itself is called
**feedback**. A pair of gates joined in a loop like this, which holds on to one
bit (a 0 or a 1) for as long as the power is on, is called a **latch**. A latch
is the smallest thing in this whole project that can **remember**.

| The corridor | In PyCPU |
|--------------|----------|
| Friend A and Friend B | Two NAND gates, each reading the other's output |
| The shouted word | The wire `q` (and its opposite, `q_n`) |
| The teacher's whisper | Briefly switching `set_n` or `reset_n` to 0 |
| Walking away | Switching both back to 1: the latch keeps going |
| A loop with nobody holding the word | Feedback, made with `wire_placeholder` and `nand_into` |
| A latch with a "listen now" switch | `d_latch(c, data, enable)` |

## Try It

First the bare loop: two NAND gates. `set_n` and `reset_n` are "active low",
meaning they do their job when they are **0** and are quiet when they are 1.
One warning: a new circuit starts with every input at 0, which here means
"set" and "reset" are both being shouted at once. That is the **forbidden
state**: both gates are forced to answer 1, so `q` and `q_n` agree instead of
being opposites, and the loop means nothing. The very first thing we do is
move both inputs to their quiet position, 1. After each step we print the two
wires. Then we build the friendlier version,
`d_latch`, with one `data` wire to say what to remember and one `enable` wire
to say "listen now".

```python
from pycpu.circuit import Circuit
from pycpu.memory import d_latch
from pycpu.simulator import Simulator

# Two NAND gates, each listening to the other.
c = Circuit()
set_n = c.input("set_n")
reset_n = c.input("reset_n")
q_n = c.wire_placeholder()  # a wire we will connect later, to close the loop
q = c.nand(set_n, q_n)
c.nand_into(reset_n, q, q_n)
sim = Simulator(c)


def step(label, set_value, reset_value):
    sim.set(set_n, set_value)
    sim.set(reset_n, reset_value)
    sim.settle()
    print(f"{label:<22} q={sim.get(q)} q_n={sim.get(q_n)}")


step("quiet (both inputs 1)", 1, 1)
step("set (set_n to 0)", 0, 1)
step("let go, it remembers", 1, 1)
step("reset (reset_n to 0)", 1, 0)
step("let go, it remembers", 1, 1)
print("gates used:", c.gate_count)

# The friendlier latch: remember `data` whenever `enable` is 1.
c2 = Circuit()
data = c2.input("data")
enable = c2.input("enable")
latch_q, latch_q_n = d_latch(c2, data, enable)
sim2 = Simulator(c2)
for label, d, e in [
    ("enable on, data 1", 1, 1),
    ("enable off, data 0", 0, 0),
    ("enable on, data 0", 0, 1),
    ("enable off, data 1", 1, 0),
]:
    sim2.set(data, d)
    sim2.set(enable, e)
    sim2.settle()
    print(f"{label:<22} q={sim2.get(latch_q)}")
print("d_latch gates:", c2.gate_count)
# Output:
# quiet (both inputs 1)  q=0 q_n=1
# set (set_n to 0)       q=1 q_n=0
# let go, it remembers   q=1 q_n=0
# reset (reset_n to 0)   q=0 q_n=1
# let go, it remembers   q=0 q_n=1
# gates used: 2
# enable on, data 1      q=1
# enable off, data 0     q=1
# enable on, data 0      q=0
# enable off, data 1     q=0
# d_latch gates: 4
```

## How It Works

The code is in `src/pycpu/memory.py`, and it is made of nothing but NAND gates.

**1. The loop.** Look at the two gates in the Try It. Gate A reads `set_n` and
the *other* gate's output; gate B reads `reset_n` and gate A's output.

```
  set_n ───►┌────────┐
            │ NAND A ├───────┬───────► q
     ┌─────►└────────┘       │
     │                       │ q goes down into B
     │                       ▼
     │     reset_n ───►┌────────┐
     │                 │ NAND B ├───┬──► q_n
     │                 └────────┘   │
     │                              │
     └──────────────────────────────┘ q_n goes up into A
```

In words: A's output `q` goes into B, and B's output `q_n` goes into A.
Remember that a NAND gives 1 unless both inputs are 1. While `set_n` and
`reset_n` are both 1, each gate is just a NOT of the other one. So the pair
can rest in two ways: `q=1, q_n=0` or `q=0, q_n=1`. Each is *stable*, because
each gate's output keeps the other gate's input exactly where it needs to be.
Neither is better. Which one you get is decided by history.

**2. Writing.** Pull `set_n` down to 0 and gate A is forced to answer 1
whatever else it hears, so `q` becomes 1, which makes B answer 0. Let go of
`set_n` and nothing changes: B is saying 0, and that alone keeps A saying 1. It
remembers! Pull `reset_n` down instead and the same thing happens the other
way round. The step-by-step output above shows each of these moments.

**3. Why it needs a wire made "later".** A gate cannot read a wire that does not
exist yet, but in a loop each gate needs the other's output first.
`wire_placeholder` makes the wire early, and `nand_into` connects the gate that
drives it later. (If you forget, `Simulator` refuses to start and tells you how
many wires nobody drives, because an undriven wire would silently read 0.)

**4. The D latch.** Two wires that mean "set" and "reset" are awkward. What we
want is "here is a value, remember it now". `d_latch` adds two more NAND gates
in front of the loop:

```
  data ──► [NAND with enable] ──► s_n ─┬──► [NAND with enable] ──► r_n
                                       │
                s_n ───► loop gate A (q) ◄──► loop gate B (q_n) ◄─── r_n
```

While `enable` is 0, both front gates answer 1 (quiet), so the loop is left
alone and holds its bit. While `enable` is 1, the front gates turn `data` into
a set (when data is 1) or a reset (when data is 0), so `q` simply follows
`data`. Four NAND gates in all, and one bit of memory.

**5. Power-on.** When a simulation starts, every gate is looked at once, in the
order it was added, and every input is 0. For a bare loop that means the
forbidden state from the Try It (both gates forced to 1), and as soon as the
inputs move to 1 the two gates race, and the gate looked at first decides which
bit the loop settles on. Which gate is looked at first is decided by the order
things happen (which gates were added first, and which input moves first), so
the same steps always give the same bit, never a random one. A test in the
repository (`tests/test_simulator.py`, the one about cross-coupled NANDs) pins
this down for loops whose inputs are tied high at power-on. `d_latch` avoids the forbidden state altogether: with `enable`
at 0 its front gates keep the loop quiet, and its gates are added so that it
powers on holding 0. (That promise only holds if `enable` starts low.)

## Why Does This Matter?

Without memory a computer would be a calculator that forgets the sum the instant
you stop pressing buttons. Every program, every picture, every save file is
stored in things that do what these two friends do. Real chips store bits in
loops like this one, a different shape of gate but the same idea: an answer
that listens to itself. You have just seen the moment gates start to remember.

## What's Next

A latch changes the instant you let it, and that is dangerous when many latches
need to change *together*. Next, [The Clock](the-clock.md) makes the whole
machine step in time, like a drummer keeping a crew rowing together.
