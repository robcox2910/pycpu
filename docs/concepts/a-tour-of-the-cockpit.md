# A Tour of the Cockpit

## Following One Letter Through the Post

You drop a letter into a red postbox at the end of your road. A day later it lands on
your friend's doormat, in a town you have never visited. In between, a lot happened that
you never saw. A van took it to a **sorting office**, where it was sorted by its
postcode. It rode on another van to the right town, then to the right street, and at
last a postman pushed it through one particular front door. If you had a tracking number,
you could follow every stop.

This page follows one line of a Pebble program in the same way. We drop the line
`n = n - 1` into the Cockpit and track it at every stop: the Pebble line, then the
machine instructions it was translated into, then the one instruction that does the
subtraction, then the part of the CPU that does the work, then one column of the adder,
and finally a **single NAND gate**, with the real 0s and 1s on its wires. Then we come
back up and see the letter arrive: the variable `n` has changed from 2 to 1.

Every earlier page climbed **up**, one layer at a time. This **tour** goes the other way,
down through all of them in one go, so you can see the whole climb at once.

| In the post | In the Cockpit |
|-------------|----------------|
| The letter | One **Pebble line**, `n = n - 1` from the `countdown` example |
| Dropping it in the postbox | Loading the program with `POST /api/pebble` and pressing **Line** (`/api/step` with `"size": "line"`) until that line is next |
| The sorting office, where one letter joins the right bag | The translator, which turned the line into machine instructions; the first six get the two numbers ready |
| The van that does the long drive | The one instruction that does the subtraction, `sub r1, r1, r2`, reached with **instruction** steps |
| The town the van drives to | `parts["instruction"]`: the part of the CPU that does that instruction's work, `cpu.alu` |
| The street, then the front door | Gate steps (`"size": "gate"`) until `last_gate["path"]` is inside `cpu.alu.adder`: one column of the adder, then one gate in it |
| Looking through the letterbox | `GET /api/view?path=...`: the gate's real input and output wires |
| The letter on the doormat | One more **Line** step: `variables` shows `n` as 1, and `changed` marks its address |
| The tracking number | The scope **path**, such as `cpu.alu.adder.bit0`, which names every stop on the way |

## Try It

We build a Cockpit with 256 words of memory (8 address bits, so it is quick to build)
and load the `countdown` example, the one that counts down from 5 and says
"Lift off!". Then we follow `n = n - 1` on the round of the loop where `n` goes from 2
to 1.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


def current_line(machine):
    pebble = machine["pebble"]
    return pebble["source"][pebble["line"] - 1].strip()


def variable_n(machine):
    return next(name for name in machine["variables"]["names"] if name["name"] == "n")


async def tour() -> None:
    client = TestClient(create_cockpit(address_bits=8))
    examples = (await client.get("/api/examples")).json()
    countdown = next(example["source"] for example in examples if example["name"] == "countdown")
    machine = (await client.post("/api/pebble", json={"source": countdown})).json()

    # 1. The postbox: press Line until n = n - 1 is next, with n holding 2.
    lines = 0
    while not (current_line(machine) == "n = n - 1" and variable_n(machine)["value"] == 2):
        machine = (await client.post("/api/step", json={"size": "line"})).json()
        lines += 1
    print(f"{lines} line steps: about to run line {machine['pebble']['line']}, n = n - 1")
    print("n is", variable_n(machine)["value"])

    # 2. The sorting office and the van: press Instruction until the sub is next.
    while not machine["instruction"]["text"].startswith("sub"):
        print("   instruction:", machine["instruction"]["text"])
        machine = (await client.post("/api/step", json={"size": "instruction"})).json()
    print("next instruction:", machine["instruction"]["text"])
    print("its part:", machine["parts"]["instruction"])

    # 3. The street and the door: press Gate until a gate in the adder works.
    gates = 0
    while not (machine["last_gate"] or {"path": ""})["path"].startswith("cpu.alu.adder"):
        machine = (await client.post("/api/step", json={"size": "gate"})).json()
        gates += 1
    gate = machine["last_gate"]
    print(f"{gates} gate steps: gate {gate['id']} in {gate['path']}")

    # 4. Through the letterbox: the gate's real wires.
    seen = (await client.get("/api/view", query={"path": gate["path"]})).json()
    wires = next(each for each in seen["gates"] if each["id"] == gate["id"])
    print("its wires: in", wires["value_a"], "and", wires["value_b"], "out", wires["value_out"])

    # 5. The doormat: press Line again and read n.
    machine = (await client.post("/api/step", json={"size": "line"})).json()
    print(machine["note"])
    n = variable_n(machine)
    print(f"n is now {n['value']}, marked changed: {n['address'] in machine['changed']['memory']}")


run(tour())
# Output:
# 12 line steps: about to run line 5, n = n - 1
# n is 2
#    instruction: load r1, [r7-1]
#    instruction: push r1
#    instruction: li r1, 1
#    instruction: push r1
#    instruction: pop r2
#    instruction: pop r1
# next instruction: sub r1, r1, r2
# its part: cpu.alu
# 2122 gate steps: gate 41226 in cpu.alu.adder.bit0.full_adder.half_adder#1.xor
# its wires: in 0 and 1 out 1
# Ran 3 instructions to reach line 3.
# n is now 1, marked changed: True
```

Follow the letter stop by stop.

**The postbox.** The countdown's first line is its title (a `#` comment), so `let n = 5`
is line 2, `while n > 0 {` is line 3, `print(n)` is line 4 and `n = n - 1` is line 5.
Each time round the loop, three presses of **Line** visit lines 3, 4 and 5. `n` starts
at 5, so it takes four rounds, 12 line steps, to stand on line 5 with `n` holding 2.
Each line step ran on the fast engine and then paused, so the machine is now in the
gates, just before the first instruction of line 5 (see
[Stepping a Pebble Line](stepping-a-pebble-line.md)).

**The sorting office.** The translator turned `n = n - 1` into machine instructions long
before we pressed anything (see [From Pebble to Machine Code](from-pebble-to-machine-code.md)).
Pebble's compiler thinks in terms of a pile of numbers, so the instructions first fetch
`n` from its place in memory (`load r1, [r7-1]`, one below the frame pointer `r7`, as
in [Variables in Memory](variables-in-memory.md)), put it on the stack, put 1 on the
stack, and then take both back off into `r1` and `r2` (see
[The Stack](the-stack.md)). Six **instruction** steps walk past them.

**The van.** Now `sub r1, r1, r2` is next: the instruction that really does `n - 1`.
The picture's `parts["instruction"]` names where its work happens, `cpu.alu`, the
calculator part from [The ALU](the-alu.md).

**The street.** Now we press **Gate**, again and again. The gate engine works out one
NAND gate per press, in the order the changes reach them
([Simulating a Circuit](simulating-a-circuit.md)). First comes the **fetch** beat, which
reads the `sub` out of memory into the CPU, and then the **execute** beat begins
([Fetch, Decode, Execute](fetch-decode-execute.md)). After 2,122 gate steps, the gate
that has just worked is inside the adder, at the path
`cpu.alu.adder.bit0.full_adder.half_adder#1.xor`. Read that path like an address, left
to right: the CPU, its ALU, the ALU's adder, the adder's first column (`bit0`, the ones
column), that column's full adder, its second half adder (`#1`: the first is just
`half_adder`, as in [Looking Inside a Circuit](looking-inside.md)), and inside that,
the XOR. The gate number, 41,226, belongs to this 256-word machine; a machine with a
different amount of memory numbers its gates differently.

**The door.** The ALU does a subtraction by adding: `2 - 1` is worked out as `2`, plus
`1` with every bit flipped, plus one more that comes in as the **carry in** of the first
column ([Negative Numbers](negative-numbers.md)). In the ones column, the first half
adder adds the last bit of 2 (a 0) and the last bit of flipped 1 (also a 0), giving 0.
The second half adder adds that 0 to the carry in, which is 1. So our gate, one of the
four NANDs that make that half adder's XOR ([Logic Gates from NAND](gates.md)), sees a
**0 and a 1** on its inputs. NAND's one rule says the output is on unless both inputs
are on, so its output is **1**, exactly what `/api/view` shows. The ones column of
`2 - 1` is going to be a 1. These are the real wires of the real circuit, not a picture
of them (see [The Cockpit](the-cockpit.md)).

**The doormat.** One more press of **Line**. The machine first finishes the `sub` in the
gates, then hands over to the fast engine, which runs 3 more instructions that carry the
answer back to `n`'s place in memory. Then it pauses before line 3, `while n > 0 {`
again. The variables pane shows `n` as 1, and `changed` lists `n`'s address among the
memory words that changed, so the Cockpit marks it. The letter has arrived.

## How It Works

There is no new machinery on this page. The tour uses only buttons and routes from the
pages before it, all in `src/pycpu/cockpit/app.py`, with the rules in
`src/pycpu/cockpit/session.py` and the pictures in `src/pycpu/cockpit/picture.py`. What
is new is seeing all the layers at once. Here is the journey we just made, each stop
built from the one below it:

```text
  Pebble line      n = n - 1                      the Pebble pane, pebble["line"]
       |           translated by the translator   (From Pebble to Machine Code)
       v
  Instructions     load, push, li, push, pop, pop, sub, ...    the machine code pane
       |           each is one 16-bit word        (Machine Code, Assembly Language)
       v
  One instruction  sub r1, r1, r2                 instruction step; parts["instruction"]
       |           fetched, then executed         (Fetch, Decode, Execute)
       v
  A part           cpu.alu                        /api/view?path=cpu.alu
       |           the ALU's adder subtracts      (The ALU, Negative Numbers)
       v
  A column         cpu.alu.adder.bit0             one full adder: two half adders and an OR
       |                                          (Adding)
       v
  A gate           ...half_adder#1.xor, gate 41226    gate step; last_gate
                   NAND: in 0 and 1, out 1        (Switches and NAND, Logic Gates)
```

Going down uses the three smaller step sizes. A **line** step runs on the fast engine
and stops just before the next Pebble line. An **instruction** step runs one instruction
in the gates. A **gate** step works out a single NAND gate, and the picture's
`last_gate` names it, with its path read from the circuit's own filing
(`Circuit.scope_of`). Each step goes through `Computer.resume` and `Computer.pause` from
[Pausing and Rewinding](pausing-and-rewinding.md), so the gate engine is always loaded
with the true state when we look inside it. The two engines always agree, because the
tests run them side by side ([Two Engines](two-engines.md)).

Looking inside uses the scope path. Every gate was filed under a path when the circuit
was built, so `/api/view` with that path answers with the gates in that part and the
real 0 or 1 on each wire, read straight from the simulator that is running.

Coming back up is the line step again: it finishes the half-done `sub` in the gates
first, so nothing is skipped, and then runs on at full speed to the next line.

## Why Does This Matter?

Most people never see what happens between typing `n = n - 1` and the computer
remembering a new number. Here you have watched every stop: one line of a programming
language, a handful of machine instructions, one instruction fetched and executed, an
adder doing a subtraction by adding, and one NAND gate turning a 0 and a 1 into a 1.
Nothing in between was skipped and nothing was faked, so there is no layer left where
magic could be hiding.

Real computers work the same way, only with billions of gates and far faster. When a
debugger shows you a variable changing, a processor somewhere has just done what you
saw here: fetched an instruction, sent two numbers into its adder, and let the gates
settle. Chip designers really do follow single signals through their designs like this,
in simulators, before a chip is ever made.

## What's Next

The Cockpit's one Step button follows how closely you look: read [The Magnifying Glass](the-magnifying-glass.md)
for the four depths. This page was the whole climb, from one NAND gate to a Pebble program you can pause and look
inside. Go back to [What Is a Computer, Really?](../index.md) to see the whole ladder
again, or open the Cockpit yourself with `uv run python -m pycpu`. It opens with the
`tour` example loaded, the program that uses every piece of Pebble PyCPU can run
([The Cockpit](the-cockpit.md) shows its first lines), so you can follow any line of it
down to a gate in just the same way.
