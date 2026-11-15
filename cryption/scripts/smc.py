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
