---
title: 00 pwn
date: 2026-11-15T22:15:41+08:00
lastmod: 2026-11-15T22:15:54+08:00
---

# 00 pwn

# pwn

二进制漏洞利用笔记。先记两件事：**看得懂汇编**（知道参数在哪、返回地址在哪）和**算得准偏移**（知道写多少字节能踩到返回地址）。这两件做扎实，后面的 ROP、ret2libc、堆利用都是在这上面加东西。

> 原则：pwn 不是背 payload，是搞清楚"内存里现在长什么样"。每写一个 exploit，先在 gdb 里看一眼栈、寄存器和保护，再动手。

## 目录

- 01 汇编基础：寄存器、指令、调用约定、栈帧与 syscall
- 02 栈溢出：偏移计算、ret2text、ret2shellcode、ret2libc

## 使用顺序

- 先看 01，能用 gdb 把 ​`main`​ 的序言、​`read` 的参数、返回地址的位置一一对上。
- 再看 02，拿一个自己编译的 ​`vuln`​ 走一遍：​`checksec`​ → ​`cyclic` 找偏移 → 覆盖返回地址 → 拿 shell。
- 每道题先把保护机制抄下来，再决定走 ret2text 还是 ret2libc，不要上来就写 ROP。

## 约定

- 默认 Linux x86-64（System V 调用约定），32 位会单独标注。
- 地址写成 ​`0x401132`​ 这种形式，payload 用 pwntools 的 ​`p64`​ / ​`p32`。
- `vuln` 是自己编译的靶子，编译参数固定为下面这组，方便对照：

```bash
gcc -O0 -fno-stack-protector -no-pie -z execstack -o vuln vuln.c
```

## 环境与工具

|工具|用途|
| --------------------| -----------------------------------------|
|`pwntools`|起进程、发 payload、收输出、​`p64`​ / ​`flat`|
|`gdb`​ + ​`pwndbg`​ / ​`gef`|看栈、寄存器、内存映射、​`checksec`|
|`checksec`|一次看全 NX / Canary / PIE / RELRO|
|`ROPgadget`​ / ​`ropper`|找 ​`pop rdi; ret` 这类 gadget|
|`one_gadget`|libc 里一把梭的 execve 偏移|
|`patchelf`|换题目自带的 libc / ld|
|`seccomp-tools`|看沙箱允许哪些 syscall|

## 一句话版本

栈溢出 = 往缓冲区写超过它长度的数据，把栈上的 saved rbp 和返回地址一起覆盖掉；返回地址换成一个函数（ret2text）、一段 shellcode（ret2shellcode），或者 libc 里的 ​`system`（ret2libc）。

配套文件在 ​`scripts/`​：​`vuln.c`​ 是可直接编译的靶子，​`exp_template.py`​ 是 ret2text / ret2libc 两种起手式（​`python exp_template.py libc` 切到 libc 模式）。
