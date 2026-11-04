"""Tests for the fast engine: the ALU model, power-on, and every kind of instruction.

The fast engine is the answer key that the gate CPU is later proved against, so
these tests spell out what each instruction must do, fault included.
"""

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.arithmetic import AluOp, alu
from pycpu.circuit import Circuit
from pycpu.fast import FastMachine, alu_model
from pycpu.isa import OUTPUT_PORT, Condition, Fault, Opcode, encode
from pycpu.simulator import Simulator
from pycpu.state import Flags, MachineState, power_on

SMALL = 64
WORD = 16
WORD_MAX = 0xFFFF
words = st.integers(min_value=0, max_value=WORD_MAX)
ops = st.sampled_from(list(AluOp))
COUNTDOWN = [0x2203, 0xE2FF, 0x83FE, 0xF000]
COUNTDOWN_STEPS = 8
TEN = 10
LI_HI_RESULT = 0x3412
MIN_NEGATIVE = 0x8000
STORED_VALUE = 99
STORED_ADDRESS = 37
AFTER_LOAD_FAULT_PC = 3
BAD_JUMP = 4000
CALL_PROGRAM_STEPS = 5
PUSHED_VALUE = 42
FULL_WORDS = 4096


class AluRig:
    """The Plan 1 gate ALU wired to inputs, for the model to be checked against."""

    def __init__(self) -> None:
        """Build the circuit once and bring it to life."""
        c = Circuit()
        self.a = c.bus_input("a", WORD)
        self.b = c.bus_input("b", WORD)
        self.op = c.bus_input("op", 3)
        self.out = alu(c, self.a, self.b, self.op)
        self.sim = Simulator(c)

    def run(self, a: int, b: int, op: AluOp) -> tuple[int, Flags]:
        """Return (result, flags) as the gates work them out."""
        self.sim.set_bus(self.a, a)
        self.sim.set_bus(self.b, b)
        self.sim.set_bus(self.op, op)
        self.sim.settle()
        get = self.sim.get
        flags = Flags(
            zero=get(self.out.zero),
            negative=get(self.out.negative),
            carry=get(self.out.carry),
            overflow=get(self.out.overflow),
        )
        return self.sim.get_bus(self.out.result), flags


@pytest.fixture(scope="module")
def rig() -> AluRig:
    """Share one gate ALU between tests, because building it is the slow part."""
    return AluRig()


def make(program: list[int], words_count: int = SMALL) -> FastMachine:
    """Build a small machine with a program loaded."""
    machine = FastMachine(words_count)
    machine.load_program(program)
    return machine


def with_sp(machine: FastMachine, sp: int) -> FastMachine:
    """Return the same machine with its stack pointer changed."""
    machine.load_state(replace(machine.state(), sp=sp))
    return machine


@settings(max_examples=300)
@given(words, words, ops)
def test_alu_model_matches_the_gate_alu(rig: AluRig, a: int, b: int, op: AluOp) -> None:
    """The plain-Python ALU gives the gate ALU's result and all four flags."""
    assert alu_model(a, b, op) == rig.run(a, b, op)


def test_power_on_is_all_zero_except_the_stack_pointer() -> None:
    """A fresh machine has pc 0, sp at the end of memory, and nothing else set."""
    state = power_on(SMALL)
    assert (state.pc, state.sp) == (0, SMALL)
    assert state.registers == (0,) * 8
    assert state.flags == Flags(0, 0, 0, 0)
    assert state.memory == (0,) * SMALL
    assert (state.halted, state.halt_code, state.output) == (False, 0, ())


def test_the_output_text_is_the_low_bytes_of_the_output_words() -> None:
    """`output_text` turns the words written to the port into characters."""
    state = replace(power_on(SMALL), output=(72, 0x169, 33))
    assert state.output_text == "Hi!"


def test_the_countdown_counts_down_and_halts() -> None:
    """The countdown program takes eight steps and ends halted with r1 = 0."""
    machine = make(COUNTDOWN)
    assert machine.run(100) == COUNTDOWN_STEPS
    state = machine.state()
    assert state.registers[1] == 0
    assert (state.halted, state.halt_code, state.pc) == (True, 0, len(COUNTDOWN))


def test_run_stops_after_max_steps() -> None:
    """A program that never halts is stopped by the step limit."""
    machine = make([encode(Opcode.JMP, imm=0)])
    assert machine.run(10) == TEN
    assert not machine.state().halted


def test_li_then_lhi_builds_a_sixteen_bit_number() -> None:
    """`li` fills the low byte and `lhi` fills the high byte, keeping the low one."""
    machine = make(
        [encode(Opcode.LI, rd=1, imm=0x12), encode(Opcode.LHI, rd=1, imm=0x34), encode(Opcode.HALT)]
    )
    machine.run(10)
    assert machine.state().registers[1] == LI_HI_RESULT


def test_addi_on_the_largest_signed_number_overflows() -> None:
    """Adding 1 to 0x7FFF gives 0x8000 with the negative and overflow lamps on."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=0xFF),
            encode(Opcode.LHI, rd=1, imm=0x7F),
            encode(Opcode.ADDI, rd=1, imm=1),
        ]
    )
    machine.run(3)
    state = machine.state()
    assert state.registers[1] == MIN_NEGATIVE
    assert state.flags == Flags(zero=0, negative=1, carry=0, overflow=1)


def test_alu_instruction_adds_and_sets_flags() -> None:
    """`add r3, r1, r2` writes r3 and the flags; `mov` copies rb."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=200),
            encode(Opcode.LI, rd=2, imm=100),
            encode(Opcode.ALU, rd=3, ra=1, rb=2, fn=AluOp.ADD),
            encode(Opcode.ALU, rd=4, rb=3, fn=AluOp.PASS_B),
        ]
    )
    machine.run(4)
    state = machine.state()
    assert state.registers[3:5] == (300, 300)
    assert state.flags.zero == 0


def test_cmp_sets_flags_and_changes_no_register() -> None:
    """`cmp` of equal numbers turns the zero lamp on and writes nothing."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=5),
            encode(Opcode.LI, rd=2, imm=5),
            encode(Opcode.CMP, ra=1, rb=2),
        ]
    )
    machine.run(3)
    state = machine.state()
    assert state.flags == Flags(zero=1, negative=0, carry=1, overflow=0)
    assert state.registers[:3] == (0, 5, 5)


def test_a_branch_that_is_not_taken_goes_to_the_next_card() -> None:
    """`br eq` with the zero lamp off falls through; with it on, it jumps."""
    program = [
        encode(Opcode.LI, rd=1, imm=1),
        encode(Opcode.ADDI, rd=1, imm=0),
        encode(Opcode.BR, rd=Condition.EQ, imm=5),
    ]
    machine = make(program)
    machine.run(3)
    assert machine.state().pc == len(program)
    taken = make([encode(Opcode.ADDI, rd=1, imm=0), encode(Opcode.BR, rd=Condition.EQ, imm=5)])
    taken.run(2)
    assert taken.state().pc == 2 + 5


def test_store_then_load_round_trips_through_memory() -> None:
    """A word stored at ra + offset is the word loaded back from it."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=40),
            encode(Opcode.LI, rd=2, imm=99),
            encode(Opcode.STORE, rd=2, ra=1, imm=-3),
            encode(Opcode.LOAD, rd=3, ra=1, imm=-3),
        ]
    )
    machine.run(4)
    state = machine.state()
    assert state.memory[STORED_ADDRESS] == STORED_VALUE
    assert state.registers[3] == STORED_VALUE


def test_store_to_the_output_port_adds_to_output_and_leaves_memory_alone() -> None:
    """The port is a screen: the word goes to `output`, and no RAM changes."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=0xFF),
            encode(Opcode.LHI, rd=1, imm=0xFF),
            encode(Opcode.LI, rd=2, imm=65),
            encode(Opcode.STORE, rd=2, ra=1),
        ]
    )
    before = machine.state().memory
    machine.run(4)
    state = machine.state()
    assert state.registers[1] == OUTPUT_PORT
    assert state.output == (65,)
    assert state.output_text == "A"
    assert state.memory == before
    assert not state.halted


def test_load_from_the_output_port_is_a_fault() -> None:
    """Reading the write-only port halts with BAD_ADDRESS."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=0xFF),
            encode(Opcode.LHI, rd=1, imm=0xFF),
            encode(Opcode.LOAD, rd=2, ra=1),
        ]
    )
    machine.run(3)
    state = machine.state()
    assert (state.halted, state.halt_code) == (True, Fault.BAD_ADDRESS)
    assert state.registers[2] == 0
    assert state.pc == AFTER_LOAD_FAULT_PC


def _faulted(machine: FastMachine, steps: int) -> tuple[MachineState, MachineState]:
    """Run until just before the last step, then take it; return both states."""
    machine.run(steps - 1)
    before = machine.state()
    machine.step()
    return before, machine.state()


def _same_but_halted(before: MachineState, after: MachineState, pc: int) -> None:
    """Check that a fault changed nothing but the halted flag, the code and maybe pc."""
    assert (after.halted, after.halt_code) == (True, Fault.BAD_ADDRESS)
    expected = replace(before, halted=True, halt_code=1, pc=pc)
    assert after == expected


def test_a_jump_outside_memory_faults_at_the_next_fetch() -> None:
    """After `jmp 4000` the fetch fails, and pc stays at the bad address."""
    machine = make([encode(Opcode.JMP, imm=4000)])
    before, after = _faulted(machine, 2)
    assert before.pc == BAD_JUMP
    _same_but_halted(before, after, pc=4000)


def test_push_with_the_stack_pointer_at_zero_faults() -> None:
    """Pushing below address 0 halts and changes nothing else."""
    machine = with_sp(make([encode(Opcode.PUSH, rd=1)]), 0)
    before = machine.state()
    machine.step()
    _same_but_halted(before, machine.state(), pc=1)


def test_pop_with_the_stack_pointer_at_the_end_faults() -> None:
    """Popping from the first address past memory halts and changes nothing else."""
    machine = make([encode(Opcode.POP, rd=1)])
    before = machine.state()
    assert before.sp == SMALL
    machine.step()
    _same_but_halted(before, machine.state(), pc=1)


def test_ret_with_the_stack_pointer_at_the_end_faults() -> None:
    """Returning with nothing on the stack halts and changes nothing else."""
    machine = make([encode(Opcode.RET)])
    before = machine.state()
    machine.step()
    _same_but_halted(before, machine.state(), pc=1)


def test_a_load_past_the_end_of_memory_faults() -> None:
    """Loading from address 64 in a 64-word memory halts and changes nothing else."""
    machine = make([encode(Opcode.LI, rd=1, imm=SMALL), encode(Opcode.LOAD, rd=2, ra=1)])
    machine.step()
    before = machine.state()
    machine.step()
    _same_but_halted(before, machine.state(), pc=2)


def test_a_store_past_the_end_of_memory_faults() -> None:
    """Storing to address 64 in a 64-word memory halts and changes nothing else."""
    machine = make([encode(Opcode.LI, rd=1, imm=SMALL), encode(Opcode.STORE, rd=1, ra=1)])
    machine.step()
    before = machine.state()
    machine.step()
    _same_but_halted(before, machine.state(), pc=2)


def test_push_to_the_output_port_address_is_a_fault_not_output() -> None:
    """`push` is not `store`: with sp = 0, the address is 0xFFFF but it still faults."""
    machine = with_sp(make([encode(Opcode.PUSH, rd=1)]), 0)
    machine.step()
    assert machine.state().output == ()
    assert machine.state().halt_code == Fault.BAD_ADDRESS


def test_call_and_ret_come_back_with_the_stack_restored() -> None:
    """A call runs the function, `ret` returns, and sp is back where it began."""
    program = [
        encode(Opcode.LI, rd=1, imm=7),
        encode(Opcode.CALL, imm=3),
        encode(Opcode.HALT),
        encode(Opcode.ALU, rd=1, ra=1, rb=1, fn=AluOp.ADD),
        encode(Opcode.RET),
    ]
    machine = make(program)
    assert machine.run(100) == CALL_PROGRAM_STEPS
    state = machine.state()
    assert (state.registers[1], state.sp, state.halted) == (14, SMALL, True)


def test_push_and_pop_move_values_and_the_stack_pointer() -> None:
    """`push` writes just below sp; `pop` reads it back; `getsp` and `setsp` see sp."""
    machine = make(
        [
            encode(Opcode.LI, rd=1, imm=42),
            encode(Opcode.PUSH, rd=1),
            encode(Opcode.GETSP, rd=2),
            encode(Opcode.POP, rd=3),
            encode(Opcode.LI, rd=4, imm=10),
            encode(Opcode.SETSP, rd=4),
        ]
    )
    machine.run(3)
    state = machine.state()
    assert state.memory[SMALL - 1] == PUSHED_VALUE
    assert state.registers[2] == SMALL - 1
    machine.run(3)
    state = machine.state()
    assert (state.registers[3], state.sp) == (42, 10)


def test_halt_records_its_code() -> None:
    """`halt 3` stops with halt_code 3."""
    machine = make([encode(Opcode.HALT, imm=3)])
    machine.step()
    state = machine.state()
    assert (state.halted, state.halt_code) == (True, 3)


def test_stepping_a_halted_machine_does_nothing() -> None:
    """`step` says False for a halted machine, and its state does not change."""
    machine = make([encode(Opcode.HALT)])
    assert machine.step() is True
    frozen = machine.state()
    assert machine.step() is False
    assert machine.state() == frozen


def test_load_program_puts_words_from_address_zero() -> None:
    """`load_program` resets to power-on and then writes the words at 0, 1, 2 ..."""
    machine = make([1, 2, 3])
    assert machine.state().memory[:4] == (1, 2, 3, 0)
    machine.load_program([9])
    assert machine.state().memory[:3] == (9, 0, 0)


def test_load_program_refuses_a_program_bigger_than_memory() -> None:
    """A program that does not fit is a ValueError, not a silent cut."""
    with pytest.raises(ValueError, match="memory"):
        FastMachine(4).load_program([0] * 5)


def test_load_state_round_trips() -> None:
    """A state taken from one machine and loaded into another matches."""
    machine = make(COUNTDOWN)
    machine.run(4)
    other = FastMachine(SMALL)
    other.load_state(machine.state())
    assert other.state() == machine.state()


@pytest.mark.parametrize(
    "bad",
    [
        {"memory": (0,) * (SMALL - 1)},
        {"registers": (0, 0, 0, 0, 0, 0, 0, 0x10000)},
        {"registers": (0,) * 7},
        {"flags": Flags(2, 0, 0, 0)},
        {"pc": -1},
        {"sp": 0x10000},
        {"halt_code": 0x10000},
        {"halt_code": 0x100},
    ],
)
def test_load_state_rejects_a_state_that_does_not_fit(bad: dict[str, object]) -> None:
    """A wrong-sized memory, an out-of-range register, a halt code above 255 or a bad flag fails."""
    machine = FastMachine(SMALL)
    with pytest.raises(ValueError, match=r"memory|register|flag|pc|sp|halt"):
        machine.load_state(replace(power_on(SMALL), **bad))


def test_the_default_machine_has_four_thousand_words() -> None:
    """With no size given, the machine has the full RAM size."""
    assert FastMachine().words == FULL_WORDS


@pytest.mark.parametrize("size", [0, -1, 0xFFFF])
def test_a_machine_size_that_cannot_exist_is_refused(size: int) -> None:
    """Memory must hold at least one word and stop short of the output port."""
    with pytest.raises(ValueError, match="words"):
        FastMachine(size)


def test_load_program_refuses_a_word_that_is_not_sixteen_bits() -> None:
    """A program word of 65536 is a ValueError."""
    with pytest.raises(ValueError, match="16-bit"):
        FastMachine(SMALL).load_program([0x10000])


def test_call_with_the_stack_pointer_at_zero_faults() -> None:
    """A call cannot push below address 0: it halts and changes nothing else."""
    machine = with_sp(make([encode(Opcode.CALL, imm=5)]), 0)
    before = machine.state()
    machine.step()
    _same_but_halted(before, machine.state(), pc=1)


def test_pc_halted_and_register_agree_with_state_after_a_few_steps() -> None:
    """The cheap readers give the same answers as a full `state()`."""
    machine = make(COUNTDOWN)
    for _ in range(3):
        machine.step()
        state = machine.state()
        assert machine.pc == state.pc
        assert machine.halted == state.halted
        assert [machine.register(i) for i in range(len(state.registers))] == list(state.registers)
    machine.run(100)
    assert machine.halted is True
    assert machine.pc == machine.state().pc


def test_the_handler_table_is_built_once() -> None:
    """Two steps use the very same table, so nothing is rebuilt per instruction."""
    machine = make(COUNTDOWN)
    machine.step()
    first = id(machine.handler_table_for_tests)
    machine.step()
    assert id(machine.handler_table_for_tests) == first
