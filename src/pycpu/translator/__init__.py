"""The translator: a phrasebook that turns Pebble sentences into PyCPU machine talk.

Imagine a traveller who speaks Pebble and has to talk to a computer that only knows
adding, shifting and jumping. The traveller needs a phrasebook, and also a few
ready-made phrases for things the computer cannot say in one word, like "multiply".
This package is both. `translate` looks up every Pebble instruction and writes the
PyCPU assembly for it (`subset.py` checks the program first, `codegen.py` writes the
assembly), and `run_pebble` runs the result on the fast engine. The ready-made
phrases, the multiply, divide and print routines, live in `runtime.py`.
"""

from pycpu.translator.codegen import FrameLayout, Slot
from pycpu.translator.program import PebbleRun, TranslatedProgram, run_pebble, translate
from pycpu.translator.runtime import RUNTIME, RUNTIME_STACK_WORDS
from pycpu.translator.subset import PebbleCPUError, UnsupportedFeature

__all__ = [
    "RUNTIME",
    "RUNTIME_STACK_WORDS",
    "FrameLayout",
    "PebbleCPUError",
    "PebbleRun",
    "Slot",
    "TranslatedProgram",
    "UnsupportedFeature",
    "run_pebble",
    "translate",
]
