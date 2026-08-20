# MMIO Interface

Memory-mapped I/O occupies the top of the 16 KB address space.

```text
MMIO_BASE = MEM_SIZE - MMIO_SIZE
```

All registers are 8-bit unless otherwise noted. Multi-byte registers are little-endian.

## Address Map

| Device | Register | Offset | Size | Address |
| --- | --- | --- | --- | --- |
| Console | `CONSOLE_DATA` | 0x00 | 1 | `MMIO_BASE + 0x00` |
| Console | `CONSOLE_STATUS` | 0x01 | 1 | `MMIO_BASE + 0x01` |
| Console | `CONSOLE_CONTROL` | 0x02 | 1 | `MMIO_BASE + 0x02` |
| Keyboard | `KEYBOARD_DATA` | 0x03 | 1 | `MMIO_BASE + 0x03` |
| Keyboard | `KEYBOARD_STATUS` | 0x04 | 1 | `MMIO_BASE + 0x04` |
| Keyboard | `KEYBOARD_CONTROL` | 0x05 | 1 | `MMIO_BASE + 0x05` |
| Timer | `TIMER_VALUE` | 0x06 | 4 | `MMIO_BASE + 0x06` |
| Timer | `TIMER_RELOAD` | 0x0A | 4 | `MMIO_BASE + 0x0A` |
| Timer | `TIMER_CONTROL` | 0x0E | 1 | `MMIO_BASE + 0x0E` |
| Timer | `TIMER_STATUS` | 0x0F | 1 | `MMIO_BASE + 0x0F` |
| Interrupt Controller | `INTERRUPT_PENDING` | 0x10 | 4 | `MMIO_BASE + 0x10` |
| Interrupt Controller | `INTERRUPT_MASK` | 0x14 | 4 | `MMIO_BASE + 0x14` |
| Interrupt Controller | `INTERRUPT_EOI` | 0x18 | 1 | `MMIO_BASE + 0x18` |
| Interrupt Controller | `INTERRUPT_VECTOR_BASE` | 0x19 | 4 | `MMIO_BASE + 0x19` |
| Interrupt Controller | `INTERRUPT_STATUS` | 0x1D | 1 | `MMIO_BASE + 0x1D` |
| Interrupt Controller | `SYSCALL_VECTOR_BASE` | 0x1E | 4 | `MMIO_BASE + 0x1E` |
| System | `SYSTEM_VERSION` | 0x31 | 4 | `MMIO_BASE + 0x31` |
| System | `SYSTEM_MEMORY_SIZE` | 0x35 | 4 | `MMIO_BASE + 0x35` |
| System | `SYSTEM_CURRENT_PID` | 0x39 | 4 | `MMIO_BASE + 0x39` |
| System | `SYSTEM_PRIVILEGE` | 0x3D | 1 | `MMIO_BASE + 0x3D` |
| System | `SYSTEM_CONTROL` | 0x3E | 1 | `MMIO_BASE + 0x3E` |
| System | `SYSTEM_STATUS` | 0x3F | 1 | `MMIO_BASE + 0x3F` |

## Console

### `CONSOLE_DATA`

Write a byte here to output a character. Reads return `0` when the console is idle.

### `CONSOLE_STATUS`

| Value | Meaning |
| --- | --- |
| `0` | Idle |
| `1` | Ready |

### `CONSOLE_CONTROL`

| Value | Meaning |
| --- | --- |
| `0` | Normal operation |
| `1` | Clear screen |

## Keyboard

### `KEYBOARD_DATA`

Read a byte here to receive a character. Returns `0` when no key is available.

### `KEYBOARD_STATUS`

| Value | Meaning |
| --- | --- |
| `0` | No data available |
| `1` | Data available |

### `KEYBOARD_CONTROL`

| Value | Meaning |
| --- | --- |
| `0` | Normal operation |
| `1` | Clear buffer |

## Timer

### `TIMER_VALUE`

Current timer count (read).

### `TIMER_RELOAD`

Value to reload when the timer expires (write).

### `TIMER_CONTROL`

| Value | Meaning |
| --- | --- |
| `0` | Disabled |
| `1` | Enabled |

### `TIMER_STATUS`

| Value | Meaning |
| --- | --- |
| `0` | No event |
| `1` | Expired |

## Interrupt Controller

### `INTERRUPT_PENDING`

Bitmask of pending interrupts. Each bit corresponds to an `Interrupt` enum value.

### `INTERRUPT_MASK`

Bitmask of enabled interrupts.

### `INTERRUPT_EOI`

Write any value here to signal end-of-interrupt to the controller.

### `INTERRUPT_VECTOR_BASE`

Base address for the interrupt vector table.

### `INTERRUPT_STATUS`

| Value | Meaning |
| --- | --- |
| `0` | Idle |
| `1` | Active |

### `SYSCALL_VECTOR_BASE`

Base address for the syscall vector table in kernel memory. Each entry is a 4-byte handler address indexed by the syscall number passed to the `SYSCALL` instruction. When a syscall is invoked, the VM reads `base + syscall_number * 4` from kernel memory and transfers control to that address.

## System

### `SYSTEM_VERSION`

Kernel version number.

### `SYSTEM_MEMORY_SIZE`

Total memory size in bytes.

### `SYSTEM_CURRENT_PID`

Currently executing process ID.

### `SYSTEM_PRIVILEGE`

| Value | Meaning |
| --- | --- |
| `0` | User |
| `1` | Kernel |

### `SYSTEM_CONTROL`

| Value | Meaning |
| --- | --- |
| `0` | Normal |
| `1` | Reset |
| `2` | Shutdown |

### `SYSTEM_STATUS`

| Value | Meaning |
| --- | --- |
| `0` | Running |
| `1` | Halted |

## Accessing MMIO

The kernel accesses MMIO registers with `LOAD` and `STORE`. User programs cannot access MMIO directly; they must use `SYSCALL`.

Example kernel code to write a character to the console:

```text
LOAD_CONST r0, 16320      ; MMIO_BASE + CONSOLE_DATA.offset
LOAD_CONST r1, 72         ; 'H'
STORE r0, 0, r1
```

Example kernel code to read a character from the keyboard:

```text
LOAD_CONST r0, 16383      ; MMIO_BASE + KEYBOARD_DATA.offset
LOAD r1, r0, 0
```

## Extensions

Extensions are Python modules loaded from an `extensions/` directory (or a single `.py` file). Each extension exposes one or more functions that are mapped to dynamically-allocated MMIO addresses.

### Loading

Extensions are loaded by both the assembler and the VM from the same source directory or file:

```text
# Assembler
python3 src/assembler.py -e extensions/ kernel.asm kernel.bin

# VM
python3 src/vm.py -e extensions/ kernel.bin
```

The loader scans all `.py` files in the directory (alphabetically) and creates an MMIO register for each function argument and return value. Extension modules may define:

- **`returns`** — a set of function names that return values (used to allocate result addresses).
- **`constants`** — an optional dict of named constants surfaced to the assembler.

### MMIO Allocation

Each extension function is allocated MMIO registers according to its signature:

- **Arguments** — one 4-byte write address per parameter. Writing to the last
  argument's address triggers the function call with all accumulated arguments.
- **Return values** — one 4-byte read address is allocated for functions listed in
  `returns`. For zero-argument functions, reading this address triggers the call
  and returns the result. For functions with arguments, the result is stored after
  the last-argument write and can be read from the result address.

The extension MMIO region is reserved at the top of the MMIO space (after `HWRAND`).

### Constant Naming

Constants are available in assembly and named according to the convention:

```
f"{ext_name}_{func_name}"                          # single-arg or zero-arg+return
f"{ext_name}_{func_name}_{arg_name}"               # multi-arg
f"{ext_name}_{func_name}_RESULT"                   # return value (functions with args)
```

All upper-cased. For example, given `extensions/filesystem.py` with:

```python
returns = {"read", "size"}

def read(address: int):
    ...

def write(address: int, value: int):
    ...

def size():
    ...
```

The assembler constants are:

| Constant | Purpose |
| --- | --- |
| `FILESYSTEM_READ` | Write the address argument (triggers `read(address)`) |
| `FILESYSTEM_READ_RESULT` | Read the return value |
| `FILESYSTEM_WRITE_ADDRESS` | Write the `address` argument |
| `FILESYSTEM_WRITE_VALUE` | Write the `value` argument (triggers `write(address, value)`) |
| `FILESYSTEM_SIZE` | Read to trigger `size()` and get the result |
