"""Run a Pebble program on PyCPU, the computer built from NAND gates.

Like handing a recipe written in English to a cook who only reads picture cards:
the translator turns each Pebble line into PyCPU's own instructions (cards), and
the fast engine follows them. What the cook serves up is what the program prints,
and it is exactly what Pebble's own VM prints for the same program.

Run this with: uv run python examples/run_pebble.py
"""

from pycpu.translator import run_pebble, translate

DOUBLE_IN_A_LOOP = """\
fn double(n) {
    return n * 2
}
let i = 3
while i > 0 {
    print(double(i))
    i = i - 1
}
"""


def main() -> None:
    """Translate the double-in-a-loop program, run it, and show what it printed."""
    translated = translate(DOUBLE_IN_A_LOOP)
    run = run_pebble(DOUBLE_IN_A_LOOP)
    print(f"{len(translated.program.words)} words of machine code, {run.steps} instructions run")
    print(run.describe())
    print(run.output, end="")
    print("printed:", " ".join(run.output.split()))


if __name__ == "__main__":
    main()
