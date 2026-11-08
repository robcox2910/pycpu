# The Code Behind a Part

## A Toy and Its Instruction Booklet

Open a box of building bricks and you find a booklet. Page 12 says "build the little
red wagon". When you have built it and you wonder how the wheels hang on, you do not
guess. You turn back to page 12.

The Cockpit works the same way. When you zoom to a part of the CPU, such as the ALU,
the page shows the part's real wires, and under them **the code that built it**: the
Python that put those gates together. It is page 12 of the booklet, open at the right
place. Start the docs on your own computer with `uv run mkdocs serve`, and the same
panel has a link to the concept page that explains the part.

| Part you zoom to | The code that built it | The page that explains it |
|------------------|------------------------|---------------------------|
| ALU (`cpu.alu`) | `pycpu.arithmetic.alu` | [The ALU](the-alu.md) |
| Registers (`cpu.registers`) | `pycpu.cpu_parts.RegisterFile.__init__` | [Registers](registers.md) |
| RAM (`ram`) | `pycpu.memory.Ram.__init__` | [RAM](ram.md) |
| Halt (`cpu.halt`) | `GateMachine._build_cpu` | [What Happens When Things Go Wrong](what-happens-when-things-go-wrong.md) |
| Write-back (`cpu.write_back`) | `GateMachine._build_write_back` | [Fetch, Decode, Execute](fetch-decode-execute.md) |
| Memory address (`cpu.address_mux`) | `GateMachine._build_datapath` | [Fetch, Decode, Execute](fetch-decode-execute.md) |
| Next instruction (`cpu.next_pc`) | `GateMachine._build_next_pc` | [Fetch, Decode, Execute](fetch-decode-execute.md) |
| Stack pointer (`cpu.next_sp`) | `GateMachine._build_write_back` | [The Stack](the-stack.md) |

## Try It

Build the gate machine and ask who built the ALU. The answer is a record with the
function's name, its file, the code, and the page that explains it. We print the parts
that stay the same when somebody edits the file: the name, the file, the first line of
code and the page.

```python
from pycpu.cockpit.code import built_by
from pycpu.cpu import GateMachine

gate = GateMachine(6)
record = built_by(gate, "cpu.alu")
print("function:", record["function"])
print("file:", record["file"])
print("first line:", str(record["code"]).splitlines()[0])
print("page:", record["page"]["url"])
# Output:
# function: pycpu.arithmetic.alu
# file: src/pycpu/arithmetic.py
# first line: with c.scope("alu"):
# page: http://127.0.0.1:8000/concepts/the-alu/
```

Two parts, the write-back and the stack pointer, are built by the same method. Each
one gets only its own block of it. RAM and halt are the odd ones out, and the second
block shows how.

```python
from pycpu.cockpit.code import built_by
from pycpu.cpu import GateMachine

gate = GateMachine(6)
for path in ("cpu.write_back", "cpu.next_sp"):
    record = built_by(gate, path)
    print(path, "is built by", str(record["function"]).split(".")[-1])
    print("   it shows:", str(record["code"]).splitlines()[0])
halt = built_by(gate, "cpu.halt")
print("halt is cut out of", str(halt["function"]).split(".")[-1])
print("   it shows:", str(halt["code"]).splitlines()[0])
ram = built_by(gate, "ram")
print("RAM shows its whole method:", str(ram["code"]).startswith("def __init__("))
# Output:
# cpu.write_back is built by _build_write_back
#    it shows: with c.scope("write_back"):
# cpu.next_sp is built by _build_write_back
#    it shows: with c.scope("next_sp"):
# halt is cut out of _build_cpu
#    it shows: with c.scope("halt"):
# RAM shows its whole method: True
```

## How It Works

**1. The CPU writes down who built what.** While `GateMachine` wires up the CPU, each
time it names a part's wires for the part view (a *tap*), it also writes down the
function that is building the part, in `GateMachine.builders`. That is a list of
names. It makes no gate and no wire, so the machine still has exactly the same number
of gates as before.

**2. `inspect` reads the live file.** Python can show you the source of any function
it is running. The standard `inspect` module finds the module on disk and hands back
the function's lines and the number of its first line. `built_by` asks for that every
time you look. Nothing is copied into a file or a string. Edit `arithmetic.py`, look
again, and the panel shows your edit. That is why the code **cannot drift** from the
circuit: it is not a description of the code, it is the code.

**3. A two-part method is cut to one block.** Some methods build more than one part.
`_build_write_back` builds the write-back choosers and then the stack pointer's
choosers. Every part the CPU builds sits inside a block that starts
`with c.scope("<name>"):`, and everything inside is indented one step deeper. So
`built_by` looks for the line that opens the viewed part's block, keeps it and every
line indented deeper than it, and stops at the first line that is not. Then it takes
the shared indentation off the front so the block reads from the left margin. The
record's `line` is the number of the first line kept, so you can find the same line
in the file.

**4. When there is no block to cut.** The halt part's block sits in `_build_cpu`, a
long method that builds the whole CPU, so the halt view shows only its three lines
there. The RAM is different: it opens its scope with a name it was given
(`with c.scope(name):`), so the words `scope("ram")` appear nowhere. The RAM view
then shows the whole of `Ram.__init__`, which is the honest answer.

**5. If the source is missing.** If the program is run from a zip file, Python may
not find the source. Then `code` is empty (`None`), the panel says "The code isn't
available here.", and the function name, file and page still show. It never fails.

## Why Does This Matter?

A picture of gates is only half an answer. The other half is "who put them there?".
Real engineers do the same thing: they open a chip's design file to see what made the
gates, and the file has to match the chip. By reading the live source, PyCPU gives you
a panel that can never be out of date, and it joins the circuit you can see to the
Python you can read.

## What's Next

Zoom to a part in the Cockpit and read its code beside its wires. For the story of how
a circuit gets watched while it runs, continue with
[The Magnifying Glass](the-magnifying-glass.md).
