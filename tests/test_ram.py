"""Tests for the RAM: real gates, checked against a plain Python list."""

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.circuit import Bus, Circuit, Clock, Wire
from pycpu.memory import RAM_ADDRESS_BITS, RAM_WORDS, WORD_BITS, Ram, Register, make_clock
from pycpu.simulator import Simulator

SMALL_BITS = 4
SMALL_WORDS = 1 << SMALL_BITS
BYTE_BITS = 8
BYTE_WORDS = 1 << BYTE_BITS
STEP_BUDGET = 300
JUMPS = 300
JUMP_BUDGET = 10_000
MAX_WORD = 0xFFFF
SOME_VALUE = 0xBEEF
OTHER_VALUE = 0x1234
FIRST_LOADED = 100


class Rig:
    """A RAM with its inputs and simulator, ready to use."""

    def __init__(self, address_bits: int) -> None:
        """Build a RAM with an `address_bits`-bit address and simulate it."""
        self.c = Circuit()
        self.clock: Clock = make_clock(self.c)
        self.address: Bus = self.c.bus_input("address", address_bits)
        self.data: Bus = self.c.bus_input("data", WORD_BITS)
        self.write_enable: Wire = self.c.input("write_enable")
        self.ram = Ram(self.c, self.address, self.data, self.write_enable, self.clock)
        self.sim = Simulator(self.c)
        self.words = 1 << address_bits

    def reset(self) -> None:
        """Put every word back to zero and switch writing off."""
        self.ram.load(self.sim, [0] * self.words)
        self.sim.set(self.write_enable, 0)
        self.sim.settle()

    def write(self, address: int, value: int) -> None:
        """Write `value` at `address` through the gates, on a clock beat."""
        self.sim.set_bus(self.address, address)
        self.sim.set_bus(self.data, value)
        self.sim.set(self.write_enable, 1)
        self.sim.tick(self.clock)
        self.sim.set(self.write_enable, 0)
        self.sim.settle()

    def read(self, address: int) -> int:
        """Read the word at `address` from the RAM's output wires."""
        self.sim.set_bus(self.address, address)
        self.sim.settle()
        return self.sim.get_bus(self.ram.out)


@pytest.fixture(scope="module")
def small() -> Rig:
    """One 16-word RAM shared by the tests in this module."""
    return Rig(SMALL_BITS)


@pytest.fixture(scope="module")
def byte() -> Rig:
    """One 256-word RAM shared by the tests in this module."""
    return Rig(BYTE_BITS)


def test_the_size_constants_describe_the_full_ram() -> None:
    """The full RAM is 4096 words of 16 bits, addressed by 12 bits."""
    assert (RAM_ADDRESS_BITS, RAM_WORDS, WORD_BITS) == (12, 4096, 16)


def test_ram_powers_on_all_zero() -> None:
    """A new RAM reads zero at every address."""
    fresh = Rig(SMALL_BITS)
    assert [fresh.read(a) for a in range(SMALL_WORDS)] == [0] * SMALL_WORDS


def test_write_then_read_back(small: Rig) -> None:
    """A word written through the gates reads back, and its neighbours stay zero."""
    small.reset()
    small.write(5, SOME_VALUE)
    assert small.read(5) == SOME_VALUE
    assert small.read(4) == 0
    assert small.read(6) == 0


def test_write_enable_low_changes_nothing(small: Rig) -> None:
    """With write_enable low a clock beat leaves the memory alone."""
    small.reset()
    small.write(3, OTHER_VALUE)
    small.sim.set_bus(small.address, 3)
    small.sim.set_bus(small.data, SOME_VALUE)
    small.sim.set(small.write_enable, 0)
    small.sim.tick(small.clock)
    assert small.read(3) == OTHER_VALUE


def test_overwriting_replaces_the_old_word(small: Rig) -> None:
    """A second write to the same address replaces the first."""
    small.reset()
    small.write(9, SOME_VALUE)
    small.write(9, OTHER_VALUE)
    assert small.read(9) == OTHER_VALUE


@settings(max_examples=25, deadline=None)
@given(
    writes=st.lists(
        st.tuples(st.integers(0, SMALL_WORDS - 1), st.integers(0, MAX_WORD)), max_size=20
    )
)
def test_ram_behaves_like_a_list(writes: list[tuple[int, int]]) -> None:
    """After any run of writes, every address reads what a Python list would hold."""
    rig = _shared_small()
    rig.reset()
    model = [0] * SMALL_WORDS
    for address, value in writes:
        rig.write(address, value)
        model[address] = value
        assert [rig.read(a) for a in range(SMALL_WORDS)] == model


# Hypothesis runs the test body many times, and building a RAM per example would be slow
# (and a function-scoped fixture is refused), so one RAM is built once and reset each time.
_SHARED: list[Rig] = []


def _shared_small() -> Rig:
    """Build the 16-word RAM once and hand back the same one every time."""
    if not _SHARED:
        _SHARED.append(Rig(SMALL_BITS))
    return _SHARED[0]


def test_first_and_last_address(small: Rig, byte: Rig) -> None:
    """The lowest and highest addresses both work, in small and 8-bit RAMs."""
    for rig, last in ((small, SMALL_WORDS - 1), (byte, BYTE_WORDS - 1)):
        rig.reset()
        rig.write(0, SOME_VALUE)
        rig.write(last, OTHER_VALUE)
        assert rig.read(0) == SOME_VALUE
        assert rig.read(last) == OTHER_VALUE
        assert rig.read(1) == 0


def test_poked_words_read_back_through_the_gates(small: Rig) -> None:
    """Words placed with load and poke show up on the output wires."""
    small.reset()
    small.ram.load(small.sim, list(range(FIRST_LOADED, FIRST_LOADED + SMALL_WORDS)))
    assert [small.read(a) for a in range(SMALL_WORDS)] == list(
        range(FIRST_LOADED, FIRST_LOADED + SMALL_WORDS)
    )
    small.ram.poke(small.sim, 7, SOME_VALUE)
    small.sim.settle()
    assert small.read(7) == SOME_VALUE
    assert small.ram.peek(small.sim, 7) == SOME_VALUE
    assert small.ram.peek(small.sim, 8) == FIRST_LOADED + 8


def test_poke_refuses_bad_input(small: Rig) -> None:
    """Out-of-range addresses and too-big values are refused."""
    with pytest.raises(ValueError, match="address"):
        small.ram.poke(small.sim, SMALL_WORDS, 1)
    with pytest.raises(ValueError, match="fit"):
        small.ram.poke(small.sim, 0, 1 << WORD_BITS)
    with pytest.raises(ValueError, match="words"):
        small.ram.load(small.sim, [0] * (SMALL_WORDS + 1))


def test_data_must_be_a_word_wide() -> None:
    """A data bus that is not 16 wires wide is refused."""
    c = Circuit()
    clock = make_clock(c)
    with pytest.raises(ValueError, match="width"):
        Ram(c, c.bus_input("a", 2), c.bus_input("d", 8), c.input("we"), clock)


def test_cells_live_in_word_and_bit_scopes(small: Rig) -> None:
    """Each cell sits in `ram.word<N>.bit<M>` and decoders in `ram.decoder`."""
    c = small.c
    assert c.has_scope("ram.word15.bit15")
    assert c.has_scope("ram.decoder")
    assert len(c.gates_in("ram.word3.bit0")) > 0


def test_inputs_still_moving_do_not_corrupt_other_words(byte: Rig) -> None:
    """Setting address, data and write_enable together, then ticking, writes only the target."""
    byte.ram.load(byte.sim, list(range(BYTE_WORDS)))
    byte.sim.set_bus(byte.address, BYTE_WORDS - 1)
    byte.sim.set_bus(byte.data, SOME_VALUE)
    byte.sim.set(byte.write_enable, 1)
    byte.sim.tick(byte.clock)
    byte.sim.set(byte.write_enable, 0)
    expected = [*range(BYTE_WORDS - 1), SOME_VALUE]
    assert [byte.ram.peek(byte.sim, a) for a in range(BYTE_WORDS)] == expected


def test_sweeping_the_address_with_write_enable_high_changes_nothing(byte: Rig) -> None:
    """Without a write pulse, moving the address around never alters a word."""
    byte.ram.load(byte.sim, list(range(BYTE_WORDS)))
    byte.sim.set(byte.write_enable, 1)
    byte.sim.set_bus(byte.data, SOME_VALUE)
    for address in (0, BYTE_WORDS - 1, 85, 170, 1, 254):
        byte.sim.set_bus(byte.address, address)
        byte.sim.settle()
    byte.sim.set(byte.write_enable, 0)
    assert [byte.ram.peek(byte.sim, a) for a in range(BYTE_WORDS)] == list(range(BYTE_WORDS))


def test_a_register_can_drive_the_address_and_write() -> None:
    """Load an address into a register on one beat, write on the next, neighbours stay."""
    c = Circuit()
    clock = make_clock(c)
    new_address = c.bus_input("new_address", BYTE_BITS)
    load = c.input("load")
    data = c.bus_input("data", WORD_BITS)
    write_enable = c.input("write_enable")
    pointer = Register(c, BYTE_BITS, new_address, load, clock, "pointer")
    ram = Ram(c, pointer.q, data, write_enable, clock)
    sim = Simulator(c)
    ram.load(sim, list(range(BYTE_WORDS)))
    sim.set_bus(new_address, 200)
    sim.set(load, 1)
    sim.tick(clock)
    sim.set(load, 0)
    sim.set_bus(data, SOME_VALUE)
    sim.set(write_enable, 1)
    sim.tick(clock)
    sim.set(write_enable, 0)
    sim.settle()
    expected = list(range(BYTE_WORDS))
    expected[200] = SOME_VALUE
    assert [ram.peek(sim, a) for a in range(BYTE_WORDS)] == expected
    assert sim.get_bus(ram.out) == SOME_VALUE


def test_a_write_leaves_non_adjacent_words_alone(byte: Rig) -> None:
    """Writing one word of a loaded 8-bit RAM leaves words far from it as they were."""
    byte.ram.load(byte.sim, list(range(BYTE_WORDS)))
    byte.write(100, SOME_VALUE)
    for other in (0, 1, 99, 101, 16, 255):
        assert byte.ram.peek(byte.sim, other) == other
    assert byte.ram.peek(byte.sim, 100) == SOME_VALUE


def test_stepping_to_the_next_address_costs_under_300_evaluations(byte: Rig) -> None:
    """In a 256-word RAM full of ones, stepping from address 0 to 1 costs under 300."""
    byte.ram.load(byte.sim, [MAX_WORD] * BYTE_WORDS)
    byte.sim.set_bus(byte.address, 0)
    byte.sim.settle()
    byte.sim.set_bus(byte.address, 1)
    cost = byte.sim.settle()
    assert 0 < cost < STEP_BUDGET
    assert byte.sim.get_bus(byte.ram.out) == MAX_WORD


def test_random_jumps_touch_a_small_part_of_the_circuit(byte: Rig) -> None:
    """Jumping to a random address costs more (the decoder flickers) but stays a sliver."""
    byte.ram.load(byte.sim, [MAX_WORD] * BYTE_WORDS)
    byte.sim.set_bus(byte.address, 0)
    byte.sim.settle()
    rng = random.Random(7)  # noqa: S311 - fixed seed, not for secrets
    costs: list[int] = []
    for _ in range(JUMPS):
        byte.sim.set_bus(byte.address, rng.randrange(BYTE_WORDS))
        costs.append(byte.sim.settle())
    assert max(costs) < JUMP_BUDGET
    assert max(costs) * 4 < byte.c.gate_count  # even the worst jump leaves most gates still
