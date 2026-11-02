"""Hold the stopwatch up to both engines and print how they did against each limit.

The measuring itself lives in `pycpu.proof.measure_engines`; this script is the
clipboard that writes the results down. Run it fresh each time, because the
memory figure is the peak of the whole process.
"""

import argparse
import operator
import sys
from collections.abc import Callable

from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.proof import measure_engines

# Each figure, its limit, and the comparison it must pass (most are "under").
LIMITS: dict[str, tuple[float, Callable[[float, float], bool], str]] = {
    "build_seconds": (30.0, operator.lt, "under"),
    "memory_mib": (1024.0, operator.lt, "under"),
    "pause_seconds": (2.0, operator.lt, "under"),
    "read_state_seconds": (2.0, operator.lt, "under"),
    "gate_instruction_seconds": (0.5, operator.lt, "under"),
    "fast_instructions_per_second": (50_000.0, operator.gt, "over"),
}


def main(argv: list[str] | None = None) -> int:
    """Measure one machine size, print a table, and return 0 only if every limit is met."""
    parser = argparse.ArgumentParser(description="Measure the gate engine and the fast engine.")
    parser.add_argument("--address-bits", type=int, default=RAM_ADDRESS_BITS)
    bits: int = parser.parse_args(argv).address_bits

    result = measure_engines(bits)
    print(f"Computer with {1 << bits} words of RAM")
    print(f"cpu_gates   {result['cpu_gates']:>12,.0f}")
    print(f"total_gates {result['total_gates']:>12,.0f}")
    print(f"{'measure':<29} {'result':>12} {'limit':>15}")
    missed = False
    for name, (limit, passes, side) in LIMITS.items():
        verdict = "ok" if passes(result[name], limit) else "MISSED"
        missed = missed or verdict == "MISSED"
        print(f"{name:<29} {result[name]:>12.4f} {side:>5} {limit:>9,.1f}  {verdict}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
