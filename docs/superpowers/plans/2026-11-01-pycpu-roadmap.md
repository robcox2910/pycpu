# PyCPU Implementation Roadmap

The spec (`docs/superpowers/specs/2026-11-01-pycpu-design.md`) is built as five sequential
plans. Each produces working, tested software on its own, and each adds to the local Bench
page so progress can be seen. **Nothing is tagged or released until Plan 5** (spec goal 7);
merging to `main` is fine, publishing a version is not.

Only Plan 1 is written in detail. Later plans are written when the one before finishes,
because each depends on what the last one proved: Plan 2's memory size comes from Plan 1's
proof, and Plan 3 depends on Pebble's public API at the pinned tag.

| # | Plan | Deliverable |
|---|------|-------------|
| 1 | **Gates to memory** (`2026-11-01-pycpu-01-gates-to-memory.md`) | Repo scaffold; netlist and event-driven gate engine; logic gates from NAND; adder and ALU; latch, flip-flop, register, RAM; the 4K-word proof, with its result recorded; Bench page with a live circuit view. |
| 2 | **CPU and assembler** | Instruction set; decoder, control unit, program counter, stack pointer; fast engine; lockstep equivalence property tests; pause, step, rewind and resume between engines; assembler; fault halts. Bench shows registers, memory and current instruction. |
| 3 | **Pebble on the CPU** | Bytecode-to-machine-code translator with source-line map; friendly errors at the subset's edges; multiply, divide, modulo, decimal-print routines in assembly; string-literal print; conformance against the Pebble VM. |
| 4 | **The Cockpit** | Bench grows into the full layout A: Pebble and machine-code panes, registers, memory, drill-down zoom panel, four step sizes, program loading, live updates over WebSocket or SSE. |
| 5 | **Integration and first release** | PyStack `pycpu` plugin (shell command, `import "cpu"`, pin, registry, docs); complete docs and README; final definition-of-done pass against spec section 9; add PyCPU to the series with the runbook in `robcox2910.github.io/README.md` (`series.yml`, `HOME_GROUPS`, enable Pages, `series sync`, `series hub`); `v0.1.0` tag. |

## Proof result

**`RAM_ADDRESS_BITS` stays 12: 4,096 words of 16 bits, every bit real gates. All limits met,
with no engine changes needed.** Plan 2 can rely on this size.

Measured 2026-11-02 with `scripts/prove_ram.py` (`measure` in `src/pycpu/proof.py`), fresh
process, on an Intel Core i7-9750H at 2.60 GHz with 16 GB, macOS 26.5, Python 3.14.3. RAM holds
random words from a fixed seed; reads and writes go through the gates at random addresses, and
a write includes `Simulator.tick`. Every read, and every word after the writes, is checked.

| Measure | Result | Limit |
|---|---|---|
| `gates` | 607,454 | none |
| `build_seconds` | 2.52 | under 30 |
| `memory_mib` | 115 | under 1024 |
| `load_seconds` | 0.095 | under 5 |
| `read_seconds` (median of 100) | 0.0010 | under 0.1 |
| `write_seconds` (median of 100) | 0.024 | under 0.1 |

Ranges seen across five fresh runs, not bounds, since timings move with whatever else the
laptop is doing (an independent run saw load 0.11 s and write 0.0277 s, both outside these):
build 2.49 to 2.71 s, memory 111 to 115 MiB, load 0.091 to 0.102 s, read 0.0009 to 0.0010 s,
write 0.023 to 0.027 s.

`scripts/ram_tails.py` (seed 2026; 2,000 reads, 500 writes) gives the tails on the same laptop.
Slowest seen in one run: read 0.0047 s, write 0.036 s, and a write flipping all 16 data wires
0.047 s. Plain list read about 2.7e-08 s. Gate evaluations do not vary between runs.

**This is the RAM alone.** The CPU adds gates in Plan 2, so these figures are a floor, not a
forecast. A write is costly (median about 43,270 gate evaluations against 1,745 for a read, from the same script) because
each changed data wire wakes one gate per word. Two reads and a write take about 0.026 s, which
suits gate stepping and is why long runs need Plan 2's fast engine.

## Rule #1: docs ship with the code

Documentation is as important as code, and it outranks everything else in these plans. The
audience is a curious 12-year-old. Plan 1's **Documentation Standard** applies to all five
plans: copy it into each one.

- Docs are written first. A page's `## Try It` is run by `tests/test_docs.py`, so it fails
  until the code exists.
- Every idea gets its own page, reading as one continuous climb, and each page shows how the
  thing is built from the layer below, not just how to use it.
- `docs/index.md` and `docs/from-scratch.md` tell the whole story of what this project is and
  why it starts from nothing. Each plan updates them.
- Reviewers read as the 12-year-old and reject weak explanations. A task with good code and
  weak docs is not done.

**Pages still to come, on top of Plan 1's:**

- **Plan 2:** what a CPU is; instructions and machine code; the fetch-decode-execute cycle;
  the control unit; the stack; calling and returning; assembly language; two engines and why
  they must agree; pausing and rewinding.
- **Plan 3:** from Pebble to machine code; variables in memory; `if` and `while` as jumps;
  how a function call really works; multiply and divide with only adding and shifting;
  printing a number; what happens when things go wrong; why 16-bit numbers wrap.
- **Plan 4:** a guided tour of the Cockpit, following one Pebble line all the way to a gate.
- **Plan 5:** PyCPU's place in PyStack, and a closing "you built a computer" page tying the
  whole climb together.
