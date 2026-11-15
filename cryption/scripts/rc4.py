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
