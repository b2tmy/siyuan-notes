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
