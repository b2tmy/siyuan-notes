#!/usr/bin/env python3
"""DES: complete pure-Python block, ECB and CBC implementation, no crypto library.
Permutation tables use 1-based bit positions counted from the MSB.
"""
IP = (
58,50,42,34,26,18,10,2,60,52,44,36,28,20,12,4,
62,54,46,38,30,22,14,6,64,56,48,40,32,24,16,8,
57,49,41,33,25,17,9,1,59,51,43,35,27,19,11,3,
61,53,45,37,29,21,13,5,63,55,47,39,31,23,15,7)
FP = (
40,8,48,16,56,24,64,32,39,7,47,15,55,23,63,31,
38,6,46,14,54,22,62,30,37,5,45,13,53,21,61,29,
36,4,44,12,52,20,60,28,35,3,43,11,51,19,59,27,
34,2,42,10,50,18,58,26,33,1,41,9,49,17,57,25)
E = (
32,1,2,3,4,5,4,5,6,7,8,9,8,9,10,11,12,13,
12,13,14,15,16,17,16,17,18,19,20,21,20,21,22,23,24,25,
24,25,26,27,28,29,28,29,30,31,32,1)
P = (16,7,20,21,29,12,28,17,1,15,23,26,5,18,31,10,
     2,8,24,14,32,27,3,9,19,13,30,6,22,11,4,25)
PC1 = (
57,49,41,33,25,17,9,1,58,50,42,34,26,18,
10,2,59,51,43,35,27,19,11,3,60,52,44,36,
63,55,47,39,31,23,15,7,62,54,46,38,30,22,
14,6,61,53,45,37,29,21,13,5,28,20,12,4)
PC2 = (
14,17,11,24,1,5,3,28,15,6,21,10,23,19,12,4,26,8,16,7,27,20,13,2,
41,52,31,37,47,55,30,40,51,45,33,48,44,49,39,56,34,53,46,42,50,36,29,32)
SHIFTS = (1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1)
SBOX = (
((14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7),
 (0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8),
 (4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0),
 (15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13)),
((15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10),
 (3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5),
 (0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15),
 (13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9)),
((10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8),
 (13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1),
 (13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7),
 (1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12)),
((7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15),
 (13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9),
 (10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4),
 (3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14)),
((2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9),
 (14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6),
 (4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14),
 (11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3)),
((12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11),
 (10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8),
 (9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6),
 (4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13)),
((4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1),
 (13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6),
 (1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2),
 (6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12)),
((13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7),
 (1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2),
 (7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8),
 (2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11)))


def permute(x, table, width):
    out = 0
    for pos in table:
        out = (out << 1) | ((x >> (width - pos)) & 1)
    return out


def rol28(x, n):
    return ((x << n) | (x >> (28 - n))) & 0x0fffffff


def pkcs7_pad(data, block_size=8):
    if not 1 <= block_size <= 255:
        raise ValueError("block size must be 1..255")
    n = block_size - len(data) % block_size
    return data + bytes([n]) * n


def pkcs7_unpad(data, block_size=8):
    if not 1 <= block_size <= 255:
        raise ValueError("block size must be 1..255")
    if not data or len(data) % block_size:
        raise ValueError("invalid padded length")
    n = data[-1]
    if not 1 <= n <= block_size or data[-n:] != bytes([n]) * n:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-n]


class DES:
    block_size = 8

    def __init__(self, key):
        if len(key) != 8:
            raise ValueError("DES key must be 8 bytes (56 effective bits)")
        k = permute(int.from_bytes(key, "big"), PC1, 64)
        c, d = k >> 28, k & 0x0fffffff
        self.subkeys = []
        for n in SHIFTS:
            c, d = rol28(c, n), rol28(d, n)
            self.subkeys.append(permute((c << 28) | d, PC2, 56))

    @staticmethod
    def _f(r, subkey):
        x = permute(r, E, 32) ^ subkey
        out = 0
        for i in range(8):
            six = (x >> (42 - 6*i)) & 0x3f
            row = ((six & 0x20) >> 4) | (six & 1)
            col = (six >> 1) & 0xf
            out = (out << 4) | SBOX[i][row][col]
        return permute(out, P, 32)

    def _crypt(self, block, decrypt=False, trace=None):
        if len(block) != 8:
            raise ValueError("DES block must be 8 bytes")
        x = permute(int.from_bytes(block, "big"), IP, 64)
        l, r = x >> 32, x & 0xffffffff
        if trace is not None:
            trace.append((0, l, r, None))
        keys = self.subkeys[::-1] if decrypt else self.subkeys
        for i, key in enumerate(keys, 1):
            l, r = r, (l ^ self._f(r, key)) & 0xffffffff
            if trace is not None:
                trace.append((i, l, r, key))
        return permute((r << 32) | l, FP, 64).to_bytes(8, "big")

    def encrypt_block(self, block, trace=None):
        return self._crypt(block, trace=trace)

    def decrypt_block(self, block):
        return self._crypt(block, decrypt=True)

    @staticmethod
    def _check_blocks(data):
        if len(data) % 8:
            raise ValueError("length must be a multiple of 8; padding is explicit")

    def encrypt_ecb(self, data):
        self._check_blocks(data)
        return b"".join(self.encrypt_block(data[i:i+8]) for i in range(0, len(data), 8))

    def decrypt_ecb(self, data):
        self._check_blocks(data)
        return b"".join(self.decrypt_block(data[i:i+8]) for i in range(0, len(data), 8))

    def encrypt_cbc(self, data, iv):
        self._check_blocks(data)
        if len(iv) != 8:
            raise ValueError("IV must be 8 bytes")
        out, prev = bytearray(), iv
        for i in range(0, len(data), 8):
            prev = self.encrypt_block(bytes(a ^ b for a, b in zip(data[i:i+8], prev)))
            out.extend(prev)
        return bytes(out)

    def decrypt_cbc(self, data, iv):
        self._check_blocks(data)
        if len(iv) != 8:
            raise ValueError("IV must be 8 bytes")
        out, prev = bytearray(), iv
        for i in range(0, len(data), 8):
            block = data[i:i+8]
            out.extend(a ^ b for a, b in zip(self.decrypt_block(block), prev))
            prev = block
        return bytes(out)


def main():
    import argparse  # standard library, only used by the CLI
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("op", choices=("enc", "dec"))
    p.add_argument("key", help="hexadecimal raw key")
    p.add_argument("data", help="hexadecimal data")
    p.add_argument("--mode", choices=("ECB", "CBC"), default="ECB")
    p.add_argument("--iv", help="hexadecimal CBC IV")
    p.add_argument("--pkcs7", action="store_true")
    args = p.parse_args()
    try:
        cipher = DES(bytes.fromhex(args.key))
        data = bytes.fromhex(args.data)
        if args.pkcs7 and args.op == "enc":
            data = pkcs7_pad(data, cipher.block_size)
        if args.mode == "CBC":
            if args.iv is None:
                raise ValueError("CBC requires --iv")
            out = getattr(cipher, ("encrypt_" if args.op == "enc" else "decrypt_") + "cbc")(data, bytes.fromhex(args.iv))
        else:
            out = getattr(cipher, "encrypt_ecb" if args.op == "enc" else "decrypt_ecb")(data)
        if args.pkcs7 and args.op == "dec":
            out = pkcs7_unpad(out, cipher.block_size)
        print(out.hex())
    except ValueError as e:
        p.error(str(e))


if __name__ == "__main__":
    main()
