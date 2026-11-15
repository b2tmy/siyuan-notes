---
title: 02 RC4：KSA + PRGA，重点盯状态数组和丢弃字节
date: 2026-10-09T23:05:58+08:00
lastmod: 2026-10-09T23:05:58+08:00
---

# 02 RC4：KSA + PRGA，重点盯状态数组和丢弃字节

# RC4：识别 S 盒状态机

RC4 是典型流密码：KSA 用密钥打乱 S[0..255]，PRGA 每次更新 i/j、交换 S[i]/S[j] 并取 keystream 字节与明文 XOR。解密和加密完全相同。

> 看雪式复盘原则：先确认数据边界，再确认算法轮廓；先做可逆最小实验，再对照汇编逐项核对。

## 0x00 先给结论

CTF 中看到算法名，不要直接套库。先记录输入长度、字节序、分组边界、密钥来源、常量、轮数、模式和比较点；然后用 Python 写出一个可逆参考实现，最后再把魔改点逐个 diff。

## 0x01 算法逻辑

先执行 KSA，再执行 PRGA。题目可能改 key 编码、S 盒初值、循环次数、丢弃前 N 个 keystream，或把输出字节换成 S[(S[i]+S[j]+bias)&255]。

## 0x02 逆向识别指纹

- 固定长度 256 的数组、两层 0..255 循环、i/j 自增与 swap 是核心指纹。
- 常见汇编表现为 movzx、and 0xff、数组索引和两个字节交换。
- 如果只看到一个 256 字节表，先检查是否是 RC4 S 盒而不是静态查表混淆。

## 0x03 CTF 遇到时怎么处理

1. 定位 KSA 入口，记录 key 的真实字节序列和长度。
2. 在 PRGA 第一个输出点断下，记录 i、j、S[i]、S[j] 和 keystream。
3. 用 Python 对比前 16/32 个 keystream；第一处不同通常就是魔改位置。
4. 检查是否丢弃 keystream、是否对明文做了额外 XOR/加减/旋转。

## 0x04 魔改增强：不要猜，直接做差分

- KSA 的 j 更新可能少了 key、加了常量或换成 key[i % n] ^ i。
- PRGA 可能不交换、交换后再做一次 swap，或者把 S 的索引改为加权索引。
- 题目常把 key 先 MD5/SHA1，再取 digest 的前若干字节；必须把 KDF 单独记录。

## 0x05 Python 参考脚本

```python
#!/usr/bin/env python3
"""Minimal RC4 implementation for CTF verification and differential testing."""

def rc4(data: bytes, key: bytes) -> bytes:
    if not key:
        raise ValueError("key must not be empty")
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xff
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) & 0xff
        j = (j + s[i]) & 0xff
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) & 0xff])
    return bytes(out)

if __name__ == "__main__":
    ct = rc4(b"flag{rc4}", b"key")
    print(ct.hex(), rc4(ct, b"key"))
```

## 0x06 常见坑点

- 不要只比最终明文，优先比中间 keystream。
- Python 实现的 key 必须是 bytes，不能把十六进制字符串直接当 key。
- 短数据容易被错误实现“碰巧对上”，至少用多个长度和已知样本回归。

## 0x07 复盘模板

```text
样本：sample
算法假设：RC4
输入长度：...
密钥来源：...
字节序：...
常量/轮数：...
已确认：...
未确认：...
最终校验点：...
FLAG：...
```
