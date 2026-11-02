# Instruction Set

This is the lookup page: every instruction PyCPU understands, in one place. It
is for checking a detail, not for learning from scratch. To learn the ideas, start
at [What Is a CPU?](../concepts/what-is-a-cpu.md) and
[Machine Code](../concepts/machine-code.md). The codebook itself is
`src/pycpu/isa.py`, and the fast engine in `src/pycpu/fast.py` follows it exactly.

## The machine

- **Registers:** `r0` to `r7`, 16 bits each, all of them general purpose. Also `pc`
  (the program counter, 16 bits), `sp` (the stack pointer, 16 bits) and four flags:
  `zero`, `negative`, `carry`, `overflow`.
- **Power-on:** everything is 0, except `sp`, which is the size of memory (so the
  first `PUSH` writes the top word).
- **Words:** 16 bits, and memory is addressed one word at a time. All address and
  register arithmetic wraps around at 16 bits.
- **`pc` has already moved on.** When an instruction runs, `pc` already points at the
  next instruction (fetching it added 1). So `CALL` saves the address after itself
  and `BR` counts its offset from the next instruction.

## Encoding

One instruction is one 16-bit word. The opcode is bits 15 to 12.

| Field | Bits | Meaning |
|-------|------|---------|
| `opcode` | 15-12 | Which instruction |
| `rd` (or `cond`) | 11-9 | Destination register; the condition for `BR`; the register to read for `STORE`, `PUSH` and `SETSP` |
| `ra` | 8-6 | First source register |
| `rb` | 5-3 | Second source register |
| `fn` | 2-0 | Which ALU operation (an `AluOp`) |
| `imm8` | 7-0 | 8-bit number |
| `off6` | 5-0 | 6-bit signed offset, -32 to 31 |
| `off9` | 8-0 | 9-bit signed offset, -256 to 255 |
| `addr12` | 11-0 | 12-bit address, 0 to 4095 |

Unused bits are written as 0 and ignored when read, so every 16-bit word is a
valid instruction.

## The instructions

The last column is a worked example: the instruction written out, then its word.
"Flags" says whether the instruction sets the four flags or leaves them alone.

| Op | Name | Fields | Effect | Flags | Example |
|----|------|--------|--------|-------|---------|
| 0 | `ALU` | rd ra rb fn | `rd = ra <fn> rb`, where `fn` is an `AluOp` | set | `add r3, r1, r2` = `0x0650` |
| 1 | `CMP` | ra rb | Set flags from `ra - rb`; no register changes | set | `cmp r1, r2` = `0x1050` |
| 2 | `LI` | rd imm8 | `rd = imm8` (0 to 255) | kept | `li r1, 5` = `0x2205` |
| 3 | `LHI` | rd imm8 | `rd = (imm8 << 8) \| (rd & 0xFF)` | kept | `lhi r1, 0x12` = `0x3212` |
| 4 | `LOAD` | rd ra off6 | `rd = mem[ra + off6]` | kept | `load r1, [r2 - 1]` = `0x42BF` |
| 5 | `STORE` | rd ra off6 | `mem[ra + off6] = rd` | kept | `store r1, [r2 + 1]` = `0x5281` |
| 6 | `JMP` | addr12 | `pc = addr12` | kept | `jmp 100` = `0x6064` |
| 7 | `CALL` | addr12 | Push `pc`, then `pc = addr12` | kept | `call 100` = `0x7064` |
| 8 | `BR` | cond off9 | If `cond` holds, `pc = pc + off9` | kept | `br ne, -2` = `0x83FE` |
| 9 | `RET` | none | Pop into `pc` | kept | `ret` = `0x9000` |
| 10 | `PUSH` | rd | `sp = sp - 1`, then `mem[sp] = rd` | kept | `push r1` = `0xA200` |
| 11 | `POP` | rd | `rd = mem[sp]`, then `sp = sp + 1` | kept | `pop r1` = `0xB200` |
| 12 | `GETSP` | rd | `rd = sp` | kept | `getsp r1` = `0xC200` |
| 13 | `SETSP` | rd | `sp = rd` | kept | `setsp r1` = `0xD200` |
| 14 | `ADDI` | rd imm8 | `rd = rd + imm8`, signed (-128 to 127) | set | `addi r1, -1` = `0xE2FF` |
| 15 | `HALT` | imm8 | Stop, with `halt_code = imm8` (0 means finished normally) | kept | `halt 3` = `0xF003` |

## The ALU operations (`fn`)

`ALU` instructions pick one of eight operations with the `fn` field. The mnemonic
is the name used when writing the instruction.

| `fn` | `AluOp` | Mnemonic | Result |
|------|---------|----------|--------|
| 0 | `ADD` | `add` | `ra + rb` |
| 1 | `SUB` | `sub` | `ra - rb` |
| 2 | `AND` | `and` | `ra AND rb`, bit by bit |
| 3 | `OR` | `or` | `ra OR rb`, bit by bit |
| 4 | `XOR` | `xor` | `ra XOR rb`, bit by bit |
| 5 | `SHL` | `shl` | `ra` shifted left one place (uses `ra` only) |
| 6 | `SHR` | `shr` | `ra` shifted right one place, a 0 coming in at the top (uses `ra` only) |
| 7 | `PASS_B` | `mov` | `rb` unchanged (uses `rb` only), so `mov rd, rb` copies a register |

The flags follow the ALU: `carry` is the carry out for `add`, 1 for `sub` when
nothing had to be borrowed, the bit shifted out for `shl` and `shr`, and 0 for the
logic operations and `mov`. `overflow` is only ever 1 for `add` and `sub`.

## Conditions (`cond`)

`BR` takes one of eight conditions, in the three-bit `rd` field.

| Number | `Condition` | Holds when |
|--------|-------------|------------|
| 0 | `EQ` | `zero` is 1 |
| 1 | `NE` | `zero` is 0 |
| 2 | `LT` | `negative` is not equal to `overflow` |
| 3 | `GE` | `negative` equals `overflow` |
| 4 | `LE` | `zero` is 1, or `negative` is not equal to `overflow` |
| 5 | `GT` | `zero` is 0, and `negative` equals `overflow` |
| 6 | `LTU` | `carry` is 0 |
| 7 | `GEU` | `carry` is 1 |

After `cmp a, b`: `EQ`, `NE`, `LT`, `GE`, `LE` and `GT` compare `a` with `b` as signed
numbers; `LTU` and `GEU` compare them as unsigned numbers.

## The memory map

- Addresses `0` up to the size of memory minus one are RAM.
- `OUTPUT_PORT = 0xFFFF` is a write-only character port, like a screen. A `STORE` to
  it adds the stored word to the machine's `output` instead of writing RAM.
- Every other access outside RAM is a fault. That includes fetching an
  instruction from there, `LOAD`, `POP` or `RET` from the port, and `PUSH` or
  `CALL` to it. (`PUSH` is not `STORE`, so it does not get the port.)

## Faults

A fault sets `halted` and `halt_code`, and changes nothing else. A halted machine
ignores further steps. In a fetch fault `pc` stays at the bad address; in an
execute fault `pc` is already one past the faulting instruction.

| Code | `Fault` | Meaning |
|------|---------|---------|
| 0 | none | `HALT 0`: finished normally |
| 1 | `BAD_ADDRESS` | An address outside memory, raised by the hardware |
| 2 | `STACK_OVERFLOW` | Reserved: raised by generated code with `HALT` |
| 3 | `DIVIDE_BY_ZERO` | Reserved: raised by generated code with `HALT` |
