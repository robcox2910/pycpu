"""The proof: a stopwatch and a tape measure held up against our memory.

Imagine promising to build a school with four thousand lockers. Before anyone
moves in, you walk the corridors with a stopwatch: how long did the building
take, how much land does it cover, and how long does it take to reach a locker
and back? This file is that walk, for a RAM made of real gates.

Nothing here works out a logic result. It builds a real `Ram`, fills it with
mixed-up numbers (an empty RAM would flatter the figures, because a gate whose
inputs never change costs nothing), and then reads and writes through the gates
at random addresses while the clock runs. Every read is compared with what
should be there, because a fast memory that gives wrong answers proves nothing.
"""

import random
import resource
import statistics
import sys
import time
from collections.abc import Callable

from pycpu.circuit import Circuit
from pycpu.memory import WORD_BITS, Ram, make_clock
from pycpu.simulator import Simulator

SEED = 2026
ACCESSES = 100
BYTES_PER_MIB = 1024 * 1024
KIB_PER_MIB = 1024


def _peak_memory_mib() -> float:
    """Return the most memory this whole Python process has used so far, in MiB.

    The operating system keeps this high-water mark, and it never goes down, so
    an honest figure needs a fresh process. macOS counts it in bytes, Linux in KiB.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (BYTES_PER_MIB if sys.platform == "darwin" else KIB_PER_MIB)


def _stopwatch(action: Callable[[], object]) -> float:
    """Return how many seconds `action` took."""
    start = time.perf_counter()
    action()
    return time.perf_counter() - start


def measure(address_bits: int) -> dict[str, float]:
    """Build a RAM with `address_bits` address wires and time everything that matters.

    Only the RAM is measured. The processor added in a later plan brings gates
    of its own, so these figures are the cost of memory, not of the whole machine.
    The random numbers come from a fixed seed, so each run makes the same moves.

    Args:
        address_bits: How many address wires; the RAM has `2 ** address_bits` words.

    Returns:
        Six figures. `gates`: NAND gates in the circuit. `build_seconds`: making
        the circuit and its simulator. `memory_mib`: peak memory of this whole
        Python process so far, so it means most in a fresh process.
        `load_seconds`: poking every word and settling. `read_seconds` and
        `write_seconds`: the median of 100 random accesses through the gates; a
        write includes a full `Simulator.tick`.

    Raises:
        RuntimeError: If a read gives the wrong word, or any word is wrong after
            the writes.

    """
    rng = random.Random(SEED)  # noqa: S311 - a fixed seed for repeatable runs, not for secrets
    words = 1 << address_bits

    def random_word() -> int:
        """Pick a word whose bits are half ones and half zeros on average."""
        return rng.randrange(1 << WORD_BITS)

    c = Circuit()
    clock = make_clock(c)
    address = c.bus_input("address", address_bits)
    data = c.bus_input("data", WORD_BITS)
    write_enable = c.input("write_enable")

    start = time.perf_counter()
    ram = Ram(c, address, data, write_enable, clock)
    sim = Simulator(c)
    build_seconds = time.perf_counter() - start

    expected = [random_word() for _ in range(words)]
    load_seconds = _stopwatch(lambda: ram.load(sim, expected))

    def read(where: int) -> int:
        """Choose a word through the gates and return what appears on `out`."""
        sim.set_bus(address, where)
        sim.settle()
        return sim.get_bus(ram.out)

    def write(where: int, value: int) -> None:
        """Store a word through the gates, on one beat of the clock."""
        sim.set_bus(address, where)
        sim.set_bus(data, value)
        sim.set(write_enable, 1)
        sim.tick(clock)
        sim.set(write_enable, 0)
        sim.settle()

    read_times: list[float] = []
    for _ in range(ACCESSES):
        where = rng.randrange(words)
        start = time.perf_counter()
        seen = read(where)
        read_times.append(time.perf_counter() - start)
        if seen != expected[where]:
            msg = f"read {seen} at address {where}, expected {expected[where]}"
            raise RuntimeError(msg)

    write_times: list[float] = []
    for _ in range(ACCESSES):
        where, value = rng.randrange(words), random_word()
        expected[where] = value
        write_times.append(_stopwatch(lambda w=where, v=value: write(w, v)))

    wrong = [where for where in range(words) if ram.peek(sim, where) != expected[where]]
    if wrong:
        msg = f"{len(wrong)} word(s) wrong after the writes, the first at address {wrong[0]}"
        raise RuntimeError(msg)

    return {
        "gates": float(c.gate_count),
        "build_seconds": build_seconds,
        "memory_mib": _peak_memory_mib(),
        "load_seconds": load_seconds,
        "read_seconds": statistics.median(read_times),
        "write_seconds": statistics.median(write_times),
    }
