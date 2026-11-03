"""Hold the stopwatch up to both engines and print how they did against each limit.

The measuring itself lives in `pycpu.proof.measure_engines`, and the limits in
`pycpu.proof.ENGINE_LIMITS`; this script is the clipboard that writes the results down. Run it fresh each time, because the
memory figure is the peak of the whole process.
"""

import argparse
import sys

from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.proof import ENGINE_LIMITS, measure_engines


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
    for name, (limit, passes, side) in ENGINE_LIMITS.items():
        verdict = "ok" if passes(result[name], limit) else "MISSED"
        missed = missed or verdict == "MISSED"
        print(f"{name:<29} {result[name]:>12.4f} {side:>5} {limit:>9,.1f}  {verdict}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
