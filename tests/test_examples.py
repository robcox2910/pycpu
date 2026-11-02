"""Check that every program in `examples/` runs and says what it should.

The examples are the first thing a newcomer tries, like the demo model in a
shop window, so a broken one would be the worst first impression we could make.
"""

import runpy
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent / "examples"

EXPECTED = {
    "add_two_numbers.py": "1234 + 4321 = 5555 (carry out 0)",
    "alu_tour.py": "SUB    ->     7   flags: carry",
    "counter.py": "beats: 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 0 1 2 3 4",
}


def test_every_example_has_an_expected_line() -> None:
    """Each example file is listed here, so none can skip being run."""
    assert sorted(p.name for p in EXAMPLES.glob("*.py")) == sorted(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_runs_and_prints_its_answer(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Run the example as a script and find its key line in the output."""
    runpy.run_path(str(EXAMPLES / name), run_name="__main__")
    assert EXPECTED[name] in capsys.readouterr().out.splitlines()
