---
title: 03 TEA：32 轮 Feistel，字节序、delta 和无符号溢出是生死线
date: 2026-10-09T23:05:58+08:00
lastmod: 2026-11-15T21:44:31+08:00
---

# 03 TEA：32 轮 Feistel，字节序、delta 和无符号溢出是生死线

# TEA：两个 32 位字与 delta 常量

TEA 把 64 位分组拆成 v0/v1 两个 32 位无符号整数，使用 128 位 key 分成四个 32 位字，循环 32 轮；每轮通过移位、加法、异或和 delta 累积更新。

> 看雪式复盘原则：先确认数据边界，再确认算法轮廓；先做可逆最小实验，再对照汇编逐项核对。

## 0x00 先给结论

CTF 中看到算法名，不要直接套库。先记录输入长度、字节序、分组边界、密钥来源、常量、轮数、模式和比较点；然后用 Python 写出一个可逆参考实现，最后再把魔改点逐个 diff。

## 0x01 算法逻辑

三种算法共用 32 位无符号算术和 delta 常量，但结构不一样，先分清再抄代码：

## 0x02 逆向识别指纹

- `0x9E3779B9`​（delta）、​`0xC6EF3720`​（32 轮后的 sum）、​`<<4`​ / ​`>>5` 是 TEA 的强指纹。
- 64 位分组 + 128 位密钥 + 每轮两次加法更新，是 TEA / XTEA 的共同轮廓。
- XTEA 里会出现 ​`key[sum & 3]`​、​`key[(sum >> 11) & 3]` 两条取 key 的指令，这是和 TEA 的分界。
- XXTEA 没有固定分组：代码里会出现 ​`6 + 52 / n`​、​`(p & 3) ^ e`​、​`v[(p + 1) % n]` 这类和长度绑定的下标。
- XXTEA 密文长度 = 明文向上取整到 4 的倍数；不是 8 的倍数就先怀疑它。
- 大端实现会有 ​`bswap`​ / ​`htonl`​ / ​`movbe`​，或者 Python 里写 ​`struct.unpack(">")`。

## 0x03 CTF 遇到时怎么处理

1. 先判断 8 字节分组是否小端；把输入按 uint32_t 两两拆分。
2. 从反编译中抄出轮数、delta、移位量和 key 下标，不要套默认 32 轮。
3. 用一个块验证加密/解密互逆，再用完整 flag 验证 padding 与拼接。
4. 检查题目是 TEA、XTEA 还是 XXTEA；XXTEA 往往是变长数组而不是固定 8 字节块。

## 0x04 魔改增强：不要猜，直接做差分

- 先把参数化做掉：轮数、delta、左右移位、字节序、key 顺序都做成参数，不要复制三份代码。
- TEA 魔改：delta 换常量、rounds 改 16 / 64、​`<<4 / >>5`​ 改成 ​`<<3 / >>7`、v0 与 v1 顺序互换、key 四字重排。
- XTEA 魔改：​`sum & 3`​ 与 ​`(sum >> 11) & 3` 互换、先更新 v1 再更新 v0、轮数减半。
- XXTEA 魔改：rounds 写死、delta 改值、补齐方式变化、带 4 字节长度头、按大端拆字。
- 外层再套 XOR / base64 / 自定义 padding 时，按层拆开，一层一层验证，不要一次性猜全部。
- 手里有明文-密文对时，直接跑 ​`auto_identify()` 枚举常见组合，别靠肉眼猜。

## 0x05 Python 参考脚本

下面这份脚本是参数化的，三种算法共用一套调用习惯，遇到魔改只改参数：

|参数|含义|常见魔改|
| -------------| ------------------| -------------------------|
|`rounds`|轮数|16 / 32 / 64|
|`delta`|每轮累加常量|0x9E3779B9 / 0x61C88647|
|`endian`|数据字节序|`<`​ / ​`>`|
|`lshift`​ / ​`rshift`|TEA 左右移位|4/5 → 3/7|
|`key_index`|XTEA 取 key 方式|`low`​ / ​`high`|
|`order`|key 四字重排|(2,3,0,1)|

脚本末尾带自测：TEA 零密钥向量、XTEA 一轮向量、三种算法互逆、魔改参数互逆、​`auto_identify` 反推参数。

```python
﻿#!/usr/bin/env python3
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
```

## 0x06 常见坑点

- 每次加减都要 ​`& 0xffffffff`​，Python 不会自动模拟 ​`uint32_t` 溢出。
- TEA 的左移是 4、右移是 5，**不是一个数**；把两者写成同一个 shift 参数，结果会完全不同。
- 小端 / 大端错一个字节结果就完全不同；优先从汇编的 load 指令确认。
- 不要把 ASCII key 直接当四个整数，先确认是否 ​`memcpy` 到 16 字节缓冲区。
- XXTEA 要求 ​`n >= 2`​（至少 8 字节），轮数是 ​`6 + 52 // n`，写死 32 必错。
- XXTEA 的 ​`k[(p & 3) ^ e]`​ 在 Python 里必须写成 ​`k[((p & 3) ^ e)]`​：​`&`​ 的优先级低于 ​`^`，不括号会算错。
- XXTEA 解密从 ​`delta * rounds`​ 开始，循环条件是 ​`while total`，少跑一轮就是乱码。
- 解出来是乱码但长度对：先换端序，再试 key 顺序，最后才怀疑算法选错。

## 0x07 复盘模板

```python
# 1) 抄参数：全部从反编译里抄，不要用默认值
KEY   = b"0123456789abcdef"
CT    = bytes.fromhex("...")
ROUNDS, DELTA, ENDIAN = 32, 0x9E3779B9, "<"

# 2) 选变体，先试标准参数
pt = tea_decrypt(CT, KEY, rounds=ROUNDS, delta=DELTA, endian=ENDIAN)
# pt = xtea_decrypt(CT, KEY, key_index="low", rounds=ROUNDS, delta=DELTA, endian=ENDIAN)
# pt = xxtea_decrypt(CT, KEY, delta=DELTA, endian=ENDIAN)
print(pt)

# 3) 手里有明文-密文对时，先自动识别参数，再套整段
# cfg = auto_identify(PT_KNOWN, CT_KNOWN, KEY)[0]
# print(cfg)
# print(decrypt_with(cfg, CT, KEY))

# 4) 文档记录
# 样本 / 变体 / 分组 / 端序 / key 来源 / rounds / delta / 是否套外层 / FLAG
```
