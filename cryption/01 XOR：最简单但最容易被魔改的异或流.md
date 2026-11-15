---
title: 01 XOR：最简单但最容易被魔改的异或流
date: 2026-10-09T23:05:57+08:00
lastmod: 2026-10-09T23:05:57+08:00
---

# 01 XOR：最简单但最容易被魔改的异或流

# XOR：从单字节到滚动密钥

XOR 的核心是按位异或，满足自反性：C = P xor K，P = C xor K。单字节、重复密钥、位置相关密钥和前一字节反馈都属于同一类骨架。

> 看雪式复盘原则：先确认数据边界，再确认算法轮廓；先做可逆最小实验，再对照汇编逐项核对。

## 0x00 先给结论

CTF 中看到算法名，不要直接套库。先记录输入长度、字节序、分组边界、密钥来源、常量、轮数、模式和比较点；然后用 Python 写出一个可逆参考实现，最后再把魔改点逐个 diff。

## 0x01 算法逻辑

对每个字节执行 b ^ key[i]。当 key 只有一个字节时可直接枚举 0..255；当 key 重复时按 i mod len(key) 取值；当密钥由前一轮密文/明文更新时，必须按程序执行顺序复现。

## 0x02 逆向识别指纹

- 常量 0xAA/0x55、短 key、循环下标和按字节 XOR 是最直观指纹。
- 密文长度与明文一致，通常没有 padding；出现固定前缀时适合做 known-plaintext。
- 若每轮出现 key = (key + 1) & 0xff、key ^= i 或 rotate，说明已经是滚动/位置相关魔改。

## 0x03 CTF 遇到时怎么处理

1. 先把比较点前的 buffer dump 出来，确认程序比较的是明文、密文还是二次编码结果。
2. 用已知的 flag 前缀 flag{、CTF{、字符串长度建立密钥候选，再验证整个输入。
3. 对单字节和短重复密钥做暴力；对长密钥优先利用重复周期、明文结构和多组样本。
4. 若输出不可打印，先尝试 hex/base64/倒序/按 DWORD 重排，不要把编码误判成加密。

## 0x04 魔改增强：不要猜，直接做差分

- 将 key 从常量改为 key[i]、key[i % n]、key ^ i、key + prev 等，都会破坏直接套模板。
- 交换 XOR 顺序、先 rotate 再 XOR、按 32 位小端处理，是常见增强；写脚本时保留每一步中间态。
- 把校验拆成多段或加入 checksum 时，先逆向数据流，再处理最终比较。

## 0x05 Python 参考脚本

```python
#!/usr/bin/env python3
"""CTF XOR helper: single-byte, repeating-key and known-plaintext recovery."""
from __future__ import annotations

def xor_bytes(data: bytes, key: bytes) -> bytes:
    if not key:
        raise ValueError("key must not be empty")
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def single_byte_bruteforce(cipher: bytes):
    for k in range(256):
        plain = bytes(x ^ k for x in cipher)
        score = sum(c in b" ETAOINSHRDLUetaoinshrdlu0123456789{}_" for c in plain)
        yield score, k, plain

if __name__ == "__main__":
    cipher = bytes.fromhex("1b0e1b1b5c0a")
    best = max(single_byte_bruteforce(cipher))
    print(f"key=0x{best[1]:02x} plain={best[2]!r}")
```

## 0x06 常见坑点

- Python 的 bytes 与 str 不要混用；所有中间值统一 bytes 或整数。
- 异或后的值要 & 0xff；C/C++ 的 signed char 可能造成符号扩展。
- 看到 XOR 不代表安全强度低，关键看密钥是否可恢复以及是否存在已知明文。

## 0x07 复盘模板

```text
样本：sample
算法假设：XOR
输入长度：...
密钥来源：...
字节序：...
常量/轮数：...
已确认：...
未确认：...
最终校验点：...
FLAG：...
```
