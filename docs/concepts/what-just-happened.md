# What Just Happened

## A Commentator Who Only Says What Really Happened

Listen to a football match on the radio. You cannot see the pitch, so the
**commentator** tells you, one sentence at a time: "Smith passes to Jones. Jones shoots.
It's in!" A good commentator only says what really happened, with the real names and
the real score. They never say "Jones probably shot", and they never read out a
sentence they wrote before the match.

The Cockpit has a commentator too. After every move it shows one plain **sentence**
under the heading **What just happened**. The sentence is written from the machine
itself: the real numbers that went into the move and the real numbers that came out.
Nobody wrote it in advance.

| At the match | In the Cockpit |
|--------------|----------------|
| The pitch | The paused computer |
| The commentator's eyes | Two snapshots of the machine: `start`, just before the move, and `after`, just after it |
| One sentence about the last play | `Cockpit.happened`, and the picture's `happened` key |
| The commentator's set phrases ("passes to", "shoots") | The templates in `src/pycpu/cockpit/explain.py`, one for each kind of instruction |
| The real names and the real score | The **real values** filled into a template, read from `start` and `after` |
| Silence before kick-off | `happened` is `None` after a load, because nothing has happened yet |

How big a move is depends on how closely you look (see
[The Magnifying Glass](the-magnifying-glass.md)), so each depth has its own shape of
sentence:

| Depth | The shape of its sentence | Example |
|-------|---------------------------|---------|
| line | "Line *n* ran *k* instructions.", then one sentence for each variable that changed, and what the screen showed | "Line 5 ran 10 instructions. n changed from 2 to 1." |
| instruction | One template for each kind of instruction, filled with the real numbers | "The ALU took 1 away from 2. The answer, 1, went into r1." |
| part | A fetch beat says which word the CPU read; an execute beat gives the sentence of the instruction it finished | "Fetch: the CPU read the word at address 44, which says jmp 15." |
| gate | Which NAND gate worked, the small part and the big part it lives in, and the 0 or 1 it worked out; a clock step says so instead | "Gate 41226, a NAND inside an XOR in the ALU, worked out a 1." |

Run and Rewind get a sentence too: "Ran *k* instructions." and "Went back to the start
of this instruction." A Run or a line step pressed part-way through an instruction says
"finished the instruction you were in, then ran *k* more", so each count is real.

## Try It

We load the `countdown` example (it counts down from 5 and then says "Lift off!") on a
small machine with 256 words of memory, so it is quick to build. We press Step at line
depth until `n = n - 1` (line 5) is next and `n` holds 2. Then we step through that one
line an instruction at a time, printing `happened` after each step. Last of all we take
one part step, and then gate steps until one of them works out a real gate.

```python
from pycpu.cockpit.app import example_programs
from pycpu.cockpit.picture import machine_picture
from pycpu.cockpit.session import Cockpit, Depth

countdown = next(e["source"] for e in example_programs() if e["name"] == "countdown")
cockpit = Cockpit(8)
cockpit.load_pebble(countdown)
print("after the load:", cockpit.happened)


def at_line_5_with_n_2():
    picture = machine_picture(cockpit)
    if picture["pebble"]["line"] != 5:
        return False
    names = picture["variables"]["names"]
    return next(name["value"] for name in names if name["name"] == "n") == 2


while not at_line_5_with_n_2():
    cockpit.step_at(Depth.LINE)
print("line:", cockpit.happened)
for _ in range(10):
    cockpit.step_at(Depth.INSTRUCTION)
    print("instruction:", cockpit.happened)
cockpit.step_at(Depth.PART)
print("part:", cockpit.happened)
lines = cockpit.translated.line_at
print(f"address 14 is on line {lines(14)}, address 15 on line {lines(15)}")
while True:
    cockpit.step_at(Depth.GATE)
    print("gate:", cockpit.happened)
    if cockpit.last_gate.kind == "gate":
        break
# Output:
# after the load: None
# line: Line 4 ran 174 instructions. The screen showed "2".
# instruction: The CPU copied 2 from memory address 254 into r1.
# instruction: The CPU pushed 2 from r1 onto the stack, at address 253.
# instruction: The CPU put the number 1 into r1.
# instruction: The CPU pushed 1 from r1 onto the stack, at address 252.
# instruction: The CPU popped 1 off the stack into r2.
# instruction: The CPU popped 2 off the stack into r1.
# instruction: The ALU took 1 away from 2. The answer, 1, went into r1.
# instruction: The CPU pushed 1 from r1 onto the stack, at address 253.
# instruction: The CPU popped 1 off the stack into r1.
# instruction: The CPU copied 1 from r1 into memory address 254.
# part: Fetch: the CPU read the word at address 44, which says jmp 15.
# address 14 is on line 2, address 15 on line 3
# gate: That step moved the write clock wire, not a gate, so there is no gate to show.
# gate: Gate 0, a NAND inside an AND in the memory, worked out a 1.
```

Read it from the top:

- Straight after a load `happened` is `None`: the match has not kicked off.
- The line step that brought us here ran line 4, `print(n)`, and the screen showed
  the 2 it printed.
- The ten instruction sentences are the ten instructions of `n = n - 1`. The first
  copies `n` out of memory, the pushes and pops shuffle the two numbers into `r1` and
  `r2`, the `sub` works out the answer, and the last one puts the answer back in `n`'s
  box in memory.
- The part step was a **fetch** beat: the CPU read the next instruction, `jmp 15`, but
  has not obeyed it yet, so its sentence says what the word says. The next printed line
  shows that address 15 is the first word of line 3, `while n > 0` (address 14 still
  belongs to line 2), so this jump takes the loop round again.
- The first gate step did not work out a gate at all: it moved the `write` clock wire,
  and the sentence says so instead of making a gate up. The next one worked out gate 0.
  Like every gate in the machine it is a NAND; this one is one of the NAND gates that
  make up an AND in the memory, and the sentence names it and the 1 it worked out.

## How It Works

The sentence is written in `src/pycpu/cockpit/explain.py` by `describe_move`. Before
each move the Cockpit remembers `start`, the state at the start of the current
instruction (`instruction_start`). After the move it reads `after`, the state now. The
numbers that go **into** an instruction are read from the registers in `start`, and the
answer that comes **out** is read from `after`:

```text
   start (before the move)                        after (after the move)
   r1 = 2, r2 = 1                                  r1 = 1
        |                                              |
        |   the word at start's pc:  sub r1, r1, r2    |
        |   isa.decode -> opcode ALU, fn SUB,          |
        |                 rd 1, ra 1, rb 2             |
        v                                              v
   a = r1 in start = 2                            answer = r1 in after = 1
   b = r2 in start = 1
        \                                             /
         +--> template for SUB, filled in:           +
              "The ALU took {b} away from {a}. The answer, {answer}, went into r{rd}."
              "The ALU took 1 away from 2. The answer, 1, went into r1."
```

The instruction is taken apart by `decode` in `isa.py`, the same codebook the machine
uses, so the sentence never guesses what a word means. The templates sit in two tables
in `explain.py`: `OPCODE_TEMPLATES` has one for every opcode, and `ALU_TEMPLATES` has
one for every ALU function. This prints the ALU table, straight from the file:

```python
from pycpu.cockpit.explain import ALU_TEMPLATES

for function, template in ALU_TEMPLATES.items():
    print(f"{function.name}: {template}")
# Output:
# ADD: The ALU added {a} and {b}.
# SUB: The ALU took {b} away from {a}.
# AND: The ALU kept only the bits that are 1 in both {a} and {b}.
# OR: The ALU kept the bits that are 1 in {a} or in {b}.
# XOR: The ALU kept the bits that are 1 in {a} or in {b}, but not in both.
# SHL: The ALU slid every bit of {a} one place to the left.
# SHR: The ALU slid every bit of {a} one place to the right.
# PASS_B: The ALU let {b} straight through.
```

Each ALU sentence then ends with "The answer, *answer*, went into r*d*.", read from
`after`. The numbers are the plain register words, the same numbers the register pane
shows. A register holds a raw 16-bit word, so an instruction sentence says 65535 where
a line sentence about a Pebble variable says -1: the line and variable sentences read
the word as a signed number, the way the variables pane and your Pebble program do (see
[Why 16-Bit Numbers Wrap](why-16-bit-numbers-wrap.md)).

The other depths build on the instruction sentence:

- **part**: a fetch beat finishes no instruction, so its sentence reads the word at
  `start`'s `pc` and says what it says. An execute beat finishes the instruction, so
  its sentence is that instruction's sentence.
- **gate**: every gate is a NAND, so the sentence names the gate, its new output, and
  where it sits. That place is made from the gate's scope path: its last name gives
  the small part, and the name just after `cpu.` gives the big part, so
  `cpu.alu.adder.bit0.full_adder.half_adder#1.xor` becomes "an XOR in the ALU". A step
  that moved a clock wire instead of a gate says so.
- **line**: the sentence counts the instructions the line ran and compares each Pebble
  variable in `start`'s memory with `after`'s. Hidden helper variables the translator
  makes up for itself, such as `$for_limit_0`, are left out, because you never wrote
  them. A line step that goes into a function, or comes back out of one, ends in a
  different frame, so it compares nothing and says where it went instead, with the
  variables it finds there: for the `factorial` example, "Line 8 ran 21 instructions
  and went into fact, where n is 5." (the tests in `tests/test_explain.py` pin this
  sentence and the others like it).
- **a step that cannot move**, such as a line step on a machine-code program or any step
  once the program has finished, leaves `happened` as `None`. Nothing happened, so the
  commentator stays quiet, and `note` says why in one sentence.

Here is the line sentence for `n = n - 1`, and what happens if you press a deeper Step
first. Five gate steps start the line's first instruction. The line step then finishes
that instruction in the gates and runs the other 9 on the fast engine, and the sentence
says the two parts apart, so every number in it is a real count:

```python
from pycpu.cockpit.app import example_programs
from pycpu.cockpit.picture import machine_picture
from pycpu.cockpit.session import Cockpit, Depth

countdown = next(e["source"] for e in example_programs() if e["name"] == "countdown")


def at_line_5_with_n_2(cockpit):
    picture = machine_picture(cockpit)
    if picture["pebble"]["line"] != 5:
        return False
    names = picture["variables"]["names"]
    return next(name["value"] for name in names if name["name"] == "n") == 2


def ready():
    cockpit = Cockpit(8)
    cockpit.load_pebble(countdown)
    while not at_line_5_with_n_2(cockpit):
        cockpit.step_at(Depth.LINE)
    return cockpit


plain = ready()
plain.step_at(Depth.LINE)
print(plain.happened)

deeper_first = ready()
for _ in range(5):
    deeper_first.step_at(Depth.GATE)
deeper_first.step_at(Depth.LINE)
print(deeper_first.happened)
# Output:
# Line 5 ran 10 instructions. n changed from 2 to 1.
# Line 5 finished the instruction you were in, then ran 9 more. n changed from 2 to 1.
```

The line sentence does not list the ten instructions by name. Ten names in a row is
more than anyone can read at a glance; the instruction depth is where each one gets its
own sentence.

## Why Does This Matter?

The Cockpit's panes show true numbers, but a page full of numbers does not say what
they **mean**. Without the sentence, you would see `r1` turn from 2 into 1 and have to
work out for yourself that a subtraction did it. The sentence joins the numbers up into
a story, and because it is written from the real machine it can never tell you
something that did not happen.

Real tools do the same. A debugger prints "Breakpoint hit at line 12", and a car's
dashboard says "Door open" rather than lighting up a wire number. Turning what a machine
did into words a person can read is one of the most useful things a program can do.

## What's Next

You can now read every move the machine makes. Next, let the Cockpit show you round:
[Guided Walks](guided-walks.md) are short tours that move the real machine one step at
a time, with one sentence for each step.
