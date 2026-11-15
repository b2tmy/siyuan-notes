#!/usr/bin/env python3
"""AES-128/192/256: complete pure-Python block, ECB and CBC implementation.
No crypto library. Byte state is column-major: state[4*c+r].
"""

def gf_mul(a, b):
    """GF(2^8), modulus x^8+x^4+x^3+x+1 (0x11b)."""
    out = 0
    for _ in range(8):
        if b & 1:
            out ^= a
        a = ((a << 1) ^ (0x11b if a & 0x80 else 0)) & 0xff
        b >>= 1
    return out


def gf_pow(a, n):
    out = 1
    while n:
        if n & 1:
            out = gf_mul(out, a)
        a = gf_mul(a, a)
        n >>= 1
    return out


def rol8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xff


def make_sboxes():
    sbox, inverse = [], [0] * 256
    for x in range(256):
        a = gf_pow(x, 254) if x else 0
        y = a ^ rol8(a, 1) ^ rol8(a, 2) ^ rol8(a, 3) ^ rol8(a, 4) ^ 0x63
        sbox.append(y)
        inverse[y] = x
    return tuple(sbox), tuple(inverse)


SBOX, INV_SBOX = make_sboxes()


def pkcs7_pad(data, block_size=16):
    if not 1 <= block_size <= 255:
        raise ValueError("block size must be 1..255")
    n = block_size - len(data) % block_size
    return data + bytes([n]) * n


def pkcs7_unpad(data, block_size=16):
    if not 1 <= block_size <= 255:
        raise ValueError("block size must be 1..255")
    if not data or len(data) % block_size:
        raise ValueError("invalid padded length")
    n = data[-1]
    if not 1 <= n <= block_size or data[-n:] != bytes([n]) * n:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-n]


class AES:
    block_size = 16

    def __init__(self, key):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24 or 32 bytes")
        nk = len(key) // 4
        self.rounds = nk + 6
        words = [list(key[i:i + 4]) for i in range(0, len(key), 4)]
        rcon = 1
        for i in range(nk, 4 * (self.rounds + 1)):
            t = words[i - 1][:]
            if i % nk == 0:
                t = [SBOX[x] for x in t[1:] + t[:1]]
                t[0] ^= rcon
                rcon = gf_mul(rcon, 2)
            elif nk == 8 and i % nk == 4:  # AES-256 extra SubWord
                t = [SBOX[x] for x in t]
            words.append([a ^ b for a, b in zip(words[i - nk], t)])
        self.round_keys = [sum(words[4*r:4*r + 4], [])
                           for r in range(self.rounds + 1)]

    @staticmethod
    def _add_key(state, key):
        return [a ^ b for a, b in zip(state, key)]

    @staticmethod
    def _shift_rows(state, inverse=False):
        return [state[4 * ((c - r if inverse else c + r) % 4) + r]
                for c in range(4) for r in range(4)]

    @staticmethod
    def _mix_columns(state, inverse=False):
        matrix = ((14, 11, 13, 9), (9, 14, 11, 13),
                  (13, 9, 14, 11), (11, 13, 9, 14)) if inverse else (
                  (2, 3, 1, 1), (1, 2, 3, 1), (1, 1, 2, 3), (3, 1, 1, 2))
        out = []
        for c in range(4):
            a = state[4*c:4*c + 4]
            for row in matrix:
                out.append(gf_mul(a[0], row[0]) ^ gf_mul(a[1], row[1]) ^
                           gf_mul(a[2], row[2]) ^ gf_mul(a[3], row[3]))
        return out

    def encrypt_block(self, block, trace=None):
        if len(block) != 16:
            raise ValueError("AES block must be 16 bytes")
        s = self._add_key(list(block), self.round_keys[0])
        if trace is not None:
            trace.append((0, "AddRoundKey", bytes(s).hex()))
        for r in range(1, self.rounds + 1):
            s = [SBOX[x] for x in s]
            if trace is not None:
                trace.append((r, "SubBytes", bytes(s).hex()))
            s = self._shift_rows(s)
            if trace is not None:
                trace.append((r, "ShiftRows", bytes(s).hex()))
            if r != self.rounds:
                s = self._mix_columns(s)
                if trace is not None:
                    trace.append((r, "MixColumns", bytes(s).hex()))
            s = self._add_key(s, self.round_keys[r])
            if trace is not None:
                trace.append((r, "AddRoundKey", bytes(s).hex()))
        return bytes(s)

    def decrypt_block(self, block):
        if len(block) != 16:
            raise ValueError("AES block must be 16 bytes")
        s = self._add_key(list(block), self.round_keys[self.rounds])
        for r in range(self.rounds - 1, -1, -1):
            s = self._shift_rows(s, inverse=True)
            s = [INV_SBOX[x] for x in s]
            s = self._add_key(s, self.round_keys[r])
            if r:
                s = self._mix_columns(s, inverse=True)
        return bytes(s)

    @staticmethod
    def _check_blocks(data):
        if len(data) % 16:
            raise ValueError("length must be a multiple of 16; padding is explicit")

    def encrypt_ecb(self, data):
        self._check_blocks(data)
        return b"".join(self.encrypt_block(data[i:i+16]) for i in range(0, len(data), 16))

    def decrypt_ecb(self, data):
        self._check_blocks(data)
        return b"".join(self.decrypt_block(data[i:i+16]) for i in range(0, len(data), 16))

    def encrypt_cbc(self, data, iv):
        self._check_blocks(data)
        if len(iv) != 16:
            raise ValueError("IV must be 16 bytes")
        out, prev = bytearray(), iv
        for i in range(0, len(data), 16):
            prev = self.encrypt_block(bytes(a ^ b for a, b in zip(data[i:i+16], prev)))
            out.extend(prev)
        return bytes(out)

    def decrypt_cbc(self, data, iv):
        self._check_blocks(data)
        if len(iv) != 16:
            raise ValueError("IV must be 16 bytes")
        out, prev = bytearray(), iv
        for i in range(0, len(data), 16):
            block = data[i:i+16]
            out.extend(a ^ b for a, b in zip(self.decrypt_block(block), prev))
            prev = block
        return bytes(out)


def main():
    import argparse  # standard library, only used by the CLI
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("op", choices=("enc", "dec"))
    p.add_argument("key", help="hexadecimal raw key")
    p.add_argument("data", help="hexadecimal data; use empty string for no bytes")
    p.add_argument("--mode", choices=("ECB", "CBC"), default="ECB")
    p.add_argument("--iv", help="hexadecimal CBC IV")
    p.add_argument("--pkcs7", action="store_true")
    args = p.parse_args()
    try:
        cipher = AES(bytes.fromhex(args.key))
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
