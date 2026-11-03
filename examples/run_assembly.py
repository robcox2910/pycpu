"""Assemble a small program and run it on the fast engine.

Like writing a recipe in words, having a friend copy it onto numbered cards,
and handing the cards to a cook who follows them one by one: the assembler
makes the cards, the fast engine is the cook, and the output port is the plate.

Run this with: uv run python examples/run_assembly.py
"""

from pycpu.assembler import assemble
from pycpu.fast import FastMachine

WORDS = 64
RUN_LIMIT = 1_000

HELLO = """
    set r1, msg       ; r1 points at the first letter
    set r2, 0xFFFF    ; r2 holds the output port's address
next:
    load r3, [r1]     ; pick up one letter
    cmp r3, r0        ; is it the 0 that ends the message?
    br eq, done
    store r3, [r2]    ; send it to the screen
    addi r1, 1        ; move on to the next letter
    jmp next
done:
    halt
msg:
    .string "Hi"
"""


def main() -> None:
    """Assemble the hello program, run it, and show what it printed."""
    program = assemble(HELLO, words=WORDS)
    machine = FastMachine(WORDS)
    machine.load_program(program.words)
    steps = machine.run(RUN_LIMIT)
    state = machine.state()
    print(f"assembled {len(program.words)} words; the message starts at {program.labels['msg']}")
    print(f"ran {steps} instructions and halted with code {state.halt_code}")
    print(state.output_text)


if __name__ == "__main__":
    main()
