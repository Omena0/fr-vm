# Instruction Encoding

## Overview

Each instruction is encoded as a single-byte opcode followed by operand fields. The operand layout varies per instruction. All multi-byte values are little-endian.

```text
[ opcode ] [ operand 0 ] [ operand 1 ] ...
```

The total instruction size is:

```text
size = 1 + sum(operand sizes)
```

## Operand Types

| Operand Type | Size | Description |
| --- | --- | --- |
| `REGISTER` | 1 | General-purpose register index (`0`–`15`) |
| `IMMEDIATE8` | 1 | Unsigned 8-bit immediate |
| `IMMEDIATE16` | 2 | Unsigned 16-bit immediate |
| `IMMEDIATE32` | 4 | Unsigned 32-bit immediate |
| `IMMEDIATE64` | 8 | Unsigned 64-bit immediate |
| `ADDRESS8` | 1 | 8-bit absolute address |
| `ADDRESS16` | 2 | 16-bit absolute address |
| `ADDRESS32` | 4 | 32-bit absolute address |
| `ADDRESS64` | 8 | 64-bit absolute address |
| `OFFSET8` | 1 | 8-bit signed offset |
| `OFFSET16` | 2 | 16-bit signed offset |
| `OFFSET32` | 4 | 32-bit signed offset |
| `OFFSET64` | 8 | 64-bit signed offset |
| `SYSCALL` | 4 | Syscall identifier |

## Encoding

### Data Movement

#### `LOAD` — `0x00`

```text
opcode (1 byte)
destination register (1 byte)
base register (1 byte)
offset (4 bytes, signed)
```

Total: 7 bytes

---

#### `STORE` — `0x01`

```text
opcode (1 byte)
base register (1 byte)
offset (4 bytes, signed)
source register (1 byte)
```

Total: 7 bytes

---

#### `LOAD_CONST` — `0x02`

```text
opcode (1 byte)
destination register (1 byte)
immediate (4 bytes, unsigned)
```

Total: 6 bytes

---

#### `MOVE` — `0x03`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
```

Total: 3 bytes

---

### Integer Arithmetic

#### `ADD` — `0x10`

```text
opcode (1 byte)
destination register (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 4 bytes

---

#### `SUB` — `0x11`

```text
opcode (1 byte)
destination register (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 4 bytes

---

#### `MUL` — `0x12`

```text
opcode (1 byte)
destination register (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 4 bytes

---

#### `DIV` — `0x13`

```text
opcode (1 byte)
destination register (1 byte)
dividend register (1 byte)
divisor register (1 byte)
```

Total: 4 bytes

---

#### `MOD` — `0x14`

```text
opcode (1 byte)
destination register (1 byte)
dividend register (1 byte)
divisor register (1 byte)
```

Total: 4 bytes

---

#### `NEG` — `0x15`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
```

Total: 3 bytes

---

#### `ADDI` — `0x16`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
immediate (4 bytes, signed)
```

Total: 7 bytes

---

### Bitwise Operations

#### `AND` — `0x20`

```text
opcode (1 byte)
destination register (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 4 bytes

---

#### `OR` — `0x21`

```text
opcode (1 byte)
destination register (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 4 bytes

---

#### `XOR` — `0x22`

```text
opcode (1 byte)
destination register (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 4 bytes

---

#### `NOT` — `0x23`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
```

Total: 3 bytes

---

#### `SHL` — `0x24`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
amount register (1 byte)
```

Total: 4 bytes

---

#### `SHR` — `0x25`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
amount register (1 byte)
```

Total: 4 bytes

---

#### `SAR` — `0x26`

```text
opcode (1 byte)
destination register (1 byte)
source register (1 byte)
amount register (1 byte)
```

Total: 4 bytes

---

### Comparison

All comparison instructions set flags (`Z`, `S`, `C`, `V`) based on the comparison. They do not write a destination register.

#### `CMP_EQ` — `0x30`

```text
opcode (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 3 bytes

---

#### `CMP_NE` — `0x31`

```text
opcode (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 3 bytes

---

#### `CMP_LT` — `0x32`

```text
opcode (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 3 bytes

---

#### `CMP_LE` — `0x33`

```text
opcode (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 3 bytes

---

#### `CMP_GT` — `0x34`

```text
opcode (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 3 bytes

---

#### `CMP_GE` — `0x35`

```text
opcode (1 byte)
left register (1 byte)
right register (1 byte)
```

Total: 3 bytes

---

### Control Flow

#### `JUMP` — `0x40`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JZ` — `0x41`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JNZ` — `0x42`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JC` — `0x43`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JNC` — `0x44`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JS` — `0x45`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JNS` — `0x46`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JO` — `0x47`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `JNO` — `0x48`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `CALL` — `0x49`

```text
opcode (1 byte)
target address (4 bytes)
```

Total: 5 bytes

---

#### `RETURN` — `0x4A`

```text
opcode (1 byte)
```

Total: 1 byte

---

### Stack

#### `PUSH` — `0x50`

```text
opcode (1 byte)
source register (1 byte)
```

Total: 2 bytes

---

#### `POP` — `0x51`

```text
opcode (1 byte)
destination register (1 byte)
```

Total: 2 bytes

---

#### `LOAD_SP` — `0x52`

```text
opcode (1 byte)
destination register (1 byte)
```

Total: 2 bytes

---

#### `STORE_SP` — `0x53`

```text
opcode (1 byte)
source register (1 byte)
```

Total: 2 bytes

---

#### `ADD_SP` — `0x54`

```text
opcode (1 byte)
immediate (4 bytes, signed)
```

Total: 5 bytes

---

#### `SUB_SP` — `0x55`

```text
opcode (1 byte)
immediate (4 bytes, signed)
```

Total: 5 bytes

---

### System / Privilege

#### `SYSCALL` — `0x70`

```text
opcode (1 byte)
syscall id (4 bytes)
```

Total: 5 bytes

---

#### `HALT` — `0x71`

```text
opcode (1 byte)
```

Total: 1 byte

---

#### `ENABLE_INT` — `0x72`

```text
opcode (1 byte)
```

Total: 1 byte

---

#### `DISABLE_INT` — `0x73`

```text
opcode (1 byte)
```

Total: 1 byte

---

#### `BREAK` — `0x74`

```text
opcode (1 byte)
```

Total: 1 byte

---

#### `NOP` — `0x75`

```text
opcode (1 byte)
```

Total: 1 byte

---

## Opcode Map

| Opcode | Instruction |
| --- | --- |
| `0x00` | `LOAD` |
| `0x01` | `STORE` |
| `0x02` | `LOAD_CONST` |
| `0x03` | `MOVE` |
| `0x10` | `ADD` |
| `0x11` | `SUB` |
| `0x12` | `MUL` |
| `0x13` | `DIV` |
| `0x14` | `MOD` |
| `0x15` | `NEG` |
| `0x16` | `ADDI` |
| `0x20` | `AND` |
| `0x21` | `OR` |
| `0x22` | `XOR` |
| `0x23` | `NOT` |
| `0x24` | `SHL` |
| `0x25` | `SHR` |
| `0x26` | `SAR` |
| `0x30` | `CMP_EQ` |
| `0x31` | `CMP_NE` |
| `0x32` | `CMP_LT` |
| `0x33` | `CMP_LE` |
| `0x34` | `CMP_GT` |
| `0x35` | `CMP_GE` |
| `0x40` | `JUMP` |
| `0x41` | `JZ` |
| `0x42` | `JNZ` |
| `0x43` | `JC` |
| `0x44` | `JNC` |
| `0x45` | `JS` |
| `0x46` | `JNS` |
| `0x47` | `JO` |
| `0x48` | `JNO` |
| `0x49` | `CALL` |
| `0x4A` | `RETURN` |
| `0x50` | `PUSH` |
| `0x51` | `POP` |
| `0x52` | `LOAD_SP` |
| `0x53` | `STORE_SP` |
| `0x54` | `ADD_SP` |
| `0x55` | `SUB_SP` |
| `0x60` | `LOAD_BYTE` |
| `0x61` | `STORE_BYTE` |
| `0x62` | `LOAD_WORD` |
| `0x63` | `STORE_WORD` |
| `0x64` | `LOAD_DWORD` |
| `0x65` | `STORE_DWORD` |
| `0x66` | `LOAD_QWORD` |
| `0x67` | `STORE_QWORD` |
| `0x70` | `SYSCALL` |
| `0x71` | `HALT` |
| `0x72` | `ENABLE_INT` |
| `0x73` | `DISABLE_INT` |
| `0x74` | `BREAK` |
| `0x75` | `NOP` |
