---
title: 05 AES：状态矩阵与模式优先，魔改题要抓 AddRoundKey 前后状态
date: 2026-10-09T23:05:59+08:00
lastmod: 2026-10-10T10:49:44+08:00
---

# 05 AES：状态矩阵与模式优先，魔改题要抓 AddRoundKey 前后状态

# AES：SubBytes、ShiftRows、MixColumns、AddRoundKey

AES 以 128 位状态矩阵为核心，经过轮密钥扩展和多轮变换：SubBytes、ShiftRows、MixColumns、AddRoundKey；最后一轮省略 MixColumns。

> 看雪式复盘原则：先确认数据边界，再确认算法轮廓；先做可逆最小实验，再对照汇编逐项核对。

## 0x00 先给结论

CTF 中看到算法名，不要直接套库。先记录输入长度、字节序、分组边界、密钥来源、常量、轮数、模式和比较点；然后用 Python 写出一个可逆参考实现，最后再把魔改点逐个 diff。

## 0x01 算法逻辑：把四个名字展开成可逐字节验证的动作

### 1.1 分组、密钥与状态布局

AES 的分组固定为 16 字节。16/24/32 字节密钥分别对应 Nk=4/6/8 个 32 位字、Nr=10/12/14 轮。下面两份代码全部支持 AES-128、AES-192 和 AES-256，单块接口不隐式填充，ECB/CBC 则处理任意整块数。

状态使用列优先布局，不用本机整数端序猜矩阵：state[4*c+r] 就是第 r 行、第 c 列。输入 00 11 22 ... ff 对应：

```text
00 44 88 cc
11 55 99 dd
22 66 aa ee
33 77 bb ff
```

### 1.2 GF(2^8) 与 S 盒从零推导

字节乘法在 GF(2<sup>8) 中进行，模多项式为 x</sup>8+x<sup>4+x</sup>3+x+1（0x11b）。加法等于 XOR；乘以 2 时先左移，原最高位为 1 则约减 0x11b。只保留低 8 位时，C 写成 XOR 0x1b 等价，不能误当普通整数乘法。

S 盒不是这里偷偷调用的内置函数：非零 x 的逆元为 x^254；0 的逆元按 0 处理。设逆元为 a，S(x)=a XOR ROL8(a,1) XOR ROL8(a,2) XOR ROL8(a,3) XOR ROL8(a,4) XOR 0x63。代码枚举 256 个输入构造 SBOX，同时反向填充 INV_SBOX。SubBytes 就是逐字节查表。

### 1.3 ShiftRows 和 MixColumns

ShiftRows 将第 r 行向左循环移动 r 个位置；逆操作向右移动。对平坦列优先数组，正向的新 state[4*c+r] 来自旧 state[4*((c+r)%4)+r]，解密用 (c-r)%4。C 先复制到临时数组再覆盖，避免原地循环破坏后面的源字节。

MixColumns 对每一列独立做下面的矩阵乘法；所有乘法是 gf_mul，所有相加是 XOR。解密使用右侧逆矩阵。

```text
正向                   逆向（十六进制）
02 03 01 01            0e 0b 0d 09
01 02 03 01            09 0e 0b 0d
01 01 02 03            0d 09 0e 0b
03 01 01 02            0b 0d 09 0e
```

AddRoundKey 是 state 与本轮 16 字节轮密钥逐字节 XOR。它的逆仍然是同一轮密钥 XOR。

### 1.4 KeyExpansion 不等于重复原始 key

原始 key 拆成 Nk 个四字节字 w[i]。随后生成总共 4*(Nr+1) 个字。每一步先取 temp=w[i-1]：

```text
i % Nk == 0:
    temp = SubWord(RotWord(temp))
    temp[0] ^= Rcon
    Rcon = gf_mul(Rcon, 2)
AES-256 且 i % Nk == 4:
    temp = SubWord(temp)
w[i] = w[i-Nk] XOR temp
```

Rcon 从 01 开始，每生成一组时更新一次；AES-256 的额外 SubWord 容易漏掉。第 r 轮取 w[4*r] 到 w[4*r+3] 作为 16 字节轮密钥。下方 Python 的 round_keys 可直接输出，C 将它们连续存入 ctx.round_keys。

### 1.5 加密与解密的精确顺序

```text
加密：
  AddRoundKey(K0)
  r=1..Nr-1: SubBytes -> ShiftRows -> MixColumns -> AddRoundKey(Kr)
  r=Nr:      SubBytes -> ShiftRows -> AddRoundKey(KNr)

解密（本代码使用标准逆变换，不预先变换轮密钥）：
  AddRoundKey(KNr)
  r=Nr-1..1: InvShiftRows -> InvSubBytes -> AddRoundKey(Kr) -> InvMixColumns
  r=0:       InvShiftRows -> InvSubBytes -> AddRoundKey(K0)
```

最后一轮不做 MixColumns。不能只把加密循环倒过来却忘记逆矩阵，也不能拿适用于“等价逆密码”的预处理轮密钥混入这个实现。

### 1.6 模式与显式填充

ECB 每块独立。CBC 设置 C0=IV，加密 Ci=E(Pi XOR C(i-1))，解密 Pi=D(Ci) XOR C(i-1)。C 的 CBC 原地解密先保存当前密文，再写明文，防止破坏下一块的链值。

PKCS#7 的补齐量 n=block_size-len%block_size；数据已经整块时也补一整块。解填充必须同时验证总长度、末字节范围以及尾部全部 n 个字节；不能只删最后一个字节指示的长度。算法本体、模式、padding 分开便于处理 CTF 自定义补零或明文长度。

## 0x02 逆向识别指纹

- S 盒 0x63 开头的 256 字节表、Rcon、GF(2^8) 乘法和 16 字节状态是识别重点。
- AES-128/192/256 的轮数分别为 10/12/14；内联实现通常有明显的 T-table 或 xtime。
- ECB 无 IV、CBC 有 XOR 前一块、CTR 生成 nonce+counter keystream，模式差异比算法名更重要。

## 0x03 CTF 遇到时怎么处理

1. 先确定 key/iv 的来源和长度，再判断模式；不要先猜明文。
2. 对一个 16 字节块记录 AddRoundKey、SubBytes 后状态，和下方纯 Python 的 trace 逐阶段对比。
3. 如果是库调用，hook AES 解密返回值或比较前 buffer，通常比逆完整实现快。
4. 检查 PKCS#7、零填充、手工 trim 和多层 base64/hex。

## 0x04 魔改增强：不要猜，直接做差分

- 减少轮数、删除 MixColumns、替换 S 盒、改变 state 的行列映射都是常见魔改。
- key schedule 可能只生成一把 key，或者把 round key 与输入异或顺序调换。
- 常见“增强”是 AES 外包一层 XOR/TEA/编码；按数据流从外到内拆层。

## 0x05 纯 Python 完整实现

本实现仅在命令行解析时使用标准库 argparse；加密核心完全由本文代码执行。没有 Crypto、cryptography、OpenSSL 子进程或其他加密库。以下代码可整块保存成 aes_pure.py 独立运行，不需要 pip install。

```python
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
```

### Python 运行与固定答案

```powershell
python -X utf8 "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.py" enc 000102030405060708090a0b0c0d0e0f 00112233445566778899aabbccddeeff
python -X utf8 "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.py" dec 000102030405060708090a0b0c0d0e0f 69c4e0d86a7b0430d8cdb78070b4c55a
```

```text
加密输出：69c4e0d86a7b0430d8cdb78070b4c55a
解密输出：00112233445566778899aabbccddeeff
```

### 纯 C99 完整实现

源码只包含标准 C 头文件。内部完成 S 盒/置换、密钥调度和正逆轮函数，ECB/CBC 和显式 PKCS#7 也自行完成；不链接外部密码库。保存后单个文件即可编译，且 Python 与 C 的输出一致。

```c
/* Complete reference cipher, ISO C99, no third-party crypto library.
 * Build: gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic FILE.c -o FILE
 * Block APIs also work with -DCIPHER_NO_MAIN, without the command-line driver.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint8_t round_keys[240];
    uint8_t sbox[256], inv_sbox[256];
    unsigned rounds;
} aes_ctx;

static uint8_t gf_mul(uint8_t a, uint8_t b) {
    uint8_t out = 0;
    unsigned i;
    for (i = 0; i < 8; ++i) {
        if (b & 1u) out ^= a;
        a = (uint8_t)((a << 1) ^ ((a & 0x80u) ? 0x1bu : 0u));
        b >>= 1;
    }
    return out;
}

static uint8_t gf_pow(uint8_t a, unsigned n) {
    uint8_t out = 1;
    while (n) {
        if (n & 1u) out = gf_mul(out, a);
        a = gf_mul(a, a);
        n >>= 1;
    }
    return out;
}

static uint8_t rol8(uint8_t x, unsigned n) {
    return (uint8_t)((x << n) | (x >> (8u - n)));
}

int aes_init(aes_ctx *ctx, const uint8_t *key, size_t key_len) {
    unsigned i, j, nk, words;
    uint8_t rcon = 1;
    if (!ctx || !key || (key_len != 16 && key_len != 24 && key_len != 32)) return -1;
    for (i = 0; i < 256; ++i) {
        uint8_t a = i ? gf_pow((uint8_t)i, 254) : 0;
        uint8_t y = (uint8_t)(a ^ rol8(a, 1) ^ rol8(a, 2) ^
                              rol8(a, 3) ^ rol8(a, 4) ^ 0x63u);
        ctx->sbox[i] = y;
        ctx->inv_sbox[y] = (uint8_t)i;
    }
    nk = (unsigned)key_len / 4;
    ctx->rounds = nk + 6;
    words = 4 * (ctx->rounds + 1);
    memcpy(ctx->round_keys, key, key_len);
    for (i = nk; i < words; ++i) {
        uint8_t t[4];
        memcpy(t, ctx->round_keys + 4 * (i - 1), 4);
        if (i % nk == 0) {
            uint8_t first = t[0];
            t[0] = ctx->sbox[t[1]];
            t[1] = ctx->sbox[t[2]];
            t[2] = ctx->sbox[t[3]];
            t[3] = ctx->sbox[first];
            t[0] ^= rcon;
            rcon = gf_mul(rcon, 2);
        } else if (nk == 8 && i % nk == 4) {
            for (j = 0; j < 4; ++j) t[j] = ctx->sbox[t[j]];
        }
        for (j = 0; j < 4; ++j)
            ctx->round_keys[4*i + j] = ctx->round_keys[4*(i - nk) + j] ^ t[j];
    }
    return 0;
}

static void add_key(uint8_t s[16], const uint8_t key[16]) {
    unsigned i;
    for (i = 0; i < 16; ++i) s[i] ^= key[i];
}

static void sub_bytes(uint8_t s[16], const uint8_t box[256]) {
    unsigned i;
    for (i = 0; i < 16; ++i) s[i] = box[s[i]];
}

static void shift_rows(uint8_t s[16], int inverse) {
    uint8_t t[16];
    unsigned c, r;
    for (c = 0; c < 4; ++c)
        for (r = 0; r < 4; ++r) {
            unsigned src = inverse ? ((c + 4 - r) % 4) : ((c + r) % 4);
            t[4*c + r] = s[4*src + r];
        }
    memcpy(s, t, 16);
}

static void mix_columns(uint8_t s[16], int inverse) {
    static const uint8_t forward[4][4] = {
        {2,3,1,1},{1,2,3,1},{1,1,2,3},{3,1,1,2}
    };
    static const uint8_t backward[4][4] = {
        {14,11,13,9},{9,14,11,13},{13,9,14,11},{11,13,9,14}
    };
    const uint8_t (*m)[4] = inverse ? backward : forward;
    unsigned c, r, j;
    for (c = 0; c < 4; ++c) {
        uint8_t a[4];
        memcpy(a, s + 4*c, 4);
        for (r = 0; r < 4; ++r) {
            uint8_t v = 0;
            for (j = 0; j < 4; ++j) v ^= gf_mul(a[j], m[r][j]);
            s[4*c + r] = v;
        }
    }
}

void aes_encrypt_block(const aes_ctx *ctx, const uint8_t in[16], uint8_t out[16]) {
    uint8_t s[16];
    unsigned r;
    memcpy(s, in, 16);
    add_key(s, ctx->round_keys);
    for (r = 1; r <= ctx->rounds; ++r) {
        sub_bytes(s, ctx->sbox);
        shift_rows(s, 0);
        if (r != ctx->rounds) mix_columns(s, 0);
        add_key(s, ctx->round_keys + 16*r);
    }
    memcpy(out, s, 16);
}

void aes_decrypt_block(const aes_ctx *ctx, const uint8_t in[16], uint8_t out[16]) {
    uint8_t s[16];
    int r;
    memcpy(s, in, 16);
    add_key(s, ctx->round_keys + 16*ctx->rounds);
    for (r = (int)ctx->rounds - 1; r >= 0; --r) {
        shift_rows(s, 1);
        sub_bytes(s, ctx->inv_sbox);
        add_key(s, ctx->round_keys + 16*(unsigned)r);
        if (r) mix_columns(s, 1);
    }
    memcpy(out, s, 16);
}

/* iv == NULL selects ECB; a 16-byte IV selects CBC. No implicit padding.
 * Separate buffers or exactly in == out are supported. No partial overlap.
 */
int aes_crypt_blocks(const aes_ctx *ctx, int decrypt,
                       const uint8_t *in, uint8_t *out, size_t len,
                       const uint8_t *iv) {
    uint8_t prev[16] = {0}, t[16], block[16];
    size_t i;
    unsigned j;
    if (!ctx || (!in && len) || (!out && len) || len % 16) return -1;
    if (iv) memcpy(prev, iv, 16);
    for (i = 0; i < len; i += 16) {
        memcpy(block, in + i, 16);
        if (decrypt) {
            aes_decrypt_block(ctx, block, t);
            if (iv) for (j = 0; j < 16; ++j) t[j] ^= prev[j];
            memcpy(prev, block, 16);
        } else {
            if (iv) for (j = 0; j < 16; ++j) block[j] ^= prev[j];
            aes_encrypt_block(ctx, block, t);
            memcpy(prev, t, 16);
        }
        memcpy(out + i, t, 16);
    }
    return 0;
}

#ifndef CIPHER_NO_MAIN
static int hex_digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static uint8_t *parse_hex(const char *s, size_t *len) {
    size_t n = strlen(s), i;
    uint8_t *out;
    if (n % 2) return NULL;
    *len = n / 2;
    out = (uint8_t *)malloc(*len ? *len : 1);
    if (!out) return NULL;
    for (i = 0; i < *len; ++i) {
        int a = hex_digit(s[2*i]), b = hex_digit(s[2*i + 1]);
        if (a < 0 || b < 0) { free(out); return NULL; }
        out[i] = (uint8_t)((a << 4) | b);
    }
    return out;
}

int main(int argc, char **argv) {
    aes_ctx ctx;
    uint8_t *key = NULL, *data = NULL, *iv = NULL, *out = NULL;
    size_t key_len = 0, len = 0, iv_len = 0, i;
    int decrypt, cbc, padding, rc = 2;
    const char *mode, *pad_mode;
    if (argc < 4 || argc > 7) {
        fprintf(stderr, "usage: %s enc|dec KEYHEX DATAHEX [ECB|CBC] [IVHEX|-] [NONE|PKCS7]\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "enc") && strcmp(argv[1], "dec")) {
        fprintf(stderr, "operation must be enc or dec\n"); return 2;
    }
    decrypt = !strcmp(argv[1], "dec");
    mode = argc > 4 ? argv[4] : "ECB";
    pad_mode = argc > 6 ? argv[6] : "NONE";
    if (strcmp(mode, "ECB") && strcmp(mode, "CBC")) {
        fprintf(stderr, "mode must be ECB or CBC\n"); return 2;
    }
    if (strcmp(pad_mode, "NONE") && strcmp(pad_mode, "PKCS7")) {
        fprintf(stderr, "padding must be NONE or PKCS7\n"); return 2;
    }
    cbc = !strcmp(mode, "CBC");
    padding = !strcmp(pad_mode, "PKCS7");
    key = parse_hex(argv[2], &key_len); data = parse_hex(argv[3], &len);
    if (!key || !data) { fprintf(stderr, "invalid hex or allocation failure\n"); goto done; }
    if (aes_init(&ctx, key, key_len)) { fprintf(stderr, "invalid key length\n"); goto done; }
    if (cbc) {
        if (argc < 6) { fprintf(stderr, "CBC requires an IV\n"); goto done; }
        iv = parse_hex(argv[5], &iv_len);
        if (!iv || iv_len != 16) { fprintf(stderr, "invalid IV length\n"); goto done; }
    } else if (argc > 5 && strcmp(argv[5], "-")) {
        fprintf(stderr, "ECB uses no IV; use - as placeholder\n"); goto done;
    }
    if (padding && !decrypt) {
        size_t pad = 16 - len % 16;
        uint8_t *grown;
        if (len > SIZE_MAX - pad) { fprintf(stderr, "size overflow\n"); goto done; }
        grown = (uint8_t *)realloc(data, len + pad);
        if (!grown) { fprintf(stderr, "allocation failure\n"); goto done; }
        data = grown; memset(data + len, (int)pad, pad); len += pad;
    }
    if (len % 16 || (padding && decrypt && !len)) {
        fprintf(stderr, "invalid data length\n"); goto done;
    }
    out = (uint8_t *)malloc(len ? len : 1);
    if (!out) { fprintf(stderr, "allocation failure\n"); goto done; }
    if (aes_crypt_blocks(&ctx, decrypt, data, out, len, iv)) {
        fprintf(stderr, "cipher error\n"); goto done;
    }
    if (padding && decrypt) {
        size_t pad = out[len - 1];
        if (!pad || pad > 16) { fprintf(stderr, "invalid PKCS#7 padding\n"); goto done; }
        for (i = 0; i < pad; ++i)
            if (out[len - 1 - i] != pad) { fprintf(stderr, "invalid PKCS#7 padding\n"); goto done; }
        len -= pad;
    }
    for (i = 0; i < len; ++i) printf("%02x", (unsigned)out[i]);
    putchar('\n'); rc = 0;
done:
    free(key); free(data); free(iv); free(out);
    return rc;
}
#endif
```

### C 编译、运行与作为函数复用

```powershell
gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.c" -o "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.exe"
& "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.exe" enc 000102030405060708090a0b0c0d0e0f 00112233445566778899aabbccddeeff
& "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.exe" dec 000102030405060708090a0b0c0d0e0f 69c4e0d86a7b0430d8cdb78070b4c55a
```

```text
加密输出：69c4e0d86a7b0430d8cdb78070b4c55a
解密输出：00112233445566778899aabbccddeeff
```

C 的 aes_init 初始化上下文，aes_encrypt_block / aes_decrypt_block 是单块接口；aes_crypt_blocks 的 iv=NULL 选择 ECB，非NULL选择 CBC。调用者给 IV 分配完整块长并按整块长度提供数据。传入 CIPHER_NO_MAIN 宏可禁用命令行入口，用于自己的 C 程序；原地 in==out 已通过单独测试。

### CBC 与 PKCS#7 的使用例子

Python 在需要时使用 --pkcs7，不使用时要求输入整块。C 第4到6个参数依次为模式、IV和padding；ECB 使用 '-' 作为没有IV的占位。字符串数据的十六进制例子 666c61677b64656d6f7d 对应 flag{demo}。

```powershell
python -X utf8 "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.py" enc 000102030405060708090a0b0c0d0e0f 666c61677b64656d6f7d --mode CBC --iv 000102030405060708090a0b0c0d0e0f --pkcs7
& "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.exe" enc 000102030405060708090a0b0c0d0e0f 666c61677b64656d6f7d CBC 000102030405060708090a0b0c0d0e0f PKCS7
```

解密把 enc 换成 dec，数据参数换为上一步的密文，key/IV/mode/padding 保持一致。

## 0x06 常见坑点

- AES 状态在内存中通常是列主序，直接按字符串下标看会错位。
- CBC 解密公式是 D(C_i) xor C_{i-1}；IV 不应当忘记。
- 先确认是 16/24/32 字节 key，短口令往往经过 MD5/SHA256/补零。

## 0x07 复盘模板

```text
样本：sample
算法假设：AES
输入长度：...
密钥来源：...
字节序：...
常量/轮数：...
已确认：...
未确认：...
最终校验点：...
FLAG：...
```

‍

## 0x07.1 魔改定位：明确修改哪个函数

- S 盒替换：在 make_sboxes / aes_init 中换表，同时检查它是否为双射并重建逆表。若非双射，逐字节 INV_SBOX 不再成立。
- 行列交换：先核对 state[4*c+r] 与 ShiftRows 的来源位置；打印第一轮就能区分“错误端序”和“改了行移位”。
- 轮数改变：同时调整轮密钥生成长度、encrypt/decrypt 的循环和最后一轮判断，不能只改一个循环上限。C round_keys[240] 容量对应标准最多14轮，增加轮数先修改容量与边界。
- MixColumns 修改：改矩阵后需推导其 GF(2^8) 逆矩阵；删除此步骤则相应删除逆步骤。只改正向函数会让解密失败。
- key schedule 修改：在 round_keys 上逐轮 diff，重点检查 Rcon、RotWord 和 AES-256 的额外 SubWord，而不是先对密文穷举。
- 编码与反馈叠加：先把前置 XOR/倒序、CBC IV、尾部校验分层，保留第一处状态差异。

用 trace 观察标准第一轮，再在题目内存相同位置取16字节对照：

```python
from aes_pure import AES
trace = []
a = AES(bytes.fromhex("000102030405060708090a0b0c0d0e0f"))
a.encrypt_block(bytes.fromhex("00112233445566778899aabbccddeeff"), trace)
for round_no, stage, state in trace:
    print(round_no, stage, state)
for round_no, key in enumerate(a.round_keys):
    print("round_key", round_no, bytes(key).hex())
```

## 0x08 本次实际验证（2026-10-10）

- Python/C 全部通过 AES-128、AES-192、AES-256 的固定单块加解密答案，以及 SP800-38A 的三种密钥四块 CBC 答案。
- DES 三组已知答案、K1/K16、IP 和第一轮中间值通过；奇偶位、互补性质与弱密钥性质通过。
- 随机 ECB/CBC 差分、PKCS#7 的空串/整块/非整块与非法填充、错误 key/block/IV 的拒绝通过。
- C99 严格编译通过，C 原地 ECB/CBC 加解密也通过。这里只声明这些确定测试结果，不把往返成功当成标准答案的替代。

```text
CRYPTO_TESTS PASS checks=924 c_invocations=238
C_IN_PLACE AES+DES ECB+CBC PASS
```

## 0x09 原始资料与本地文件

FIPS 197：AES 算法、密钥扩展与逆变换；2001 原版 Appendix C 提供本文三组单块答案，2023 update 1 保持算法不变。  
SP 800-38A Appendix F.2：AES CBC 多块测试向量与模式定义。源码是本文独立实现；测试脚本只使用 Python 标准库和本机 C 编译器。

完整 Python 文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.py  
完整 C 文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\aes_pure.c  
综合测试文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\test_crypto.py  
原地测试文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\test_inplace.c  
本次测试日志：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\test-output.txt

Python 支持 --mode ECB/CBC、--iv、--pkcs7；C 支持 ECB/CBC 与 NONE/PKCS7。这些实现的表与控制流可直接用于 CTF 逐轮取证。
