# How Big Is Our Memory?

## Lockers and a Stopwatch

Imagine your head teacher says, "Let's put four thousand lockers in the school!"
A sensible builder asks two questions before saying yes. *How many can we fit?*
Every locker needs a door, a hinge, a lock and some floor. And *how long will it
take to walk the corridors?* If fetching your lunchbox takes all of break, the
lockers are useless, however many there are.

Our RAM has the same two questions. People write a memory of 4,096 words as
**4K words**: computer people count in powers of two, and 4,096 is 2 multiplied
by itself twelve times, close enough to four thousand to borrow the "k" from
"kilo". So we have promised 4K lockers, every one built from real **gates**. Now
we check that promise. We don't guess: every number on this page was **measured**
by running the real circuit with a stopwatch.

The headline: the promise holds. 4K words of real gates passed all five tests.

| At the school | In PyCPU |
|---------------|----------|
| Counting the parts in the lockers | `gates`: how many NAND gates the RAM is made of |
| The time to build the lockers | `build_seconds`: making the circuit and its simulator |
| The land the building sits on | `memory_mib`: how much of the computer's own memory it takes |
| Filling every locker before term | `load_seconds`: poking in all 4,096 words and settling |
| Walking to a locker and looking inside | `read_seconds`: one read through the gates |
| Walking to a locker and swapping its contents | `write_seconds`: one write, with a clock beat |
| The builder with the stopwatch | `measure` in `src/pycpu/proof.py` |

## Try It

`measure` builds a real RAM and times it. Here it builds a small one, with a
6-bit address, which means 64 lockers. We print only the gate count, because
that is the same on every computer. The timings depend on how fast your computer
is, and a page can't promise those.

```python
from pycpu.proof import measure

result = measure(6)
print("gates:", int(result["gates"]))
# Output:
# gates: 9496
```

To time the full 4K RAM on your own computer, run this in a terminal:

```text
uv run python scripts/prove_ram.py
```

It takes a few seconds, then prints each result next to its limit. Try
`--address-bits 8` on the end to measure a smaller RAM.

## How It Works

`measure` lives in `src/pycpu/proof.py`. It is the builder with the stopwatch:
it does no logic of its own. It builds a real `Ram`, fills it with mixed-up
numbers, then reads and writes at 100 random addresses through the gates.

**Why mixed-up numbers?** Remember the dominoes from
[Simulating a Circuit](simulating-a-circuit.md): only a gate whose input changes
costs any work. A RAM full of zeros has almost nothing to change, so filling it
with zeros would be like timing the corridors in the holidays when they are empty.
Mixed-up numbers are the busy school day. The numbers come from a fixed
**seed** (the starting point for the random numbers), so each run makes the same
moves.

**Checking the answers.** A fast locker that hands you the wrong lunchbox is no
use. So every read is compared with what should be there, and after the writes
every word in the RAM is checked. If one is wrong, `measure` stops with an error.

**How many gates does one word cost?** Here is the real RAM, counted by its parts:

```
 one word, 16 bits
 ┌──────────────────────────────────────────┐
 │  word line and write line        4 gates │
 │  16 bits, each one:                      │
 │     D latch, the memory itself   4 gates │
 │     "am I chosen and holding 1?" 2 gates │
 │     = 6 gates x 16 bits         96 gates │
 ├──────────────────────────────────────────┤
 │  the word's own parts          100 gates │
 │  one more OR on each of the 16           │
 │  output lines, 3 gates each     48 gates │
 ├──────────────────────────────────────────┤
 │  the true cost of one word     148 gates │
 └──────────────────────────────────────────┘
```

Those 148 gates hold only one number. Multiply by 4,096 words and add the small
parts that are shared by everybody:

| Part of the RAM | Gates |
|-----------------|-------|
| The words themselves (100 each) | 409,600 |
| The OR trees that join the answers | 196,560 |
| The two decoders | 1,292 |
| The write pulse | 2 |
| **Total** | **607,454** |

Sharp-eyed readers will spot something. 148 x 4,096 is 606,208, but the first two
rows of the table add up to 606,160, which is 48 fewer. Nothing is missing. Joining
4,096 answers takes 4,095 ORs, not 4,096, just as tying 4 bits of string into one
line takes 3 knots. So each of the 16 output lines has 4,095 ORs of 3 gates:
16 x 4,095 x 3 = 196,560. The first word gets its 48 joining gates for free.

**The results.** Measured on 2 November 2026, on one laptop: an Intel Core i7-9750H
at 2.60 GHz with 16 GB of memory, running macOS 26.5 and Python 3.14.3.

| Test | Measured | Limit | Passed? |
|------|----------|-------|---------|
| Gates | 607,454 | (no limit) | |
| Build the circuit and simulator | 2.52 seconds | under 30 | yes |
| Peak memory | 115 MiB | under 1,024 | yes |
| Load all 4,096 words | 0.095 seconds | under 5 | yes |
| One read | 0.0010 seconds | under 0.1 | yes |
| One write | 0.024 seconds | under 0.1 | yes |

Three of those words need explaining.

- A **MiB** (say "mebibyte") is 1,048,576 bytes, and a byte is eight bits. The
  115 MiB covers all of Python too, so a tiny 64-word RAM still measured 19 MiB.
- The read and write figures are the **median**: line up all 100 times from
  fastest to slowest and take the one in the middle. One unlucky moment on the
  computer can't spoil a median.
- Those limits were written down *before* anything was measured, so that nobody
  could pick them to suit the answer.

A median can hide a bad day, so we also looked at the slowest. The script
`scripts/ram_tails.py` makes a longer run of 2,000 reads and 500 writes, with the
seed 2026, on the same laptop. The slowest read took 0.0047 seconds and the
slowest write took 0.036 seconds. Even a write that flipped all 16 data wires
took 0.047 seconds at most. All of those are under the limit too. Run it yourself
and your times will differ, but the gate evaluations below will not.

**How it grows.** Each extra address wire doubles the lockers. Most of these
figures double as well, more or less, but a read barely moves:

| Words | Gates | Build | Memory | Load | Read | Write |
|-------|-------|-------|--------|------|------|-------|
| 64 | 9,496 | 0.04 s | 19 MiB | 0.002 s | 0.0002 s | 0.0006 s |
| 256 | 38,042 | 0.16 s | 25 MiB | 0.005 s | 0.0002 s | 0.0013 s |
| 1,024 | 152,028 | 0.64 s | 45 MiB | 0.020 s | 0.0006 s | 0.0049 s |
| 2,048 | 303,965 | 1.25 s | 77 MiB | 0.042 s | 0.0008 s | 0.0093 s |
| 4,096 | 607,454 | 2.52 s | 115 MiB | 0.095 s | 0.0010 s | 0.024 s |

**Why is a write so much slower than a read?** In that longer run, a typical read
needed 1,745 gate evaluations (one gate working out its answer once). A typical
write needed about 43,270. A read only wakes the decoders and one word. But every data
wire runs to *every* word, because any word might be the one being written. When
one data wire changes, all 4,096 gates listening to it have to think again, and
about half of the 16 data wires change on each write. Those gates all work out
that they have nothing to do, but a simulator has to ask each of them to find out.

## Why Does This Matter?

Memory is the hard part of simulating a computer. Our whole ALU has 896 gates.
The RAM has more than 600,000, because storing things
means keeping a lot of latches ready, and nearly all of them sit still at any
moment. It only works because the simulator wakes just the gates that need it.

There is an easy shortcut: keep the numbers in a plain Python list and have the
circuit pretend. In that same longer run a list read took about 0.00000003 seconds,
which is roughly 32,000 times quicker than a typical read through the gates. We still chose real
gates, because this project promises no faking. When you zoom into a locker,
you must see a real latch holding the real bit, not a picture of one. The test on
this page was there to answer one question: can we keep that promise and still
have a computer quick enough to use? We can.

Real computers face the same trade. The memory in your phone doesn't use four
gates for each bit, because billions of latches would be far too big. It uses
much tinier cells, and a large part of designing a computer is deciding how much
fast memory you can afford.

These results come with a warning. Only the RAM was measured here. The processor
we build next adds gates of its own, which means more to build and more to wake.
An instruction does about three memory accesses, so two reads and a write would
take roughly 0.026 seconds on this laptop for the RAM alone. That's quick
enough to watch a program step along gate by gate, and much too slow to run a big
program, which is why we will need a faster way of running it too.

## What's Next

The RAM is big enough and quick enough, so 4K words it stays. We have now built
every part up to memory, but so far we have only seen numbers printed on a
screen. Next comes [The Bench](the-bench.md): a workbench with the lid off, where you can look
inside any part we have built and watch its real gates working.
