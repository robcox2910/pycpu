# PyCPU Plan 2: CPU and Assembler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Plan 1's gates and memory into a working 16-bit computer: an instruction set, a CPU built from gates, a fast instruction-level engine that provably agrees with it, an assembler, pause/step/rewind/resume between the engines, and a Bench that shows registers, memory and the current instruction.

**Architecture:** The instruction set is defined once in `isa.py`. `FastMachine` (plain Python) and `GateMachine` (NAND gates plus Plan 1's 4K RAM) both implement it, both read and write the same `MachineState`, and Hypothesis runs them in lockstep from random states. Every instruction takes two clock cycles, fetch then execute. A `Computer` runs on the fast engine and, on pause, loads its state into the gates so a learner can step gate by gate, rewind, and resume.

**Tech Stack:** Python 3.14, uv, pytest, Hypothesis, ruff, strict pyright, PyWeb v0.3.1 (Bench), mkdocs-material.

**Spec:** `docs/superpowers/specs/2026-11-01-pycpu-design.md`. Roadmap, Proof result and Notes for Plan 2: `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`. Plan 1 (for how existing code was built): `docs/superpowers/plans/2026-11-01-pycpu-01-gates-to-memory.md`.

## Global Constraints

- NAND is the single primitive. Nothing above `simulator.py` computes a logic result in Python, except test helpers, `peek`/`poke`, and the fast engine (which is a separate engine by design and never feeds the gate view).
- The gate view must show the real circuit's real values. Never fake it.
- RAM is 4K words of 16 bits (`RAM_ADDRESS_BITS = 12`), every bit real gates, with the same size on both engines. Never add a behavioural store to the gate engine.
- 16-bit words, word-addressed. Buses are tuples of wires, least significant bit first. Arithmetic wraps at 16 bits.
- RAM cells are level-sensitive latches: a RAM write's `data` and `address` must never depend on `ram.out`. Route every value read from RAM through a register first.
- All CPU state lives in `Register`s or the `Ram`, so it is registered as state pairs. Never hold machine state in a bare `d_latch`.
- After an `OscillationError` a simulator is dead; nothing may keep using it.
- Never use `TYPE_CHECKING` or `from __future__ import annotations`.
- Documentation is as important as code, and ranks above every other rule here. See the Documentation Standard below. A task with weak docs is not done, however good its code is.
- Do not publish: GitHub Pages stays off, `docs.yml` stays manual-only, no `series.yml` entry, no version tag. The owner turns the site on when the project is complete. `mkdocs build --strict` must pass at every commit.
- Work on branch `plan-2-cpu-and-assembler`; one PR into `main` at the end, merged when CI is green.
- Conventional commits ending with the `Co-Authored-By` line.

## Documentation Standard

This project exists to teach. The audience is a curious 12-year-old who has never heard of a logic gate. Read `pyweb/docs/concepts/server-sent-events.md` for the tone and shape to match.

**Write the doc first.** In every task with a concept doc, the doc is written before the code. Its `## Try It` block fails until the code exists, so it is part of the red step, and the doc shapes the API a learner sees.

**Every concept page has these, in this order:**

1. `# Title`, then a `##` heading naming an everyday analogy, opening with that analogy before any jargon.
2. A table mapping the analogy to the real thing, using the actual names in the code.
3. `## Try It`: a complete, copy-paste Python example with its output in a comment. `tests/test_docs.py` runs it.
4. `## How It Works`: the step-by-step, with an ASCII diagram, showing how the thing is *built* from the layer below, not just how to use it. Name the file it lives in.
5. `## Why Does This Matter?`: what would be impossible without it, and a link to the real world.
6. `## What's Next`: a link to the next page, so the docs read as one continuous climb.

**The site must also tell the whole from-scratch story.** A learner landing on `docs/index.md` should understand what the project is, why anyone would build a computer out of nothing, and how to read it. Each page builds only on pages before it, and every new word is explained where it first appears.

**Docstrings:** every public module, class and function has one. Module docstrings open with an analogy, in the style of `pystack/src/pystack/plugins/llm_plugin.py`. Class and function docstrings say what the thing is in plain words before any jargon, and are still imperative and Google-style. Private helpers explain *why* where it is not obvious.

**Tests read as sentences** and double as examples.

**Reviewers check docs as a first-class gate.** For every task, the reviewer reads the docs as if they were the 12-year-old, follows `## Try It`, and rejects the task if a page leans on an unexplained word, skips how the thing is built, or only describes the API. Tests can catch a missing section, not a bad explanation.

**Honesty rule for docs:** the numbers in docs are measured, never invented. Output in `## Try It` is checked by running it.

**Every new page** goes in `mkdocs.yml` nav and in `KEY_IDEAS` in `tests/test_docs.py`, and the previous page's `## What's Next` links to it.

## Review Focus

- Any 16-bit word can be an instruction, and any state can be loaded: random memory, registers, SP, PC and flags must give identical results on both engines, including faults, and never a Python exception. Test in Task 7 (lockstep from random states).
- Memory edges: PC running past the end of RAM, PUSH with SP = 0 (address `0xFFFF`, which is the output port but PUSH is not STORE), POP/RET with SP = the RAM size, LOAD from `0xFFFF`: each must halt with `Fault.BAD_ADDRESS` and change nothing else. Tests in Task 2 (fast) and Tasks 5–6 (gates).
- A program that writes over its own next instruction must fetch the new word on both engines. Pinned lockstep case in Task 7.
- Pause, step some gates, rewind, step again, resume: the result must equal a straight fast run, with no drift. Test in Task 8.
- Any text given to the assembler, however wrong, gives an `AssemblyError` naming the line, never another exception. Hypothesis test in Task 3.

---

## The Instruction Set

This section is the contract both engines implement. Task 2 turns it into `isa.py` and the reference page; every later task consumes it.

**Registers:** `r0`–`r7`, 16 bits each, all general. `pc` (16 bits), `sp` (16 bits), flags `zero`, `negative`, `carry`, `overflow`.

**Power-on:** everything 0 except `sp = words` (the RAM size, so the first PUSH writes the top word).

**Encoding:** one 16-bit word per instruction; opcode in bits 15–12. Field positions: `rd` (or `cond`) bits 11–9, `ra` bits 8–6, `rb` bits 5–3, `fn` bits 2–0, `imm8` bits 7–0, `off6` bits 5–0 (signed), `off9` bits 8–0 (signed), `addr12` bits 11–0. Unused bits are written 0 and ignored when decoding.

| Op | Name | Fields | Effect | Flags |
|---|---|---|---|---|
| 0 | `ALU` | rd ra rb fn | `rd = ra <fn> rb` with `fn` an `AluOp` (mnemonics `add sub and or xor shl shr mov`; `shl`/`shr` use `ra` only, `mov rd, rb` uses `rb` only) | set |
| 1 | `CMP` | ra rb | flags from `ra - rb`; no register changes | set |
| 2 | `LI` | rd imm8 | `rd = imm8` (0–255) | kept |
| 3 | `LHI` | rd imm8 | `rd = (imm8 << 8) \| (rd & 0xFF)` | kept |
| 4 | `LOAD` | rd ra off6 | `rd = mem[ra + off6]` | kept |
| 5 | `STORE` | rd ra off6 | `mem[ra + off6] = rd` | kept |
| 6 | `JMP` | addr12 | `pc = addr12` | kept |
| 7 | `CALL` | addr12 | push `pc`, then `pc = addr12` | kept |
| 8 | `BR` | cond off9 | if `cond` holds, `pc = pc + off9` | kept |
| 9 | `RET` | – | pop into `pc` | kept |
| 10 | `PUSH` | rd | `sp = sp - 1`, `mem[sp] = rd` | kept |
| 11 | `POP` | rd | `rd = mem[sp]`, `sp = sp + 1` | kept |
| 12 | `GETSP` | rd | `rd = sp` | kept |
| 13 | `SETSP` | rd | `sp = rd` | kept |
| 14 | `ADDI` | rd imm8 | `rd = rd + imm8` (signed, −128 to 127) | set |
| 15 | `HALT` | imm8 | stop, with `halt_code = imm8` (0 means finished normally) | kept |

`pc` already points at the next instruction when an instruction executes (fetch adds 1), so `CALL` pushes the return address and `BR` offsets count from the next instruction. All address and register arithmetic wraps at 16 bits.

**Conditions** (`Condition`, 3 bits): `EQ=0` zero; `NE=1` not zero; `LT=2` negative ≠ overflow; `GE=3` negative = overflow; `LE=4` zero or negative ≠ overflow; `GT=5` not zero and negative = overflow; `LTU=6` not carry; `GEU=7` carry.

**Memory map:** addresses `0` to `words - 1` are RAM. `OUTPUT_PORT = 0xFFFF` is a write-only character port: `STORE` there appends the stored word to `output` instead of writing RAM. Every other access outside RAM, including a fetch, any LOAD/POP/RET from the port, and PUSH/CALL to it, is a fault.

**Faults** (`Fault`, an `IntEnum` of halt codes): `BAD_ADDRESS = 1` (raised by the hardware), `STACK_OVERFLOW = 2` and `DIVIDE_BY_ZERO = 3` (reserved for Plan 3's generated code, which raises them with `HALT`). A fault sets `halted` and `halt_code` and changes nothing else. In a fetch fault `pc` stays at the bad address; in an execute fault `pc` is already one past the faulting instruction. A halted machine ignores further steps.

**Output device:** the port is a peripheral outside the CPU, like a screen. On the gate engine, a small piece of Python watches the CPU's real `port_write` wire and data bus at the write pulse, the way a terminal watches a cable. It never computes anything the CPU should.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pycpu/simulator.py` | Modify: `step` (one gate), `storage`/`restore_storage`, dead after oscillation |
| `src/pycpu/isa.py` | `Opcode`, `Condition`, `Fault`, `OUTPUT_PORT`, `Instruction`, `encode`, `decode`, `condition_holds` |
| `src/pycpu/state.py` | `Flags`, `MachineState`, `power_on` |
| `src/pycpu/fast.py` | `alu_model`, `FastMachine` |
| `src/pycpu/assembler.py` | `assemble`, `Program`, `AssemblyError`, `disassemble` |
| `src/pycpu/cpu_parts.py` | Gate builders: `RegisterFile`, `opcode_lines`, `condition_met`, `sign_extend`, `outside_ram` |
| `src/pycpu/cpu.py` | `GateMachine`, `Phase`, `MicroStep`: the CPU wired to the RAM |
| `src/pycpu/computer.py` | `Computer`: run fast, pause into gates, step, rewind, resume |
| `src/pycpu/bench/app.py`, `page.html` | Bench grows to show the machine |
| `scripts/measure_engines.py` | Full-size engine measurements |
| `tests/test_<module>.py`, `tests/test_lockstep.py`, `tests/test_combined_stack.py` | Tests |
| `examples/run_assembly.py` | Example: assemble and run a program |

**Pages in reading order** (all new pages go after `how-big-is-our-memory.md` in a new nav section "The Computer"; `the-bench.md` moves to the end of that section):

| Page | Task | Teaches |
|---|---|---|
| `concepts/simulating-a-circuit.md` (extend Try It) | 1 | Stepping one gate at a time |
| `concepts/what-is-a-cpu.md` | 2 | A CPU is a machine that follows a list of instructions; registers, PC |
| `concepts/machine-code.md` | 2 | Instructions as numbers; opcodes and fields; the flags; faults |
| `reference/instruction-set.md` | 2 | The full table above, for looking things up (not a concept page) |
| `concepts/assembly-language.md` | 3 | Words people can read, turned into numbers; labels |
| `concepts/the-control-unit.md` | 4 | Decoding: how an opcode lights the right wires; the register file |
| `concepts/fetch-decode-execute.md` | 5 | The two-beat cycle in gates; jumps and branches; output port; faults |
| `concepts/the-stack.md` | 6 | A pile of plates; SP; push and pop |
| `concepts/calling-and-returning.md` | 6 | CALL and RET; why functions need the stack |
| `concepts/two-engines.md` | 7 | Why a fast engine exists, why it must agree, and the measured speeds |
| `concepts/pausing-and-rewinding.md` | 8 | Pause, step gate by gate, rewind, resume |
| `concepts/the-bench.md` (rewrite) | 9 | Looking inside the running computer |

---

### Task 1: Simulator stepping, storage and the combined-stack check

**Files:**
- Modify: `src/pycpu/simulator.py`, `docs/concepts/simulating-a-circuit.md`
- Test: `tests/test_simulator.py`, `tests/test_combined_stack.py` (new), `tests/test_ram.py`

**Interfaces:**
- Produces:
  - `Simulator.step() -> int`: evaluate the one gate at the front of the queue, exactly as `settle` would next; return its gate id, or `-1` if nothing is waiting.
  - `Simulator.pending -> int` (property): how many gates are waiting.
  - `Simulator.storage() -> bytes`: the `q` value of every state pair, in `circuit.state_pairs` order.
  - `Simulator.restore_storage(bits: bytes) -> None`: poke every pair from `bits`, then settle. Raises `ValueError` if the length is wrong. The caller must have dropped `clk` and `write` to 0 and settled first (document this).
  - After an `OscillationError`, `set`, `settle`, `step`, `tick`, `poke_pairs` and `restore_storage` raise `RuntimeError` saying the simulator stopped after an oscillation and a new one is needed.

- [ ] **Step 1: Write failing tests** in `tests/test_simulator.py`:
  - `test_stepping_gate_by_gate_ends_where_settle_ends`: build a 16-bit `ripple_adder`, two simulators, same inputs; settle one, `step()` the other until it returns `-1`; every wire value is equal, and the number of steps equals `settle`'s return value.
  - `test_step_with_nothing_waiting_returns_minus_one` and `pending` counts down to 0.
  - `test_a_simulator_is_dead_after_an_oscillation`: a NOT fed its own output, small `max_events`; after the `OscillationError`, `settle()` raises `RuntimeError`.
  - `test_storage_round_trips_into_a_second_simulator`: a `Register` and a 16-word `Ram` with values poked; `restore_storage(first.storage())` on a fresh simulator of the same circuit makes every wire equal.
  - `test_restore_storage_rejects_the_wrong_length`.
- [ ] **Step 2: Write the slow combined-stack tests** in `tests/test_combined_stack.py` (`@pytest.mark.slow`, `@pytest.mark.timeout(600)`): one circuit with the full 4K `Ram`, an `alu`, and eight 16-bit `Register`s, as in the roadmap's scratch experiment. Assert: clone via `storage`/`restore_storage` into a second simulator gives 0 differing wires; after 50 ticks with changing inputs, restoring the saved storage (clock wires low, settled first) gives 0 differing wires against the saved wire values. Add to `tests/test_ram.py` a slow test that writes and reads address 4095 (the roadmap note).
- [ ] **Step 3: Extend `docs/concepts/simulating-a-circuit.md`** first: a second `## Try It` block (keeping section order) stepping a half adder gate by gate with `step()`, printing each gate and the wire it changed, explained as watching dominoes fall one at a time. Add `step` to its `KEY_IDEAS`.
- [ ] **Step 4: Run** `uv run pytest tests/test_simulator.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 5: Implement.** `settle` and `step` share one evaluation rule; refactor so `settle` is not slower (measure with `scripts/prove_ram.py` before and after; the write median must stay within 10%).
- [ ] **Step 6: Run** `uv run pytest` and `uv run pytest -m slow tests/test_combined_stack.py tests/test_ram.py --no-cov -v`. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "feat: step one gate at a time and save simulator storage"`

---

### Task 2: The instruction set and the fast engine

**Files:**
- Create: `src/pycpu/isa.py`, `src/pycpu/state.py`, `src/pycpu/fast.py`, `docs/concepts/what-is-a-cpu.md`, `docs/concepts/machine-code.md`, `docs/reference/instruction-set.md`
- Test: `tests/test_isa.py`, `tests/test_fast.py`

**Interfaces:**
- Consumes: `AluOp` from `pycpu.arithmetic`; `RAM_WORDS`, `WORD_BITS` from `pycpu.memory`.
- Produces:
  - `isa.py`: `class Opcode(IntEnum)` (names and numbers as the table); `class Condition(IntEnum)`; `class Fault(IntEnum)`; `OUTPUT_PORT = 0xFFFF`; `@dataclass(frozen=True) class Instruction: opcode: Opcode; rd: int = 0; ra: int = 0; rb: int = 0; fn: int = 0; imm: int = 0` (`rd` doubles as `cond`; `imm` holds the signed value of whichever immediate the opcode uses); `encode(opcode: Opcode, *, rd=0, ra=0, rb=0, fn=0, imm=0) -> int` (raises `ValueError` naming the field when a value does not fit); `decode(word: int) -> Instruction`; `condition_holds(cond: Condition, flags: Flags) -> bool`.
  - `state.py`: `class Flags(NamedTuple): zero: int; negative: int; carry: int; overflow: int`; `@dataclass(frozen=True) class MachineState: pc: int; sp: int; registers: tuple[int, ...]; flags: Flags; memory: tuple[int, ...]; halted: bool; halt_code: int; output: tuple[int, ...]` with `output_text` property (`"".join(chr(w & 0xFF) ...)`); `power_on(words: int = RAM_WORDS) -> MachineState`.
  - `fast.py`: `alu_model(a: int, b: int, op: AluOp) -> tuple[int, Flags]`; `class FastMachine: __init__(self, words: int = RAM_WORDS)`, `words`, `load_state(state)`, `state() -> MachineState`, `load_program(words: Sequence[int])` (into memory from address 0, after `power_on`), `step() -> bool` (False if already halted), `run(max_steps: int) -> int` (steps taken; stops at halt).

- [ ] **Step 1: Write the docs first.** `what-is-a-cpu.md` (analogy: a cook following a recipe card by card, with a finger on the current line, which is the PC, and a few bowls on the counter, which are the registers). `machine-code.md` (analogy: a secret code where each number is an order; split one word into its fields on screen; the flags as four lamps; a fault as the machine refusing an impossible order). Both Try Its use `encode`, `decode` and `FastMachine` on the countdown program below written as raw words. `reference/instruction-set.md`: the Instruction Set section above as a page, with a worked encoding for every opcode. `KEY_IDEAS`: `what-is-a-cpu.md: ["instruction", "register", "program counter"]`, `machine-code.md: ["opcode", "flag", "fault"]`. The reference page is in the nav under "Reference" but not in `docs/concepts/`, so the concept-section guard skips it.
- [ ] **Step 2: Write failing tests** in `tests/test_isa.py`:
  - pinned encodings: `encode(Opcode.ALU, rd=3, ra=1, rb=2, fn=AluOp.ADD) == 0x0650`; `encode(Opcode.LI, rd=1, imm=5) == 0x2205`; `encode(Opcode.LOAD, rd=1, ra=2, imm=-1) == 0x42BF`; `encode(Opcode.ADDI, rd=1, imm=-1) == 0xE2FF`; `encode(Opcode.BR, rd=Condition.NE, imm=-2) == 0x83FE`; `encode(Opcode.HALT) == 0xF000`.
  - `encode` raises `ValueError` for `LI imm=256`, `ADDI imm=128`, `LOAD imm=32`, `BR imm=256`, `JMP imm=4096`, register `8`.
  - Hypothesis: `decode(encode(...)) ` returns the same fields for every opcode; `decode` accepts every word 0–65535 without raising.
  - `test_every_opcode_is_in_the_reference_page`: each `Opcode` name appears in a table row of `docs/reference/instruction-set.md`.
  - `condition_holds` for all 8 conditions after `alu_model(a, b, SUB)`, over Hypothesis `(a, b)`, against Python comparisons of `a` and `b` as signed and unsigned 16-bit numbers.
- [ ] **Step 3: Write failing tests** in `tests/test_fast.py` (words = 64 unless stated):
  - `test_alu_model_matches_the_gate_alu`: Hypothesis over `(a, b, op)` against Plan 1's `alu` in a `Simulator`: result and all four flags.
  - `power_on(64)`: `pc 0, sp 64`, eight zero registers, zero flags, 64 zero words, not halted, code 0, no output.
  - Countdown `[0x2203, 0xE2FF, 0x83FE, 0xF000]`: `run(100) == 8`, `r1 == 0`, `halted`, `halt_code == 0`, `pc == 4`.
  - `LHI`: `li r1, 0x12` then `lhi r1, 0x34` gives `0x3412`. `ADDI` on `0x7FFF` by 1 gives `0x8000` with negative 1, overflow 1.
  - `STORE` to `OUTPUT_PORT` appends to `output` and leaves memory alone; `LOAD` from it faults.
  - Faults, each changing nothing but `halted` and `halt_code`: `JMP 4000` (fetch fault at the next step, `pc == 4000`); `PUSH` with `sp == 0`; `POP` with `sp == 64`; `LOAD` at address 64.
  - `CALL`/`RET`: `[li r1,7; call 3; halt; add r1,r1,r1; ret]` ends with `r1 == 14`, `sp == 64`, 5 steps.
  - `HALT 3` gives `halt_code == 3`; `step()` on a halted machine returns False and the state is unchanged.
  - `load_state` rejects memory of the wrong length, a register outside 0–65535, or a flag not 0 or 1, with `ValueError`.
- [ ] **Step 4: Run** `uv run pytest tests/test_isa.py tests/test_fast.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 5: Implement** `isa.py`, `state.py`, `fast.py`. `FastMachine` keeps lists internally and builds a `MachineState` only in `state()`.
- [ ] **Step 6: Run** the same tests. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "feat: define the instruction set and the fast engine"`

---

### Task 3: The assembler

**Files:**
- Create: `src/pycpu/assembler.py`, `docs/concepts/assembly-language.md`
- Test: `tests/test_assembler.py`

**Interfaces:**
- Consumes: `isa.py` from Task 2.
- Produces: `class AssemblyError(ValueError)` with `line: int` (1-based) and a friendly message that starts `line N:`; `@dataclass(frozen=True) class Program: words: tuple[int, ...]; labels: dict[str, int]; lines: tuple[int, ...]` (the source line for each word); `assemble(source: str, words: int = RAM_WORDS) -> Program`; `disassemble(word: int, address: int) -> str`.

**Syntax** (decided here): one instruction per line; `;` starts a comment; `name:` defines a label (letters, digits, `_`, not starting with a digit; case-sensitive); mnemonics and registers are case-insensitive. Operands are comma-separated. Memory operands are `[ra]`, `[ra+n]` or `[ra-n]`. Numbers are decimal, `-` decimal, `0x` hex or a character literal `'A'`. `jmp`, `call` and `br` take a label or a number (an absolute address). `br` is written `br <cond>, <target>`; the assembler works out the offset as the target minus the next address, wrapped into −256 to 255, and if it does not fit says "too far for br: branch over a jmp instead". Pseudo-instruction `set rd, value` is always two words, `li rd, low byte` then `lhi rd, high byte`, and accepts a label. Directives: `.word value` (a number or label) and `.string "text"` (one word per character, then a 0). `halt` alone means `halt 0`. `disassemble` prints the canonical form of these (lower case, `br eq, 17` with the absolute target, `[r2-1]`).

- [ ] **Step 1: Write the doc first.** `assembly-language.md` (analogy: writing a recipe in words, then a helper who translates every word into the cook's number code; labels as bookmarks). Try It assembles and runs the hello program below, printing the words in hex and the output text. `KEY_IDEAS`: `["assembler", "label", "mnemonic"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_assembler.py`:
  - the countdown program (`li r1, 3` / `loop: addi r1, -1` / `br ne, loop` / `halt`) assembles to `(0x2203, 0xE2FF, 0x83FE, 0xF000)` with `labels == {"loop": 1}` and `lines == (1, 2, 3, 4)`.
  - the hello program (`set r1, msg` / `set r2, 0xFFFF` / `next: load r3, [r1]` / `cmp r3, r0` / `br eq, done` / `store r3, [r2]` / `addi r1, 1` / `jmp next` / `done: halt` / `msg: .string "Hi"`) has `labels["msg"] == 11` and, run on `FastMachine`, prints `Hi`.
  - errors, each an `AssemblyError` with the right `line`: unknown mnemonic, `r8`, `li r1, 256`, duplicate label, unknown label, missing operand, unterminated string, a `br` out of range, and a program longer than `words`.
  - Hypothesis, random text (including random lines built from real mnemonics and junk): `assemble` either returns a `Program` or raises `AssemblyError`, nothing else.
  - Hypothesis round trip: for every valid `Instruction` (encoded with unused bits 0) and address `a` from 0 to 300, assembling `".word 0"` × `a` followed by `disassemble(word, a)` puts `word` at address `a`.
- [ ] **Step 3: Run** `uv run pytest tests/test_assembler.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `assembler.py` as two passes (labels, then words).
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: add the assembler and disassembler"`

---

### Task 4: CPU parts from gates

**Files:**
- Create: `src/pycpu/cpu_parts.py`, `docs/concepts/the-control-unit.md`
- Test: `tests/test_cpu_parts.py`

**Interfaces:**
- Consumes: `logic.py`, `memory.Register`, `isa.Opcode`, `isa.Condition`.
- Produces (each opens its own scope, named as shown):
  - `class RegisterFile` (scope `registers`): `__init__(self, c, data: Bus, write: Wire, write_select: Bus, read_a: Bus, read_b: Bus, clock: Clock)`; eight 16-bit `Register`s named `r0`–`r7`; `self.a: Bus`, `self.b: Bus` (the two read ports); `self.registers: list[Register]`. Register `n` loads `data` on the beat when `write` is 1 and `write_select` spells `n`.
  - `opcode_lines(c, opcode: Bus) -> Bus` (scope `decode`): 16 wires, line `n` high when the 4 opcode bits spell `n` (a `decoder`).
  - `condition_met(c, cond: Bus, zero: Wire, negative: Wire, carry: Wire, overflow: Wire) -> Wire` (scope `condition`).
  - `sign_extend(c, bits: Bus, width: int = 16) -> Bus`: wires only, no gates (copies the top bit).
  - `outside_ram(c, address: Bus, ram_bits: int) -> Wire` (scope `address_check`): 1 when any address bit at or above `ram_bits` is 1.

- [ ] **Step 1: Write the doc first.** `the-control-unit.md` (analogy: a railway signal box, where one lever number lights exactly the signals for that route; the register file as a row of eight lockers with two windows to look through). Try It builds `opcode_lines` and `condition_met` and prints which line lights for a few words. `KEY_IDEAS`: `["control unit", "decode", "register file"]`.
- [ ] **Step 2: Write failing tests**: `opcode_lines` lights exactly line `n` for each of the 16 opcodes; `condition_met` equals `isa.condition_holds` for all 8 conditions × 16 flag combinations; `RegisterFile` writes only the selected register on a beat, keeps all when `write` is 0, and both read ports see any register (Hypothesis over values and selects); `outside_ram` is 1 exactly for addresses at or above `1 << ram_bits` (Hypothesis, `ram_bits` 6 and 12); `sign_extend` of 6 and 9 bits matches Python for every value.
- [ ] **Step 3: Run** `uv run pytest tests/test_cpu_parts.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `cpu_parts.py`, using only Plan 1 builders and `c.nand`.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: add the control unit's parts from gates"`

---

### Task 5: The gate CPU: fetch, decode, execute

**Files:**
- Create: `src/pycpu/cpu.py`, `docs/concepts/fetch-decode-execute.md`
- Test: `tests/test_cpu.py`

**Interfaces:**
- Consumes: Tasks 1, 2 and 4; `Ram`, `Register`, `make_clock`, `alu`.
- Produces:
  - `class Phase(IntEnum): FETCH = 0; EXECUTE = 1`.
  - `@dataclass(frozen=True) class MicroStep: kind: str` (`"gate"`, `"edge"` or `"end"`)`; gate: int` (−1 unless a gate)`; wire: str` (the clock wire for an edge, else `""`)`; value: int; phase: Phase`.
  - `class GateMachine: __init__(self, address_bits: int = RAM_ADDRESS_BITS)`; `words`, `circuit`, `simulator`, `phase`, `at_boundary` (True when no instruction is part-way through); `load_state(state: MachineState)`; `state() -> MachineState`; `step() -> bool` (one whole instruction; False if halted); `step_cycle() -> None` (finish the current clock cycle); `micro_step() -> MicroStep` (one gate evaluation or one clock edge; `"end"` when an instruction has just finished); `run(max_steps: int) -> int`.
  - Scopes: everything of the CPU sits in part `cpu`, whose children include `phase`, `ir`, `pc`, `sp`, `flags`, `halt`, `registers`, `decode`, `condition`, `alu`, `address_check`; the RAM is part `ram` at the top level.

**Design** (decided here; the doc explains it):
- One clock cycle is one `Simulator.tick`. Fetch cycle: address = `pc`; at the beat, `ir` takes `ram.out`, `pc` takes `pc + 1`, `phase` flips. Execute cycle: decode `ir`, do the work, write results at the beat, `phase` flips back. RAM `write_enable` is 0 in fetch.
- The memory address is chosen by a mux: `pc` (fetch), `ra + off6` (LOAD/STORE), `sp - 1` (PUSH/CALL), `sp` (POP/RET). Every source is a register or the ALU on registers, never `ram.out`.
- Register write-back is chosen from: ALU result, `ram.out` (LOAD), the LI value, the LHI value, `sp` (GETSP). The ALU's `a` input is register port A, which reads `ra`, or `rd` for ADDI and LHI; its `b` input is port B or the sign-extended `imm8` (ADDI). Port B reads `rb`, or `rd` for STORE, PUSH and SETSP. CMP uses `fn = SUB` and writes only flags.
- `halt` is a 1-bit register and `halt_code` an 8-bit register (both inside part `halt`). Every load signal is ANDed with NOT `halted`, so a halted machine freezes, `phase` included; `at_boundary` is True once halted, and `step`, `step_cycle` and `micro_step` do nothing (`micro_step` returns kind `"end"`). A bad address (from `outside_ram`, except a STORE to `0xFFFF`) or a HALT opcode raises `halted` and loads the code, and blocks every other load and the RAM write in that cycle.
- `port_write` is a named wire: execute AND STORE AND address = `0xFFFF` AND NOT `halted`. The machine's output list gets the store data when `port_write` is 1 at the execute write edge, in both `step` and `micro_step`.
- `load_state`: set `clk` and `write` to 0, settle, poke every register and RAM word (`ir` and `phase` to 0), settle. `state()` reads registers with `peek` and RAM with `Ram.peek`. The output list is copied in and out with the state.
- In this task the stack opcodes (PUSH, POP, CALL, RET) do nothing; Task 6 adds them. GETSP and SETSP are in this task.

- [ ] **Step 1: Write the doc first.** `fetch-decode-execute.md` (analogy: a cook who, for every card, first picks it up and reads it, then does it; two beats of the drum per card). The How It Works diagram shows the datapath above. Try It: build `GateMachine(address_bits=6)`, assemble the countdown, run it, print registers and how many gates the CPU has outside the RAM. `KEY_IDEAS`: `["fetch", "execute", "instruction register"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_cpu.py` (`address_bits=6`; build one machine per module with a fixture, and `load_state` per test):
  - every pinned fast-engine case from Task 2 that has no stack opcode gives the same final `MachineState` on `GateMachine`, including the faults and the output port.
  - `test_pc_running_off_the_end_faults_at_fetch`: a program of 64 non-jumping words ends `halted` with `Fault.BAD_ADDRESS` and `pc == 64`.
  - `test_loading_a_state_twice_leaves_every_wire_the_same`: load state S into a used machine and into a fresh one: the simulator wire values are equal (proves no state escapes the state pairs).
  - `test_micro_steps_end_where_step_ends`: from the same state, `micro_step()` until `"end"` gives the same `state()` as `step()`, and both edges per cycle appear in order `write↑ write↓ clk↑ clk↓`.
  - `test_two_cycles_make_one_instruction`: `step_cycle()` twice equals `step()`; `phase` is EXECUTE in between and `at_boundary` is False.
  - `test_the_cpu_is_zoomable`: `circuit.children("cpu")` includes every scope named in Interfaces.
- [ ] **Step 3: Run** `uv run pytest tests/test_cpu.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `cpu.py`.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: build the CPU from gates with a fetch and execute cycle"`

---

### Task 6: The stack, calling and returning

**Files:**
- Modify: `src/pycpu/cpu.py`
- Create: `docs/concepts/the-stack.md`, `docs/concepts/calling-and-returning.md`
- Test: `tests/test_cpu.py`

**Interfaces:**
- Consumes: Task 5's `GateMachine` and its address mux.
- Produces: PUSH, POP, CALL and RET on `GateMachine`, per the Instruction Set. No interface changes.

- [ ] **Step 1: Write the docs first.** `the-stack.md` (analogy: a pile of plates; you only touch the top; SP is your finger on the top plate; the pile grows downward from the top of memory). `calling-and-returning.md` (analogy: leaving a bookmark on a pile before going to read another chapter, then picking it up to come back). Each Try It runs a program on `GateMachine(address_bits=6)` and prints SP and the top of the stack after each instruction. `KEY_IDEAS`: `the-stack.md: ["stack", "push", "pop", "stack pointer"]`, `calling-and-returning.md: ["call", "return", "return address"]`.
- [ ] **Step 2: Write failing tests**: all remaining pinned Task 2 cases (CALL/RET, PUSH with `sp == 0`, POP with `sp == 64`) give the same `MachineState` on both engines; nested calls three deep return in order; RET with a corrupted return address on the stack jumps there exactly as the fast engine does.
- [ ] **Step 3: Run** `uv run pytest tests/test_cpu.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the stack opcodes in `cpu.py`. CALL pushes `pc` (already the return address) and loads `addr12` in one execute cycle; RET loads `pc` from `ram.out` at the beat.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: add the stack, calls and returns to the gate CPU"`

---

### Task 7: Lockstep equivalence and measured speeds

**Files:**
- Create: `tests/test_lockstep.py`, `scripts/measure_engines.py`, `tests/test_engine_speed.py`, `docs/concepts/two-engines.md`
- Modify: `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md` (add an "Engine result" section)

**Interfaces:**
- Consumes: `FastMachine`, `GateMachine`, `MachineState`, `assemble`.
- Produces: `measure_engines(address_bits: int) -> dict[str, float]` in `src/pycpu/proof.py`, with keys `cpu_gates` (gates outside the RAM), `total_gates`, `build_seconds`, `memory_mib`, `pause_seconds` (median `load_state`), `read_state_seconds` (median `state()`), `gate_instruction_seconds` (median `step()` over a mixed program), `fast_instructions_per_second`; `scripts/measure_engines.py` is a thin wrapper printing a table.

- [ ] **Step 1: Write failing lockstep tests** (`address_bits=6`, one `GateMachine` per module):
  - `test_both_engines_agree_from_any_state`: Hypothesis generates a full random `MachineState` (any memory words, registers, flags, `pc`, `sp`, not halted); load into both; step both up to 30 times; after every step the two `state()`s are equal. `max_examples=200`, `deadline=None`.
  - `test_both_engines_agree_on_assembled_programs`: Hypothesis builds short programs from random real instructions with small immediates and in-range addresses; same check.
  - `test_self_modifying_code_fetches_the_new_word`: a STORE that overwrites the next instruction with `halt 7`; both engines end with `halt_code == 7`.
  - Any difference is a bug in one engine: fix it, never loosen the test.
- [ ] **Step 2: Run, fix, run** `uv run pytest tests/test_lockstep.py -v` until PASS.
- [ ] **Step 3: Write the slow speed test** `tests/test_engine_speed.py` (`@pytest.mark.slow`, `@pytest.mark.timeout(900)`): `measure_engines(12)` meets `build_seconds < 30`, `memory_mib < 1024`, `pause_seconds < 2`, `read_state_seconds < 2`, `gate_instruction_seconds < 0.5`, `fast_instructions_per_second > 50_000`. A fast test calls `measure_engines(6)` and checks every key is present and positive.
- [ ] **Step 4: Measure.** Run `uv run python scripts/measure_engines.py` and `uv run pytest -m slow tests/test_engine_speed.py --no-cov -v`. Do not edit the limits. If one fails, make the engine faster; if that is not possible, stop and report with the numbers. Never shrink the RAM without the owner.
- [ ] **Step 5: Write `two-engines.md`** from the measurements (analogy: a flip-book and a slow-motion camera filming the same juggler; you trust the flip-book because you check frame by frame that they match). Every number comes from Step 4, with the machine it ran on. Try It runs both engines on one program and prints that their states match. `KEY_IDEAS`: `["fast engine", "gate engine", "lockstep"]`. Record the same numbers in the roadmap's new "Engine result" section.
- [ ] **Step 6: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "test: prove the engines agree and measure them at full size"`

---

### Task 8: Pause, step, rewind and resume

**Files:**
- Create: `src/pycpu/computer.py`, `docs/concepts/pausing-and-rewinding.md`
- Test: `tests/test_computer.py`

**Interfaces:**
- Consumes: `FastMachine`, `GateMachine`, `Program`, `MachineState`.
- Produces: `class StepSize(StrEnum): GATE = "gate"; CYCLE = "cycle"; INSTRUCTION = "instruction"`; `class Computer: __init__(self, program: Program | Sequence[int], address_bits: int = RAM_ADDRESS_BITS)`; `fast`, `gate`, `paused: bool`; `run(max_steps: int) -> int` (fast engine; raises `RuntimeError` while paused); `pause() -> None` (loads the fast state into the gate engine and remembers it as the instruction's start); `step(size: StepSize) -> MicroStep | None` (paused only; returns the micro step for `GATE`); `rewind() -> None` (back to the start of the current instruction); `resume() -> None` (finish the current instruction in the gate engine, copy its state to the fast engine, unpause); `state() -> MachineState` (from the live engine); `instruction_start: MachineState`.

- [ ] **Step 1: Write the doc first.** `pausing-and-rewinding.md` (analogy: watching a football match, pressing pause, switching to the slow-motion replay camera, rewinding the replay to the start of the move, then going back to live). Try It: run the countdown 3 instructions, pause, take 20 gate steps printing a few, rewind, check the state equals the instruction start, resume, run to the end. `KEY_IDEAS`: `["pause", "rewind", "resume"]`.
- [ ] **Step 2: Write failing tests** (`address_bits=6`):
  - `test_pause_lands_on_an_instruction_boundary`: after `pause()`, `gate.at_boundary` is True and `state() == fast.state()`.
  - `test_rewind_after_gate_steps_restores_the_instruction_start`: Hypothesis over how many gate steps (0 to 2000) before `rewind()`: `state() == instruction_start`, and the next `step(INSTRUCTION)` gives the same state as the fast engine stepping once.
  - `test_resume_mid_instruction_matches_a_straight_run`: Hypothesis over a stop point `k` and gate-step count `m`: run `k`, pause, `m` gate steps, resume, run to halt; the final state equals running the fast engine alone to halt.
  - `test_step_instruction_moves_the_rewind_point`: after `step(INSTRUCTION)`, `instruction_start` is the new boundary state.
  - `test_run_while_paused_is_refused` and `test_stepping_while_running_is_refused` (`RuntimeError`).
- [ ] **Step 3: Run** `uv run pytest tests/test_computer.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `computer.py`.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: pause into the gates, step, rewind and resume"`

---

### Task 9: The Bench shows the running computer, and the story is updated

**Files:**
- Modify: `src/pycpu/bench/app.py`, `src/pycpu/bench/page.html`, `src/pycpu/__main__.py`, `docs/concepts/the-bench.md`, `docs/index.md`, `docs/from-scratch.md`, `README.md`, `mkdocs.yml`, `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`
- Create: `examples/run_assembly.py`
- Test: `tests/test_bench.py`, `tests/test_examples.py`

**Interfaces:**
- Consumes: `Computer`, `assemble`, `disassemble`, `circuit_view`.
- Produces: `create_bench(address_bits: int = RAM_ADDRESS_BITS) -> App` with a `Computer` running `DEMO_PROGRAM` (an assembly string in `app.py` that counts down and prints, using a CALL), paused at the start. Routes:
  - `GET /` the page; `GET /api/view?path=` as before (now over the CPU's circuit), 404 for an unknown part.
  - `GET /api/machine` → `{"paused", "phase", "at_boundary", "registers", "pc", "sp", "flags", "halted", "halt_code", "output", "instruction": {"address", "word", "text"}, "memory": [{"address", "word", "text"}, ...]}`; memory is the 16 words starting at `max(0, pc - 4)`.
  - `POST /api/step` `{"size": "gate" | "cycle" | "instruction"}` → the machine JSON; 400 for any other size.
  - `POST /api/rewind` → the machine JSON.
  - `POST /api/run` `{"instructions": 1..10000}` → resume, run, pause again, the machine JSON; 400 when out of range.
  - `POST /api/program` `{"source": "..."}` → a new `Computer` from the assembled source; 400 with the `AssemblyError` message (including its line) when it does not assemble.

**Decision:** the ALU dial is replaced by the running machine; the zoom panel now opens on the CPU, and the ALU is one click down (`cpu.alu`). The Bench page is still local only.

- [ ] **Step 1: Rewrite `the-bench.md` first** to tour the machine view: registers, memory, the current instruction, the three step sizes, rewind, and zooming from the current instruction into `cpu.alu` down to a gate. Try It drives `create_bench(address_bits=6)` through PyWeb's `TestClient`, steps one instruction and prints the new PC and the instruction text. `KEY_IDEAS`: `["bench", "register", "gate", "instruction"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_bench.py` for every route above, including each 400 and 404, and that a gate step changes the reported `phase` or the view's wire values over a full instruction.
- [ ] **Step 3: Run** `uv run pytest tests/test_bench.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the routes and the page: registers, flags, memory window with the current instruction highlighted, the step buttons, rewind, run, a text box to load assembly, and the existing zoom panel.
- [ ] **Step 5: Check in a real browser.** `uv run python -m pycpu`; step one instruction, then gate by gate through the next, rewind, and drill from `cpu` to `cpu.alu` to a gate. Expected: PC and registers change as the fast engine predicts, gate values move, no console errors.
- [ ] **Step 6: Add `examples/run_assembly.py`** (assembles and runs the hello program on `FastMachine`, printing `Hi`) and its line in `tests/test_examples.py`.
- [ ] **Step 7: Update the story.** `index.md`, `from-scratch.md` and the README ladder: the CPU and Assembler rungs are built; Pebble and the Cockpit are still to come. README Concepts table gains the new pages. Add a "Notes for Plan 3" section to the roadmap with anything this plan learned, and the Bench's measured start-up time.
- [ ] **Step 8: Final verification.** `uv run pytest && uv run pytest -m slow --no-cov && uv run ruff check . && uv run ruff format --check . && uv run pyright src tests examples && uv run mkdocs build --strict`. Expected: all pass.
- [ ] **Step 9: Commit and open the PR.** `git commit -m "feat: show the running computer on the bench"`. Push, open the PR, merge when CI is green. Create no tag.
