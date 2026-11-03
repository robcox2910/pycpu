"""Tests for the control unit's parts: decoder, conditions, register file and helpers."""

from typing import NamedTuple

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.circuit import Bus, Circuit, Clock, Wire
from pycpu.cpu_parts import RegisterFile, condition_met, opcode_lines, outside_ram, sign_extend
from pycpu.isa import Condition, Opcode, condition_holds
from pycpu.memory import make_clock
from pycpu.simulator import Simulator
from pycpu.state import Flags

WORD = 16
WORD_MAX = (1 << WORD) - 1
REGISTERS = 8
OPCODE_BITS = 4
OPCODES = 1 << OPCODE_BITS
COND_BITS = 3
SELECT_BITS = 3
SMALL_RAM_BITS = 6
FULL_RAM_BITS = 12
OFFSET_BITS = 6
BRANCH_BITS = 9
words = st.integers(min_value=0, max_value=WORD_MAX)
selects = st.integers(min_value=0, max_value=REGISTERS - 1)


def test_each_opcode_lights_exactly_its_own_line() -> None:
    """For all 16 opcodes, line n is high and the other fifteen are low."""
    c = Circuit()
    opcode = c.bus_input("op", OPCODE_BITS)
    lines = opcode_lines(c, opcode)
    sim = Simulator(c)
    assert len(lines) == OPCODES
    for member in Opcode:
        sim.set_bus(opcode, member)
        sim.settle()
        assert [sim.get(line) for line in lines] == [int(n == member) for n in range(OPCODES)]


def test_the_decoder_lives_in_a_part_named_decode() -> None:
    """The Bench can find the decoder by its scope name."""
    c = Circuit()
    opcode_lines(c, c.bus_input("op", OPCODE_BITS))
    assert c.has_scope("decode")


@pytest.mark.parametrize("condition", list(Condition))
@pytest.mark.parametrize("flag_bits", range(16))
def test_condition_met_agrees_with_the_instruction_set(
    condition: Condition, flag_bits: int
) -> None:
    """Every condition on every flag combination matches `isa.condition_holds`."""
    c = Circuit()
    cond = c.bus_input("cond", COND_BITS)
    zero, negative, carry, overflow = (c.input(n) for n in ("z", "n", "c", "v"))
    met = condition_met(c, cond, zero, negative, carry, overflow)
    sim = Simulator(c)
    flags = Flags(
        zero=flag_bits & 1,
        negative=(flag_bits >> 1) & 1,
        carry=(flag_bits >> 2) & 1,
        overflow=(flag_bits >> 3) & 1,
    )
    sim.set_bus(cond, condition)
    for wire, value in zip((zero, negative, carry, overflow), flags, strict=True):
        sim.set(wire, value)
    sim.settle()
    assert sim.get(met) == int(condition_holds(condition, flags))
    assert c.has_scope("condition")


class Ports(NamedTuple):
    """The free input wires of a register file under test."""

    data: Bus
    write: Wire
    write_select: Bus
    read_a: Bus
    read_b: Bus
    clock: Clock


def _register_file() -> tuple[Circuit, RegisterFile, Ports]:
    """Build a register file whose every input is a free wire or bus."""
    c = Circuit()
    ports = Ports(
        data=c.bus_input("data", WORD),
        write=c.input("wr"),
        write_select=c.bus_input("ws", SELECT_BITS),
        read_a=c.bus_input("ra", SELECT_BITS),
        read_b=c.bus_input("rb", SELECT_BITS),
        clock=make_clock(c),
    )
    return c, RegisterFile(c, *ports), ports


def test_the_register_file_has_eight_registers_in_the_registers_part() -> None:
    """There are eight 16-bit registers, named r0 to r7 inside `registers`."""
    c, file, _ = _register_file()
    assert len(file.registers) == REGISTERS
    assert all(len(r.q) == WORD for r in file.registers)
    assert c.has_scope("registers")
    assert all(c.has_scope(f"registers.r{n}") for n in range(REGISTERS))


@given(values=st.lists(words, min_size=REGISTERS, max_size=REGISTERS), new=words, target=selects)
def test_a_write_changes_only_the_selected_register(
    values: list[int], new: int, target: int
) -> None:
    """With write high, one beat loads the chosen register and leaves the others."""
    c, file, ports = _register_file()
    sim = Simulator(c)
    for register, value in zip(file.registers, values, strict=True):
        register.poke(sim, value)
    sim.set_bus(ports.data, new)
    sim.set_bus(ports.write_select, target)
    sim.set(ports.write, 1)
    sim.tick(ports.clock)
    expected = [new if n == target else v for n, v in enumerate(values)]
    assert [r.peek(sim) for r in file.registers] == expected


@given(values=st.lists(words, min_size=REGISTERS, max_size=REGISTERS), new=words, target=selects)
def test_nothing_changes_when_write_is_low(values: list[int], new: int, target: int) -> None:
    """With write low, a beat leaves all eight registers as they were."""
    c, file, ports = _register_file()
    sim = Simulator(c)
    for register, value in zip(file.registers, values, strict=True):
        register.poke(sim, value)
    sim.set_bus(ports.data, new)
    sim.set_bus(ports.write_select, target)
    sim.tick(ports.clock)
    assert [r.peek(sim) for r in file.registers] == values


@given(values=st.lists(words, min_size=REGISTERS, max_size=REGISTERS), a=selects, b=selects)
def test_both_read_ports_see_any_register(values: list[int], a: int, b: int) -> None:
    """Port a shows register `read_a` and port b shows register `read_b`, independently."""
    c, file, ports = _register_file()
    sim = Simulator(c)
    for register, value in zip(file.registers, values, strict=True):
        register.poke(sim, value)
    sim.set_bus(ports.read_a, a)
    sim.set_bus(ports.read_b, b)
    sim.settle()
    assert sim.get_bus(file.a) == values[a]
    assert sim.get_bus(file.b) == values[b]


@pytest.mark.parametrize("ram_bits", [SMALL_RAM_BITS, FULL_RAM_BITS])
@given(address=words)
def test_outside_ram_is_one_exactly_at_or_above_the_ram_size(ram_bits: int, address: int) -> None:
    """The check is 1 for addresses of `1 << ram_bits` and up, and 0 below."""
    c = Circuit()
    bus = c.bus_input("address", WORD)
    flag = outside_ram(c, bus, ram_bits)
    sim = Simulator(c)
    sim.set_bus(bus, address)
    sim.settle()
    assert sim.get(flag) == int(address >= 1 << ram_bits)
    assert c.has_scope("address_check")


@pytest.mark.parametrize("width_in", [OFFSET_BITS, BRANCH_BITS])
def test_sign_extend_matches_python_for_every_value(width_in: int) -> None:
    """Extending a short signed number to 16 bits keeps its meaning, and adds no gates."""
    c = Circuit()
    bits = c.bus_input("bits", width_in)
    extended = sign_extend(c, bits)
    sim = Simulator(c)
    assert len(extended) == WORD
    assert c.gate_count == 0
    for value in range(1 << width_in):
        signed = value - (1 << width_in) if value >> (width_in - 1) else value
        sim.set_bus(bits, value)
        sim.settle()
        assert sim.get_bus(extended) == signed & WORD_MAX


def test_sign_extend_refuses_to_shrink_a_bus() -> None:
    """Asking for a width smaller than the input is a mistake and says so."""
    c = Circuit()
    with pytest.raises(ValueError, match="narrower"):
        sign_extend(c, c.bus_input("bits", BRANCH_BITS), BRANCH_BITS - 1)


@pytest.mark.parametrize("ram_bits", [WORD, WORD + 1])
@given(address=words)
def test_outside_ram_is_never_one_when_ram_covers_every_address_bit(
    ram_bits: int, address: int
) -> None:
    """A RAM as wide as the address bus can never be overrun, so the check stays 0."""
    c = Circuit()
    bus = c.bus_input("address", WORD)
    flag = outside_ram(c, bus, ram_bits)
    sim = Simulator(c)
    sim.set_bus(bus, address)
    sim.settle()
    assert sim.get(flag) == 0
