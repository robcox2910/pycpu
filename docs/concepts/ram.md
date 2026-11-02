# RAM

## A Wall of Lockers

Picture a long wall of numbered lockers, 4,096 of them. Each locker holds one
sixteen-bit number. You do not want to search the whole wall every time, so the
wall has a clever trick: a **corridor light** for each row of lockers and a
**column light** for each column. To open locker 1,234 you switch on exactly
one corridor light and exactly one column light. Only the locker where the two
lights cross has both lights shining on it, so only that locker opens its door.

That wall is **RAM**, the computer's big working memory. Each locker is a
**word** (one sixteen-bit number). The number you give to choose a locker is the
**address**. The signal that picks out one locker, made from a row light and a
column light, is the **word line**. Looking at what is in the locker is a
**read**. Putting a new number in is a **write**, and it only happens if you
also say "yes, write now" (`write_enable`) on the beat of the clock.

| The lockers | In PyCPU |
|-------------|----------|
| The wall of lockers | `Ram(c, address, data, write_enable, clock)` |
| A locker's number | A word: 16 memory cells, one per bit |
| One slot inside a locker | A D latch from [Remembering](remembering.md) |
| The locker number you ask for | The `address` bus |
| Corridor light and column light | Two decoders, one for each half of the address |
| The one locker that lights up | The word line: row line AND column line |
| Looking inside | A read: `ram.out`, always showing the chosen word |
| Putting a number in | A write: `write_enable` is 1 when the clock beat comes |

## Try It

A small wall: a 4-bit address gives 16 lockers. We write a number into locker 5
through the gates, read it back, and see that a locker we never touched is
still empty, and that `write_enable` really is the switch.

```python
from pycpu.circuit import Circuit
from pycpu.memory import Ram, make_clock
from pycpu.simulator import Simulator

c = Circuit()
clock = make_clock(c)
address = c.bus_input("address", 4)
data = c.bus_input("data", 16)
write_enable = c.input("write_enable")
ram = Ram(c, address, data, write_enable, clock)
sim = Simulator(c)

print("lockers:", 1 << len(address))
print("gates:", c.gate_count)
print("power-on, locker 5:", ram.peek(sim, 5))

sim.set_bus(address, 5)
sim.set_bus(data, 0xBEEF)
sim.tick(clock)
print("write_enable low, locker 5:", hex(sim.get_bus(ram.out)))
sim.set(write_enable, 1)
sim.tick(clock)
print("write_enable high, locker 5:", hex(sim.get_bus(ram.out)))
sim.set(write_enable, 0)
sim.set_bus(address, 6)
sim.settle()
print("look at locker 6:", hex(sim.get_bus(ram.out)))
sim.set_bus(address, 5)
sim.settle()
print("back to locker 5:", hex(sim.get_bus(ram.out)))
# Output:
# lockers: 16
# gates: 2342
# power-on, locker 5: 0
# write_enable low, locker 5: 0x0
# write_enable high, locker 5: 0xbeef
# look at locker 6: 0x0
# back to locker 5: 0xbeef
```

A computer that rushes can write into the wrong lockers. Here we change the
address and `write_enable` and fire the write pulse by hand *immediately*, with
no waiting, in a 256-locker RAM where locker `n` holds `n`. Then we do the same
thing through `tick`, which waits first.

```python
from pycpu.circuit import Circuit
from pycpu.memory import Ram, make_clock
from pycpu.simulator import Simulator


def build():
    c = Circuit()
    clock = make_clock(c)
    address = c.bus_input("address", 8)
    data = c.bus_input("data", 16)
    write_enable = c.input("write_enable")
    ram = Ram(c, address, data, write_enable, clock)
    sim = Simulator(c)
    ram.load(sim, list(range(256)))
    return clock, address, data, write_enable, ram, sim


clock, address, data, write_enable, ram, sim = build()
sim.set_bus(address, 255)
sim.set_bus(data, 0xBEEF)
sim.set(write_enable, 1)
sim.set(clock.write, 1)  # the pulse, before the wires have finished moving
sim.settle()
sim.set(clock.write, 0)
sim.settle()
hurt = [a for a in range(256) if ram.peek(sim, a) != a]
print("rushed: lockers changed:", len(hurt))

clock, address, data, write_enable, ram, sim = build()
sim.set_bus(address, 255)
sim.set_bus(data, 0xBEEF)
sim.set(write_enable, 1)
sim.tick(clock)  # tick lets everything settle before it pulses
hurt = [a for a in range(256) if ram.peek(sim, a) != a]
print("tick: lockers changed:", hurt, hex(ram.peek(sim, 255)))
# Output:
# rushed: lockers changed: 43
# tick: lockers changed: [255] 0xbeef
```

## How It Works

`Ram` is in `src/pycpu/memory.py`. It is made of the latch from
[Remembering](remembering.md) and the decoder from
[Choosing and Decoding](choosing-and-decoding.md), nothing else.

**1. One memory cell.** Every bit of every word is a D latch (four NAND
gates) from [Remembering](remembering.md). A latch copies its data while its
enable is 1 and holds it while its enable is 0. A locker's door is that enable.
The cell's enable is "my word line AND the write pulse":

```
 word line ───┐
              AND ───► enable ──► [ D latch ] ──► q  (the bit this cell remembers)
 write pulse ─┘                      ▲
                      data bit ──────┘
```

Unless both are 1, the enable stays 0 and the cell just holds, so a RAM powers
on with every bit 0.

**2. Finding a locker.** The address is cut in half. The low half goes into one
decoder, which lights one *column* line. The high half goes into another, which lights one *row*
line. Each word gets an AND of one row line and one column line: that is its
word line. A 12-bit address means two small 6-bit decoders (64 lines each)
instead of one huge 4,096-line decoder.

```
 address low half ──► [decoder] ──► column lines ─┐
                                                  ├─ AND ─► word line (one per word)
 address high half ─► [decoder] ──► row lines ────┘
```

**3. Writing.** `write_pulse` is `write_enable AND clock.write`. The clock's
`write` wire goes up and down before `clk` rises (see [The Clock](the-clock.md)),
so the write is a short, clean pulse. A cell's enable is its word line AND that
pulse.

**Waiting for the wires.** Signals take time to run through gates. When the
address changes, the row decoder and the column decoder do not jump straight to
the right answer. Some address wires reach them a moment before others, like a
row of dominoes where some fall first, so for that moment each decoder is working
from an address that is part old and part new, and it lights the wrong line. We
say the decoders *flicker*. A wrong row light crossing a wrong column light
switches on a *wrong* word line. If the write pulse arrives during the flicker,
the wrong locker gets written. (The rushed run in the block above showed 43
lockers hurt this way.) The safe rule is: **let everything settle, then pulse**.
`Simulator.tick` settles first, so it is always safe. A real computer gets the
same effect by making its clock slower than its slowest path, so every signal has
arrived before the beat comes.

**4. Reading.** Every bit of every word has one more NAND that checks "am I
chosen, and am I holding a 1?". Because only one word line is ever up, only one
word can say yes. For each of the 16 output bits, all the words' answers are
joined by a tree of ORs (`or_many`), which is why a change only has to travel
through a handful of gates rather than thousands.

**5. Why not a tree of choosers?** A tree of muxes would hang the lowest address
bit on thousands of gates. With word lines, an address change only wakes the
word lines that change. Measured on a 256-word RAM (38,042 gates) with every
locker full of ones: stepping from address 0 to 1 costs 183 gate evaluations.
Jumping to a random address costs more, because the decoder flickers on the way
and each flicker wakes a few gates: over 300 random jumps the average was 885
evaluations and the worst 4,897. Even the worst is about an eighth of the
circuit, so most of the gates sit still while the answer arrives. The full
4,096-word RAM has 607,454 gates; the next page times it.

**6. Poke and peek.** `poke` writes a number straight into a word's latches and
`load` writes a whole list and settles once. They are for setting up
experiments; `peek` reads the latches directly. The gates do all the real work.

## Why Does This Matter?

A program is a list of numbers, and the data it works on is more numbers.
Both live in RAM. Everything the processor does is "fetch the number at this
address" and "store a number at that address", so this is the page where the
machine gets a memory big enough to hold a program.

## What's Next

We built a 4,096-word RAM out of gates, but is it small enough to simulate and
quick enough to use? In [How Big Is Our Memory?](how-big-is-our-memory.md) we
take out a stopwatch and measure it.
