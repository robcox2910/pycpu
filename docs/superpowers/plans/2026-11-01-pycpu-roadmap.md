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
| 2 | **CPU and assembler** (`2026-11-02-pycpu-02-cpu-and-assembler.md`) | Instruction set; decoder, control unit, program counter, stack pointer; fast engine; lockstep equivalence property tests; pause, step, rewind and resume between engines; assembler; fault halts. Bench shows registers, memory and current instruction. |
| 3 | **Pebble on the CPU** (`2026-11-03-pycpu-03-pebble-on-the-cpu.md`) | Bytecode-to-machine-code translator with source-line map; friendly errors at the subset's edges; multiply, divide, modulo, decimal-print routines in assembly; string-literal print; conformance against the Pebble VM. |
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
Slowest seen in one run: read 0.0047 s, write 0.0477 s, and a write flipping all 16 data wires
0.065 s. Outlier: another run, on a busy machine, saw the all-16-flip write take 0.179 s, so
tails are a snapshot and only the medians carry limits. Plain list read about 2.7e-08 s. Gate evaluations do not vary between runs.

**This is the RAM alone.** The CPU adds gates in Plan 2, so these figures are a floor, not a
forecast. A write is costly (median about 43,270 gate evaluations against 1,745 for a read, from the same script) because
each changed data wire wakes one gate per word. Two reads and a write take about 0.026 s, which
suits gate stepping and is why long runs need Plan 2's fast engine.

## Engine result

**Both engines meet every limit at full size, with the 4K RAM unchanged and no engine changes
needed.** The fast engine's handler table is still rebuilt on every step; it clears its floor
more than three times over, so that deferred item stays deferred.

Measured 2026-11-02 with `scripts/measure_engines.py` (`measure_engines` in
`src/pycpu/proof.py`), fresh process, on an Intel Core i7-9750H at 2.60 GHz with 16 GB, macOS
26.5, Python 3.14.3. Both engines run one looping program (ALU, LOAD/STORE, PUSH/POP,
CALL/RET, BR, JMP) from the same state, with the rest of RAM random words from seed 2026. The
gate engine's state after its 60 timed instructions must equal the fast engine's after 60 steps.

| Measure | Result | Limit |
|---|---|---|
| `cpu_gates` (outside the RAM) | 6,023 | none |
| `total_gates` | 613,477 | none |
| `build_seconds` | 2.83 | under 30 |
| `memory_mib` | 113 | under 1024 |
| `pause_seconds` (median of 5 `load_state`) | 0.106 | under 2 |
| `read_state_seconds` (median of 5 `state()`) | 0.013 | under 2 |
| `gate_instruction_seconds` (median of 60 `step()`) | 0.0236 | under 0.5 |
| `fast_instructions_per_second` (one run of 300,000) | 176,811 | over 50,000 |

Ranges seen across five fresh runs, not bounds: build 2.65 to 2.92 s, memory 112 to 115 MiB,
pause 0.099 to 0.108 s, read state 0.012 to 0.014 s, gate instruction 0.0233 to 0.0251 s,
fast 153,618 to 176,811 instructions per second. The fast engine is about 4,000 times quicker
than the gate engine (about 42 instructions per second on gates).

Lockstep (`tests/test_lockstep.py`, 64-word machine): 200 random whole states and 200 random
assembled programs, each compared after every step for up to 30 steps, plus a pinned
self-modifying-code case. No disagreement was found. A deliberately broken fast `shr` carry
was caught by the random-state test.

## Notes for Plan 2

- Start by adding slow tests for the combined stack: full RAM + ALU + registers in one
  circuit, cloning into a second `Simulator`, and rewinding via state pairs. A scratch
  experiment at 608,954 gates measured: build 2.07 s, 109 MiB, 50 ticks 0.72 s, rewind 0.05 s
  with 0 wire diffs, clone 0.10 s.
- `settle` cannot step one gate at a time, which the spec's pause needs.
- Rewinding from mid-tick must drop the clock wires and settle before poking.
- A bare `d_latch` registers no state pair, so CPU state held in one would escape cloning.
- After an `OscillationError` the simulator is inconsistent; treat it as dead.
- RAM cells are level-sensitive latches, so `data` and `address` must not depend on `ram.out`
  during a write; latch the value through a register first (`data = ram.out + 1` oscillates).
- `pynet` is imported directly but arrives only through `pyweb`; declare it when pins change.
- Add a full-size test touching address 4095.
- Make the Bench "Read more" entries real links once a site exists.

## Notes for Plan 3

What Plan 2 learned, measured on the same Intel Core i7-9750H laptop (macOS 26.5, Python
3.14.3) unless stated.

- **Gate steps per instruction.** Running the Bench's `DEMO_PROGRAM` to its halt, one
  instruction took 6,988 to 43,045 gate steps at full size (4K words), and 6,736 to 15,213
  on a 64-word machine. Writes to RAM are the slow ones: each changed data wire wakes a
  gate in every word. Pinned by the slow tests in `tests/test_bench.py`. A Pebble line will
  be several instructions, so the Cockpit's "step a line on gates" can mean 100,000+ gate
  steps; step by beat or instruction there, not by gate.
- **Engine speeds** (from the Engine result above): the fast engine runs about 150,000 to
  177,000 instructions per second, the gate engine about 42 (0.024 s per instruction).
  Plan 3's conformance runs against the Pebble VM must use the fast engine; gate runs are
  for lockstep spot checks only.
- **`halt_code` is 8 bits** (`HALT imm8`, `HALT_CODE_MAX`), on both engines. Plan 3's error
  codes (`STACK_OVERFLOW = 2`, `DIVIDE_BY_ZERO = 3` and any more) must fit in 0 to 255.
- **The Bench at full size.** `create_bench()` measured 3.05 to 3.10 s over three fresh
  builds (the `GateMachine` is built once and kept; loading a new program reuses it).
  Through PyWeb's `TestClient`: `GET /api/machine` 0.016 s (reading `state()` peeks all
  4,096 words), a cycle step 0.026 s, 100 gate steps 0.015 s, 100,000 gate steps 0.32 s.
  `python -m pycpu` prints "Building the computer from NAND gates..." before the address.
- **Bench API shape.** Every route answers with the same machine picture. The current
  instruction is read at `instruction_start.pc` from `instruction_start.memory`, because
  half way through an instruction `pc` has moved on. A gate step takes a `count` (1 to
  100,000) and stops early on a halt; cycle and instruction steps refuse any count but 1.
  `POST /api/program` reuses the built machine (`Computer.load_program`) instead of
  building a new one. The Cockpit should keep this shape and add the Pebble source map.
- **Carried from the Plan 2 ledger:**
  - `FastMachine.step` still rebuilds its opcode handler dict on every step
    (`FastMachine._handlers`). Not fixed: the engine clears its 50,000 floor more than
    three times over. Fix it if Plan 3's conformance runs are too slow.
  - `scripts/measure_engines.py` keeps its own copy of the limits in `tests/test_engine_speed.py`;
    a change to one can drift from the other. Move them into `proof.py` and import both.
  - The ledger noted that `assemble` used `splitlines`, so `\x0b`, `\x0c` and similar would
    count as line breaks. Checked for this note: `assemble` splits on `"\n"` only (since
    33b6055), so line numbers match an editor's; `li r0, 1\x0bli r1, 2` is one bad line 1.
    Text with `\r\n` line ends also assembles. Nothing to carry.
- The Bench's "Read more" entries are still plain text; make them real links when the site
  is published (carried from the Plan 2 notes).

## Notes for Plan 4

What Plan 3 learned, measured on the same Intel Core i7-9750H laptop (macOS 26.5, Python
3.14.3) on 2026-11-03 with throwaway scripts (not in the repo).

- **Instructions per Pebble line** (fast engine, the 15 programs in `tests/pebble_programs/`,
  run to their halt, 77,141 instructions in all). Three ways to count:
  - A run of consecutive instructions on one line's own words: min 1, median 12, max 61
    (1,887 runs).
  - A run inside the runtime routines (`__mul`, `__divmod`, `__print_int`, `__print_text`;
    source-map line `None`): min 14, median 153, max 875 (365 runs).
  - "Step a Pebble line" = from entering a line until a *different* located line starts,
    with routine instructions counted toward the line that called them: min 3, median 22,
    max 1,022 (1,612 steps). A `print` line is the expensive one: printing `2` costs
    4 instructions of its own plus 170 in `__print_int` (the Bench page's Try It pins both).
- **Gate steps per Pebble line at full size (4K words).** The Bench page's Try It countdown
  (`let n = 2` ... `print(n)` ...) on the gate engine, stepped gate by gate: 426 instructions,
  16,166,978 gate steps, 36.6 s (about 442,000 gate steps per second). Per instruction:
  min 6,154, median 22,082, max 172,502. Per line step (routines counted in): `let n = 2`
  400,733; `while n > 0` about 390,000; `n = n - 1` about 530,000; `print(n)` about 6.7 million
  (174 instructions). Median line step 490,376 gate steps.
- **What the Cockpit's "step a Pebble line" should do.** Run the line on the **fast
  engine** and pause at the first instruction of the next located line (resume, then step
  instruction by instruction on the fast engine until `line_at(pc)` changes to a different
  non-`None` line, then pause). On gates a line is about half a million gate steps (over a
  second) and a `print` line about 15 seconds, so stepping a line on gates is not
  interactive; the gate view is for zooming *within* an instruction. Two choices to make:
  (1) step *over* a user function call (stop only on a line of the same frame, compare
  `r7`) versus step *into* it (stop on the callee's first line) — offer both, like a real
  debugger; (2) routine instructions (`None`) always count toward the calling line, never
  stop. Cap a line step at `MAX_RUN` instructions so `while true {}` cannot hang a request.
  The Bench already gives the pieces: `TranslatedProgram.line_at`, the `pebble` key in the
  machine picture, and `POST /api/pebble`.
- **Bench API (Plan 3 shape).** `POST /api/pebble` `{"source": ...}` reuses the built
  machine (`Computer.load_program`, as `/api/program` does). The machine picture's `pebble`
  is `null` for assembly, else `{"source": [lines], "line": n | null, "message": str | null}`;
  `line` is read at `instruction_start.pc`, and once halted it is the line to blame (null
  after a normal finish) with `message` from `PebbleRun.describe()` (built by the new
  `PebbleRun.from_state`). A refused program is a 400 with PyWeb's usual `error`/`message`
  plus `line` and `column`. A small Bench (tests use 8 address bits, 256 words) refuses a
  program bigger than its memory with a 400.
- **Pebble VM bugs found** (both in the VM, not PyCPU):
  - A function that falls off its end after a `return` inside an `if` crashes the VM with
    `IndexError` (PyCPU returns null, as Pebble's own functions-without-return do). Fixed
    upstream in pebble-lang PR #84 (merge pending, to ship as v0.4.1, unreleased). Once it
    ships: raise PyCPU's floor to `fromscratch-pebble>=0.4.1`, and remove the
    `# Pebble v0.4.1:` workarounds in the tests (grep for that marker).
  - Calling a variable as a function (`let x = 1` then `x()`) crashes the Pebble v0.4.0 VM
    with `KeyError`. Not yet reported upstream. PyCPU refuses it as "functions used as values".
- **Carried from the Plan 3 ledger (minors that matter later):**
  - Stepped `range(a, b, step)` is refused ("range with a step"): Pebble lowers it with a
    `throw` guard against a zero step, which needs a new fault code to support.
  - Plan 5's series sync: `mkdocs.yml`'s theme block lacks the current template's
    `custom_dir`/overrides and plugins (search, social); the README lacks the series-managed
    Documentation/Install/Related blocks; the template CLAUDE block says docs deploy to Pages,
    which is not yet true.
  - `FastMachine.step` still rebuilds its opcode handler table on every step. The
    conformance corpus ran fast enough without fixing it, but the Cockpit's fast line step
    calls `step` per instruction: fix it if line steps feel slow.
  - Long source lines in `printing-a-number.md` and `from-pebble-to-machine-code.md` (render fine).
  - The engine speed limits now live once, in `pycpu.proof.ENGINE_LIMITS` (done in Plan 3).

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
