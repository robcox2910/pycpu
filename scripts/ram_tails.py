"""Look past the middle of the race: time the RAM's slowest moments and count its gate work.

A median is the runner in the middle of the pack, and it says nothing about the
one who limps in last. `pycpu.proof` reports medians. This script makes a longer
run, with a fixed seed, and prints the slowest times, how many gate evaluations
each access needs, the cost of a write that flips every data wire, and what a
plain Python list would have cost. Every word is checked at the end.
"""

import argparse
import random
import statistics
import sys
import time

from pycpu.circuit import Circuit
from pycpu.memory import RAM_ADDRESS_BITS, WORD_BITS, Ram, make_clock
from pycpu.simulator import Simulator

SEED = 2026
READS = 2000
WRITES = 500
FLIP_WRITES = 50
LIST_READS = 1_000_000
ALL_ONES = (1 << WORD_BITS) - 1


class Rig:
    """A RAM of real gates with its inputs and simulator, and a timed read and write."""

    def __init__(self, address_bits: int) -> None:
        """Build the RAM and bring it to life."""
        self.circuit = Circuit()
        self.clock = make_clock(self.circuit)
        self.address = self.circuit.bus_input("address", address_bits)
        self.data = self.circuit.bus_input("data", WORD_BITS)
        self.write_enable = self.circuit.input("write_enable")
        self.ram = Ram(self.circuit, self.address, self.data, self.write_enable, self.clock)
        self.sim = Simulator(self.circuit)

    def read(self, where: int) -> tuple[float, int, int]:
        """Read one word; return seconds taken, gate evaluations and the word."""
        before = self.sim.events_total
        start = time.perf_counter()
        self.sim.set_bus(self.address, where)
        self.sim.settle()
        word = self.sim.get_bus(self.ram.out)
        return time.perf_counter() - start, self.sim.events_total - before, word

    def write(self, where: int, value: int) -> tuple[float, int]:
        """Write one word on a clock beat; return seconds taken and gate evaluations."""
        before = self.sim.events_total
        start = time.perf_counter()
        self.sim.set_bus(self.address, where)
        self.sim.set_bus(self.data, value)
        self.sim.set(self.write_enable, 1)
        self.sim.tick(self.clock)
        self.sim.set(self.write_enable, 0)
        self.sim.settle()
        return time.perf_counter() - start, self.sim.events_total - before


def _show(name: str, values: list[float]) -> None:
    """Print the middle and the worst of a list of figures."""
    print(f"{name:<24} median {statistics.median(values):>12.6g}   max {max(values):>12.6g}")


def _list_read_seconds(words: list[int]) -> float:
    """Return how long one read of a plain Python list takes, for comparison."""
    index = len(words) // 2
    start = time.perf_counter()
    for _ in range(LIST_READS):
        _ = words[index]
    return (time.perf_counter() - start) / LIST_READS


def main(argv: list[str] | None = None) -> int:
    """Run the long measurement and print it; return 1 if any word comes back wrong."""
    parser = argparse.ArgumentParser(description="Time a RAM's slowest moments.")
    parser.add_argument("--address-bits", type=int, default=RAM_ADDRESS_BITS)
    bits: int = parser.parse_args(argv).address_bits

    rng = random.Random(SEED)  # noqa: S311 - a fixed seed for repeatable runs, not for secrets
    words = 1 << bits
    rig = Rig(bits)
    expected = [rng.randrange(1 << WORD_BITS) for _ in range(words)]
    rig.ram.load(rig.sim, expected)

    reads = [rig.read(rng.randrange(words)) for _ in range(READS)]

    write_results: list[tuple[float, int]] = []
    for _ in range(WRITES):
        where, value = rng.randrange(words), rng.randrange(1 << WORD_BITS)
        expected[where] = value
        write_results.append(rig.write(where, value))

    flip_seconds: list[float] = []
    value = 0
    for _ in range(FLIP_WRITES):
        value ^= ALL_ONES  # every data wire changes, the most a write can stir
        where = rng.randrange(words)
        expected[where] = value
        flip_seconds.append(rig.write(where, value)[0])

    print(f"RAM of {words} words, seed {SEED}: {READS} reads, {WRITES} writes")
    _show("read seconds", [seconds for seconds, _, _ in reads])
    _show("read evaluations", [float(count) for _, count, _ in reads])
    _show("write seconds", [seconds for seconds, _ in write_results])
    _show("write evaluations", [float(count) for _, count in write_results])
    _show("all-16-flip write secs", flip_seconds)
    print(f"plain list read seconds  {_list_read_seconds(expected):.6g}")

    wrong = sum(rig.ram.peek(rig.sim, where) != expected[where] for where in range(words))
    print(f"words wrong afterwards   {wrong}")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
