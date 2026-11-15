---
title: 07 Python CTF 逆向常用数据转换与 Flag 输出
date: 2026-10-09T23:05:59+08:00
lastmod: 2026-10-09T23:05:59+08:00
---

# 07 Python CTF 逆向常用数据转换与 Flag 输出

# Python CTF 逆向常用数据转换与 Flag 输出

这篇作为日常工具箱：不绑定某一道题，专门处理 hex/base64、大小端、32 位溢出、rotate、压缩、可打印性扫描和 flag 输出。看雪式写法强调：每个转换都先给输入/输出样例，再保留中间态，最后只在确认校验通过后输出 FLAG。

> 逆向脚本不是“跑出一个字符串”就结束，而是要让每一步字节变化都能回放、能解释、能和汇编对照。

## 0x00 常用转换表

- hex：bytes.fromhex / data.hex；注意空格、0x 前缀和奇数长度。
- base64：b64decode / b64encode；注意 URL-safe 字母表和 padding。
- 大小端：struct.unpack；先根据 mov/bswap/htonl/ntohl 判断字节序。
- 整数溢出：每次运算后 & 0xffffffff 或 & 0xffff，模拟 C 无符号类型。
- rotate：ROL/ROR 不是普通左移，移出的位要回到低位。
- 压缩：zlib/gzip/bz2/lzma 按 magic 和解压错误逐个尝试。

## 0x01 可直接复用的脚本

```python
#!/usr/bin/env python3
"""CTF reversing data conversion and flag-output helpers."""
import base64, binascii, re, struct, zlib

def hx(s: str) -> bytes: return bytes.fromhex(re.sub(r"\\s+", "", s))
def unhex(s: str) -> str: return hx(s).decode("utf-8", errors="replace")
def b64d(s: str) -> bytes: return base64.b64decode(s)
def rol32(x: int, n: int) -> int: return ((x << n) | (x >> (32 - n))) & 0xffffffff
def ror32(x: int, n: int) -> int: return ((x >> n) | (x << (32 - n))) & 0xffffffff
def u32le(b: bytes) -> int: return struct.unpack("<I", b)[0]
def u32be(b: bytes) -> int: return struct.unpack(">I", b)[0]
def pack_words(data: bytes, endian="<"): return [struct.unpack(endian + "I", data[i:i+4])[0] for i in range(0, len(data), 4)]
def printable(data: bytes) -> str: return "".join(chr(x) if 32 <= x < 127 else "." for x in data)
def find_flag(data: bytes):
    return re.findall(rb"(?:flag|ctf|FLAG)\\{[^}]{1,200}\\}", data)
def print_flag(flag: bytes | str):
    if isinstance(flag, bytes): flag = flag.decode(errors="replace")
    print(f"FLAG: {flag}")

if __name__ == "__main__":
    print_flag(unhex("666c61677b64656d6f7d"))
```

## 0x02 Flag 输出与校验模板

```python
import re

def emit_flag(candidate: bytes | str, prefix=(b"flag{", b"CTF{")):
    raw = candidate.encode() if isinstance(candidate, str) else candidate
    if any(raw.startswith(p) and raw.endswith(b"}") for p in prefix):
        print("FLAG:", raw.decode(errors="replace"))
        return True
    print("candidate:", raw.hex(), "text:", raw.decode(errors="replace"))
    return False

# 题目中若是逐字符校验，保留第一个失败位置
for i, (got, expected) in enumerate(zip(output, target)):
    if got != expected:
        print("first mismatch", i, hex(got), hex(expected))
        break
```

## 0x03 CTF 处理流程

1. 先保存原始输入：十六进制、长度、来源和端序假设。
2. 把每个变换封装成纯函数，避免在循环里偷偷修改全局状态。
3. 每一步打印长度、前 16 字节、末 16 字节和 hash；长数据不要全部刷屏。
4. 用 known-plaintext、flag 前缀、字符集和长度做候选过滤。
5. 最后对照程序真实比较点；只满足输出格式而未通过比较，不算解题完成。

## 0x04 常见魔改应对

- 遇到 bytes[::-1]、按 DWORD 反转、奇偶位拆分，先单独写 reversible 函数。
- 遇到 rolling key、前一字节反馈、位置相关加法，保留索引 i 和上一状态。
- 遇到 signed char/整数提升，显式转成 8/32 位并记录 mask。
- 遇到多层编码，先识别可逆层，再把每层命名为 step1、step2，禁止一行套娃。

## 0x05 一页式复盘模板

```python
input = ...
step1_hex = ...
step2_endian = ...
step3_cipher = ...
check = ...
flag = ...
print(f"FLAG: {flag}")
```
