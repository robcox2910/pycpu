"""The runtime: a drawer of ready-made recipes the translated program can call.

Imagine a kitchen with a card that says "to whisk eggs, do these twelve steps". Every
recipe that needs whisked eggs just says "whisk (see card)" instead of repeating the
twelve steps. The CPU has no multiply or divide instruction, so these cards are the
twelve steps: `__mul` multiplies by shifting and adding, and `__divmod` divides by
shifting and subtracting. A second pair of cards, `__print_int` and `__print_text`, post
characters one at a time through the output port, like a cash register with a slot for
one letter, so a number is broken into digits first. They are plain PyCPU assembly text
in `RUNTIME`, to be pasted after any program's code, so they run on the machine like
everything else and the Bench can show them.

The calling rules: put the inputs in `r1` and `r2` (`__print_int` and `__print_text`
take just `r1`), `call` the routine, and find the answer in `r1` (and `r2`). `r0`
(always 0) and `r7` (the frame pointer) are never changed; `r1` to `r6` may be. Every
label starts with two underscores, so it can never clash with a label a translator
generates.
"""

# The deepest case is __print_int on a 5-digit negative number: 1 word for its return
# address, 1 for the sentinel, 4 digits already waiting while the 5th is being worked
# out, 1 for the return address of the `call __divmod`, and 2 pushes inside __divmod.
# A test measures the real deepest use of every routine and checks this number.
RUNTIME_STACK_WORDS = 9

RUNTIME = """
; ---------------------------------------------------------------------------
; __mul: r1 = (r1 * r2) mod 65536, by shift and add (long multiplication).
; Uses r3 (the running total), r4 (the constant 1), r5 (scratch).
; ---------------------------------------------------------------------------
__mul:
    li   r3, 0              ; total = 0: nothing added up yet
    li   r4, 1              ; r4 = 1, so we can pick out the lowest bit of r2
__mul_loop:
    cmp  r2, r0             ; is the bottom number used up (all zero bits left)?
    br   eq, __mul_done     ; yes: the total is the answer
    and  r5, r2, r4         ; r5 = the lowest bit of r2: 1 means "add a row"
    br   eq, __mul_skip     ; the bit was 0: this row is nothing, skip the add
    add  r3, r3, r1         ; the bit was 1: add the (shifted) top number to the total
__mul_skip:
    shl  r1, r1             ; slide the top number one place left (double it)
    shr  r2, r2             ; move on to the next bit of the bottom number
    jmp  __mul_loop         ; and do the next row
__mul_done:
    mov  r1, r3             ; hand the total back in r1
    ret                     ; return to whoever called us

; ---------------------------------------------------------------------------
; __divmod: r1 = floor(r1 / r2), r2 = r1 - r2 * floor(r1 / r2), signed 16-bit.
; The caller never passes r2 = 0. Uses r3 to r6, and 2 words of stack.
; Plan: divide the sizes (ignoring signs) by long division, then fix the signs.
; ---------------------------------------------------------------------------
__divmod:
    push r1                 ; keep the original top number (we need its sign later)
    push r2                 ; keep the original divisor too
    cmp  r1, r0             ; is the top number negative?
    br   ge, __divmod_a     ; no: leave it alone
    sub  r1, r0, r1         ; yes: r1 = 0 - r1, its size without the minus sign
__divmod_a:
    cmp  r2, r0             ; is the divisor negative?
    br   ge, __divmod_b     ; no: leave it alone
    sub  r2, r0, r2         ; yes: take its size too
__divmod_b:
    li   r4, 0              ; r4 = the leftover so far (the remainder), starts at 0
    li   r5, 0              ; r5 = the answer so far (the quotient), starts at 0
    li   r6, 16             ; r6 = bits still to do: one round for each of 16 bits
__divmod_loop:
    shl  r4, r4             ; make room at the bottom of the leftover
    shl  r1, r1             ; slide out the top bit of the number: it lands in carry
    br   ltu, __divmod_nobit ; carry is 0: the bit was 0, nothing to bring down
    addi r4, 1              ; the bit was 1: bring it down into the leftover
__divmod_nobit:
    shl  r5, r5             ; make room for a new bit of the answer
    cmp  r4, r2             ; does the divisor fit into the leftover?
    br   ltu, __divmod_nofit ; no (leftover < divisor): answer bit stays 0
    sub  r4, r4, r2         ; yes: take one divisor out of the leftover
    addi r5, 1              ; and write a 1 in the answer
__divmod_nofit:
    addi r6, -1             ; one bit done
    br   ne, __divmod_loop  ; more bits left: go round again
    pop  r2                 ; get the original divisor back
    pop  r1                 ; get the original top number back
    xor  r3, r1, r2         ; r3 is negative exactly when the two signs differ
    cmp  r1, r0             ; was the top number negative?
    br   ge, __divmod_rem   ; no: the leftover stays positive
    sub  r4, r0, r4         ; yes: the leftover takes the top number's sign
__divmod_rem:
    cmp  r3, r0             ; do the signs differ?
    br   ge, __divmod_done  ; no: the answer is already right
    sub  r5, r0, r5         ; yes: the answer is negative
    cmp  r4, r0             ; was there a leftover?
    br   eq, __divmod_done  ; no: it divided exactly, nothing to fix
    addi r5, -1             ; yes: floor rounds down, one step further from zero
    add  r4, r4, r2         ; and the leftover moves to the divisor's side of 0
__divmod_done:
    mov  r1, r5             ; the quotient goes back in r1
    mov  r2, r4             ; the remainder goes back in r2
    ret                     ; return to whoever called us

; ---------------------------------------------------------------------------
; __print_int: print r1 as a signed decimal number, then a newline ("\\n").
; Divides by ten again and again with __divmod; each remainder is the next digit,
; found last digit first, so the digits wait on the stack and come back reversed.
; Uses r1 to r6, and up to 9 words of stack, counting its return address.
; ---------------------------------------------------------------------------
__print_int:
    push r0                 ; sentinel: a 0 on the stack marks "no more digits"
    cmp  r1, r0             ; is the number negative?
    br   ge, __print_int_digits ; no: go straight to the digits loop
    li   r3, '-'            ; yes: first print the minus sign
    li   r6, 0              ; r6 = 0 ...
    addi r6, -1             ; ... minus 1 = 0xFFFF, the address of the output port
    store r3, [r6]          ; post the '-' card through the slot
    li   r2, 10             ; divide the negative number itself by ten (floor division)
    call __divmod           ; r1 = quotient (rounded down), r2 = remainder (0 to 9)
    cmp  r2, r0             ; was it an exact multiple of ten?
    br   eq, __print_int_exact ; yes: last digit is 0 and the quotient is right already
    li   r3, 10             ; no: rounding down went one step too far, so
    sub  r2, r3, r2         ; the last digit of the size is 10 - remainder
    addi r1, 1              ; and the quotient steps back one
__print_int_exact:
    sub  r1, r0, r1         ; r1 = the rest of the number, now without its minus sign
    addi r2, 48             ; digit + 48 = the character code of that digit
    push r2                 ; keep it on the stack for later
    cmp  r1, r0             ; is there anything left to print?
    br   eq, __print_int_out ; no: a one-digit number, go and print what we have
__print_int_digits:
    li   r2, 10             ; divide by ten ...
    call __divmod           ; ... r1 = what is left, r2 = the last digit (0 to 9)
    addi r2, 48             ; digit + 48 = the character code of that digit
    push r2                 ; stack it: last digit goes in first, so it comes out last
    cmp  r1, r0             ; has the number run out?
    br   ne, __print_int_digits ; no: peel off the next digit (a 0 still prints once)
__print_int_out:
    li   r6, 0              ; r6 = 0 ...
    addi r6, -1             ; ... minus 1 = 0xFFFF, the output port
__print_int_pop:
    pop  r3                 ; take the top card: the leftmost digit not yet printed
    cmp  r3, r0             ; is it the sentinel 0?
    br   eq, __print_int_end ; yes: every digit is out
    store r3, [r6]          ; no: post it through the output port
    jmp  __print_int_pop    ; and take the next card
__print_int_end:
    li   r3, 10             ; 10 is the character code of a newline
    store r3, [r6]          ; post the newline
    ret                     ; return to whoever called us

; ---------------------------------------------------------------------------
; __print_text: print the 0-terminated words starting at address r1, then a newline.
; Uses r1 (stepped along the text), r3 and r6. No stack beyond the return address.
; ---------------------------------------------------------------------------
__print_text:
    li   r6, 0              ; r6 = 0 ...
    addi r6, -1             ; ... minus 1 = 0xFFFF, the output port
__print_text_loop:
    load r3, [r1]           ; r3 = the next character code of the text
    cmp  r3, r0             ; is it the 0 that ends the text?
    br   eq, __print_text_end ; yes: stop
    store r3, [r6]          ; no: post it through the output port
    addi r1, 1              ; step on to the next character
    jmp  __print_text_loop  ; and go round again
__print_text_end:
    li   r3, 10             ; 10 is the character code of a newline
    store r3, [r6]          ; post the newline
    ret                     ; return to whoever called us
"""
