#!/usr/bin/env python3
"""CTF reversing helpers for Z3: byte-level flag models, hash inversion, printing.

每个 demo 都先用已知明文算出目标常量，再让 z3 从常量反推明文，
这样脚本自身既是模板也是自测。
"""
from __future__ import annotations

from z3 import (
    BitVec, BitVecVal, UGT, ULT, Concat, Extract, LShR, RotateLeft, RotateRight,
    Solver, ZeroExt, sat,
)

PRINTABLE = (0x20, 0x7E)


def constraint_bytes(n: int, prefix: str = "flag{") -> tuple:
    """创建 n 个 8 位符号字节，约束为可打印 ASCII，并固定 flag 前缀。"""
    xs = [BitVec(f"f{i}", 8) for i in range(n)]
    s = Solver()
    for x in xs:
        s.add(x >= PRINTABLE[0], x <= PRINTABLE[1])
    for i, ch in enumerate(prefix):
        s.add(xs[i] == ord(ch))
    return s, xs


def recover(s: Solver, xs: list) -> bytes:
    r = s.check()
    if str(r) != "sat":
        raise RuntimeError(f"no model: {r}")
    m = s.model()
    return bytes(m[x].as_long() for x in xs)


def u32le(xs: list):
    """4 个 8 位字节按小端拼成 32 位字，对应 C 的 *(uint32_t*)buf。"""
    return Concat(xs[3], xs[2], xs[1], xs[0])


def u32be(xs: list):
    return Concat(xs[0], xs[1], xs[2], xs[3])


# ---------------------------------------------------------------- 示例 1: 整数线性方程
def demo_int() -> None:
    from z3 import Int
    a, b, c = Int("a"), Int("b"), Int("c")
    s = Solver()
    s.add(a + b == 12, b + c == 20, a + c == 18, a > 0)
    assert s.check() == sat
    m = s.model()
    print("[int]", m[a], m[b], m[c])


# ---------------------------------------------------------------- 示例 2: 逐字节校验
def demo_bytes() -> None:
    target = b"flag{z3_ok}"
    s, xs = constraint_bytes(len(target), prefix="flag")
    # 用真实明文生成常量，保证模型可满足
    # 链式校验：每个条件都建立在前一个字节之上，未知量逐个锁死
    s.add(xs[4] ^ BitVecVal(0x11, 8) == target[4] ^ 0x11)
    s.add(xs[5] + xs[4] == target[5] + target[4])
    s.add(xs[6] ^ xs[5] == target[6] ^ target[5])
    s.add(xs[7] + xs[6] == target[7] + target[6])
    s.add(xs[8] ^ xs[7] == target[8] ^ target[7])
    s.add(xs[9] ^ xs[8] == target[9] ^ target[8])
    s.add(xs[10] == target[10])
    got = recover(s, xs)
    print("[bytes]", got, got == target)


# ---------------------------------------------------------------- 示例 3: 32 位 hash 逆推
def hash32(x):
    h = (x ^ LShR(x, 16)) * BitVecVal(0x45D9F3B, 32)
    return h ^ BitVecVal(0xDEADBEEF, 32)


def demo_hash() -> None:
    plain = b"AB12"
    seed = int.from_bytes(plain, "little")
    target = (seed ^ (seed >> 16)) * 0x45D9F3B & 0xFFFFFFFF
    target ^= 0xDEADBEEF

    s, xs = constraint_bytes(4, prefix="")
    s.add(hash32(u32le(xs)) == BitVecVal(target, 32))
    got = recover(s, xs)
    print("[hash]", got, got == plain)


# ---------------------------------------------------------------- 示例 4: 位宽与符号扩展
def demo_width() -> None:
    """8 位乘法在 C 里提升为 int，模型里不 ZeroExt 就会被截断成 8 位。"""
    a = BitVec("a", 8)
    s = Solver()
    # 注意：0x80 在 8 位里是 -128，必须用 ULT/UGT 做无符号比较
    s.add(UGT(a, BitVecVal(0x10, 8)), ULT(a, BitVecVal(0x80, 8)))
    s.add(ZeroExt(8, a) * ZeroExt(8, a) == 0x1081)  # 0x41 * 0x41 = 0x1081
    s.add(Extract(7, 0, ZeroExt(8, a)) == a)
    print("[width]", hex(s.model()[a].as_long()) if s.check() == sat else "unsat")


# ---------------------------------------------------------------- 示例 5: 旋转
def demo_rotate() -> None:
    plain = b"\x41\x00\x00\x00"
    seed = int.from_bytes(plain, "little")
    target = ((seed << 7) | (seed >> 25)) & 0xFFFFFFFF
    target ^= ((seed >> 3) | (seed << 29)) & 0xFFFFFFFF

    x = BitVec("x", 32)
    s = Solver()
    s.add((RotateLeft(x, 7) ^ RotateRight(x, 3)) == BitVecVal(target, 32))
    s.add(x & 0xFF == 0x41)
    if s.check() == sat:
        print("[rotate]", hex(s.model()[x].as_long()))


if __name__ == "__main__":
    demo_int()
    demo_bytes()
    demo_hash()
    demo_width()
    demo_rotate()
