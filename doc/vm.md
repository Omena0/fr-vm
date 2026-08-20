# Virtual Machine

## Overview

The FR-Kernel VM is a 32-bit register-based virtual machine. It executes bytecode produced by the SSA compiler and provides isolation between a privileged kernel context and unprivileged user processes.

## Architecture

### Word Size

All registers and memory operations use 32-bit words. The VM operates on little-endian data.

### Registers

- `r0` – `r15`: general-purpose 32-bit registers
- `PC`: program counter
- `SP`: stack pointer
- `FLAGS`: arithmetic flags (`Z`, `S`, `C`, `V`, `IE`)

### Memory

The VM has a flat 16 KB address space. The top of the address space is reserved for MMIO registers.

```
0x0000 ───────────────────────┐
                              │
                              │ process / kernel memory
                              │
                              │
MEM_SIZE - MMIO_SIZE ─────────┤
                              │ MMIO region
MEM_SIZE ─────────────────────┘
```

### Flags

| Flag | Meaning |
| --- | --- |
| `Z` | Zero result |
| `S` | Sign bit set |
| `C` | Carry / borrow |
| `V` | Signed overflow |
| `IE` | Interrupts enabled |

## Execution Model

The VM fetches, decodes, and executes one instruction at a time. Each instruction is encoded as an opcode byte followed by operand bytes. The operand layout varies by instruction.

Privileged instructions (`ENABLE_INT`, `DISABLE_INT`, `IRET`, and MMIO access from user mode) raise a privilege fault when executed outside PID 0.

## Processes and Contexts

Each process has an independent `Context` containing:

- `memory`: 16 KB bytearray
- `registers`: 16 general-purpose registers
- `pc`: program counter
- `sp`: stack pointer
- `flags`: arithmetic and interrupt flags
- `pid`: process ID

PID 0 is the kernel context. All other PIDs are user contexts.

Context switching is performed by the VM itself. The kernel never directly manipulates another process's registers or memory through the VM API.

## System Calls

User programs request kernel services via the `SYSCALL` instruction. The syscall number is passed as an immediate operand and indexes into a vector table whose base address is stored in the `SYSCALL_VECTOR_BASE` MMIO register.

On entry, the VM:

1. Copies all general-purpose registers from the user context into the kernel context (PID 0)
2. Saves the interrupted user context
3. Switches to the kernel context
4. Reads the handler address from `SYSCALL_VECTOR_BASE + syscall_number * 4` in kernel memory
5. Disables interrupts and jumps to the handler

Arguments are passed in registers `r0` – `r14` according to the ABI. The kernel returns to user mode with `IRET`, which copies the kernel's registers back into the user context (so return values propagate) and restores the saved user context.

## Interrupts

When an enabled interrupt occurs, the VM:

1. Checks that the current context is user mode (PID≠0) and that `IE` is set
2. Copies all general-purpose registers from the user context into the kernel context (PID 0)
3. Saves the interrupted user context
4. Switches to the kernel context and disables interrupts
5. Looks up the handler address from `INTERRUPT_VECTOR_BASE + vector_number * 4` in kernel memory
6. Jumps to the handler

The `vector_number` is derived from the lowest set bit of (`INTERRUPT_PENDING` & `INTERRUPT_MASK`). Each bit in those masks corresponds to an `Interrupt` enum value (`TIMER`, `KEYBOARD`, `CONSOLE`).

The kernel ends interrupt handling with `IRET`, which copies the kernel's registers back into the user context and restores the interrupted context.

## Stack

The stack grows downward. `SP` points to the current top of the stack. Standard function prologue/epilogue:

```text
PUSH r15
SUB_SP frame_size
LOAD_SP r15
...
ADD_SP frame_size
POP r15
RETURN
```

## 64-bit Values

The ISA is 32-bit. The compiler represents 64-bit values as pairs of 32-bit registers. Helper functions in user mode implement 64-bit arithmetic, comparison, and bitwise operations.

## Compilation Modes

The compiler supports two modes:

- **User mode** (default): emits position-independent code with numeric syscall IDs, string data labels, and helper functions for operations not covered by the ISA.
- **Kernel mode** (`--kernel`): emits `.entry main`, uses MMIO addresses directly for console I/O, and emits symbolic syscall names.
