#!/usr/bin/env python3
"""CTF reversing data conversion and flag-output helpers."""
import base64, binascii, re, struct, zlib

def hx(s: str) -> bytes: return bytes.fromhex(re.sub(r"\\s+", "", s))
def unhex(s: str) -> str: return hx(s).decode("utf-8", errors="replace")
def b64d(s: str) -> bytes: return base64.b64decode(s)
def rol32(x: int, n: int) -> int: return ((x << n) | (x >> (32 - n))) & 0xffffffff
def ror32(x: int, n: int) -> int: return ((x >> n) | (x << (32 - n))) & 0xffffffff
def u32le(b: bytes) -> int: return struct.unpack("<I", b)[0]
def u32be(b: bytes) -> int: return struct.unpack(">I", b)[0]
def pack_words(data: bytes, endian="<"): return [struct.unpack(endian + "I", data[i:i+4])[0] for i in range(0, len(data), 4)]
def printable(data: bytes) -> str: return "".join(chr(x) if 32 <= x < 127 else "." for x in data)
def find_flag(data: bytes):
    return re.findall(rb"(?:flag|ctf|FLAG)\\{[^}]{1,200}\\}", data)
def print_flag(flag: bytes | str):
    if isinstance(flag, bytes): flag = flag.decode(errors="replace")
    print(f"FLAG: {flag}")

if __name__ == "__main__":
    print_flag(unhex("666c61677b64656d6f7d"))

