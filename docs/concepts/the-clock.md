# The Clock

## The Drummer in the Rowing Boat

Picture a rowing boat with eight rowers. If everyone pulled whenever they felt
like it, the boat would zigzag. So the boat has a drummer. *Boom*: everyone
pulls together. *Boom*: again. Nobody is allowed to move except on the beat.

A computer has a drummer too, called the **clock**: one wire that goes 0, 1, 0, 1
over and over. The moment it jumps from 0 up to 1 is the **rising edge**,
the "boom". A memory bit that only changes on the rising edge, and ignores the
data wire the rest of the time, is called a **flip-flop**. A flip-flop is a
latch that has learned to wait for the drummer.

But our clock has an unusual feature: **two wires**, not one. We call them
`write` and `clk`. Each beat is a two-step routine: first *everyone writes*,
then *everyone steps*.

| The rowing boat | In PyCPU |
|-----------------|----------|
| The drummer | `make_clock(c)`, which gives a `Clock` |
| One full beat | `sim.tick(clock)` |
| The "boom" moment | The rising edge of `clk` |
| Step 1: everyone writes down what they have | A brief pulse on the `write` wire |
| Step 2: everyone steps forward | A brief pulse on the `clk` wire |
| A rower who only moves on the boom | A flip-flop, `d_flip_flop(c, data, clk)` |

## Try It

First a flip-flop, with the `clk` wire switched by hand so you can see that it
only reacts at the rising edge. Then the reason for two wires: `r` is a
flip-flop that steps on `clk`, while `snap` is a latch that opens on `write`
and takes a photograph of whatever `r` holds at that moment.

```python
from pycpu.circuit import Circuit
from pycpu.memory import d_flip_flop, d_latch, make_clock
from pycpu.simulator import Simulator

c = Circuit()
clock = make_clock(c)
data = c.input("data")
r = d_flip_flop(c, data, clock.clk)
snap, _ = d_latch(c, r, clock.write)
sim = Simulator(c)


def show(label):
    print(f"{label:<28} data={sim.get(data)} clk={sim.get(clock.clk)} r={sim.get(r)}")


def move(wire, value):
    sim.set(wire, value)
    sim.settle()


move(data, 1)
show("data goes to 1, clk is 0")
move(clock.clk, 1)
show("clk rises: r takes data")
move(data, 0)
show("data falls, clk still 1")
move(clock.clk, 0)
show("clk falls: r ignores it")
move(data, 1)
move(clock.clk, 1)
show("clk rises again")
move(clock.clk, 0)

# Now whole beats with tick(): write first, then clk.
# r holds 1 and data is 0, so the first beat should change r to 0.
move(data, 0)
sim.tick(clock)
print("tick 1: r =", sim.get(r), "snap =", sim.get(snap))
sim.tick(clock)
print("tick 2: r =", sim.get(r), "snap =", sim.get(snap))

# The harm: photograph with `clk` instead of `write`, and the picture is wrong.
c = Circuit()
clock = make_clock(c)
data = c.input("data")
r = d_flip_flop(c, data, clock.clk)
good, _ = d_latch(c, r, clock.write)  # opens on write, before clk
bad, _ = d_latch(c, r, clock.clk)  # opens on clk, as r is changing
sim = Simulator(c)
sim.set(data, 1)
sim.tick(clock)
print("r =", sim.get(r), "| photo on write =", sim.get(good), "| photo on clk =", sim.get(bad))
# Output:
# data goes to 1, clk is 0     data=1 clk=0 r=0
# clk rises: r takes data      data=1 clk=1 r=1
# data falls, clk still 1      data=0 clk=1 r=1
# clk falls: r ignores it      data=0 clk=0 r=1
# clk rises again              data=1 clk=1 r=1
# tick 1: r = 0 snap = 1
# tick 2: r = 0 snap = 0
# r = 1 | photo on write = 0 | photo on clk = 1
```

## How It Works

The flip-flop is `d_flip_flop` in `src/pycpu/memory.py`, built from the D latch
on the [Remembering](remembering.md) page.

**1. Why a lone latch is not enough.** A latch follows its data the whole time
`enable` is 1. If its output also feeds back into its own data (as it does in
a counter that adds 1 to itself), it would race round and round, changing many
times in one beat. We need the change to happen *once*.

**2. Two latches, taking turns.** The trick is two latches in a row, called
**master** and **slave**, like a canal lock with two gates. Only one gate is
ever open.

```
                  ┌── NOT ──► enable of master
   clk ───────────┤
                  └─────────► enable of slave

   data ──► [ master latch ] ──► [ slave latch ] ──► q
```

- While `clk` is 0, the master is open (it follows `data`) and the slave is
  closed (`q` stays put).
- At the rising edge, `clk` becomes 1: the master closes, keeping the value
  `data` had at that instant, and the slave opens and copies the master.
- While `clk` is 1, the master is shut, so changes in `data` cannot get
  through. Nothing leaks.

Two latches and one NOT: nine NAND gates. The output only ever changes right
after a rising edge, which is just what the Try It shows.

**3. Why two clock wires exist.** Here is the problem. Some parts of our
machine change on the `clk` rising edge: the registers that hold numbers.
Other parts, like memory (later), copy a value in while their `write` wire is
1. Memory needs the *address* (where to put it) and the *data* (what to put) to
hold still while it is being written. But those come from registers, and
registers move on `clk`. If there were only one wire, the registers could start
changing the address while memory was still halfway through copying, and the
data would be written to the wrong place. It would be a race.

So the beat has two steps. `sim.tick(clock)` first pulses `write` up and down:
every writer copies what it sees, while all the registers still hold *this*
beat's numbers. `write` is back to 0 *before* `clk` rises. Only then does
`clk` pulse and every register steps to its new value. In the Try It, `snap`
is a writer: it takes its photo of `r` just before `r` changes, which is why
`snap` always shows one beat behind. Early computers used the same trick, and
called it a two-phase clock.

To see the harm, the last part of the Try It builds a second photographer that
opens on `clk` instead of `write`. It opens at the same moment `r` changes, so it
photographs the *new* value, not the one the beat started with. Here the
register has just taken a 1, and the `clk` photographer shows 1 where the
`write` photographer correctly shows the old 0. In a real machine that would
mean writing the wrong number into memory.

**4. The Clock itself.** `Clock` is a tiny record of two input wires, `clk`
and `write`, defined in `src/pycpu/circuit.py`. `make_clock` adds the two wires
and `Simulator.tick` is the drummer: it switches `write` up, settles, `write`
down, settles, then `clk` up, settles, `clk` down, settles.

## Why Does This Matter?

Every processor you have used has a clock, and its speed is quoted in
gigahertz: billions of beats a second. The clock is what lets millions of
parts agree on "now". Without it, the signals running through a chip arrive at
slightly different times, and the machine would act on half-changed numbers.
Splitting the beat into "write, then step" is how a real computer avoids
trampling its own data.

## What's Next

One flip-flop holds one bit. Line sixteen of them up and you have something
that holds a whole number. That is a [Register](registers.md).
