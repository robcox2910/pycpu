# The Stack

## A Pile of Plates

Think of a pile of clean plates in a canteen. You can do exactly two things with it.
You can put a plate **on top** of the pile, or you can take the **top** plate off.
You never pull a plate out of the middle, and you never have to remember where any
particular plate went: the one you get back is always the last one you put on. Last
on, first off.

A computer keeps a pile like that in its memory, and it is called the **stack**.
Putting a word on top is called a **push**, and taking the top word off is called a
**pop**. To know where the top is, the CPU keeps one register pointing at it, like
your finger resting on the top plate. That register is the **stack pointer**, `sp`.

There is one surprise. Our pile hangs from the ceiling and grows *downward*. It starts
at the very top of memory, and each push puts the new word at the next address
*below*. Why? Because the program sits at the bottom of memory, starting at address 0.
Starting the stack at the other end gives both of them as much room as possible before
they meet in the middle. That is why [What Is a CPU?](what-is-a-cpu.md) said `sp`
starts at the size of memory when the machine is switched on: the finger starts just
above the top shelf, with nothing on the pile.

| The pile of plates | In PyCPU |
|--------------------|----------|
| The pile itself | The **stack**: words at the top end of memory |
| Your finger on the top plate | The **stack pointer**, the 16-bit register `sp` |
| Putting a plate on top | `PUSH rd`: `sp = sp - 1`, then `mem[sp] = rd` |
| Taking the top plate off | `POP rd`: `rd = mem[sp]`, then `sp = sp + 1` |
| An empty pile (finger above the top shelf) | `sp` equal to the size of memory (64 in the Try It) |
| Moving your finger one plate down or up | The adders `sp_minus_1` and `sp_plus_1` in `src/pycpu/cpu.py` |
| Reaching past the floor or the ceiling | A fault: `Fault.BAD_ADDRESS` |

## Try It

We build the computer from gates with 64 words of memory, put two numbers on the
stack and take them off again, printing `sp` and the top of the pile after every
instruction. `disassemble` turns each instruction back into words so we can see which
one just ran.

```python
from pycpu.assembler import assemble, disassemble
from pycpu.cpu import GateMachine

source = """
    li r1, 7
    li r2, 9
    push r1       ; put 7 on the pile
    push r2       ; put 9 on top of it
    pop r3        ; take the top plate off: 9
    pop r4        ; and the one under it: 7
    halt
"""
machine = GateMachine(address_bits=6)
machine.load_program(assemble(source, words=machine.words).words)

while not machine.state().halted:
    before = machine.state()
    text = disassemble(before.memory[before.pc], before.pc)
    machine.step()
    after = machine.state()
    top = after.memory[after.sp] if after.sp < machine.words else "nothing"
    print(f"{text:8} sp = {after.sp}, top = {top}")
state = machine.state()
print(f"r3 = {state.registers[3]}, r4 = {state.registers[4]}")
print("memory 62 and 63:", state.memory[62], state.memory[63])
# Output:
# li r1, 7 sp = 64, top = nothing
# li r2, 9 sp = 64, top = nothing
# push r1  sp = 63, top = 7
# push r2  sp = 62, top = 9
# pop r3   sp = 63, top = 7
# pop r4   sp = 64, top = nothing
# halt     sp = 64, top = nothing
# r3 = 9, r4 = 7
# memory 62 and 63: 9 7
```

Follow the finger. It starts at 64, just above the top word (memory is 0 to 63), so the
pile is empty. `push r1` moves it down to 63 and puts 7 there. `push r2` moves it to
62 and puts 9 there. Then `pop r3` gets 9, the *last* plate put on, and `pop r4` gets 7.
The two numbers came back in the opposite order. And look at the last line: popping did
not wipe the plates. The 9 and 7 are still sitting in memory. A pop only moves the
finger back up, so those words count as "not on the pile" and the next push will
simply write over them.

Now reach past the floor. If `sp` is 0, a push would have to go to the address below
0. Numbers in our computer wrap around (see [Negative Numbers](negative-numbers.md)),
so 0 - 1 is 65535, which is `0xFFFF`: not a word of RAM at all, but the output port.
A push is not a `STORE`, so it is not allowed to use the port, and the machine stops
with a fault instead:

```python
from pycpu.assembler import assemble
from pycpu.cpu import GateMachine

source = """
    setsp r0      ; r0 is 0, so the finger goes to the floor
    li r1, 7
    push r1       ; there is nowhere below address 0
    halt
"""
machine = GateMachine(address_bits=6)
machine.load_program(assemble(source, words=machine.words).words)
machine.run(10)
state = machine.state()
print(f"halted: {state.halted}, code: {state.halt_code}, sp = {state.sp}, pc = {state.pc}")
print("output:", state.output)
print("gates in sp_minus_1:", machine.circuit.gate_count_in("cpu.sp_minus_1"))
print("gates in sp_plus_1:", machine.circuit.gate_count_in("cpu.sp_plus_1"))
print("gates in the CPU:", machine.circuit.gate_count_in("cpu"))
# Output:
# halted: True, code: 1, sp = 0, pc = 3
# output: ()
# gates in sp_minus_1: 240
# gates in sp_plus_1: 240
# gates in the CPU: 6029
```

Code 1 is `Fault.BAD_ADDRESS`. Nothing else changed: `sp` is still 0 and nothing went
out of the port. Popping with `sp` at 64 (an empty pile) faults the same way, because
address 64 is past the end of memory. The last three lines count gates; How It Works
explains them.

## How It Works

The stack is not a new kind of memory. It is ordinary RAM, plus the register `sp`, plus
two [ripple adders](adding.md), all in `GateMachine` in `src/pycpu/cpu.py`.

**1. Two adders watch `sp`.** The part `sp_minus_1` is a 16-bit ripple adder that adds
`0xFFFF` to `sp`. In two's complement (see [Negative Numbers](negative-numbers.md)),
`0xFFFF` is -1, so adding it takes one away. The part `sp_plus_1` adds 1. Both work all
the time, on every beat, whatever the instruction is; the choosers decide whether
anyone listens.

```
                 ┌──────┐   new sp, at the clock's rise
          ┌──────┤  sp  │◄──────────────────────────────┐
          │      └──────┘                               │
          │ sp                                          │
          ├──────────────┬────────────────┐             │
          ▼              ▼                │             │
   ┌────────────┐  ┌────────────┐         │       ┌─────┴──────┐
   │ sp_minus_1 │  │ sp_plus_1  │         │       │  next_sp   │
   │   sp - 1   │  │   sp + 1   ├─────────┼──────►│  chooser   │
   └─────┬──────┘  └────────────┘         │       └──▲─────▲───┘
         ├────────────────────────────────┼──────────┘     │
         │ sp - 1 (PUSH)                  │ sp (POP)       └── window b (SETSP)
         ▼                                ▼
   ┌────────────────────────────────────────────┐
   │ address_mux: pc, ALU answer, sp - 1 or sp  │
   └─────────────────────┬──────────────────────┘
                         ▼ address
                   ┌───────────┐  ram.out
   window b = rd ─►│    RAM    ├──────────► write_back ──► rd (POP)
   (data, PUSH)    └───────────┘
```

**2. Choosing the address.** On a fetch beat the `address_mux` sends `pc` to the RAM,
as on [Fetch, Decode, Execute](fetch-decode-execute.md). On an execute beat it used
to send only the ALU's answer (for `LOAD` and `STORE`). Now it has two more choices: for
`PUSH` it sends `sp - 1`, the spot just below the top, and for `POP` it sends `sp`
itself, the top plate. The decoder's `PUSH` and `POP` lines steer the choosers.

**3. A push.** Window `b` of the register file reads `rd`, and its wires run to the
RAM's data input. The RAM's write wire is raised for `PUSH`, so on the `write` pulse
the word in `rd` goes into the RAM at `sp - 1`. At the clock's rise a moment later
(see [The Clock](the-clock.md)), `sp` loads from the `next_sp` chooser, which is
showing `sp - 1`. The finger moves down onto the plate just put there.

**4. A pop.** The address is `sp`, so `ram.out` shows the top word. The `write_back`
chooser sends `ram.out` into the register file (exactly as for `LOAD`), and the
register file loads `rd`. At the same clock rise `sp` loads `sp + 1`, so the finger
moves back up. Everything happens on the one execute beat, because the old `sp`
picks the address while the new `sp` is only waiting at the register's input.

**5. Faults.** The `address_check` part watches the address wires, as before. For a
`PUSH` or `POP` any address outside RAM is a fault, *including* `0xFFFF`: only a
`STORE` may use the output port. A fault blocks every `load` wire and the RAM write
on that beat, so `sp`, the registers and memory stay exactly as they were, and only
`halted` and `halt_code` change.

**6. `GETSP` and `SETSP`.** You met these on the
[Instruction Set page](../reference/instruction-set.md). `GETSP rd` copies the finger
into a register, and `SETSP rd` puts the finger wherever `rd` says, which is how a
program could give its stack a different home. `SETSP` is the third input to the
`next_sp` chooser.

How much does the stack cost? The second Try It counted it: each adder is 240 gates
(16 full adders of 15 gates, as on [Adding](adding.md)), so the two together are 480
of the CPU's 6,029 gates, about one gate in twelve. The choosers that steer `sp`, the
address and the RAM's data add a few hundred more. Not bad for a whole new way of
using memory.

Notice the rule from [RAM](ram.md) at work: the address and the data going into the
RAM come only from registers (`sp`, `rd`) or adders working on registers, never from
`ram.out`. A popped word goes into a register first.

## Why Does This Matter?

A stack is the simplest possible way to keep things for later without having to name
where you put them. You just push, and later you pop, and you get your things back in
the reverse order. A program can use it to make room: when it runs out of its eight
registers, it pushes some of them, uses the registers for something else, then pops the
old values back.

Its real job, though, is what comes next. Without a stack, a piece of program could not
be used from two different places and still know where to go back to, and it certainly
could not call itself. Every processor in every phone, laptop and games console has a
stack pointer register and push and pop instructions (or something that does the same
thing). When a program crashes with a "stack overflow", it is this pile that grew until
it hit something it should not have.

## What's Next

The most important thing a stack holds is a note saying "come back here when you are
done". Continue with [Calling and Returning](calling-and-returning.md).
