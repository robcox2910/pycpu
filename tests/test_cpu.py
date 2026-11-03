"""Tests for the gate-built CPU: it must agree with the fast engine, beat for beat.

The fast engine is the answer key. Every program here runs on both engines and the
two `MachineState` sheets are compared after every instruction, faults and the
output port included. The machine is built once per module, with 64 words of RAM,
because building it is the slow part; each test loads its own state.
"""

from dataclasses import replace

import pytest

from pycpu.arithmetic import AluOp
from pycpu.assembler import assemble
from pycpu.cpu import GateMachine, MicroStep, Phase
from pycpu.fast import FastMachine
from pycpu.isa import Condition, Fault, Opcode, encode
from pycpu.state import Flags, MachineState, power_on

ADDRESS_BITS = 6
SMALL = 1 << ADDRESS_BITS
MAX_STEPS = 200
COUNTDOWN = [0x2203, 0xE2FF, 0x83FE, 0xF000]
EDGES_PER_CYCLE = [("write", 1), ("write", 0), ("clk", 1), ("clk", 0)]
MID_PROGRAM_STEPS = 5
MID_CYCLE_GATES = 20
LOADED_REGISTERS = (1, 2, 3, 0x1234, 0xFFFF, 0x8000, 7, 42)


def li_hi(rd: int, value: int) -> list[int]:
    """Return the two instructions that put a 16-bit `value` in register `rd`."""
    return [
        encode(Opcode.LI, rd=rd, imm=value & 0xFF),
        encode(Opcode.LHI, rd=rd, imm=value >> 8),
    ]


# Every pinned fast-engine program from Task 2 that starts from power-on.
PROGRAMS: dict[str, list[int]] = {
    "countdown": COUNTDOWN,
    "li then lhi": [*li_hi(1, 0x3412), encode(Opcode.HALT)],
    "addi overflows": [*li_hi(1, 0x7FFF), encode(Opcode.ADDI, rd=1, imm=1)],
    "alu add and mov": [
        encode(Opcode.LI, rd=1, imm=200),
        encode(Opcode.LI, rd=2, imm=100),
        encode(Opcode.ALU, rd=3, ra=1, rb=2, fn=AluOp.ADD),
        encode(Opcode.ALU, rd=4, rb=3, fn=AluOp.PASS_B),
    ],
    "every alu job": [
        *li_hi(1, 0x8421),
        *li_hi(2, 0x0F0F),
        *(encode(Opcode.ALU, rd=3 + fn % 5, ra=1, rb=2, fn=fn) for fn in AluOp),
        encode(Opcode.HALT, imm=7),
    ],
    "cmp sets flags only": [
        encode(Opcode.LI, rd=1, imm=5),
        encode(Opcode.LI, rd=2, imm=5),
        encode(Opcode.CMP, ra=1, rb=2),
    ],
    "branch not taken": [
        encode(Opcode.LI, rd=1, imm=1),
        encode(Opcode.ADDI, rd=1, imm=0),
        encode(Opcode.BR, rd=Condition.EQ, imm=5),
    ],
    "branch taken": [encode(Opcode.ADDI, rd=1, imm=0), encode(Opcode.BR, rd=Condition.EQ, imm=5)],
    "store then load": [
        encode(Opcode.LI, rd=1, imm=40),
        encode(Opcode.LI, rd=2, imm=99),
        encode(Opcode.STORE, rd=2, ra=1, imm=-3),
        encode(Opcode.LOAD, rd=3, ra=1, imm=-3),
    ],
    "store to the output port": [
        *li_hi(1, 0xFFFF),
        encode(Opcode.LI, rd=2, imm=65),
        encode(Opcode.STORE, rd=2, ra=1),
    ],
    "load from the output port faults": [*li_hi(1, 0xFFFF), encode(Opcode.LOAD, rd=2, ra=1)],
    "jump outside memory faults at fetch": [encode(Opcode.JMP, imm=4000)],
    "load past the end faults": [
        encode(Opcode.LI, rd=1, imm=SMALL),
        encode(Opcode.LOAD, rd=2, ra=1),
    ],
    "store past the end faults": [
        encode(Opcode.LI, rd=1, imm=SMALL),
        encode(Opcode.STORE, rd=1, ra=1),
    ],
    "halt records its code": [encode(Opcode.HALT, imm=3)],
    "getsp and setsp": [
        encode(Opcode.GETSP, rd=2),
        encode(Opcode.LI, rd=4, imm=10),
        encode(Opcode.SETSP, rd=4),
        encode(Opcode.GETSP, rd=5),
        encode(Opcode.HALT),
    ],
    "a store over the next instruction is fetched": [
        encode(Opcode.LI, rd=1, imm=0xF5),
        encode(Opcode.LHI, rd=1, imm=0xF0),  # r1 = HALT 0xF5
        encode(Opcode.LI, rd=2, imm=4),
        encode(Opcode.STORE, rd=1, ra=2),
        encode(Opcode.LI, rd=3, imm=1),  # overwritten before it is fetched
    ],
    "every branch condition": [
        encode(Opcode.LI, rd=1, imm=3),
        encode(Opcode.LI, rd=2, imm=5),
        encode(Opcode.CMP, ra=1, rb=2),
        *(encode(Opcode.BR, rd=cond, imm=0) for cond in Condition),
        encode(Opcode.CMP, ra=2, rb=1),
        *(encode(Opcode.BR, rd=cond, imm=1) for cond in Condition),
        encode(Opcode.HALT),
    ],
    "push and pop": [
        encode(Opcode.LI, rd=1, imm=42),
        encode(Opcode.PUSH, rd=1),
        encode(Opcode.GETSP, rd=2),
        encode(Opcode.POP, rd=3),
        encode(Opcode.LI, rd=4, imm=10),
        encode(Opcode.SETSP, rd=4),
        encode(Opcode.PUSH, rd=3),
        encode(Opcode.HALT),
    ],
    "call and ret": [
        encode(Opcode.LI, rd=1, imm=7),
        encode(Opcode.CALL, imm=3),
        encode(Opcode.HALT),
        encode(Opcode.ALU, rd=1, ra=1, rb=1, fn=AluOp.ADD),
        encode(Opcode.RET),
    ],
    "pop with nothing on the stack faults": [encode(Opcode.POP, rd=1)],
    "ret with nothing on the stack faults": [encode(Opcode.RET)],
    "hello": list(
        assemble(
            """
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
        """,
            words=SMALL,
        ).words
    ),
}


@pytest.fixture(scope="module")
def machine() -> GateMachine:
    """Build one 64-word gate machine for the whole module."""
    return GateMachine(address_bits=ADDRESS_BITS)


def program_state(program: list[int]) -> MachineState:
    """Return the power-on state with `program` at address 0."""
    start = power_on(SMALL)
    return replace(start, memory=(*program, *start.memory[len(program) :]))


def run_side_by_side(machine: GateMachine, start: MachineState) -> MachineState:
    """Run both engines from `start`, checking they agree after every instruction."""
    fast = FastMachine(SMALL)
    fast.load_state(start)
    machine.load_state(start)
    assert machine.state() == fast.state()
    for _ in range(MAX_STEPS):
        assert machine.step() == fast.step()
        assert machine.state() == fast.state()
        if fast.state().halted:
            break
    assert machine.step() is False
    assert machine.state() == fast.state()
    return machine.state()


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_each_pinned_program_ends_the_same_on_gates(machine: GateMachine, name: str) -> None:
    """Every pinned program gives the fast engine's state after every instruction."""
    run_side_by_side(machine, program_state(PROGRAMS[name]))


def test_the_countdown_halts_with_r1_at_zero(machine: GateMachine) -> None:
    """The countdown runs on gates and stops normally with r1 = 0."""
    state = run_side_by_side(machine, program_state(COUNTDOWN))
    assert (state.registers[1], state.halted, state.halt_code) == (0, True, 0)


def test_the_output_port_collects_the_letters(machine: GateMachine) -> None:
    """The hello program sends 'Hi' out of the port and leaves memory as it was."""
    state = run_side_by_side(machine, program_state(PROGRAMS["hello"]))
    assert state.output_text == "Hi"


def test_a_fault_changes_nothing_but_halted_and_the_code(machine: GateMachine) -> None:
    """A store past the end of memory halts and leaves every other value alone."""
    start = replace(
        program_state([encode(Opcode.STORE, rd=1, ra=0)]),
        registers=(SMALL, *LOADED_REGISTERS[1:]),
    )
    machine.load_state(start)
    assert machine.step() is True
    after = machine.state()
    assert after == replace(start, pc=1, halted=True, halt_code=Fault.BAD_ADDRESS)


def test_a_loaded_state_with_registers_and_flags_runs_like_the_fast_engine(
    machine: GateMachine,
) -> None:
    """Registers, flags and sp loaded from a state are the ones the program sees."""
    program = [
        encode(Opcode.ALU, rd=0, ra=3, rb=4, fn=AluOp.ADD),
        encode(Opcode.BR, rd=Condition.GEU, imm=1),
        encode(Opcode.HALT, imm=9),
        encode(Opcode.GETSP, rd=7),
        encode(Opcode.HALT),
    ]
    start = replace(program_state(program), registers=LOADED_REGISTERS, sp=17)
    run_side_by_side(machine, start)


def test_pc_running_off_the_end_faults_at_fetch(machine: GateMachine) -> None:
    """Sixty-four words that never jump end halted with BAD_ADDRESS and pc = 64."""
    words = [encode(Opcode.LI, rd=1, imm=n) for n in range(SMALL)]
    state = run_side_by_side(machine, program_state(words))
    assert (state.halted, state.halt_code, state.pc) == (True, Fault.BAD_ADDRESS, SMALL)


def test_loading_a_state_twice_leaves_every_wire_the_same(machine: GateMachine) -> None:
    """A machine stopped mid-instruction and a fresh one, given one state, agree on every wire."""
    start = replace(program_state(COUNTDOWN), registers=LOADED_REGISTERS, sp=5)
    machine.load_state(program_state(PROGRAMS["hello"]))
    machine.run(MID_PROGRAM_STEPS)
    edges_seen: list[tuple[str, int]] = []
    while edges_seen != [("write", 1), ("write", 0), ("clk", 1)]:
        step = machine.micro_step()
        if step.kind == "edge":
            edges_seen.append((step.wire, step.value))
    for _ in range(MID_CYCLE_GATES):
        machine.micro_step()
    assert not machine.state().halted
    assert not machine.at_boundary
    assert machine.simulator.get(machine._clock.clk) == 1  # caught with clk high
    machine.load_state(start)
    fresh = GateMachine(address_bits=ADDRESS_BITS)
    fresh.load_state(start)
    wires = range(machine.circuit.wire_count)
    assert [machine.simulator.get(w) for w in wires] == [fresh.simulator.get(w) for w in wires]
    assert fresh.state() == machine.state() == start
    assert machine.at_boundary


def test_micro_steps_end_where_step_ends(machine: GateMachine) -> None:
    """Gate-by-gate stepping lands where a whole step lands, with the edges in order."""
    start = program_state(PROGRAMS["store to the output port"])
    machine.load_state(start)
    machine.run(3)
    middle = machine.state()
    machine.step()
    expected = machine.state()

    machine.load_state(middle)
    steps: list[MicroStep] = []
    while not steps or steps[-1].kind != "end":
        steps.append(machine.micro_step())
    edges = [(s.wire, s.value) for s in steps if s.kind == "edge"]
    assert edges == EDGES_PER_CYCLE * 2
    assert [s.phase for s in steps if s.kind == "edge"] == [Phase.FETCH] * 4 + [Phase.EXECUTE] * 4
    assert all(s.gate >= 0 for s in steps if s.kind == "gate")
    assert all(s.gate == -1 for s in steps if s.kind != "gate")
    assert machine.state() == expected
    assert expected.output == (ord("A"),)
    assert machine.at_boundary


def test_two_cycles_make_one_instruction(machine: GateMachine) -> None:
    """Two `step_cycle` calls equal one `step`, and between them the CPU is mid-way."""
    start = program_state(COUNTDOWN)
    machine.load_state(start)
    machine.step()
    expected = machine.state()
    machine.load_state(start)
    assert (machine.phase, machine.at_boundary) == (Phase.FETCH, True)
    machine.step_cycle()
    assert (machine.phase, machine.at_boundary) == (Phase.EXECUTE, False)
    machine.step_cycle()
    assert machine.state() == expected
    assert (machine.phase, machine.at_boundary) == (Phase.FETCH, True)


def test_step_cycle_finishes_a_cycle_started_by_micro_steps(machine: GateMachine) -> None:
    """After a few gates, `step_cycle` completes the cycle, then the instruction ends."""
    start = program_state(COUNTDOWN)
    machine.load_state(start)
    machine.step()
    expected = machine.state()
    machine.load_state(start)
    for _ in range(10):
        machine.micro_step()
    machine.step_cycle()
    assert machine.phase == Phase.EXECUTE
    machine.step_cycle()
    assert machine.state() == expected


def test_a_halted_machine_does_nothing(machine: GateMachine) -> None:
    """Once halted, step, step_cycle and micro_step change nothing at all."""
    machine.load_state(program_state([encode(Opcode.HALT, imm=4)]))
    assert machine.step() is True
    frozen = machine.state()
    assert machine.at_boundary
    assert machine.step() is False
    machine.step_cycle()
    assert machine.micro_step().kind == "end"
    assert machine.state() == frozen
    assert machine.run(10) == 0


NESTED_CALLS = """
    set r7, 0xFFFF
    li r1, 'A'
    store r1, [r7]
    call second
    li r1, 'a'
    store r1, [r7]
    halt
second:
    li r1, 'B'
    store r1, [r7]
    call third
    li r1, 'b'
    store r1, [r7]
    ret
third:
    li r1, 'C'
    store r1, [r7]
    li r1, 'c'
    store r1, [r7]
    ret
"""
CORRUPTED_TARGET = 40
CORRUPTED_HALT_CODE = 5
FAR_OUTSIDE = 0x8000


def stack_start(program: list[int], sp: int) -> MachineState:
    """Return `program` at address 0 with loaded registers, two flags on, and `sp` set."""
    return replace(
        program_state(program), registers=LOADED_REGISTERS, flags=Flags(1, 0, 1, 0), sp=sp
    )


# Stack cases that need a loaded stack pointer, registers or memory.
STACK_CASES: dict[str, MachineState] = {
    "push with sp at zero faults": stack_start([encode(Opcode.PUSH, rd=1)], 0),
    "call with sp at zero faults": stack_start([encode(Opcode.CALL, imm=5)], 0),
    "pop with sp at the end faults": stack_start([encode(Opcode.POP, rd=1)], SMALL),
    "ret with sp at the end faults": stack_start([encode(Opcode.RET)], SMALL),
    "pop from the output port faults": stack_start([encode(Opcode.POP, rd=1)], 0xFFFF),
    "ret from the output port faults": stack_start([encode(Opcode.RET)], 0xFFFF),
    "push far outside memory faults": stack_start([encode(Opcode.PUSH, rd=1)], FAR_OUTSIDE),
    "pop far outside memory faults": stack_start([encode(Opcode.POP, rd=1)], FAR_OUTSIDE),
    "push into word zero overwrites the program": stack_start(
        [encode(Opcode.LI, rd=0, imm=1), encode(Opcode.PUSH, rd=4)], 1
    ),
    "pop and ret from the top word": replace(
        stack_start(
            [encode(Opcode.POP, rd=5), encode(Opcode.SETSP, rd=6), encode(Opcode.RET)],
            SMALL - 1,
        ),
        registers=(*LOADED_REGISTERS[:6], SMALL - 1, LOADED_REGISTERS[7]),
        memory=(
            encode(Opcode.POP, rd=5),
            encode(Opcode.SETSP, rd=6),
            encode(Opcode.RET),
            encode(Opcode.HALT, imm=9),
            *([0] * (SMALL - 5)),
            3,
        ),
    ),
    "call pushes onto a stack in the middle of memory": stack_start(
        [encode(Opcode.CALL, imm=3), encode(Opcode.HALT), 0, encode(Opcode.RET)], SMALL // 2
    ),
    "ret to a corrupted return address": stack_start(
        [
            encode(Opcode.CALL, imm=2),
            encode(Opcode.HALT),
            encode(Opcode.LI, rd=2, imm=CORRUPTED_TARGET),
            encode(Opcode.PUSH, rd=2),  # pushed, never popped
            encode(Opcode.RET),
            *([0] * (CORRUPTED_TARGET - 5)),
            encode(Opcode.HALT, imm=CORRUPTED_HALT_CODE),
        ],
        SMALL,
    ),
    "ret to an address outside memory faults at the next fetch": stack_start(
        [encode(Opcode.PUSH, rd=3), encode(Opcode.RET)], SMALL
    ),
    "nested calls three deep": program_state(list(assemble(NESTED_CALLS, words=SMALL).words)),
}


@pytest.mark.parametrize("name", list(STACK_CASES))
def test_each_stack_case_ends_the_same_on_gates(machine: GateMachine, name: str) -> None:
    """PUSH, POP, CALL and RET give the fast engine's state after every instruction."""
    run_side_by_side(machine, STACK_CASES[name])


def test_push_with_sp_at_zero_changes_nothing_but_halted(machine: GateMachine) -> None:
    """A push to 0xFFFF is a fault, not output, and leaves sp, registers and memory alone."""
    start = STACK_CASES["push with sp at zero faults"]
    machine.load_state(start)
    machine.step()
    assert machine.state() == replace(start, pc=1, halted=True, halt_code=Fault.BAD_ADDRESS)


def test_pop_with_sp_past_the_end_changes_nothing_but_halted(machine: GateMachine) -> None:
    """A pop from address 64 of a 64-word memory faults and leaves r1 and sp alone."""
    start = STACK_CASES["pop with sp at the end faults"]
    machine.load_state(start)
    machine.step()
    assert machine.state() == replace(start, pc=1, halted=True, halt_code=Fault.BAD_ADDRESS)


def test_nested_calls_return_in_order(machine: GateMachine) -> None:
    """Three calls deep, each return lands back in its caller, and sp ends where it began."""
    state = run_side_by_side(machine, STACK_CASES["nested calls three deep"])
    assert state.output_text == "ABCcba"
    assert (state.sp, state.halted, state.halt_code) == (SMALL, True, 0)


def test_ret_jumps_to_a_corrupted_return_address(machine: GateMachine) -> None:
    """RET trusts the stack: a pushed 40 sends it to address 40, as on the fast engine."""
    state = run_side_by_side(machine, STACK_CASES["ret to a corrupted return address"])
    assert (state.halted, state.halt_code) == (True, CORRUPTED_HALT_CODE)
    assert state.memory[SMALL - 1] == 1  # the real return address, never used
    assert state.sp == SMALL - 1


def test_call_then_ret_restores_the_stack(machine: GateMachine) -> None:
    """The pinned call program doubles r1 and leaves sp back at the top of memory."""
    state = run_side_by_side(machine, program_state(PROGRAMS["call and ret"]))
    assert (state.registers[1], state.sp, state.halted) == (14, SMALL, True)


def test_load_state_refuses_a_state_that_does_not_fit(machine: GateMachine) -> None:
    """A wrong-sized memory, or a halt code above 255, is a ValueError, as on the fast engine."""
    with pytest.raises(ValueError, match="memory"):
        machine.load_state(power_on(SMALL + 1))
    with pytest.raises(ValueError, match="halt code"):
        machine.load_state(replace(power_on(SMALL), halt_code=0x100))


def test_load_program_refuses_a_program_bigger_than_memory(machine: GateMachine) -> None:
    """A program that does not fit is a ValueError, as on the fast engine."""
    with pytest.raises(ValueError, match="memory"):
        machine.load_program([0] * (SMALL + 1))


def test_the_cpu_is_zoomable(machine: GateMachine) -> None:
    """The CPU is one part with the named parts inside, and the RAM sits beside it."""
    children = machine.circuit.children("cpu")
    for name in (
        "phase",
        "ir",
        "pc",
        "sp",
        "flags",
        "halt",
        "registers",
        "decode",
        "condition",
        "alu",
        "address_check",
        "sp_minus_1",
        "sp_plus_1",
        "next_sp",
        "ram_data",
    ):
        assert name in children
    assert "ram" in machine.circuit.children("")
    assert machine.words == SMALL


def test_load_program_powers_on_with_the_program_at_zero(machine: GateMachine) -> None:
    """`load_program` gives the power-on state with the words from address 0."""
    machine.load_program(COUNTDOWN)
    assert machine.state() == program_state(COUNTDOWN)


@pytest.mark.parametrize("bits", [0, 16])
def test_a_ram_size_that_cannot_exist_is_refused(bits: int) -> None:
    """The RAM needs at least one address wire and must stop short of the output port."""
    with pytest.raises(ValueError, match="address_bits"):
        GateMachine(address_bits=bits)
