# Build It Yourself

## A Model Kit With a Picture on Every Bag

Think of a big model kit, the kind with a dozen numbered bags of pieces. Bag 1 makes
the base. Bag 2 makes the wheels, using only the base. Bag 3 makes the engine. Every
bag has its own little picture showing what you just made, so you never have to guess
whether you got it right, and you never need a piece from a bag you have not opened yet.

PyCPU is that kit. This page is the instruction sheet: the order to open the bags, from
a single NAND gate all the way up to a computer that runs a Pebble program and prints
a number. Each row below is one bag.

| Kit | In PyCPU |
|-----|----------|
| A numbered bag of pieces | One step of the path |
| The pieces | The Python function (or class) that builds that part |
| The picture on the bag | The test that checks the part really works |
| The booklet for that bag | The concept page for that step |
| Holding the finished model | Opening the part in the Cockpit |

## The Path

Work down the table in order. Each page is in the same order as the site's menu, so you
can also just read the menu from top to bottom. Start the Cockpit with
`uv run pycpu` (or `uvx --from fromscratch-pycpu pycpu` with no clone) before you use a
"Watch it" link. The Cockpit's magnifying
glass has four depths: a Pebble line, an instruction, a part and its gates. Press Look
closer until the trail ends in a part's name; that is the part depth, and the Every
part list is under the part's code.

| # | What you build | The function | Read | How you know it works | Watch it |
|---|----------------|--------------|------|-----------------------|----------|
| 1 | The one brick: a NAND gate | `pycpu.circuit.Circuit.nand` | [Switches and NAND](concepts/switches-and-nand.md) | The NAND test tries all four input pairs and checks each answer. `tests/test_simulator.py::test_nand_truth_table` | — |
| 2 | A way to run circuits | `pycpu.simulator.Simulator` | [Simulating a Circuit](concepts/simulating-a-circuit.md) | The simulator test changes nothing and checks that no gate had to work. `tests/test_simulator.py::test_unchanged_input_costs_no_evaluations` | — |
| 3 | NOT, AND, OR and XOR | `pycpu.logic.xor` | [Logic Gates from NAND](concepts/gates.md) | The gate test checks every gate against its truth table. `tests/test_logic.py::test_two_input_gates_follow_their_truth_tables` | — |
| 4 | Choosing and decoding | `pycpu.logic.mux` | [Choosing and Decoding](concepts/choosing-and-decoding.md) | The mux test checks that it passes along exactly the input you chose. `tests/test_logic.py::test_mux_passes_the_chosen_input` | — |
| 5 | A window into a circuit | `pycpu.view.circuit_view` | [Looking Inside a Circuit](concepts/looking-inside.md) | The view test checks the window shows the real, live wire values. `tests/test_view.py::test_view_reports_real_live_values` | — |
| 6 | Adding bits | `pycpu.arithmetic.half_adder` | [Adding](concepts/adding.md) | The adder test tries every pair of bits and checks the sum and the carry. `tests/test_arithmetic.py::test_half_adder_adds_two_bits` | — |
| 7 | Negative numbers | `pycpu.logic.not_bus` and `pycpu.arithmetic.ripple_adder` | [Negative Numbers](concepts/negative-numbers.md) | The test subtracts a number from itself, which flips the bits and adds one, and checks the answer is zero. `tests/test_arithmetic.py::test_subtracting_a_number_from_itself_is_zero` | — |
| 8 | The ALU | `pycpu.arithmetic.alu` | [The ALU](concepts/the-alu.md) | The ALU test compares it with plain Python sums for many pairs of numbers. `tests/test_arithmetic.py::test_alu_matches_the_plain_python_model` | http://127.0.0.1:8765/#walk=subtracting-with-gates |
| 9 | A circuit that remembers | `pycpu.memory.d_latch` | [Remembering](concepts/remembering.md) | The latch test checks that it follows its input while enabled, then holds. `tests/test_memory.py::test_latch_follows_while_enabled_then_holds` | — |
| 10 | The clock | `pycpu.memory.d_flip_flop` | [The Clock](concepts/the-clock.md) | The flip-flop test checks that it changes only on the rising edge of the clock. `tests/test_memory.py::test_flip_flop_changes_only_on_rising_edge` | http://127.0.0.1:8765/#walk=why-the-clock-ticks |
| 11 | Registers | `pycpu.memory.Register` | [Registers](concepts/registers.md) | The register test checks that it keeps its value until told to load a new one. `tests/test_memory.py::test_register_holds_without_load_and_loads_with_it` | open **registers** from the Every part list at the part depth |
| 12 | RAM | `pycpu.memory.Ram` | [RAM](concepts/ram.md) | The RAM test writes a word, then reads it back through the gates. `tests/test_ram.py::test_write_then_read_back` | open **RAM** from the Every part list at the part depth |
| 13 | Measuring how big memory is | `pycpu.proof.measure` | [How Big Is Our Memory?](concepts/how-big-is-our-memory.md) | The proof test measures the full-size RAM and checks every limit is met. `tests/test_ram_proof.py::test_the_full_ram_meets_every_limit` | — |
| 14 | The CPU | `pycpu.cpu.GateMachine` | [What Is a CPU?](concepts/what-is-a-cpu.md) | The countdown test runs a small program on the gates and checks it halts with the right answer. `tests/test_cpu.py::test_the_countdown_halts_with_r1_at_zero` | — |
| 15 | Machine code | `pycpu.isa.encode` | [Machine Code](concepts/machine-code.md) | The encoding test checks an instruction turns into exactly the number worked out by hand. `tests/test_isa.py::test_encode_gives_the_pinned_word` | — |
| 16 | Assembly language | `pycpu.assembler.assemble` | [Assembly Language](concepts/assembly-language.md) | The assembler test checks the countdown becomes the words worked out by hand. `tests/test_assembler.py::test_the_countdown_assembles_to_the_words_worked_out_by_hand` | — |
| 17 | The control unit's decoder | `pycpu.cpu_parts.opcode_lines` | [The Control Unit](concepts/the-control-unit.md) | The decoder test checks each opcode lights exactly its own line and no other. `tests/test_cpu_parts.py::test_each_opcode_lights_exactly_its_own_line` | — |
| 18 | Fetch, decode, execute | `pycpu.cpu.GateMachine._build_datapath` | [Fetch, Decode, Execute](concepts/fetch-decode-execute.md) | The cycle test checks one instruction takes exactly two clock cycles. `tests/test_cpu.py::test_two_cycles_make_one_instruction` | — |
| 19 | The stack | `pycpu.cpu.GateMachine._build_write_back` | [The Stack](concepts/the-stack.md) | The stack test pushes 42, pops it back into another register, and checks the stack pointer moved down and back up. `tests/test_cpu.py::test_push_then_pop_gives_the_value_back` | — |
| 20 | Calling and returning | `pycpu.cpu.GateMachine._build_next_pc` | [Calling and Returning](concepts/calling-and-returning.md) | The call test calls a routine that doubles r1 (7 becomes 14), returns, and checks the stack pointer is back where it started. `tests/test_cpu.py::test_call_then_ret_restores_the_stack` | — |
| 21 | A fast twin of the CPU | `pycpu.fast.FastMachine` | [Two Engines](concepts/two-engines.md) | The lockstep test starts both engines in the same state and checks they always agree. `tests/test_lockstep.py::test_both_engines_agree_from_any_state` | — |
| 22 | Pausing and rewinding | `pycpu.computer.Computer` | [Pausing and Rewinding](concepts/pausing-and-rewinding.md) | The pause test checks that pausing always stops between whole instructions. `tests/test_computer.py::test_pause_lands_on_an_instruction_boundary` | — |
| 23 | Pebble to machine code | `pycpu.translator.translate` | [From Pebble to Machine Code](concepts/from-pebble-to-machine-code.md) | The translator test checks the assembly names each Pebble instruction it came from. `tests/test_translator.py::TestTheTranslatedProgram::test_the_assembly_names_each_pebble_instruction` | — |
| 24 | Variables in memory | `pycpu.translator.FrameLayout` | [Variables in Memory](concepts/variables-in-memory.md) | The frame test checks each variable's offset is the one the generated code uses. `tests/test_frames.py::TestTheLayout::test_the_offsets_are_the_ones_the_code_uses` | http://127.0.0.1:8765/#walk=where-n-lives |
| 25 | 16-bit numbers that wrap | `pycpu.translator.run_pebble` | [Why 16-Bit Numbers Wrap](concepts/why-16-bit-numbers-wrap.md) | The wrap test adds past the top number and checks it comes round to the bottom. `tests/test_translator.py::TestRunningPebble::test_adding_past_the_top_wraps_round_to_the_bottom` | — |
| 26 | If and while as jumps | `pycpu.translator.codegen._CodeWriter._jump` | [If and While as Jumps](concepts/if-and-while-as-jumps.md) | The loop test runs a while loop that adds 1 to 10 and checks the total is 55. `tests/test_translator.py::TestConditionsAndLoops::test_a_while_loop_counts_up_to_ten` | — |
| 27 | Function calls | `pycpu.translator.codegen._CodeWriter._call` | [How a Function Call Really Works](concepts/how-a-function-call-really-works.md) | The function test works out 7 factorial with a function that calls itself and checks it is 5040. `tests/test_functions.py::TestCallingFunctions::test_factorial_of_seven_is_5040` | http://127.0.0.1:8765/#walk=a-call-and-the-stack |
| 28 | Multiply and divide | `__mul` and `__divmod` in `pycpu.translator.runtime.RUNTIME` | [Multiply and Divide](concepts/multiply-and-divide.md) | The multiply test checks products worked out by hand, and the divide test checks the worked examples, negative numbers included. `tests/test_runtime.py::test_multiply_pinned_values` `tests/test_runtime.py::test_divmod_pinned_values` | — |
| 29 | Printing a number | `__print_int` in `pycpu.translator.runtime.RUNTIME` | [Printing a Number](concepts/printing-a-number.md) | The print test checks the exact characters sent to the screen for several numbers. `tests/test_runtime.py::test_print_int_pinned_values` | — |

When you reach row 29, you have built every layer, and a Pebble program can print its
answer on a computer made of nothing but NAND gates. Now watch it all: the
[Cockpit](concepts/the-cockpit.md) shows the whole machine running, and its
[guided walks](concepts/guided-walks.md) take you through it one idea at a time. Try
http://127.0.0.1:8765/#walk=many-instructions to see one line of Pebble turn into many
instructions.

## Try It

Step 6 of the path: build a half adder, a full adder and a 4-bit
ripple adder from the ready-made functions, and count the NAND gates each one costs.
The first two numbers are the ones the [Adding](concepts/adding.md) page prints. The
third is new: it is 4 full adders, and this page pins it.

```python
from pycpu.arithmetic import full_adder, half_adder, ripple_adder
from pycpu.circuit import Circuit

half = Circuit()
half_adder(half, half.input("a"), half.input("b"))
print("a half adder costs", half.gate_count, "NAND gates")

full = Circuit()
full_adder(full, full.input("a"), full.input("b"), full.input("carry"))
print("a full adder costs", full.gate_count, "NAND gates")

ripple = Circuit()
ripple_adder(ripple, ripple.bus_input("a", 4), ripple.bus_input("b", 4), ripple.low)
print("a 4-bit ripple adder costs", ripple.gate_count, "NAND gates")
# Output:
# a half adder costs 6 NAND gates
# a full adder costs 15 NAND gates
# a 4-bit ripple adder costs 60 NAND gates
```

Notice that 4 full adders at 15 gates each is exactly 60. The ripple adder adds no
gates of its own: it only joins the rung below.

## How It Works

**One rule: each rung uses only the rung below.** The half adder is built from XOR and
AND, which are built from NAND. The full adder is built from half adders. The ripple
adder is built from full adders. The ALU uses the ripple adder, the registers use the
flip-flops, and the CPU uses the ALU, the registers and RAM. At no point does a step
sneak in a shortcut. That is why the table can go in one order and never ask for a piece
you do not have yet.

**Every rung has a test.** The test named in each row builds the part from the function
in that row and checks it against the truth: every row of a truth table for the small
parts, and a long list of sums, stores and programs for the big ones. A part is only
finished when its test passes, like a model that only counts as built once it matches
the picture on the bag.

**The list can't go stale.** A test in `tests/test_docs.py` reads the table on this
page. It imports every function named, checks that every page exists and that every
test named in the table is really there,
checks that every walk and every part named is real, and checks the rows follow the same
order as the site's menu.

## Why Does This Matter?

Most people meet a computer from the top, where it is a box that does things. Building
it in order turns it round: you finish row 29 knowing that every instruction, every
Pebble line and every printed digit comes down to NAND gates doing one simple thing. And
if one step ever feels like magic, you can go back one row and find out what it was made
of.

## What's Next

Open the Cockpit with `uv run pycpu` (or `uvx --from fromscratch-pycpu pycpu` with no clone) and watch the machine you built run. Start
with [A Tour of the Cockpit](concepts/a-tour-of-the-cockpit.md), then try the
[guided walks](concepts/guided-walks.md). To see the code that built any part, read
[The Code Behind a Part](concepts/the-code-behind-a-part.md).
