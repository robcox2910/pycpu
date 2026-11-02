"""PyCPU: a computer built from nothing but NAND gates.

Imagine a giant machine made of Lego. Every clever thing it does, from adding
numbers to running a program, is made by snapping together tiny identical bricks.
In PyCPU the one brick is the NAND gate, a switch that is on unless both of its
inputs are on. Gates become adders, adders become an ALU, and memory and a
processor come after that, each layer built only from the one below it.

This package is the start of that climb. Nothing here is faked: when a later layer
claims to add two numbers, it will do it with real gates.
"""
