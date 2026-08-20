import os

_dir = os.path.dirname(os.path.abspath(__file__))
fs = bytearray(open(os.path.join(_dir, "user.bin"), "rb").read())

returns = {"read", "size"}


def read(address: int):
    return fs[address]


def write(address: int, value: int):
    fs[address] = value


def size():
    return len(fs)
