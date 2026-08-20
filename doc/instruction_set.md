# VM Instruction Set

## Registers

The VM has 16 general-purpose 32-bit registers, `r0` through `r15`.

The architecture also has three special registers:

- `PC` — program counter
- `SP` — stack pointer
- `FLAGS` — arithmetic and control flags

### Flags

| Flag | Meaning |
| --- | --- |
| `Z` | Result is zero |
| `S` | Result has the sign bit set |
| `C` | Carry / borrow |
| `V` | Signed overflow |
| `IE` | Interrupts enabled |

Arithmetic and comparison instructions update `Z`, `S`, `C`, and `V` as appropriate.

`IE` is controlled by `ENABLE_INT` and `DISABLE_INT` and is only accessible to privileged code.

---

## Data Movement

### `LOAD_CONST`

Load an immediate value into a register.

```text
LOAD_CONST destination, immediate
```

Example:

```text
LOAD_CONST r0, 1000
```

The immediate is truncated to 32 bits.

---

### `MOVE`

Copy a register value.

```text
MOVE destination, source
```

Example:

```text
MOVE r1, r0
```

---

### `LOAD`

Load a word from memory.

```text
LOAD destination, base, offset
```

Effective address:

```text
address = base + offset
```

Example:

```text
LOAD r0, r1, 8
```

---

### `STORE`

Store a word to memory.

```text
STORE base, offset, source
```

Effective address:

```text
address = base + offset
```

Example:

```text
STORE r1, 8, r0
```

---

## Stack

The stack grows downward. `SP` points to the current top of the stack.

### `PUSH`

Push a word onto the stack.

```text
PUSH source
```

Equivalent conceptually to:

```text
SP = SP - 4
STORE SP, 0, source
```

---

### `POP`

Pop a word from the stack.

```text
POP destination
```

Equivalent conceptually to:

```text
LOAD destination, SP, 0
SP = SP + 4
```

---

### `LOAD_SP`

Copy the stack pointer into a register.

```text
LOAD_SP destination
```

---

### `STORE_SP`

Copy a register value into the stack pointer.

```text
STORE_SP source
```

---

### `ADD_SP`

Add an immediate to the stack pointer.

```text
ADD_SP immediate
```

Equivalent to `SP = SP + immediate`.

---

### `SUB_SP`

Subtract an immediate from the stack pointer.

```text
SUB_SP immediate
```

Equivalent to `SP = SP - immediate`.

---

## Integer Arithmetic

All integer arithmetic operates on the VM's native 32-bit word size.

### `ADD`

Add two registers.

```text
ADD destination, left, right
```

Updates arithmetic flags.

---

### `ADDI`

Add an immediate value.

```text
ADDI destination, source, immediate
```

Updates arithmetic flags.

---

### `SUB`

Subtract two registers.

```text
SUB destination, left, right
```

Updates arithmetic flags.

---

### `MUL`

Multiply two registers.

```text
MUL destination, left, right
```

The result is truncated to the native word size.

---

### `DIV`

Signed integer division.

```text
DIV destination, dividend, divisor
```

Division by zero raises a VM fault.

---

### `MOD`

Signed integer remainder.

```text
MOD destination, dividend, divisor
```

Division by zero raises a VM fault.

---

### `NEG`

Negate a value.

```text
NEG destination, source
```

```text
destination = -source
```

---

## Bitwise Operations

### `AND`

Bitwise AND.

```text
AND destination, left, right
```

---

### `OR`

Bitwise OR.

```text
OR destination, left, right
```

---

### `XOR`

Bitwise XOR.

```text
XOR destination, left, right
```

---

### `NOT`

Bitwise inversion.

```text
NOT destination, source
```

---

### `SHL`

Logical left shift.

```text
SHL destination, source, amount
```

---

### `SHR`

Logical right shift.

```text
SHR destination, source, amount
```

---

### `SAR`

Arithmetic right shift.

```text
SAR destination, source, amount
```

The sign bit is preserved.

---

## Comparison

All comparison instructions set the arithmetic flags (`Z`, `S`, `C`, `V`) based on the result of comparing the two register operands. They do not write a destination register.

### `CMP_EQ`

Set flags if `left == right`.

```text
CMP_EQ left, right
```

---

### `CMP_NE`

Set flags if `left != right`.

```text
CMP_NE left, right
```

---

### `CMP_LT`

Set flags if `left < right` (signed).

```text
CMP_LT left, right
```

---

### `CMP_LE`

Set flags if `left <= right` (signed).

```text
CMP_LE left, right
```

---

### `CMP_GT`

Set flags if `left > right` (signed).

```text
CMP_GT left, right
```

---

### `CMP_GE`

Set flags if `left >= right` (signed).

```text
CMP_GE left, right
```

---

## Control Flow

### `JUMP`

Jump to an address.

```text
JUMP target
```

---

### `JZ`

Jump if the zero flag is set.

```text
JZ target
```

---

### `JNZ`

Jump if the zero flag is clear.

```text
JNZ target
```

---

### `JC`

Jump if the carry flag is set.

```text
JC target
```

---

### `JNC`

Jump if the carry flag is clear.

```text
JNC target
```

---

### `JS`

Jump if the sign flag is set.

```text
JS target
```

---

### `JNS`

Jump if the sign flag is clear.

```text
JNS target
```

---

### `JO`

Jump if signed overflow occurred.

```text
JO target
```

---

### `JNO`

Jump if signed overflow did not occur.

```text
JNO target
```

---

### `CALL`

Call a function.

```text
CALL target
```

The return address is pushed onto the stack before transferring control.

---

### `RETURN`

Return from a function.

```text
RETURN
```

The return address is popped from the stack and loaded into `PC`.

---

## System Calls

### `SYSCALL`

Request a kernel service.

```text
SYSCALL syscall_id
```

In user mode, `syscall_id` is a numeric constant. In kernel mode, it may be a symbolic syscall name.

When executed from user mode, the VM:

1. Copies all general-purpose registers from the user context into the kernel context (PID 0)
2. Saves the interrupted user context
3. Switches to the kernel context
4. Reads the handler address from `SYSCALL_VECTOR_BASE + syscall_id * 4` in kernel memory
5. Disables further interrupts (`IE = 0`) and jumps to the handler

Arguments are passed in registers `r0` – `r14` according to the ABI. The return value is passed back in `r0`. The kernel returns to user mode with `IRET`, which copies the kernel's registers back into the user context (so return values propagate) and restores the saved user context.

User code cannot directly access kernel memory or MMIO.

---

### `IRET`

Return from syscall or interrupt handler.

```text
IRET
```

Copies the kernel context's registers back into the interrupted user context, restores the user context (switches back to the saved PID), and re-enables interrupt delivery. The kernel's syscall/interrupt handler must execute `IRET` to return to user mode.

---

### `MOVE`

Copy a register value.

```text
MOVE destination, source
```

---

## Privilege Control

### `ENABLE_INT`

Enable interrupts.

```text
ENABLE_INT
```

Privileged. Sets `IE = 1`.

---

### `DISABLE_INT`

Disable interrupts.

```text
DISABLE_INT
```

Privileged. Sets `IE = 0`.

---

## Execution

### `NOP`

Do nothing.

```text
NOP
```

---

### `HALT`

Stop execution of the current VM.

```text
HALT
```

---

### `BREAK`

Raise a debug/trap exception.

```text
BREAK
```

---

## Faults

The VM can generate hardware faults independently of the instruction set.

Examples include:

```text
INVALID_INSTRUCTION
PRIVILEGE_VIOLATION
MEMORY_FAULT
EXECUTE_FAULT
DIVIDE_BY_ZERO
INVALID_REGISTER
STACK_FAULT
```

Faults cause the same kind of context transition as interrupts.

---

## Assembly Syntax

The assembler accepts the following pseudo-directives:

```text
.entry main
```

Marks the program entry point. Only valid in kernel mode.

```text
label: string "Hello, World!"
```

Emits a null-terminated string constant at the given label.

Comments start with `;` and continue to the end of the line.

Memory operands use three separate operands instead of bracketed expressions:

```text
LOAD r0, r1, 8
STORE r1, 8, r0
```

Labels may be used as immediate values:

```text
LOAD_CONST r0, my_label
```
