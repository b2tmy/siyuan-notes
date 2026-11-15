#!/usr/bin/env python3
"""TEA / XTEA / XXTEA for CTF reversing.

设计目标：比赛里遇到魔改版，改几个参数就能套上，不用现场重写。

- 三种算法共用一套参数：rounds / delta / endian / key_endian / 自定义 key 顺序
- TEA 额外支持 shift、sum 初值、v0/v1 顺序
- XTEA 额外支持 key 下标模式（sum&3 / (sum>>11)&3）
- XXTEA 支持变长、补零、可指定 rounds
- auto_identify()：给一组明文-密文对，暴力枚举常见魔改组合，直接告诉你该用哪套参数
"""
from __future__ import annotations

import struct

MASK = 0xFFFFFFFF
DELTA = 0x9E3779B9

# 常见魔改 delta，按出现频率排
DELTA_CANDIDATES = (
    0x9E3779B9, 0x61C88647, 0x9E3779B1, 0xDEADBEEF, 0x12345678,
)


# --------------------------------------------------------------------------- 工具
def _as_bytes_key(key) -> bytes:
    if isinstance(key, bytes):
        return key
    if isinstance(key, bytearray):
        return bytes(key)
    if isinstance(key, str):
        return key.encode()
    raise TypeError("key must be bytes or str")


def unpack_key(key, endian: str = "<", key_endian: str | None = None):
    """16 字节 key 拆成 4 个 uint32；不足 16 字节按循环补齐（CTF 里常见）。"""
    raw = _as_bytes_key(key)
    if len(raw) < 16:
        raw = (raw * (16 // len(raw) + 1))[:16]
    return struct.unpack((key_endian or endian) + "4I", raw)


def _reorder(k, order):
    """key 四字的自定义映射，例如 order=(2,3,0,1) 表示 k2,k3,k0,k1。"""
    if order is None:
        return k
    return tuple(k[i] for i in order)


def pad(data: bytes, block: int = 8) -> bytes:
    rem = len(data) % block
    return data if rem == 0 else data + b"\x00" * (block - rem)


# --------------------------------------------------------------------------- TEA
def tea_encrypt_block(block: bytes, key, rounds: int = 32, delta: int = DELTA,
                      endian: str = "<", key_endian: str | None = None,
                      lshift: int = 4, rshift: int = 5, order=None,
                      swap: bool = False) -> bytes:
    """swap=True 时先交换 v0/v1，对应汇编里先处理高位字的魔改。

    TEA 的移位是左 4 右 5，不是同一个值；魔改题常见改成 3/7 之类。
    """
    if len(block) != 8:
        raise ValueError("TEA block must be 8 bytes")
    v0, v1 = struct.unpack(endian + "2I", block)
    k0, k1, k2, k3 = _reorder(unpack_key(key, endian, key_endian), order)
    if swap:
        v0, v1 = v1, v0
        k0, k1, k2, k3 = k2, k3, k0, k1

    total = 0
    for _ in range(rounds):
        total = (total + delta) & MASK
        v0 = (v0 + (((v1 << lshift) + k0) ^ (v1 + total) ^ ((v1 >> rshift) + k1))) & MASK
        v1 = (v1 + (((v0 << lshift) + k2) ^ (v0 + total) ^ ((v0 >> rshift) + k3))) & MASK
    return struct.pack(endian + "2I", v0, v1)


def tea_decrypt_block(block: bytes, key, rounds: int = 32, delta: int = DELTA,
                      endian: str = "<", key_endian: str | None = None,
                      lshift: int = 4, rshift: int = 5, order=None,
                      swap: bool = False) -> bytes:
    if len(block) != 8:
        raise ValueError("TEA block must be 8 bytes")
    v0, v1 = struct.unpack(endian + "2I", block)
    k0, k1, k2, k3 = _reorder(unpack_key(key, endian, key_endian), order)
    if swap:
        v0, v1 = v1, v0
        k0, k1, k2, k3 = k2, k3, k0, k1

    total = (delta * rounds) & MASK
    for _ in range(rounds):
        v1 = (v1 - (((v0 << lshift) + k2) ^ (v0 + total) ^ ((v0 >> rshift) + k3))) & MASK
        v0 = (v0 - (((v1 << lshift) + k0) ^ (v1 + total) ^ ((v1 >> rshift) + k1))) & MASK
        total = (total - delta) & MASK
    return struct.pack(endian + "2I", v0, v1)


def tea_encrypt(data: bytes, key, **kw) -> bytes:
    out = bytearray()
    for i in range(0, len(pad(data, 8)), 8):
        out += tea_encrypt_block(data[i:i + 8].ljust(8, b"\x00"), key, **kw)
    return bytes(out)


def tea_decrypt(data: bytes, key, **kw) -> bytes:
    out = bytearray()
    for i in range(0, len(pad(data, 8)), 8):
        out += tea_decrypt_block(data[i:i + 8].ljust(8, b"\x00"), key, **kw)
    return bytes(out)


# --------------------------------------------------------------------------- XTEA
def xtea_encrypt_block(block: bytes, key, rounds: int = 32, delta: int = DELTA,
                       endian: str = "<", key_endian: str | None = None,
                       key_index: str = "low") -> bytes:
    """key_index: low = key[sum & 3]；high = key[(sum >> 11) & 3]（标准实现两种都有）。"""
    if len(block) != 8:
        raise ValueError("XTEA block must be 8 bytes")
    v0, v1 = struct.unpack(endian + "2I", block)
    k = _reorder(unpack_key(key, endian, key_endian), None)
    total = 0
    for _ in range(rounds):
        idx = (total & 3) if key_index == "low" else ((total >> 11) & 3)
        v0 = (v0 + ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (total + k[idx]))) & MASK
        total = (total + delta) & MASK
        idx = (total & 3) if key_index == "low" else ((total >> 11) & 3)
        v1 = (v1 + ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (total + k[idx]))) & MASK
    return struct.pack(endian + "2I", v0, v1)


def xtea_decrypt_block(block: bytes, key, rounds: int = 32, delta: int = DELTA,
                       endian: str = "<", key_endian: str | None = None,
                       key_index: str = "low") -> bytes:
    if len(block) != 8:
        raise ValueError("XTEA block must be 8 bytes")
    v0, v1 = struct.unpack(endian + "2I", block)
    k = _reorder(unpack_key(key, endian, key_endian), None)
    total = (delta * rounds) & MASK
    for _ in range(rounds):
        idx = (total & 3) if key_index == "low" else ((total >> 11) & 3)
        v1 = (v1 - ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (total + k[idx]))) & MASK
        total = (total - delta) & MASK
        idx = (total & 3) if key_index == "low" else ((total >> 11) & 3)
        v0 = (v0 - ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (total + k[idx]))) & MASK
    return struct.pack(endian + "2I", v0, v1)


def xtea_encrypt(data: bytes, key, **kw) -> bytes:
    out = bytearray()
    for i in range(0, len(pad(data, 8)), 8):
        out += xtea_encrypt_block(data[i:i + 8].ljust(8, b"\x00"), key, **kw)
    return bytes(out)


def xtea_decrypt(data: bytes, key, **kw) -> bytes:
    out = bytearray()
    for i in range(0, len(pad(data, 8)), 8):
        out += xtea_decrypt_block(data[i:i + 8].ljust(8, b"\x00"), key, **kw)
    return bytes(out)


# --------------------------------------------------------------------------- XXTEA
def _xxtea_mx(total: int, y: int, z: int, p: int, e: int, k) -> int:
    return ((((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((total ^ y) + (k[((p & 3) ^ e)] ^ z))) & MASK


def _data_to_words(data: bytes, endian: str, pad_tail: bool = True):
    if pad_tail and len(data) % 4:
        data = data + b"\x00" * (4 - len(data) % 4)
    return list(struct.unpack(endian + "%dI" % (len(data) // 4), data))


def _words_to_data(words, endian: str) -> bytes:
    return struct.pack(endian + "%dI" % len(words), *[w & MASK for w in words])


def xxtea_encrypt(data: bytes, key, delta: int = DELTA, endian: str = "<",
                  key_endian: str | None = None, rounds: int | None = None,
                  pad_tail: bool = True) -> bytes:
    if len(data) < 8:
        return data
    v = _data_to_words(data, endian, pad_tail)
    n = len(v)
    if n < 2:
        return data
    k = unpack_key(key, endian, key_endian)
    rounds = 6 + 52 // n if rounds is None else rounds
    total = 0
    z = v[n - 1]
    while rounds > 0:
        total = (total + delta) & MASK
        e = (total >> 2) & 3
        for p in range(n):
            y = v[(p + 1) % n]
            v[p] = (v[p] + _xxtea_mx(total, y, z, p, e, k)) & MASK
            z = v[p]
        rounds -= 1
    return _words_to_data(v, endian)


def xxtea_decrypt(data: bytes, key, delta: int = DELTA, endian: str = "<",
                  key_endian: str | None = None, rounds: int | None = None,
                  pad_tail: bool = True) -> bytes:
    if len(data) < 8:
        return data
    v = _data_to_words(data, endian, pad_tail)
    n = len(v)
    if n < 2:
        return data
    k = unpack_key(key, endian, key_endian)
    rounds = 6 + 52 // n if rounds is None else rounds
    total = (delta * rounds) & MASK
    y = v[0]
    while total:
        e = (total >> 2) & 3
        for p in range(n - 1, -1, -1):
            z = v[(p - 1) % n]
            v[p] = (v[p] - _xxtea_mx(total, y, z, p, e, k)) & MASK
            y = v[p]
        total = (total - delta) & MASK
    return _words_to_data(v, endian)


# --------------------------------------------------------------------------- 自动识别
def _try_variant(name: str, pt: bytes, ct: bytes, key, endian: str, rounds: int,
                 delta: int, **extra) -> bool:
    try:
        if name == "tea":
            got = tea_encrypt_block(pt, key, rounds=rounds, delta=delta, endian=endian, **extra)
        elif name == "xtea":
            got = xtea_encrypt_block(pt, key, rounds=rounds, delta=delta, endian=endian, **extra)
        else:
            got = xxtea_encrypt(pt, key, delta=delta, endian=endian, rounds=rounds)
        return got == ct
    except Exception:
        return False


def auto_identify(pt: bytes, ct: bytes, key,
                  rounds_list=(32, 16, 64, 8),
                  deltas=DELTA_CANDIDATES,
                  endians=("<", ">")):
    """给一组 8 字节明文/密文，枚举常见组合，返回命中的参数列表。

    pt/ct 长度不一致时按 XXTEA 处理；否则按 8 字节分组试 TEA/XTEA。
    """
    hits = []
    if len(pt) != len(ct):
        return hits

    if len(pt) != 8:
        for endian in endians:
            for rounds in rounds_list:
                for delta in deltas:
                    if _try_variant("xxtea", pt, ct, key, endian, rounds, delta):
                        hits.append({"algo": "xxtea", "endian": endian,
                                     "rounds": rounds, "delta": hex(delta)})
        return hits

    for endian in endians:
        for rounds in rounds_list:
            for delta in deltas:
                if _try_variant("tea", pt, ct, key, endian, rounds, delta):
                    hits.append({"algo": "tea", "endian": endian,
                                 "rounds": rounds, "delta": hex(delta)})
                for ki in ("low", "high"):
                    if _try_variant("xtea", pt, ct, key, endian, rounds, delta, key_index=ki):
                        hits.append({"algo": "xtea", "endian": endian, "key_index": ki,
                                     "rounds": rounds, "delta": hex(delta)})
    return hits


def decrypt_with(cfg: dict, data: bytes, key) -> bytes:
    """把 auto_identify 命中的 cfg 直接套到整段密文上。"""
    algo = cfg["algo"]
    common = {"endian": cfg["endian"], "rounds": cfg["rounds"],
              "delta": int(cfg["delta"], 16) if isinstance(cfg["delta"], str) else cfg["delta"]}
    if algo == "tea":
        return tea_decrypt(data, key, **common)
    if algo == "xtea":
        return xtea_decrypt(data, key, key_index=cfg.get("key_index", "low"), **common)
    return xxtea_decrypt(data, key, **common)


# --------------------------------------------------------------------------- 自测
def _selftest() -> None:
    key = b"0123456789abcdef"
    pt = b"flag{tea"   # 8 字节，正好一个分组

    for name, enc, dec in (
        ("tea", tea_encrypt, tea_decrypt),
        ("xtea", xtea_encrypt, xtea_decrypt),
        ("xxtea", xxtea_encrypt, xxtea_decrypt),
    ):
        ct = enc(pt, key, rounds=32) if name != "xxtea" else enc(pt, key)
        back = dec(ct, key, rounds=32) if name != "xxtea" else dec(ct, key)
        assert back.startswith(pt), (name, back)
        print(f"[{name}] ct={ct.hex()} roundtrip=ok")

    # 标准 TEA 零密钥零明文向量（32 轮）
    ct = tea_encrypt_block(b"\x00" * 8, b"\x00" * 16)
    assert ct.hex() == "0a3aea4140a9ba94", ct.hex()
    print("[tea] zero-key vector ok:", ct.hex())

    # XTEA 一轮的公开向量：零明文零密钥 → v0=0, v1=delta
    ct = xtea_encrypt_block(b"\x00" * 8, b"\x00" * 16, rounds=1)
    assert ct.hex() == "00000000b979379e", ct.hex()
    print("[xtea] one-round vector ok:", ct.hex())

    # 魔改：delta / 轮数 / 大端 / 移位，都要能自洽
    ct = tea_encrypt_block(pt, key, rounds=16, delta=0x61C88647, endian=">", lshift=3, rshift=7)
    back = tea_decrypt_block(ct, key, rounds=16, delta=0x61C88647, endian=">", lshift=3, rshift=7)
    assert back == pt
    print("[tea] modified variant roundtrip ok")

    # XTEA 两种 key 下标模式
    for ki in ("low", "high"):
        ct = xtea_encrypt_block(pt, key, key_index=ki)
        assert xtea_decrypt_block(ct, key, key_index=ki) == pt
    print("[xtea] both key-index modes ok")

    # XXTEA 变长
    data = b"flag{xxtea_variant_test_padding}"
    ct = xxtea_encrypt(data, key)
    assert xxtea_decrypt(ct, key).startswith(data)
    print("[xxtea] variable length ok, ct len =", len(ct))

    # 自动识别：拿魔改后的密文反推参数
    ct = tea_encrypt_block(pt, key, rounds=16, delta=0x61C88647, endian=">")
    hits = auto_identify(pt, ct, key)
    print("[auto] hits:", hits)
    assert any(h["algo"] == "tea" and h["rounds"] == 16 for h in hits)
    assert decrypt_with(hits[0], ct, key) == pt

    print("all self-tests passed")


if __name__ == "__main__":
    _selftest()

