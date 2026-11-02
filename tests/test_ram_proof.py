"""The proof that a RAM of real gates is small and quick enough to use."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from pycpu.circuit import Bus
from pycpu.memory import RAM_ADDRESS_BITS, WORD_BITS, Ram
from pycpu.proof import measure
from pycpu.simulator import Simulator

ROOT = Path(__file__).parent.parent
SMALL_BITS = 6
TINY_BITS = 3
KEYS = {"gates", "build_seconds", "memory_mib", "load_seconds", "read_seconds", "write_seconds"}

BUILD_LIMIT_SECONDS = 30
MEMORY_LIMIT_MIB = 1024
LOAD_LIMIT_SECONDS = 5
ACCESS_LIMIT_SECONDS = 0.1


def _script_main() -> Callable[[list[str] | None], int]:
    """Load `scripts/prove_ram.py` from its file and hand back its `main`."""
    spec = importlib.util.spec_from_file_location("prove_ram", ROOT / "scripts" / "prove_ram.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("Callable[[list[str] | None], int]", module.main)


def test_a_small_measurement_fills_in_every_figure() -> None:
    """Measuring a 64-word RAM gives every figure, each above zero."""
    result = measure(SMALL_BITS)
    assert set(result) == KEYS
    assert all(value > 0 for value in result.values())


def test_the_gate_count_grows_with_the_ram() -> None:
    """Twice as many address wires means many more gates."""
    assert measure(SMALL_BITS)["gates"] > measure(TINY_BITS)["gates"]


def test_a_ram_that_reads_wrongly_fails_the_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    """A speed measured on a broken RAM proves nothing, so a wrong read stops the run."""

    def get_bus_always_zero(_sim: Simulator, _bus: Bus) -> int:
        return 0

    monkeypatch.setattr(Simulator, "get_bus", get_bus_always_zero)
    with pytest.raises(RuntimeError, match="read"):
        measure(SMALL_BITS)


def test_a_write_that_harms_a_word_fails_the_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    """After the writes every word is checked, so a word that went wrong stops the run."""
    real_peek = Ram.peek

    def peek_with_one_bit_flipped(ram: Ram, sim: Simulator, address: int) -> int:
        return real_peek(ram, sim, address) ^ 1

    monkeypatch.setattr(Ram, "peek", peek_with_one_bit_flipped)
    with pytest.raises(RuntimeError, match="wrong after the writes"):
        measure(SMALL_BITS)


def test_the_measured_ram_holds_varied_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """The words loaded mix ones and zeros, because an empty RAM would flatter the numbers."""
    loaded: list[list[int]] = []
    real_load = Ram.load

    def spying_load(ram: Ram, sim: Simulator, words: list[int]) -> None:
        loaded.append(list(words))
        real_load(ram, sim, words)

    monkeypatch.setattr(Ram, "load", spying_load)
    measure(SMALL_BITS)
    assert len(loaded) == 1
    words = loaded[0]
    assert len(words) == 1 << SMALL_BITS
    ones = sum(word.bit_count() for word in words)
    assert WORD_BITS * len(words) / 4 < ones < WORD_BITS * len(words) * 3 / 4


def test_the_script_prints_a_table_for_the_size_it_is_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Running the script with `--address-bits` prints each figure against its limit."""
    main = _script_main()
    assert main(["--address-bits", str(TINY_BITS)]) == 0
    printed = capsys.readouterr().out
    assert "8 words" in printed
    for name in ("build_seconds", "memory_mib", "load_seconds", "read_seconds", "write_seconds"):
        assert name in printed


def test_the_script_exits_non_zero_when_a_limit_is_missed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A figure over its limit is named and the script reports failure."""
    main = _script_main()
    slow = dict.fromkeys(KEYS, 1000.0)

    def measure_slowly(_address_bits: int) -> dict[str, float]:
        return slow

    monkeypatch.setitem(main.__globals__, "measure", measure_slowly)
    assert main(["--address-bits", str(TINY_BITS)]) == 1
    assert "MISSED" in capsys.readouterr().out


@pytest.mark.slow
@pytest.mark.timeout(600)
def test_the_full_ram_meets_every_limit() -> None:
    """The real RAM, at its real size, is quick enough to build, load, read and write."""
    result = measure(RAM_ADDRESS_BITS)
    assert result["build_seconds"] < BUILD_LIMIT_SECONDS
    assert result["memory_mib"] < MEMORY_LIMIT_MIB
    assert result["load_seconds"] < LOAD_LIMIT_SECONDS
    assert result["read_seconds"] < ACCESS_LIMIT_SECONDS
    assert result["write_seconds"] < ACCESS_LIMIT_SECONDS
