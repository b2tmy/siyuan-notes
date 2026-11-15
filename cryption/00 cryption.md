---
title: 00 cryption
date: 2026-10-09T23:05:57+08:00
lastmod: 2026-11-15T21:44:31+08:00
---

# 00 cryption

# cryption

加密算法与 CTF 逆向复盘笔记。组织方式按看雪论坛技术帖：0x00 结论，0x01 原理，0x02 指纹，0x03 实战，0x04 魔改，0x05 Python，0x06 坑点。

## 目录

- XOR：单字节、重复密钥、滚动密钥与 known-plaintext。
- RC4：KSA、PRGA、状态数组和 keystream 差分。
- TEA / XTEA / XXTEA：delta、轮数、移位、字节序与可直接套用的参数化脚本。
- DES：16 轮 Feistel、模式、IV、padding 与弱密钥。
- AES：状态矩阵、轮密钥、模式、IV 和内联魔改。
- SMC：自修改代码、运行时解密、内存 dump 与代码 diff。
- Python CTF：常用数据转换、候选过滤与 FLAG 输出。
- Z3：把校验逻辑翻译成约束、位宽与符号陷阱、unsat 排查。

## 使用顺序

1. 先看对应算法笔记的识别指纹。
2. 再按 CTF 流程记录输入、边界、key、模式和比较点。
3. 运行对应 scripts 目录中的 Python 参考脚本，逐步对齐中间态。
4. 最后把样本特有的魔改写进复盘模板，而不是改坏标准实现。  
   说明：SMC 在这里按 CTF 逆向中常见的 Self-Modifying Code 处理，它是运行时自修改/解密代码场景，不是与 AES、DES 同类的固定分组密码。
