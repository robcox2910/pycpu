# Build It Yourself

## A Model Kit With a Picture on Every Bag

Think of a big model kit, the kind with a dozen numbered bags of pieces. Bag 1 makes
the base. Bag 2 makes the wheels, using only the base. Bag 3 makes the engine. Every
bag has its own little picture showing what you just made, so you never have to guess
whether you got it right, and you never need a piece from a bag you have not opened yet.

PyCPU is that kit. This page is the instruction sheet: the order to open the bags, from
a single NAND gate all the way up to a computer that runs a Pebble program and prints
a number. Each row below is one bag.

| Kit | In PyCPU |
|-----|----------|
| A numbered bag of pieces | One step of the path |
| The pieces | The Python function (or class) that builds that part |
| The picture on the bag | The test that checks the part really works |
| The booklet for that bag | The concept page for that step |
| Holding the finished model | Opening the part in the Cockpit |

## The Path

Work down the table in order. Each page is in the same order as the site's menu, so you
can also just read the menu from top to bottom. Start the Cockpit with
`uv run python -m pycpu` before you use a "Watch it" link.

| # | What you build | The function | Read | The test that checks it | Watch it |
|---|----------------|--------------|------|-------------------------|----------|
| 1 | The one brick: a NAND gate | `pycpu.circuit.Circuit` | [Switches and NAND](concepts/switches-and-nand.md) | `tests/test_simulator.py` | — |
| 2 | A way to run circuits | `pycpu.simulator.Simulator` | [Simulating a Circuit](concepts/simulating-a-circuit.md) | `tests/test_simulator.py` | — |
| 3 | NOT, AND, OR and XOR | `pycpu.logic.xor` | [Logic Gates from NAND](concepts/gates.md) | `tests/test_logic.py` | — |
| 4 | Choosing and decoding | `pycpu.logic.mux` | [Choosing and Decoding](concepts/choosing-and-decoding.md) | `tests/test_logic.py` | — |
| 5 | A window into a circuit | `pycpu.view.circuit_view` | [Looking Inside a Circuit](concepts/looking-inside.md) | `tests/test_view.py` | — |
| 6 | Adding bits | `pycpu.arithmetic.half_adder` | [Adding](concepts/adding.md) | `tests/test_arithmetic.py` | — |
| 7 | Negative numbers | `pycpu.logic.not_bus` | [Negative Numbers](concepts/negative-numbers.md) | `tests/test_logic.py` | — |
| 8 | The ALU | `pycpu.arithmetic.alu` | [The ALU](concepts/the-alu.md) | `tests/test_arithmetic.py` | http://127.0.0.1:8765/#walk=subtracting-with-gates |
| 9 | A circuit that remembers | `pycpu.memory.d_latch` | [Remembering](concepts/remembering.md) | `tests/test_memory.py` | — |
| 10 | The clock | `pycpu.memory.d_flip_flop` | [The Clock](concepts/the-clock.md) | `tests/test_memory.py` | http://127.0.0.1:8765/#walk=why-the-clock-ticks |
| 11 | Registers | `pycpu.memory.Register` | [Registers](concepts/registers.md) | `tests/test_memory.py` | open `cpu.registers` in the glass |
| 12 | RAM | `pycpu.memory.Ram` | [RAM](concepts/ram.md) | `tests/test_ram.py` | open `ram` in the glass |
| 13 | Measuring how big memory is | `pycpu.proof.measure` | [How Big Is Our Memory?](concepts/how-big-is-our-memory.md) | `tests/test_ram_proof.py` | — |
| 14 | The CPU | `pycpu.cpu.GateMachine` | [What Is a CPU?](concepts/what-is-a-cpu.md) | `tests/test_cpu.py` | — |
| 15 | Machine code | `pycpu.isa.encode` | [Machine Code](concepts/machine-code.md) | `tests/test_isa.py` | — |
| 16 | Assembly language | `pycpu.assembler.assemble` | [Assembly Language](concepts/assembly-language.md) | `tests/test_assembler.py` | — |
| 17 | The control unit | `pycpu.cpu_parts.RegisterFile` | [The Control Unit](concepts/the-control-unit.md) | `tests/test_cpu_parts.py` | open `cpu.registers` in the glass |
| 18 | Fetch, decode, execute | `pycpu.cpu.GateMachine` | [Fetch, Decode, Execute](concepts/fetch-decode-execute.md) | `tests/test_cpu.py` | — |
| 19 | The stack | `pycpu.cpu.GateMachine` | [The Stack](concepts/the-stack.md) | `tests/test_cpu.py` | — |
| 20 | Calling and returning | `pycpu.cpu.GateMachine` | [Calling and Returning](concepts/calling-and-returning.md) | `tests/test_cpu.py` | — |
| 21 | A fast twin of the CPU | `pycpu.fast.FastMachine` | [Two Engines](concepts/two-engines.md) | `tests/test_lockstep.py` | — |
| 22 | Pausing and rewinding | `pycpu.computer.Computer` | [Pausing and Rewinding](concepts/pausing-and-rewinding.md) | `tests/test_computer.py` | — |
| 23 | Pebble to machine code | `pycpu.translator.translate` | [From Pebble to Machine Code](concepts/from-pebble-to-machine-code.md) | `tests/test_translator.py` | — |
| 24 | Variables in memory | `pycpu.translator.FrameLayout` | [Variables in Memory](concepts/variables-in-memory.md) | `tests/test_frames.py` | http://127.0.0.1:8765/#walk=where-n-lives |
| 25 | 16-bit numbers that wrap | `pycpu.translator.run_pebble` | [Why 16-Bit Numbers Wrap](concepts/why-16-bit-numbers-wrap.md) | `tests/test_translator.py` | — |
| 26 | If and while as jumps | `pycpu.translator.translate` | [If and While as Jumps](concepts/if-and-while-as-jumps.md) | `tests/test_translator.py` | — |
| 27 | Function calls | `pycpu.translator.translate` | [How a Function Call Really Works](concepts/how-a-function-call-really-works.md) | `tests/test_functions.py` | http://127.0.0.1:8765/#walk=a-call-and-the-stack |
| 28 | Multiply and divide | `pycpu.translator.runtime.RUNTIME` | [Multiply and Divide](concepts/multiply-and-divide.md) | `tests/test_runtime.py` | — |
| 29 | Printing a number | `pycpu.translator.runtime.RUNTIME` | [Printing a Number](concepts/printing-a-number.md) | `tests/test_runtime.py` | — |

When you reach row 29, you have built every layer, and a Pebble program can print its
answer on a computer made of nothing but NAND gates. Now watch it all: the
[Cockpit](concepts/the-cockpit.md) shows the whole machine running, and its
[guided walks](concepts/guided-walks.md) take you through it one idea at a time. Try
http://127.0.0.1:8765/#walk=many-instructions to see one line of Pebble turn into many
instructions.

## Try It

Steps 6 and 7 of the path in one go: build a half adder, a full adder and a 4-bit
ripple adder from the ready-made functions, and count the NAND gates each one costs.
These are the same numbers the [Adding](concepts/adding.md) page prints.

```python
from pycpu.arithmetic import full_adder, half_adder, ripple_adder
from pycpu.circuit import Circuit

half = Circuit()
half_adder(half, half.input("a"), half.input("b"))
print("a half adder costs", half.gate_count, "NAND gates")

full = Circuit()
full_adder(full, full.input("a"), full.input("b"), full.input("carry"))
print("a full adder costs", full.gate_count, "NAND gates")

ripple = Circuit()
ripple_adder(ripple, ripple.bus_input("a", 4), ripple.bus_input("b", 4), ripple.low)
print("a 4-bit ripple adder costs", ripple.gate_count, "NAND gates")
# Output:
# a half adder costs 6 NAND gates
# a full adder costs 15 NAND gates
# a 4-bit ripple adder costs 60 NAND gates
```

Notice that 4 full adders at 15 gates each is exactly 60. The ripple adder adds no
gates of its own: it only joins the rung below.

## How It Works

**One rule: each rung uses only the rung below.** The half adder is built from XOR and
AND, which are built from NAND. The full adder is built from half adders. The ripple
adder is built from full adders. The ALU uses the ripple adder, the registers use the
flip-flops, and the CPU uses the ALU, the registers and RAM. At no point does a step
sneak in a shortcut. That is why the table can go in one order and never ask for a piece
you do not have yet.

**Every rung has a test.** The test file in each row builds the part from the function
in that row and checks it against the truth: every row of a truth table for the small
parts, and a long list of sums, stores and programs for the big ones. A part is only
finished when its test passes, like a model that only counts as built once it matches
the picture on the bag.

**The list can't go stale.** A test in `tests/test_docs.py` reads the table on this
page. It imports every function named, checks that every page and every test file exists,
checks that every walk and every part named is real, and checks the rows follow the same
order as the site's menu.

## Why Does This Matter?

Most people meet a computer from the top, where it is a box that does things. Building
it in order turns it round: you finish row 29 knowing that every instruction, every
Pebble line and every printed digit comes down to NAND gates doing one simple thing. And
if one step ever feels like magic, you can go back one row and find out what it was made
of.

## What's Next

Open the Cockpit with `uv run python -m pycpu` and watch the machine you built run. Start
with [A Tour of the Cockpit](concepts/a-tour-of-the-cockpit.md), then try the
[guided walks](concepts/guided-walks.md). To see the code that built any part, read
[The Code Behind a Part](concepts/the-code-behind-a-part.md).
