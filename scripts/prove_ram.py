"""Hold the stopwatch up to the RAM and print how it did against each limit.

The measuring itself lives in `pycpu.proof`; this script is the clipboard that
writes the results down. Run it fresh each time, because the memory figure is
the peak of the whole process.
"""

import argparse
import sys

from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.proof import measure

LIMITS = {
    "build_seconds": 30.0,
    "memory_mib": 1024.0,
    "load_seconds": 5.0,
    "read_seconds": 0.1,
    "write_seconds": 0.1,
}


def main(argv: list[str] | None = None) -> int:
    """Measure one RAM size, print a table, and return 0 only if every limit is met."""
    parser = argparse.ArgumentParser(description="Measure a RAM made of real gates.")
    parser.add_argument("--address-bits", type=int, default=RAM_ADDRESS_BITS)
    bits: int = parser.parse_args(argv).address_bits

    result = measure(bits)
    print(f"RAM of {1 << bits} words: {result['gates']:,.0f} gates")
    print(f"{'measure':<15} {'result':>10} {'limit':>10}")
    missed = False
    for name, limit in LIMITS.items():
        verdict = "ok" if result[name] < limit else "MISSED"
        missed = missed or verdict == "MISSED"
        print(f"{name:<15} {result[name]:>10.4f} {limit:>10.1f}  {verdict}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
