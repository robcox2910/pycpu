"""The proof: a stopwatch and a tape measure held up against our memory and our engines.

Imagine promising to build a school with four thousand lockers. Before anyone
moves in, you walk the corridors with a stopwatch: how long did the building
take, how much land does it cover, and how long does it take to reach a locker
and back? This file is that walk, for a RAM made of real gates.

Nothing here works out a logic result. It builds a real `Ram`, fills it with
mixed-up numbers (an empty RAM would flatter the figures, because a gate whose
inputs never change costs nothing), and then reads and writes through the gates
at random addresses while the clock runs. Every read is compared with what
should be there, because a fast memory that gives wrong answers proves nothing.

`measure_engines` does the same walk for the whole computer: the CPU and the RAM
built from gates (`GateMachine`), and the fast engine (`FastMachine`) that runs
the same instructions with plain Python. Both run one mixed program, and their
states are compared before any time counts, so a quick but wrong engine fails.
"""

import operator
import random
import resource
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import replace

from pycpu.assembler import assemble
from pycpu.circuit import Circuit
from pycpu.cpu import GateMachine
from pycpu.fast import FastMachine
from pycpu.memory import WORD_BITS, Ram, make_clock
from pycpu.simulator import Simulator
from pycpu.state import MachineState, power_on

SEED = 2026
ACCESSES = 100
BYTES_PER_MIB = 1024 * 1024
KIB_PER_MIB = 1024
PAUSES = 5  # how many times `load_state` and `state()` are each timed
GATE_INSTRUCTIONS = 60  # instructions timed one by one on the gate engine
FAST_INSTRUCTIONS = 300_000  # instructions in the fast engine's long run

# The limit each `measure_engines` figure must meet at full size, written down before
# anything was measured: the limit, the comparison it must pass, and the word the table
# prints for that comparison. Most are "under"; the fast engine's speed is "over".
# `scripts/measure_engines.py` and `tests/test_engine_speed.py` both read this one copy.
ENGINE_LIMITS: dict[str, tuple[float, Callable[[float, float], bool], str]] = {
    "build_seconds": (30.0, operator.lt, "under"),
    "memory_mib": (1024.0, operator.lt, "under"),
    "pause_seconds": (2.0, operator.lt, "under"),
    "read_state_seconds": (2.0, operator.lt, "under"),
    "gate_instruction_seconds": (0.5, operator.lt, "under"),
    "fast_instructions_per_second": (50_000.0, operator.gt, "over"),
}

# A loop that never ends, using every kind of instruction worth timing: sums,
# a store and a load, the stack, a call and a return, and a branch.
MIXED_PROGRAM = """
    set r5, data
loop:
    li r1, 7
    add r2, r2, r1      ; ALU
    xor r3, r2, r1
    store r3, [r5]      ; STORE and LOAD through the RAM
    load r4, [r5]
    push r4             ; the stack
    call double         ; a call and a return
    pop r4
    sub r6, r4, r2
    addi r7, 1
    cmp r7, r2
    br ne, loop         ; a branch, taken most times
    jmp loop
double:
    shl r4, r4
    ret
data:
    .word 0
"""


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


def _random_state(rng: random.Random, words: int, program: tuple[int, ...]) -> MachineState:
    """Return a powered-on state holding `program`, with every other word mixed up."""
    rest = [rng.randrange(1 << WORD_BITS) for _ in range(words - len(program))]
    return replace(power_on(words), memory=(*program, *rest))


def measure_engines(address_bits: int) -> dict[str, float]:
    """Build the whole computer both ways and time everything that matters.

    The gate engine and the fast engine each run `MIXED_PROGRAM` from the same
    state, with the memory after the program full of mixed-up numbers (from the
    fixed seed). After the gate engine's timed instructions, its state must equal
    the fast engine's after the same number of steps.

    Args:
        address_bits: How many address wires; the RAM has `2 ** address_bits` words.

    Returns:
        Eight figures. `cpu_gates`: NAND gates outside the RAM. `total_gates`:
        every gate in the machine. `build_seconds`: making the gate machine and
        its simulator. `memory_mib`: peak memory of this whole Python process so
        far. `pause_seconds`: the median of 5 `load_state` calls, which is what
        moving a paused computer onto the gates costs. `read_state_seconds`: the
        median of 5 `state()` calls, reading the whole machine back.
        `gate_instruction_seconds`: the median of 60 `step()` calls on the gate
        engine. `fast_instructions_per_second`: from a run of 300,000 steps on
        the fast engine.

    Raises:
        RuntimeError: If the two engines disagree after the timed instructions.

    """
    rng = random.Random(SEED)  # noqa: S311 - a fixed seed for repeatable runs, not for secrets
    words = 1 << address_bits
    program = assemble(MIXED_PROGRAM, words=words).words

    start = time.perf_counter()
    gate = GateMachine(address_bits)
    build_seconds = time.perf_counter() - start
    total_gates = gate.circuit.gate_count
    cpu_gates = total_gates - gate.circuit.gate_count_in("ram")

    # Pause timings load whole random states, then put back the one to run.
    samples = [_random_state(rng, words, program) for _ in range(PAUSES)]
    pause_times = [_stopwatch(lambda s=state: gate.load_state(s)) for state in samples]
    read_times = [_stopwatch(gate.state) for _ in range(PAUSES)]
    begin = samples[0]
    gate.load_state(begin)

    step_times = [_stopwatch(gate.step) for _ in range(GATE_INSTRUCTIONS)]
    fast = FastMachine(words)
    fast.load_state(begin)
    for _ in range(GATE_INSTRUCTIONS):
        fast.step()
    if gate.state() != fast.state():
        msg = f"the engines disagree after {GATE_INSTRUCTIONS} instructions"
        raise RuntimeError(msg)

    fast.load_state(begin)
    start = time.perf_counter()
    ran = fast.run(FAST_INSTRUCTIONS)
    fast_seconds = time.perf_counter() - start

    return {
        "cpu_gates": float(cpu_gates),
        "total_gates": float(total_gates),
        "build_seconds": build_seconds,
        "memory_mib": _peak_memory_mib(),
        "pause_seconds": statistics.median(pause_times),
        "read_state_seconds": statistics.median(read_times),
        "gate_instruction_seconds": statistics.median(step_times),
        "fast_instructions_per_second": ran / fast_seconds,
    }
