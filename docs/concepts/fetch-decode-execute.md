# Fetch, Decode, Execute

## A Cook and a Drum

Go back to the cook from [What Is a CPU?](what-is-a-cpu.md), with the stack of
numbered recipe cards on the wall. This time there is a drummer in the corner of the
kitchen, beating a slow, steady drum: *boom ... boom ... boom*. The cook is only
allowed to move on a beat, and every card takes exactly two beats.

On the first beat the cook **picks up** the card the finger points at, holds it in one
hand where it can be read, and slides the finger along to the next card. That is all.
Nothing is cooked yet. On the second beat the cook **does** what the card in the hand
says: cracks an egg into a bowl, or moves the finger somewhere else, or rings the bell
to say dinner is ready. Then the drum beats again and the cook picks up the next card.
Pick up, do. Pick up, do. Round and round.

The first beat is called **fetch** (go and get the instruction). Reading the card to
work out what it means is called **decode**, and it happens during the second beat,
while the cook is getting ready to act. The second beat is called **execute** (do what
the instruction says). The card held in the hand is the **instruction register**: a
register whose only job is to hold the instruction being carried out, so the cook can
keep reading it while the finger has already moved on. And the cook has to remember
which beat comes next, "pick up" or "do": that one-bit memory is the **phase**.

On this page we build that cook out of gates. Every part was made on an earlier page;
here they are finally wired together into a computer that runs programs.

| The kitchen | In PyCPU |
|-------------|----------|
| One beat of the drum | One clock cycle: `Simulator.tick` (see [The Clock](the-clock.md)) |
| Which beat comes next, "pick up" or "do" | The 1-bit `phase` register: `Phase.FETCH` or `Phase.EXECUTE` |
| Picking up the card and moving the finger | The fetch cycle: `ir` takes the word at `pc`, and `pc` takes `pc + 1` |
| The card held in the hand | The instruction register, `ir` |
| Reading the card | The decoder (`decode`) and the `condition` checker from [The Control Unit](the-control-unit.md) |
| Doing what the card says | The execute cycle: the ALU, the register file, RAM and `pc` |
| The bell for "dinner is ready" | The `halt` and `halt_code` registers, in the part `halt` |
| A shout out of the window | The output port and its wire `port_write` |
| The whole kitchen | `GateMachine` in `src/pycpu/cpu.py` |
| Watching the cook one movement at a time | `GateMachine.micro_step()` |

## Try It

We build the computer from gates with a small memory of 64 words (`address_bits=6`
means 6 address wires, and 2 to the power 6 is 64), so it builds in a blink. Then we
give it the countdown from [What Is a CPU?](what-is-a-cpu.md), this time written in
[assembly language](assembly-language.md), and let it run.

```python
from pycpu.assembler import assemble
from pycpu.cpu import GateMachine

source = """
    li r1, 3        ; r1 = 3
again:
    addi r1, -1     ; take one away
    br ne, again    ; not zero yet? go round again
    halt
"""
machine = GateMachine(address_bits=6)
machine.load_program(assemble(source, words=machine.words).words)

machine.step_cycle()  # one beat: fetch
state = machine.state()
print(f"after one beat:  next is {machine.phase.name}, pc = {state.pc}, r1 = {state.registers[1]}")
machine.step_cycle()  # another beat: execute
state = machine.state()
print(f"after two beats: next is {machine.phase.name}, pc = {state.pc}, r1 = {state.registers[1]}")

more = machine.run(100)  # whole instructions until it halts
state = machine.state()
print("instructions run:", 1 + more)
print(f"r1 = {state.registers[1]}, pc = {state.pc}, halted: {state.halted}")
print("gates in the CPU:", machine.circuit.gate_count_in("cpu"))
print("gates in the RAM:", machine.circuit.gate_count_in("ram"))
# Output:
# after one beat:  next is EXECUTE, pc = 1, r1 = 0
# after two beats: next is FETCH, pc = 1, r1 = 3
# instructions run: 8
# r1 = 0, pc = 4, halted: True
# gates in the CPU: 5219
# gates in the RAM: 9496
```

After one beat the card has been picked up (the phase now says the *execute* beat
comes next) and the finger has already moved on to card 1, but `r1` has not changed
yet. After the second beat the card has been obeyed, and `r1` is 3. `run` then carries
on a whole instruction (two beats) at a time and counts the 7 instructions after the
first, the same 8 the fast engine took on [What Is a CPU?](what-is-a-cpu.md). The last
two lines count the gates: the CPU is a few thousand, and with only 64 words the RAM
is already bigger.

The computer can also talk. Storing a word at the address `0xFFFF` does not go into
memory at all: it goes out of the **output port**, like a letter shouted out of the
kitchen window. Here is the hello program from [Assembly Language](assembly-language.md),
run on gates:

```python
from pycpu.assembler import assemble
from pycpu.cpu import GateMachine

source = """
    set r1, msg
    set r2, 0xFFFF
next:
    load r3, [r1]
    cmp r3, r0
    br eq, done
    store r3, [r2]
    addi r1, 1
    jmp next
done:
    halt
msg:
    .string "Hi"
"""
machine = GateMachine(address_bits=6)
machine.load_program(assemble(source, words=machine.words).words)
machine.run(1000)
print("output:", machine.state().output_text)
# Output:
# output: Hi
```

## How It Works

`GateMachine` lives in `src/pycpu/cpu.py`. It builds one circuit holding the RAM (the
part `ram`) and, beside it, the CPU (the part `cpu`). Inside `cpu` is every register
the cook needs, each a [`Register`](registers.md) of flip-flops: `phase` (1 bit), `ir`,
`pc` and `sp` (16 bits each), `flags` (4 bits: zero, negative, carry, overflow), and
the part `halt`, holding `halted` (1 bit) and `halt_code` (8 bits). Next to them sit
the parts from [The Control Unit](the-control-unit.md) (`registers`, `decode`,
`condition`, `address_check`) and the [ALU](the-alu.md).

The Try It measured 5,219 gates in the CPU. The full-size machine, with 4,096 words,
has 5,213 gates in its CPU (its `address_check` has fewer high address bits to watch)
and 607,454 in its RAM: the thinking part of the computer is less than one gate in a
hundred. Almost all of a computer is memory.

The wires and choosers that carry numbers between those parts are called the
**datapath**: the roads of the kitchen. Here it is. Every box is a part (a scope) of
that name inside `cpu`, and every arrow is a bus of real wires.

```
                ┌────────┐        ┌────────┐  one lit line per opcode:
   ram.out ───► │   ir   ├───────►│ decode ├──► steers every chooser below
   (fetch)      └───┬────┘        └────────┘    (control, operand, next_pc,
                    │ fields: rd ra rb fn imm    write_back, fault, port)
                    ▼
 ┌──────┐  pc + 1  ┌───────────────┐
 │  pc  ├─────────►│ pc_plus_1     ├──┐   ┌─────────┐
 │      ├─────────►│ branch_target ├──┴──►│ next_pc ├──► new pc
 └──┬───┘ pc+off9  └───────────────┘      └─────────┘
    │ fetch: pc
    ▼                                 ┌────────────┐
 ┌─────────────┐   address            │    RAM     │  ram.out
 │ address_mux ├─────────────────────►│ (part ram) ├───► ir (fetch), write_back (LOAD)
 └─────▲───────┘                      └─────▲──────┘
       │ execute: ALU answer                │ data ◄── window b (STORE)
       │
       │      new rd ┌───────────────────────────────────────┐
       │             ▼                                       │
 ┌─────┴─────┐  a  ┌──────────────┐ window b                 │
 │    alu    │◄────┤  registers   ├────┐                     │
 │           │     │  r0 ... r7   │    │                     │
 │           │     └──────────────┘    ▼                     │
 │           │  b  ┌──────────────────────────┐              │
 │           │◄────┤ operand: picks window b, │              │
 │           │     │ imm8 or off6             │              │
 └──┬─────┬──┘     └──────────────────────────┘              │
    │     │ answer ┌──────────────────────────────────┐      │
    │     └───────►│ write_back: picks the answer,    ├──────┘
    │              │ ram.out, LI, LHI or sp           │
    │ lamps        └──────────────────────────────────┘
    ▼
 ┌───────┐
 │ flags │ zero, negative, carry, overflow
 └───────┘
```

`ir` holds the instruction. Its fields are just wires (no gates), and its top four bits
go into `decode`, which lights one line per opcode. Those lines steer every chooser in
the picture. The ALU's input `a` is window `a`; its input `b` comes through the
`operand` chooser, which picks window `b`, the 8-bit immediate or the 6-bit offset. The
ALU's answer goes to `write_back` (and, on an execute beat, to the RAM's address), and
its four lamps go to `flags`.

**1. The fetch beat.** While `phase` is 0 (`Phase.FETCH`), the `address_mux` chooser
sends `pc` to the RAM's address wires, so `ram.out` shows the word the finger points
at. Three registers get their `load` wire raised: `ir` (whose data wires are `ram.out`),
`pc` (whose data wires come from `pc_plus_1`, a [ripple adder](adding.md) adding 1),
and `phase` (whose data wire is NOT `phase`). When the clock rises, all three change
together: the card is in the hand, the finger is on the next card, and the next beat
will be an execute beat. The RAM's `write_enable` is held at 0 during fetch, so a fetch
can never change memory.

**2. Decoding.** Now `ir` holds the instruction. Its top four bits go into the
decoder, and exactly one opcode line lights up. The other fields are just wires taken
from `ir`: bits 11 to 9 are `rd`, bits 8 to 6 are `ra`, and so on, exactly as in
[Machine Code](machine-code.md). Nothing has to be cut out with arithmetic, because a
field *is* a handful of wires. Decoding takes no beat of its own: the lines light up
as soon as `ir` changes, a little like reading a card in the time it takes to look at
it. That is why the page is called fetch, decode, execute, but the drum only beats
twice.

**3. The execute beat.** While `phase` is 1 (`Phase.EXECUTE`), the lit opcode line
picks what each chooser lets through:

- The register file's window `a` reads `ra`, or `rd` for `ADDI` and `LHI`. Window `b`
  reads `rb`, or `rd` for `STORE` and `SETSP` (the register whose value is going
  somewhere).
- The ALU gets window `a`, and either window `b`, or the sign-extended 8-bit immediate
  (`ADDI`), or the sign-extended 6-bit offset (`LOAD`, `STORE`). Its job dial is the
  instruction's `fn` bits, except that `CMP` forces `SUB` and `ADDI`, `LOAD` and
  `STORE` force `ADD`. So for `LOAD r3, [r1 - 3]` the ALU works out `r1 + (-3)`, which
  is the address to read.
- The `address_mux` sends that ALU answer to the RAM. Notice that every number that
  reaches the RAM's address and data wires comes from a register or the ALU working on
  registers, never from `ram.out` itself. That is the rule from [RAM](ram.md): a RAM
  cell is a latch, and a latch whose input depends on its own output may never settle.
- The `write_back` choosers pick what goes into register `rd`: the ALU's answer
  (`ALU`, `ADDI`), `ram.out` (`LOAD`), the 8-bit immediate (`LI`), the immediate
  glued on top of `rd`'s low byte (`LHI`), or `sp` (`GETSP`).
- Each `load` wire is an AND of "this is the execute beat" and the opcode lines that
  need it. The register file writes for `ALU`, `LI`, `LHI`, `LOAD`, `GETSP` and `ADDI`;
  `flags` load for `ALU`, `CMP` and `ADDI`; `sp` loads for `SETSP`; the RAM writes for
  `STORE`.
- `pc` loads a new value for `JMP` (the 12-bit address in `ir`) or for `BR` when the
  `condition` part says the condition holds. A branch target comes from a second
  adder, `branch_target`, which adds the sign-extended 9-bit offset to `pc`. Because
  the fetch beat already moved `pc` on by one, the offset counts from the next card.

On the clock's rise every register that was told to load does so at the same moment,
and `phase` flips back to fetch. Memory is written a moment earlier, on the `write`
pulse, while every register still holds this beat's values (see
[The Clock](the-clock.md)), so a `STORE` writes exactly what it was told to.

**4. Stopping.** `halted` is a 1-bit register and `halt_code` an 8-bit one. Every
`load` wire in the CPU, including the RAM's write, is ANDed with NOT `halted`, so once
`halted` is 1 nothing can ever change again: the machine is frozen. Two things raise
it. A `HALT` instruction loads its 8-bit immediate into `halt_code`. And a **fault**,
a mistake the machine catches itself, loads `Fault.BAD_ADDRESS`, which is 1: the
`address_check` part watches the address wires, and if any bit above the RAM's
address bits is 1, the address is off the end of memory. In that same beat the fault
blocks every other `load` and the RAM write, so a fault changes nothing except
`halted` and `halt_code`. A bad fetch leaves `pc` on the bad address; a bad `LOAD` or
`STORE` leaves `pc` one past the instruction, because the fetch beat had already moved
it.

**5. The output port.** One address is special: `0xFFFF`, the output port. A
`STORE` there is not a fault and does not write RAM. Instead a wire called
`port_write` goes to 1: it is execute AND `STORE` AND "the address is all ones" AND
NOT `halted`. The screen is a **peripheral**, a device outside the CPU, like a printer
plugged into a laptop. In PyCPU it is a few lines of Python that, at the moment of the
`write` pulse, look at the real `port_write` wire and, if it is 1, copy the word on
the store data wires into the machine's output list. It does not decide anything the
CPU should; it only listens to the cable.

**6. Slow motion.** `step()` runs a whole instruction (two clock cycles), and
`step_cycle()` runs one cycle. `micro_step()` goes further: each call does just one
thing, either one gate thinking (see [Simulating a Circuit](simulating-a-circuit.md))
or one clock edge (the `write` wire going up or down, or `clk` going up or down). It
follows exactly the order `Simulator.tick` uses, so stepping gate by gate ends in the
same place as running fast. When an instruction has just finished it returns a
`MicroStep` of kind `"end"`.

**7. Saving and loading.** `state()` reads every register with `peek` and every RAM
word with `Ram.peek`, and gives back the same `MachineState` the fast engine uses.
`load_state()` writes one in with `poke`, setting `ir` and `phase` to 0 so the next
beat is a fetch. Because the two engines share that one sheet of paper, the tests run
every program on both and check that the sheets come out the same, fault for fault.

## Why Does This Matter?

This is the moment the pile of parts becomes a computer. Before this page we had a
calculator that did one sum when we set its inputs by hand. Now the machine sets its
own inputs: it fetches an instruction, decodes it, and executes it, and then fetches
the next, with nobody touching anything but the clock. Change the words in memory and
the same gates do a completely different job.

Real processors still do this cycle. The first computers that kept their program in
memory, built in the late 1940s, did it one step at a time, just like ours. Modern chips
cheat by working on several instructions at once, fetching the next card while still
doing the last one (that trick is called a *pipeline*), but every instruction still
goes through fetch, decode and execute.

## What's Next

You can now watch the CPU run, beat by beat. To look inside the parts we have built,
gate by gate, continue with [The Bench](the-bench.md).
