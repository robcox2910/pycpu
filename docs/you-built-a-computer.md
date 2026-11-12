# You Built a Computer

## A Tower of Building Blocks

Picture a tower made of one kind of brick. Not bricks and planks and steel beams, just
one brick, over and over. You glue a few bricks into a wall, a few walls into a room,
a few rooms into a floor, and when you stand back there is a whole tower. Nobody ever
brought in a different material. Every floor is made of the floor below it, and the
bottom floor is made of the one brick.

That is what you have just climbed. The brick is the **NAND** gate, a tiny switch that
answers 0 only when both of its inputs are 1. From that single brick you built every
other part of a working computer. Here is each **layer** of the tower, from the ground
up, with the page that taught it and how many NAND gates it costs.

| Layer | What it does | Gates it costs | The page |
|-------|--------------|----------------|----------|
| NAND | The one brick every other layer is built from | 1 | [Switches and NAND](concepts/switches-and-nand.md) |
| Gates | NOT, AND, OR and XOR, each made from NANDs | 1, 2, 3 and 4 | [Logic Gates from NAND](concepts/gates.md) |
| Adders | Add two bits (half adder), then two bits and a carry (full adder) | 6 and 15 | [Adding](concepts/adding.md) |
| ALU | The calculator part: add, subtract and compare 16-bit numbers | 896 | [The ALU](concepts/the-alu.md) |
| Memory | A latch remembers one bit, a flip-flop remembers it on the clock's tick | 4 and 9 | [Remembering](concepts/remembering.md) and [The Clock](concepts/the-clock.md) |
| RAM | 4,096 words of 16 bits, every bit real gates | 607,454 | [How Big Is Our Memory?](concepts/how-big-is-our-memory.md) |
| CPU | Fetches, decodes and runs instructions (with a small memory, the whole machine has 15,525 gates at 6 address bits) | 6,029 | [Two Engines](concepts/two-engines.md) |
| Assembler | Turns readable instructions into the numbers the CPU understands | 0 (it is a program) | [Assembly Language](concepts/assembly-language.md) |
| Pebble | A friendly language, translated into those instructions | 0 (it is a program) | [From Pebble to Machine Code](concepts/from-pebble-to-machine-code.md) |
| Cockpit | A screen where you watch it all run, down to one gate | 0 (it only looks) | [The Cockpit](concepts/the-cockpit.md) |

Look at the gate column. Everything up to the CPU is real NAND gates. Past that, the
layers are programs that make the machine easy to talk to, and the Cockpit lets you look
inside the layers below.

## Try It

Here is one Pebble program, `fib(10)`, which adds up numbers in a famous pattern. It
runs on the fast engine. Then a much smaller program, adding 1 to 5, runs on the real
gate engine and on the fast engine, and we check that they agree.

```python
from pycpu.cpu import GateMachine
from pycpu.fast import FastMachine
from pycpu.translator import translate
from pycpu.translator.program import run_pebble

fib = """fn fib(n) {
    if n < 2 { return n }
    return fib(n - 1) + fib(n - 2)
}
print(fib(10))
"""
run = run_pebble(fib)
print("fib(10) printed:", run.output.strip())
print("halted:", run.halted, "in", run.steps, "steps")

total = """let total = 0
for i in range(1, 6) {
    total = total + i
}
print(total)
"""
words = translate(total).program.words
fast = FastMachine(words=256)
fast.load_program(words)
gates = GateMachine(address_bits=8)
gates.load_program(words)
fast_steps = fast.run(1_000)
gate_steps = gates.run(1_000)
print("fast engine:", fast.state().output_text.strip(), "in", fast_steps, "steps")
print("gate engine:", gates.state().output_text.strip(), "in", gate_steps, "steps")
print("the same:", fast.state() == gates.state())
# Output:
# fib(10) printed: 55
# halted: True in 7953 steps
# fast engine: 15 in 548 steps
# gate engine: 15 in 548 steps
# the same: True
```

The first program needed 7,953 instructions to find 55. The second one was run twice,
once by sums and once by sending signals through the NAND gates. Both printed 15 in 548
steps, and every register and every word of memory ended up identical.

## How It Works

**Each layer only uses the one below.** The ALU never reaches past the adders, and the
adders never reach past the gates. That is why you could build the tower one floor at
a time, and test each floor before you built the next.

**The same program runs on the real gates.** Pebble is a real language that other
people use. When the translator turns your Pebble into machine code, the gate engine
runs that code, with no shortcut. Every sum goes through the ALU's NAND gates, every
remembered number sits in latches built from NAND gates. The fast engine exists only
to get the same answer sooner, and the [Two Engines](concepts/two-engines.md) page
shows how we check, instruction by instruction, that the two never disagree.

**Nothing in the middle is faked.** The NAND gate is the single primitive. No layer
above it works out a logic answer in Python. When the Cockpit shows you a wire, it is
the real wire, carrying the real value.

## Why Does This Matter?

Computers can feel like magic: a box that does whatever the screen says. You now know
the magic is a tower. It is a very tall tower, but every floor is made of the floor
below it, and the ground floor is a brick you could explain to a friend in a minute.
When something on a computer surprises you from now on, you know there is a layer
underneath, and a layer under that, and that you could in principle follow it all the
way down to one gate.

## What's Next

You can go back over the path in [Build It Yourself](build-it-yourself.md), or open
the [Cockpit](concepts/the-cockpit.md) with `uv run python -m pycpu` and take the
guided walks again, now that you know what every part is. And there is more to come:
PyStack, the project that joins the whole series together, is getting an
`import "cpu"` so that a Pebble program can run on PyCPU. It is coming to PyStack.
