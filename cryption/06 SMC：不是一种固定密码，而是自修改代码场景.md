---
title: 06 SMC：不是一种固定密码，而是自修改代码场景
date: 2026-10-09T23:05:59+08:00
lastmod: 2026-10-09T23:05:59+08:00
---

# 06 SMC：不是一种固定密码，而是自修改代码场景

# SMC：运行时解密代码与动态还原

这里的 SMC 指 Self-Modifying Code。题目常把 .text 中的函数或关键逻辑加密，运行时修改页权限、解密到原地址，再跳转执行；静态看到的是假代码或乱码。

> 看雪式复盘原则：先确认数据边界，再确认算法轮廓；先做可逆最小实验，再对照汇编逐项核对。

## 0x00 先给结论

CTF 中看到算法名，不要直接套库。先记录输入长度、字节序、分组边界、密钥来源、常量、轮数、模式和比较点；然后用 Python 写出一个可逆参考实现，最后再把魔改点逐个 diff。

## 0x01 算法逻辑

先找 VirtualProtect/mprotect/NtProtectVirtualMemory、memcpy、循环异或和间接跳转；重点记录解密前地址、长度、密钥、解密后首字节和跳转目标。

## 0x02 逆向识别指纹

- 先区分“代码加密”与“数据加密”：SMC 的关键证据是写入可执行区域。
- 在解密函数返回、权限恢复或间接 call/jmp 前下断点，dump 已还原的内存区域。
- 把内存 dump 与文件 .text 做 diff，得到真实函数；再对真实函数中的 XOR/RC4/AES 等算法单独分析。
- 若有反调试，先记录触发条件和返回值，避免直接 patch 掉后丢失控制流证据。

## 0x03 CTF 遇到时怎么处理

1. 解密 key 可能来自输入、时间、进程环境、TEB/PEB 或前置校验。
2. 页权限可能从 RX -> RWX -> RX；权限切换点通常比算法常量更可靠。
3. 循环范围、异或反馈、解密顺序、跳板和 self-check 都是魔改点；按内存差分逐字节确认。

## 0x04 魔改增强：不要猜，直接做差分

- 内存中的真实代码只在运行时出现，不能用静态反编译结果直接下结论。
- dump 时要记录模块基址、RVA、长度和权限，否则无法还原到文件偏移。
- SMC 与壳/虚拟化保护可能叠加，先拿到稳定的解密后代码，再分析其内部算法。

## 0x05 Python 参考脚本

```python
#!/usr/bin/env python3
"""SMC (self-modifying code) dump/decrypt skeleton for CTF reversing."""
from pathlib import Path

def xor_region(blob: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(blob))

def dump_decrypted_region(path: str, offset: int, size: int, key: bytes, out: str):
    data = Path(path).read_bytes()
    region = data[offset:offset + size]
    Path(out).write_bytes(xor_region(region, key))

if __name__ == "__main__":
    print("先在调试器中记录解密前后内存，再把 region 导出到文件")
```

## 0x06 常见坑点

- 如果题目把 SMC 写成“加密算法”，先核对语境；本篇按 CTF 逆向中最常见的自修改代码处理。
- Linux 下关注 mprotect，Windows 下关注 VirtualProtect/NtProtectVirtualMemory。
- dump 出来的代码可能还含相对地址修正，重建时保留原加载基址。

## 0x07 复盘模板

```text
样本：sample
算法假设：SMC
输入长度：...
密钥来源：...
字节序：...
常量/轮数：...
已确认：...
未确认：...
最终校验点：...
FLAG：...
```
