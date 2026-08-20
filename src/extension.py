from __future__ import annotations

import inspect
import os

from mmio import alloc_extension_mmio, reset_extensions


class ExtFunctionArg:
    __slots__ = ("name", "mmio_addr")

    def __init__(self, name: str, mmio_addr: int):
        self.name = name
        self.mmio_addr = mmio_addr


class ExtFunction:
    __slots__ = (
        "name",
        "func",
        "args",
        "result_addr",
        "arg_values",
        "result",
    )

    def __init__(
        self,
        name: str,
        func,
        args: list[ExtFunctionArg],
        result_addr: int | None,
    ):
        self.name = name
        self.func = func
        self.args = args
        self.result_addr = result_addr
        self.arg_values: list = [0] * len(args)
        self.result: int = 0


class Extension:
    __slots__ = ("name", "path", "functions", "constants")

    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        self.functions: list[ExtFunction] = []
        self.constants: dict[str, int] = {}


class ExtensionLoader:
    def __init__(self):
        self.extensions: list[Extension] = []
        self.constants: dict[str, int] = {}
        self.write_map: dict[int, tuple[ExtFunction, int]] = {}
        self.read_map: dict[int, ExtFunction] = {}

    def load(self, source: str):
        reset_extensions()

        if os.path.isdir(source):
            files = sorted(
                f
                for f in os.listdir(source)
                if f.endswith(".py") and not f.startswith("__")
            )
            for filename in files:
                self._load_file(os.path.join(source, filename))
        elif os.path.isfile(source) and source.endswith(".py"):
            self._load_file(source)
        else:
            raise ValueError(f"unknown extension source: {source}")

    def _load_file(self, path: str):
        ext_name = os.path.basename(path).rsplit(".", 1)[0]
        ext = Extension(name=ext_name, path=path)

        with open(path, "r", encoding="utf-8") as f:
            source = f.read()

        namespace: dict = {"__file__": path}
        exec(compile(source, path, "exec"), namespace)

        returns: set = namespace.get("returns", set())

        if "constants" in namespace:
            ext.constants = namespace["constants"]
            for key, value in ext.constants.items():
                self.constants[f"{ext_name}_{key}".upper()] = value

        for name, obj in namespace.items():
            if not callable(obj) or name.startswith("_"):
                continue
            if name in ("returns", "constants"):
                continue

            sig = inspect.signature(obj)
            params = list(sig.parameters.keys())

            args = []
            for param in params:
                addr = alloc_extension_mmio(4)
                args.append(ExtFunctionArg(param, addr))

            result_addr = None
            if name in returns:
                result_addr = alloc_extension_mmio(4)

            func = ExtFunction(
                name=name,
                func=obj,
                args=args,
                result_addr=result_addr,
            )
            ext.functions.append(func)

            prefix = f"{ext_name}_{name}".upper()

            if len(params) == 0:
                if result_addr is not None:
                    self.constants[prefix] = result_addr
            elif len(params) == 1:
                self.constants[prefix] = args[0].mmio_addr
                if result_addr is not None:
                    self.constants[f"{prefix}_RESULT"] = result_addr
            else:
                for arg in args:
                    self.constants[
                        f"{prefix}_{arg.name.upper()}"
                    ] = arg.mmio_addr
                if result_addr is not None:
                    self.constants[f"{prefix}_RESULT"] = result_addr

            for i, arg in enumerate(args):
                self.write_map[arg.mmio_addr] = (func, i)

            if result_addr is not None:
                self.read_map[result_addr] = func

        self.extensions.append(ext)
