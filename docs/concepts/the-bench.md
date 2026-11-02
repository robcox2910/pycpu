# The Bench

## A Workbench With the Lid Off

Imagine a radio on a workbench. Normally you only see the box: a dial, a speaker,
a smooth lid. But someone has taken the lid off, and now you can lean over and
see every wire and every part inside. Better still, the radio is switched on. You
can turn the dial, then point at any tiny part and say, "That one is carrying a
signal *right now*."

We have built a lot of parts out of NAND gates: gates, adders, an ALU, registers,
RAM. Until now we could only look at their answers, printed as numbers. The
**Bench** is a web page on your own computer that takes the lid off the **ALU**,
and so every adder and gate inside it. (Registers and RAM are not on the Bench yet;
they join when the CPU does.) You type in
two numbers, pick what the ALU should do, and then **zoom** (move from a big part
into the smaller parts it is made of) all the way down to a single **gate**. It
shows the real circuit, with real wires carrying real 0s and 1s. Nothing on it is
drawn from memory or faked.

| The workbench | In PyCPU |
|---------------|----------|
| The radio with its lid off | The Bench page, served by `python -m pycpu` |
| The radio's dial | The inputs `a`, `b` and `op` on the page |
| A part you point at | A **scope**, such as `alu.adder.bit1` (see [Looking Inside a Circuit](looking-inside.md)) |
| The trail of where you have pointed | The breadcrumb trail along the top of the list |
| A wire carrying a signal | A wire holding a 1, highlighted on the page |
| The smallest part you can find | One NAND gate, with its two inputs and one output |
| The man who reads the dials for you | `circuit_view`, which reads the simulator's own values |
| The workshop door | `create_bench()` in `src/pycpu/bench/app.py` |

## Try It

The Bench is a small web app, but you can talk to it without opening a browser.
Python has a pretend browser for this, called `TestClient` (it sends requests
straight to the app, with no network). We ask the Bench to add 3 and 1, and then
to show us the part of the ALU where the addition of the very first column happens.

Three small words appear that you may not have met. A web request is a message that
has to wait for its reply, so the code that sends one is written as `async def` ("this
function may wait"), and each wait is marked `await` ("pause here until the answer
arrives"). `run(...)` is the starter button: it starts the waiting machinery and runs
our function to the end.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.bench.app import create_bench


async def visit() -> None:
    client = TestClient(create_bench())
    sent = await client.post("/api/inputs", json={"a": 3, "b": 1, "op": 0})
    print(sent.json())
    where = "alu.adder.bit0.full_adder.half_adder.and"
    seen = await client.get("/api/view", query={"path": where})
    for gate in seen.json()["gates"]:
        print(gate)
    missing = await client.get("/api/view", query={"path": "alu.nope"})
    print(missing.status, "No part called alu.nope" in missing.text)


run(visit())
# Output:
# {'result': 4, 'zero': 0, 'negative': 0, 'carry': 0, 'overflow': 0}
# {'id': 74, 'a': 2, 'b': 46, 'out': 111, 'value_a': 1, 'value_b': 1, 'value_out': 0}
# {'id': 75, 'a': 111, 'b': 111, 'out': 112, 'value_a': 0, 'value_b': 0, 'value_out': 1}
# 404 True
```

To open the real thing, run this in a terminal, then visit the address it prints:

```text
uv run python -m pycpu
```

It serves the page at `http://127.0.0.1:8765`. The address `127.0.0.1` means "this
computer only", so nobody else on your network can see it.

## How It Works

The Bench has three small parts, all in `src/pycpu/bench/`.

```
   your browser                            your computer
 ┌──────────────┐   GET /            ┌──────────────────────────┐
 │  page.html   │ <───────────────── │  app.py: create_bench()  │
 │  (the lid    │                    │                          │
 │   is off)    │   POST /api/inputs │   one real ALU, built    │
 │              │ ─────────────────> │   from 896 NAND gates,   │
 │              │                    │   plus its Simulator     │
 │              │   GET /api/view    │                          │
 │              │ <───────────────── │   circuit_view reads it  │
 └──────────────┘                    └──────────────────────────┘
```

**`create_bench()`** builds one real ALU out of NAND gates, exactly as the
[ALU page](the-alu.md) does, and wraps it in a `Simulator`. It has three routes:

- `GET /` hands over `page.html`.
- `POST /api/inputs` takes `{"a", "b", "op"}`, puts those numbers on the ALU's
  input wires, lets the gates settle, and answers with the result and the four
  flags. A number that does not fit in 16 bits, such as 70000, gets a 400
  ("bad request") answer instead.
- `GET /api/view?path=alu.adder` answers with `circuit_view` for that scope. A
  scope that does not exist, such as `alu.nope`, gets a friendly 404 ("not
  found") answer that says `No part called alu.nope`.

**The page** is plain HTML, CSS and JavaScript in one file. It asks for a view,
draws the parts inside it as a list, and draws each gate with its two inputs and
its output. A wire holding a 1 is highlighted, so you can see the signal travel.
Each level you reach is labelled in one plain sentence, with the name of the
page that explains it.

### A guided tour: find the gate that carried the one

Let us add 3 and 1 and then hunt for the exact gate that does the carrying. In
binary 3 is `11` and 1 is `01`. Adding the right-hand column, 1 + 1, gives 2,
which is `10`: write down 0 and **carry** a 1 to the next column.

1. Open the Bench, set `a` to 3, `b` to 1 and `op` to 0 (that is ADD), and press the
   **Set inputs** button. The result
   says 4. Good, the ALU got the sum right. Now to find *how*.
2. You start at the top. Click **alu**. This is the whole ALU, 896 gates, split
   into parts such as `control`, `adder` and `select`. The sums happen in `adder`.
3. Click **adder**. Now you see sixteen parts, `bit0` to `bit15`: one for each
   column of the sum. Our carry happens in the first column, so click **bit0**.
4. Inside is a `full_adder` (a part that adds two bits and a carry coming in,
   explained in [Adding](adding.md)), which holds two `half_adder` parts and an
   `or`. Click down into the first `half_adder`. It holds an `xor`, which finds
   the sum digit, and an `and`, which finds the carry.
5. Click **and**. The two gates here are `74` and `75`. Gate 74 has both inputs at
   1, so a NAND gives 0. Gate 75 takes that 0 on both inputs, and a NAND of two
   0s gives 1. That 1 is the first half adder's carry. You have found the gate: it
   is gate 75, in `alu.adder.bit0.full_adder.half_adder.and`. The full adder's `or`
   then passes that 1 on as the column's carry-out, which closes the loop: the 1
   leaves `bit0` and goes into `bit1`.
6. Now change `a` to 2 and press **Set inputs** again, and come back to the same
   place. Gate 74 now has a 0 on one input, so its output is 1, and gate 75
   turns it back into a 0. Nothing carried. The highlight moved because the real
   wires changed.

The numbers 74 and 75 are not made up for this page. They are the gate numbers
the real circuit hands out in the order the ALU is built, and the Try It above
reads them from the same circuit.

**Why can the page look inside at all?** Back in
[Looking Inside a Circuit](looking-inside.md), every gate was filed under the name
of the part it belongs to as it was built. `circuit_view` looks up that filing and
reads each gate's three wires from the simulator. The Bench does no logic of its
own: it only asks the simulator what is on each wire, and shows you.

### The levels, in plain words

The page shows a one-line explanation and a pointer to the matching concept page
at every level you visit.

| Level | What the page says | Read more |
|-------|--------------------|-----------|
| The whole circuit | Everything we built, as named parts | [Looking Inside a Circuit](looking-inside.md) |
| `alu` | Two numbers go in, a dial picks the job, a result comes out | [The ALU](the-alu.md) |
| `adder` | Sixteen columns that add, one after the other | [Adding](adding.md) |
| `bit0`, `bit1`, ... | One column of the sum | [Adding](adding.md) |
| `full_adder`, `half_adder` | Adds bits and a carry | [Adding](adding.md) |
| `mux`, `choose` | A chooser that picks one of two wires | [Choosing and Decoding](choosing-and-decoding.md) |
| `or_many`, `is_zero` | An OR over many wires, and the check that a result is all 0s | [The ALU](the-alu.md) |
| `xor`, `and`, `or` | A gate built from NANDs | [Logic Gates from NAND](gates.md) |
| A gate | One NAND: its output is 0 only if both inputs are 1 | [Switches and NAND](switches-and-nand.md) |

## Why Does This Matter?

Without the Bench, a wrong answer from the ALU is a mystery: you see 5 where you
expected 4 and you have no way to ask *where did it go wrong?* With the lid off you
can follow the 1 from the input wire, through the column that carried it, to the
single gate that got it wrong. That is how engineers debug real chips, with
probes and logic analysers that show the same thing: which wire is high, right now.

It matters for teaching too. The promise of this project is "nothing is faked",
and the Bench is where you check that promise yourself. The same zoom panel
becomes part of the **Cockpit** (the screen where you will watch a whole program
run), so you will be able to pause a running program and drop from a line of
code down to the very gates doing the work.

## What's Next

That finishes the first climb: from one NAND gate up through gates, adders, the
ALU, registers and RAM, with a Bench to look inside the ALU and everything under it.
Registers and RAM join the Bench when the CPU does. What we do not
have yet is something to *use* all these parts. The next climb builds the
processor, which fetches an instruction from RAM, hands the sums to the ALU, and
keeps its answers in registers. The Bench will follow it all the way.
