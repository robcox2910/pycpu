"""The stopwatch held up to both engines: each must be quick enough at full size.

Limits were written down before anything was measured, so nobody could pick
them to suit the answer. The full-size test is slow, so it only runs with `-m slow`.
"""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from pycpu import proof
from pycpu.fast import FastMachine
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.proof import measure_engines

ROOT = Path(__file__).parent.parent
SMALL_BITS = 6
KEYS = {
    "cpu_gates",
    "total_gates",
    "build_seconds",
    "memory_mib",
    "pause_seconds",
    "read_state_seconds",
    "gate_instruction_seconds",
    "fast_instructions_per_second",
}

BUILD_LIMIT_SECONDS = 30
MEMORY_LIMIT_MIB = 1024
PAUSE_LIMIT_SECONDS = 2
READ_STATE_LIMIT_SECONDS = 2
GATE_INSTRUCTION_LIMIT_SECONDS = 0.5
FAST_INSTRUCTIONS_PER_SECOND_FLOOR = 50_000


def _script_main() -> Callable[[list[str] | None], int]:
    """Load `scripts/measure_engines.py` by its file and hand back its `main`."""
    path = ROOT / "scripts" / "measure_engines.py"
    spec = importlib.util.spec_from_file_location("measure_engines", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("Callable[[list[str] | None], int]", module.main)


def test_a_small_measurement_fills_in_every_figure() -> None:
    """Measuring a 64-word machine gives every figure, each above zero."""
    result = measure_engines(SMALL_BITS)
    assert set(result) == KEYS
    assert all(value > 0 for value in result.values())


def test_the_cpu_gates_are_the_gates_outside_the_ram() -> None:
    """The CPU's share is the whole machine less the RAM, a few thousand gates."""
    result = measure_engines(SMALL_BITS)
    ram_gates = proof.measure(SMALL_BITS)["gates"]
    assert result["cpu_gates"] == result["total_gates"] - ram_gates


def test_engines_that_disagree_fail_the_measurement(monkeypatch: pytest.MonkeyPatch) -> None:
    """A speed measured on an engine giving wrong answers proves nothing, so it stops the run."""
    real_step = FastMachine.step

    def step_twice(machine: FastMachine) -> bool:
        real_step(machine)
        return real_step(machine)

    monkeypatch.setattr(FastMachine, "step", step_twice)
    with pytest.raises(RuntimeError, match="disagree"):
        measure_engines(SMALL_BITS)


def test_the_script_prints_a_table_for_the_size_it_is_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running the script with `--address-bits` prints each figure against its limit."""
    main = _script_main()
    assert main(["--address-bits", str(SMALL_BITS)]) == 0
    printed = capsys.readouterr().out
    assert "64 words" in printed
    for name in KEYS:
        assert name in printed


def test_the_script_exits_non_zero_when_a_limit_is_missed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A figure on the wrong side of its limit is named and the script reports failure."""
    main = _script_main()

    def measure_slowly(_address_bits: int) -> dict[str, float]:
        return dict.fromkeys(KEYS, 1000.0) | {"fast_instructions_per_second": 1.0}

    monkeypatch.setitem(main.__globals__, "measure_engines", measure_slowly)
    assert main(["--address-bits", str(SMALL_BITS)]) == 1
    assert "MISSED" in capsys.readouterr().out


@pytest.mark.slow
@pytest.mark.timeout(900)
def test_both_engines_are_quick_enough_at_full_size() -> None:
    """The whole computer, with its full 4K RAM, meets every limit on both engines."""
    result = measure_engines(RAM_ADDRESS_BITS)
    assert result["build_seconds"] < BUILD_LIMIT_SECONDS
    assert result["memory_mib"] < MEMORY_LIMIT_MIB
    assert result["pause_seconds"] < PAUSE_LIMIT_SECONDS
    assert result["read_state_seconds"] < READ_STATE_LIMIT_SECONDS
    assert result["gate_instruction_seconds"] < GATE_INSTRUCTION_LIMIT_SECONDS
    assert result["fast_instructions_per_second"] > FAST_INSTRUCTIONS_PER_SECOND_FLOOR
