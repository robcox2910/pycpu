# PyCPU: Design Spec

**Date:** 2026-11-01
**Status:** Draft, awaiting approval
**Series:** Next project in the "from scratch in Python" collection
**Role in PyStack:** The **computer itself**, the machine underneath everything else.

"Decided" below means the project owner said it. "Builder's call" means the designer chose
it and the owner can still overrule it.

## 1. Intent

Build a computer in Python in the spirit of Charles Petzold's *Code*: start from logic gates
and add layers until it runs real programs. The payoff is one moment:

> A learner watches a Pebble program run on a CPU built from scratch, hits pause at any
> instant, and can see everything going on inside, from the Pebble line down to individual
> gates, in a UI.

The series already teaches languages (Pebble), operating systems (PyOS) and databases
(PyDB). This goes one level lower and answers what is actually happening when code runs.

## 2. Goals

**Decided:**

1. A simulated 16-bit computer built up in layers.
2. Compile and run a small subset of Pebble on it.
3. A UI, the Cockpit (section 6), showing Pebble source, machine code, registers, memory and
   the current instruction all at once.
4. Zoom from any of those down to gates.
5. Pause and inspect at any moment.
6. The CPU design and compiler route leave room to grow the Pebble subset later.
7. **Everything above ships together.** The first public release is the whole thing, gates
   to Pebble in the Cockpit, integrated into PyStack. No partial layer releases.

**Builder's call:** step by gate change, clock cycle, instruction or Pebble line.

## 3. Non-goals (first release)

- Pebble beyond the subset in section 5: floats, strings as values, lists, dicts, closures,
  classes, async, generators, exceptions, imports.
- An operating system on the CPU, interrupts, or running PyOS on it.
- Modelling analogue electronics, signal timing, or transistors. The bottom layer is the
  logic gate.
- Modelling a real commercial CPU.

## 4. Anti-goals

These would make it a failure even if it technically worked.

- **Faking it.** If the zoom panel shows a drawing of gates while the real work happens in
  ordinary Python, the project has lied to the learner. What the gate view shows must be the
  actual simulated circuit computing the actual value.
- **Docs as an afterthought.** Every layer needs kid-friendly docs with analogies. This is
  the series' first priority.
- **Shipping a slice.** See goal 7.

## 5. The machine (builder's calls unless stated)

### Layers, each built only from the one below

1. Gates: NAND as the single primitive; everything else is composed from it.
2. Arithmetic: half adder, full adder, ripple-carry adder, ALU.
3. Memory: latch, flip-flop, register, RAM.
4. CPU: instruction decoder, control unit, program counter, registers, stack pointer.
5. Assembler: text to machine code.
6. Pebble: the subset compiled to machine code.

### Word size and memory

16-bit (decided). Word-addressed. The instruction set must include call/return and a stack,
because Pebble functions need them.

**RAM is 4K words, every bit real gates, with the same limit on both engines (decided).** No
behavioural store behind a gate-built sample: that would break the no-faking anti-goal. The
gate engine's speed and memory use at this size are unproven, so **prove them first, before
building upward**. If 4K is not workable, shrink the RAM rather than fake it, and tell the
owner the new size.

### Simulation engines

- **Gate engine:** the real circuit, represented as a data structure (a netlist) so the UI
  can draw exactly what is running. Event-driven, so each step costs in proportion to what
  changed, not to the size of the circuit.
- **Fast engine:** an ordinary Python model of the CPU at instruction level, used so programs
  can run at a watchable speed.
- **Equivalence is a test, not a hope.** Property tests run both engines in lockstep over
  generated programs and require identical registers, memory and flags after each
  instruction. Any difference is a bug.
- **Pause (decided):** pause lands just before the next instruction, and machine state is
  loaded into the gate engine, which is what the zoom panel displays. The learner can then
  step forward gate by gate through that instruction and rewind to its start to watch it
  again. Stopping mid-instruction at the exact click is out, because it would mean running
  whole programs at gate level.
- **Resume (decided):** pressing run finishes the current instruction in the gate engine,
  then copies state back to the fast engine at the instruction boundary.

### Pebble subset (decided in outline)

Integers, variables, `if`, `while`, functions, `print`.

**Builder's calls on the edges of the subset:**

- **Booleans exist only inside conditions.** `true`, `false`, comparisons, `and`, `or` and
  `not` work when the result is consumed by `if` or `while`. Storing, returning or printing
  one is a friendly error, because on an untagged 16-bit word `true` and `1` are identical
  and printing it would silently differ from the Pebble VM. Value tagging is a later growth
  step.
- **`print` accepts integers and string literals,** so demos can say hello. Strings are not
  otherwise values, and interpolation is out. This needs string data in memory and a
  character output device.
- **`/` is a friendly error,** because Pebble's `/` always gives a float. `//` and `%` are
  supported and floor as Pebble does (`-7 // 2` is `-4`, `-7 % 2` is `1`).
- **Runtime failures halt the machine** with a fault code, which the Cockpit reports against
  the Pebble line. Division by zero and stack overflow are checked by generated code and
  routines. Conformance compares these: a program that errors on the VM must fault on PyCPU.

- **Route:** reuse Pebble's existing front end and translate its compiled stack bytecode
  (`CompiledProgram`) into PyCPU machine code. `Instruction.location` carries the source
  location, which gives the Cockpit its Pebble-line-to-machine-code link.
- **Anything outside the subset** gets a friendly error naming the unsupported feature, never
  a crash or wrong output.
- **Integers** are 16-bit and wrap on overflow, unlike the Pebble VM. This is a teachable
  moment and must be documented as such.
- **Multiply, divide, modulo:** software routines written in PyCPU assembly unless the
  builder adds hardware for them.
- **`print`:** memory-mapped output. Number-to-decimal conversion is a routine in PyCPU
  assembly, so it is visible on the machine like everything else.
- **Conformance test:** subset programs must print the same on the Pebble VM and on PyCPU,
  for values that stay in 16-bit range.

## 6. The Cockpit (decided: layout A)

One screen with everything visible, as mocked up during design:

- top left, Pebble source with the current line highlighted
- top right, machine code with the current instruction highlighted
- below, registers and memory, with changed values marked
- bottom, a zoom panel showing the real circuit for whatever was clicked, with wires showing
  live values; the learner can drill down through ALU, adder, bit, gate

Controls: run, pause, the four step sizes, and a way to load a Pebble program.

Served by PyWeb, with live state over WebSocket or server-sent events (both exist in PyWeb).
Front-end technology is left to the builder.

## 7. Structure and integration (builder's calls)

- **Own repo:** `robcox2910/pycpu`, local `/Users/robcox/development/python/pycpu`, using the
  series conventions: uv, ruff, strict pyright, TDD, Hypothesis, conventional commits, PRs
  into a protected main, `docs/concepts/` guarded by tests, mkdocs site.
- **Dependencies:** `pebble-lang` and `pyweb` as pinned git tags; never `path` sources.
- **PyStack:** a `pycpu` plugin in `pystack/src/pystack/plugins/`, following its plugin rules
  (state on the instance, `@pebble_method`, public Pebble API only), with:
  - a shell command that launches the Cockpit
  - an `import "cpu"` Pebble module that can run a program on the CPU and return its output
  - pyproject pin, registry entry and docs
- **The Cockpit is not rebuilt in PyStack's web UI.** That UI is Flask and has no plugin web
  hook, and new modules should build on PyWeb. Launching the PyWeb Cockpit keeps both true.
- **Extending siblings is allowed.** If Pebble needs to expose anything publicly, change
  Pebble and release a tag.

## 8. Build order

Work happens in this order, with the Cockpit growing alongside so each stage can be seen and
checked locally, but nothing is released until all of it is done:

gates → arithmetic → memory → CPU → assembler → Pebble → PyStack integration → first release.

The memory stage includes the 4K-word speed and memory proof from section 5. Before writing
the Pebble stage, check Pebble's public API at the pinned tag: PyStack imports `run_source`
and `StdlibModule` from `pebble`, but the local checkout's `__init__.py` exports nothing, so
the local copy may not match the tag. Any compile entry point PyCPU needs must be public.

## 9. Definition of done

- A Pebble program using every subset feature runs on PyCPU in the Cockpit.
- It can be paused at any moment, and zoomed from Pebble line to individual gate, with the
  gate view showing the real circuit's real values.
- Both engines pass lockstep equivalence; conformance against the Pebble VM passes.
- Every layer has concept docs.
- PyStack launches it and `import "cpu"` works.

## 10. Left to the builder

Exact instruction set and encoding, register count, netlist format, wire protocol, front-end
technology, package layout, demo programs, and how the work is split into plans.
