import re
import sys
from dataclasses import dataclass

from encoding import (
    INSTRUCTIONS,
    OperandType,
    encode_instruction,
    operand_size,
)

from mmio import *
from arch import *


REGISTER_RE = re.compile(r"^(?:r|reg)(\d+)$", re.IGNORECASE)
NUMBER_RE = re.compile(
    r"^[+-]?(?:"
    r"0[xX][0-9a-fA-F]+|"
    r"0[bB][01]+|"
    r"0[oO][0-7]+|"
    r"\d+"
    r")$"
)

MEMORY_INSTRUCTIONS = {
    "LOAD",
    "STORE",
    "LOAD_BYTE",
    "STORE_BYTE",
    "LOAD_WORD",
    "STORE_WORD",
    "LOAD_DWORD",
    "STORE_DWORD",
    "LOAD_QWORD",
    "STORE_QWORD",
}

BRANCH_INSTRUCTIONS = {
    "JUMP",
    "JZ",
    "JNZ",
    "JC",
    "JNC",
    "JS",
    "JNS",
    "JO",
    "JNO",
    "CALL",
}


@dataclass(slots=True)
class ParsedInstruction:
    line: int
    name: str
    operands: list[str]
    location: int = 0


class AssemblerError(Exception):
    pass


def parse_number(value: str) -> int | None:
    value = value.strip()

    if not NUMBER_RE.fullmatch(value):
        return None

    try:
        return int(value, 0)
    except ValueError:
        return None


def parse_register(value: str) -> int | None:
    match = REGISTER_RE.fullmatch(value.strip())

    if not match:
        return None

    register = int(match.group(1))

    if not 0 <= register < 16:
        raise AssemblerError(
            f"invalid register: {value}"
        )

    return register


def split_operands(text: str) -> list[str]:
    operands = []
    current = []
    bracket_depth = 0

    for char in text:
        if char == "[":
            bracket_depth += 1

        elif char == "]":
            bracket_depth -= 1

            if bracket_depth < 0:
                raise AssemblerError("unexpected ']'")

        if char == "," and bracket_depth == 0:
            operand = "".join(current).strip()

            if operand:
                operands.append(operand)

            current = []
        else:
            current.append(char)

    if bracket_depth != 0:
        raise AssemblerError("unclosed '['")

    operand = "".join(current).strip()

    if operand:
        operands.append(operand)

    return operands


def parse_memory_operand(
    operand: str,
) -> tuple[str, str]:
    operand = operand.strip()

    if not (
        operand.startswith("[")
        and operand.endswith("]")
    ):
        raise AssemblerError(
            f"expected memory operand, got: {operand}"
        )

    expression = operand[1:-1].strip()

    match = re.fullmatch(
        r"(.+?)(?:\s*([+-])\s*(.+))?",
        expression,
    )

    if not match:
        raise AssemblerError(
            f"invalid memory operand: {operand}"
        )

    base = match.group(1).strip()
    sign = match.group(2)
    offset = match.group(3)

    if sign is None:
        return base, "0"

    offset = offset.strip()

    if sign == "-":
        if offset.startswith("-"):
            raise AssemblerError(
                f"invalid memory operand: {operand}"
            )

        offset = "-" + offset

    return base, offset


def strip_comment(line: str) -> str:
    in_string = False
    escaped = False

    for index, char in enumerate(line):
        if char == '"' and not escaped:
            in_string = not in_string

        if char in ("#", ";") and not in_string:
            return line[:index]

        escaped = char == "\\" and not escaped

        if char != "\\":
            escaped = False

    return line


class Assembler:
    def __init__(self, extension_constants: dict[str, int] | None = None):
        self.labels: dict[str, int] = {}
        self.instructions: list[ParsedInstruction] = []
        self.data: dict[int, bytes] = {}
        self.location = 0
        self._extension_constants = extension_constants or {}

    @staticmethod
    def _builtin_constants() -> dict[str, int]:
        return {
            "MEM_SIZE": MEM_SIZE,
            "REG_COUNT": REG_COUNT,
            "PC_INIT": PC_INIT,
            "SP_INIT": SP_INIT,
            "WORD_BITS": WORD_BITS,
            "WORD_SIZE": WORD_SIZE,
            "WORD_MAX": WORD_MAX,
            "IE": IE,
            "OPCODE_BITS": OPCODE_BITS,
            "OPCODE_SIZE": OPCODE_SIZE,
            "OPCODE_MAX": OPCODE_MAX,
            "MMIO_BASE": MMIO_BASE,
            "MMIO_SIZE": MMIO_SIZE,
            "MMIO_END": MMIO_END,
            "CONSOLE_DATA": CONSOLE_DATA.address,
            "CONSOLE_STATUS": CONSOLE_STATUS.address,
            "CONSOLE_CONTROL": CONSOLE_CONTROL.address,
            "KEYBOARD_DATA": KEYBOARD_DATA.address,
            "KEYBOARD_STATUS": KEYBOARD_STATUS.address,
            "KEYBOARD_CONTROL": KEYBOARD_CONTROL.address,
            "TIMER_VALUE": TIMER_VALUE.address,
            "TIMER_RELOAD": TIMER_RELOAD.address,
            "TIMER_CONTROL": TIMER_CONTROL.address,
            "TIMER_STATUS": TIMER_STATUS.address,
            "INTERRUPT_PENDING": INTERRUPT_PENDING.address,
            "INTERRUPT_MASK": INTERRUPT_MASK.address,
            "INTERRUPT_EOI": INTERRUPT_EOI.address,
            "INTERRUPT_VECTOR_BASE": INTERRUPT_VECTOR_BASE.address,
            "INTERRUPT_STATUS": INTERRUPT_STATUS.address,
            "SYSCALL_VECTOR_BASE": SYSCALL_VECTOR_BASE.address,
            "PROC_CREATE": PROC_CREATE.address,
            "PROC_CREATED": PROC_CREATED.address,
            "PROC_DELETE": PROC_DELETE.address,
            "PROC_SWITCH": PROC_SWITCH.address,
            "PROC_TARGET_PID": PROC_TARGET_PID.address,
            "PROC_REG_INDEX": PROC_REG_INDEX.address,
            "PROC_REG_VALUE": PROC_REG_VALUE.address,
            "PROC_SP": PROC_SP.address,
            "PROC_PC": PROC_PC.address,
            "PROC_FLAGS": PROC_FLAGS.address,
            "PROC_MEM_ADDR": PROC_MEM_ADDR.address,
            "PROC_MEM_BYTE": PROC_MEM_BYTE.address,
            "PROC_MEM_WORD": PROC_MEM_WORD.address,
            "SYSTEM_VERSION": SYSTEM_VERSION.address,
            "SYSTEM_MEMORY_SIZE": SYSTEM_MEMORY_SIZE.address,
            "SYSTEM_CURRENT_PID": SYSTEM_CURRENT_PID.address,
            "SYSTEM_PRIVILEGE": SYSTEM_PRIVILEGE.address,
            "SYSTEM_CONTROL": SYSTEM_CONTROL.address,
            "SYSTEM_STATUS": SYSTEM_STATUS.address,
            "HWRAND": HWRAND.address,
            "INTERRUPT_TIMER": Interrupt.TIMER.value,
            "INTERRUPT_KEYBOARD": Interrupt.KEYBOARD.value,
            "INTERRUPT_CONSOLE": Interrupt.CONSOLE.value,
            "HWRAND_SIZE": HWRAND.size,
        }

    def _preprocess(self, source: str, base_path: str = "") -> str:
        defines: dict[str, str] = {}
        imported: set[str] = set()
        lines = source.splitlines()

        def resolve_imports(path: str, seen: set[str]) -> str:
            if path in seen:
                raise AssemblerError(
                    f"circular import detected: {path}"
                )

            seen.add(path)

            with open(path, "r", encoding="utf-8") as file:
                content = file.read()

            result = []
            for raw_line in content.splitlines():
                stripped = raw_line.strip()

                if stripped.startswith("#import "):
                    parts = stripped.split(None, 2)
                    if len(parts) < 2:
                        raise AssemblerError(
                            f"#import expects a file path"
                        )

                    import_path = parts[1].strip("\"'")

                    if not import_path.endswith(".asm"):
                        import_path += ".asm"

                    if not import_path.startswith("/"):
                        import_path = (
                            f"{path.rsplit('/', 1)[0]}/{import_path}"
                            if "/" in path
                            else import_path
                        )

                    result.append(
                        resolve_imports(import_path, seen)
                    )
                    continue

                if stripped.startswith("#define "):
                    parts = stripped.split(None, 2)
                    if len(parts) < 3:
                        raise AssemblerError(
                            f"#define expects a name and value"
                        )

                    name = parts[1]
                    value = parts[2]
                    defines[name] = value
                    continue

                for name, value in defines.items():
                    stripped = stripped.replace(name, value)

                result.append(stripped)

            return "\n".join(result)

        expanded_lines = []
        for raw_line in lines:
            stripped = raw_line.strip()

            if stripped.startswith("#import "):
                parts = stripped.split(None, 2)
                if len(parts) < 2:
                    raise AssemblerError(
                        f"#import expects a file path"
                    )

                import_path = parts[1].strip("\"'")

                if not import_path.endswith(".asm"):
                    import_path += ".asm"

                if not import_path.startswith("/") and base_path:
                    import_path = f"{base_path}/{import_path}"

                expanded_lines.append(
                    resolve_imports(import_path, imported)
                )
                continue

            if stripped.startswith("#define "):
                parts = stripped.split(None, 2)
                if len(parts) < 3:
                    raise AssemblerError(
                        f"#define expects a name and value"
                    )

                defines[parts[1]] = parts[2]
                continue

            for name, value in defines.items():
                stripped = stripped.replace(name, value)

            expanded_lines.append(stripped)

        return "\n".join(expanded_lines)

    def parse(self, source: str):
        self.labels.clear()
        self.instructions.clear()
        self.data.clear()
        self.location = 0

        source = self._preprocess(source)

        for line_number, raw_line in enumerate(
            source.splitlines(),
            1,
        ):
            line = strip_comment(raw_line).strip()

            if not line:
                continue

            if line.startswith(".entry"):
                continue

            if line.startswith(".data"):
                continue

            while ":" in line:
                label, remainder = line.split(":", 1)

                label = label.strip()

                if not re.fullmatch(
                    r"[A-Za-z_.$][A-Za-z0-9_.$]*",
                    label,
                ):
                    raise AssemblerError(
                        f"line {line_number}: "
                        f"invalid label: {label}"
                    )

                if label in self.labels:
                    raise AssemblerError(
                        f"line {line_number}: "
                        f"duplicate label: {label}"
                    )

                self.labels[label] = self.location

                line = remainder.strip()

                if line.startswith("string"):
                    self._emit_string_data(line, line_number)
                    line = ""
                    break

                if line.startswith("constant"):
                    self._emit_constant_data(line, line_number)
                    line = ""
                    break

                if line.startswith("data"):
                    self._emit_byte_data(line, line_number)
                    line = ""
                    break

                if not line:
                    break

            if not line:
                continue

            if line.startswith("string"):
                self._emit_string_data(line, line_number)
                continue

            if line.startswith("constant"):
                self._emit_constant_data(line, line_number)
                continue

            if line.startswith("data"):
                self._emit_byte_data(line, line_number)
                continue

            parts = line.split(None, 1)
            name = parts[0].upper()

            if name not in INSTRUCTIONS:
                raise AssemblerError(
                    f"line {line_number}: "
                    f"unknown instruction: {name}"
                )

            operand_text = parts[1] if len(parts) > 1 else ""

            operands = (
                split_operands(operand_text)
                if operand_text
                else []
            )

            parsed = ParsedInstruction(
                line=line_number,
                name=name,
                operands=operands,
                location=self.location,
            )

            self.instructions.append(parsed)

            instruction = INSTRUCTIONS[name]

            if name in MEMORY_INSTRUCTIONS:
                self.location += self._memory_instruction_size(
                    parsed
                )
            else:
                self.location += instruction.size

    def _emit_string_data(self, line: str, line_number: int):
        parts = line.split(None, 1)
        if len(parts) < 2:
            raise AssemblerError(
                f"line {line_number}: "
                f"string expects a quoted literal"
            )

        raw = parts[1].strip()

        if not (raw.startswith('"') and raw.endswith('"')):
            raise AssemblerError(
                f"line {line_number}: "
                f"string expects a quoted literal"
            )

        unescaped = raw[1:-1]
        unescaped = unescaped.replace('\\n', '\n')
        unescaped = unescaped.replace('\\t', '\t')
        unescaped = unescaped.replace('\\"', '"')
        unescaped = unescaped.replace('\\\\', '\\')

        self.data[self.location] = (
            unescaped.encode("utf-8") + b"\x00"
        )
        self.location += len(self.data[self.location])

    def _emit_constant_data(self, line: str, line_number: int):
        parts = line.split(None, 1)
        if len(parts) < 2:
            raise AssemblerError(
                f"line {line_number}: "
                f"constant expects a value"
            )

        value = self.resolve_value(
            parts[1].strip(),
            line_number,
            allow_label=True,
        )

        self.data[self.location] = value.to_bytes(
            4, "little"
        )
        self.location += 4

    def _emit_byte_data(self, line: str, line_number: int):
        parts = line.split(None, 1)
        operand_text = parts[1].strip() if len(parts) > 1 else ""

        if not operand_text:
            raise AssemblerError(
                f"line {line_number}: "
                f"data expects byte values"
            )

        bytes_out = bytearray()

        for raw in operand_text.split(","):
            raw = raw.strip()

            if not raw:
                continue

            value = parse_number(raw)

            if value is None or not 0 <= value <= 255:
                raise AssemblerError(
                    f"line {line_number}: "
                    f"invalid byte value: {raw}"
                )

            bytes_out.append(value)

        if not bytes_out:
            raise AssemblerError(
                f"line {line_number}: "
                f"data expects at least one byte"
            )

        self.data[self.location] = bytes(bytes_out)
        self.location += len(bytes_out)

    def _memory_instruction_size(
        self,
        instruction: ParsedInstruction,
    ) -> int:
        definition = INSTRUCTIONS[instruction.name]

        if len(instruction.operands) != 3:
            raise AssemblerError(
                f"line {instruction.line}: "
                f"{instruction.name} expects "
                f"3 assembly operands"
            )

        definition_operands = (
            OperandType.REGISTER,
            OperandType.REGISTER,
            OperandType.OFFSET32,
        )

        if instruction.name.startswith("LOAD"):
            definition_operands = (
                OperandType.REGISTER,
                OperandType.REGISTER,
                OperandType.OFFSET32,
            )

        return 1 + sum(
            operand_size(operand)
            for operand in definition_operands
        )

    def resolve_value(
        self,
        value: str,
        line: int,
        *,
        allow_label: bool = True,
    ) -> int:
        value = value.strip()

        number = parse_number(value)

        if number is not None:
            return number

        if value in self._builtin_constants():
            return self._builtin_constants()[value]

        if value in self._extension_constants:
            return self._extension_constants[value]

        if allow_label and value in self.labels:
            return self.labels[value]

        raise AssemblerError(
            f"line {line}: unknown value: {value}"
        )

    def encode(self) -> bytes:
        output = bytearray()
        cursor = 0

        instruction_iter = iter(self.instructions)
        data_items = sorted(self.data.items())

        next_instruction = next(instruction_iter, None)
        next_data = data_items.pop(0) if data_items else None

        while next_instruction is not None or next_data is not None:
            next_instr_addr = (
                next_instruction.location if next_instruction else None
            )
            next_data_addr = next_data[0] if next_data else None

            if next_data is not None and (
                next_instruction is None
                or next_data[0] < next_instruction.location
            ):
                gap = next_data_addr - cursor
                if gap > 0:
                    output.extend(b"\x00" * gap)
                    cursor += gap

                output.extend(next_data[1])
                cursor += len(next_data[1])

                next_data = data_items.pop(0) if data_items else None
                continue

            if next_instruction is not None:
                gap = next_instruction.location - cursor
                if gap > 0:
                    output.extend(b"\x00" * gap)
                    cursor += gap

                encoded = self._encode_instruction(
                    next_instruction
                )
                output.extend(encoded)
                cursor += len(encoded)

                next_instruction = next(
                    instruction_iter, None
                )
                continue

            break

        return bytes(output)

    def _encode_instruction(
        self,
        parsed: ParsedInstruction,
    ) -> bytes:
        name = parsed.name
        definition = INSTRUCTIONS[name]

        if name in MEMORY_INSTRUCTIONS:
            return self._encode_memory_instruction(parsed)

        if len(parsed.operands) != len(
            definition.operands
        ):
            raise AssemblerError(
                f"line {parsed.line}: {name} expects "
                f"{len(definition.operands)} operands, "
                f"got {len(parsed.operands)}"
            )

        values = []

        for operand_type, operand in zip(
            definition.operands,
            parsed.operands,
        ):
            values.append(
                self._resolve_operand(
                    operand_type,
                    operand,
                    parsed.line,
                )
            )

        return encode_instruction(
            definition,
            tuple(values),
        )

    def _encode_memory_instruction(
        self,
        parsed: ParsedInstruction,
    ) -> bytes:
        name = parsed.name

        if len(parsed.operands) != 3:
            raise AssemblerError(
                f"line {parsed.line}: "
                f"{name} expects 3 operands"
            )

        if name.startswith("LOAD"):
            destination_text = parsed.operands[0]
            base_text = parsed.operands[1]
            offset_text = parsed.operands[2]

            destination = self._resolve_register(
                destination_text,
                parsed.line,
            )

            base = self._resolve_register(
                base_text,
                parsed.line,
            )

            offset = self.resolve_value(
                offset_text,
                parsed.line,
                allow_label=False,
            )

            values = (
                destination,
                base,
                offset,
            )

        else:
            base_text = parsed.operands[0]
            offset_text = parsed.operands[1]
            source_text = parsed.operands[2]

            base = self._resolve_register(
                base_text,
                parsed.line,
            )

            offset = self.resolve_value(
                offset_text,
                parsed.line,
                allow_label=False,
            )

            source = self._resolve_register(
                source_text,
                parsed.line,
            )

            values = (
                base,
                offset,
                source,
            )

        definition = INSTRUCTIONS[name]

        return encode_instruction(
            definition,
            values,
        )

    def _resolve_register(
        self,
        operand: str,
        line: int,
    ) -> int:
        register = parse_register(operand)

        if register is None:
            raise AssemblerError(
                f"line {line}: "
                f"expected register, got {operand}"
            )

        return register

    def _resolve_operand(
        self,
        operand_type: OperandType,
        operand: str,
        line: int,
    ) -> int:
        if operand_type == OperandType.REGISTER:
            return self._resolve_register(
                operand,
                line,
            )

        allow_label = operand_type in {
            OperandType.ADDRESS8,
            OperandType.ADDRESS16,
            OperandType.ADDRESS32,
            OperandType.ADDRESS64,
            OperandType.IMMEDIATE8,
            OperandType.IMMEDIATE16,
            OperandType.IMMEDIATE32,
            OperandType.IMMEDIATE64,
            OperandType.OFFSET8,
            OperandType.OFFSET16,
            OperandType.OFFSET32,
            OperandType.OFFSET64,
            OperandType.SYSCALL,
        }

        return self.resolve_value(
            operand,
            line,
            allow_label=allow_label,
        )

    def assemble(self, source: str) -> bytes:
        self.parse(source)
        return self.encode()


def assemble(
    source: str,
    extensions: str | None = None,
) -> bytes:
    ext_constants: dict[str, int] = {}

    if extensions:
        from extension import ExtensionLoader

        loader = ExtensionLoader()
        loader.load(extensions)
        ext_constants = loader.constants

    return Assembler(
        extension_constants=ext_constants,
    ).assemble(source)


def assemble_file(
    input_path: str,
    output_path: str,
    extensions: str | None = None,
):
    with open(input_path, "r", encoding="utf-8") as file:
        source = file.read()

    machine_code = assemble(source, extensions=extensions)

    with open(output_path, "wb") as file:
        file.write(machine_code)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="assembler",
        description="Assemble FR-Kernel assembly to bytecode",
    )
    parser.add_argument("input", help="input assembly file")
    parser.add_argument("output", help="output binary file")
    parser.add_argument(
        "-e",
        "--extensions",
        dest="extensions",
        default=None,
        help="extension directory or file",
    )

    args = parser.parse_args()

    try:
        assemble_file(
            args.input,
            args.output,
            extensions=args.extensions,
        )
    except AssemblerError as error:
        print(f"assembler error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

