"""The translator: a phrasebook that turns Pebble sentences into PyCPU machine talk.

Imagine a traveller who speaks Pebble and has to talk to a computer that only knows
adding, shifting and jumping. The traveller needs a phrasebook, and also a few
ready-made phrases for things the computer cannot say in one word, like "multiply".
This package is that phrasebook. For now it holds only the ready-made phrases, the
multiply, divide and print routines in `runtime.py`, written in PyCPU assembly.
"""

from pycpu.translator.runtime import RUNTIME, RUNTIME_STACK_WORDS

__all__ = ["RUNTIME", "RUNTIME_STACK_WORDS"]
