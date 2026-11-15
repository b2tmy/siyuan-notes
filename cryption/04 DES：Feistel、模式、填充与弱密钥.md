---
title: 04 DES：Feistel、模式、填充与弱密钥
date: 2026-10-09T23:10:06+08:00
lastmod: 2026-10-10T10:49:44+08:00
---

# 04 DES：Feistel、模式、填充与弱密钥

# DES：64 位分组与 16 轮 Feistel

DES 以 64 位分组工作，有效密钥为 56 位，经过初始置换、16 轮 Feistel、逆初始置换得到密文。轮函数包含扩展、与子密钥异或、S 盒替换和 P 置换。

> 看雪式复盘原则：先确认数据边界，再确认算法轮廓；先做可逆最小实验，再对照汇编逐项核对。

## 0x00 先给结论

CTF 中看到算法名，不要直接套库。先记录输入长度、字节序、分组边界、密钥来源、常量、轮数、模式和比较点；然后用 Python 写出一个可逆参考实现，最后再把魔改点逐个 diff。

## 0x01 算法逻辑：从初始置换走到最后交换

### 1.1 数据与位编号

DES 处理 8 字节分组，外部 key 长 8 字节，其中 8 个奇偶校验位不参与子密钥生成，因此有效密钥为 56 位。下面 Python 与 C 都按大端字节序载入 64 位分组。置换表以 1 为起点，从最高位数：表元素 pos 对应 (x>>(width-pos))&1。

permute(x, table, width) 顺序取出表指定的位并向左拼接。它用于 IP/FP、E、P、PC1/PC2，参数 width 必须是该阶段的输入宽度，而不是输出位数：IP=64，E=32，PC1=64，PC2=56。

### 1.2 PC-1、28 位旋转与 PC-2

PC-1 将 64 位 key 挑选、重排成 56 位，分成 C0 与 D0，各 28 位。每轮对 C/D 循环左移并截断到 28 位，再用 PC-2 选出 48 位子密钥。

```text
每轮左移位数：1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1
Ci = ROL28(C(i-1), shift[i])
Di = ROL28(D(i-1), shift[i])
Ki = PC2((Ci << 28) | Di)  # 输入56位，输出48位
```

对于 key=133457799bbcdff1，应得到 K1=1b02effc7072，K16=cb3d8b0e17f5。翻转每字节最低位只改变奇偶校验位，不改变本实现的密文。

### 1.3 f(R,K) 的四个阶段

E 将 32 位 R 扩展为 48 位（含边界位重复），与 48 位子密钥 XOR，然后从高到低拆成 8 个 6 位分组，分别输入 S1..S8。每个 S 盒有 4 行、16 列：首尾两位组成行，中间四位组成列。

```text
six = (x >> (42 - 6*i)) & 0x3f
row = ((six & 0x20) >> 4) | (six & 1)
col = (six >> 1) & 0x0f
value = SBOX[i][row][col]  # 输出4位
```

8 个输出按高到低拼成 32 位，再经过 P 置换。S 盒不需要可逆：Feistel 的可逆性来自左右半部保留与 XOR，不来自单独反解 S 盒。

### 1.4 16 轮 Feistel、最后交换与解密

输入先经过 IP，拆为 L0/R0。每轮 Li=R(i-1)，Ri=L(i-1) XOR f(R(i-1),Ki)。完成第16轮后，拼接 R16||L16（注意交换），再经过 FP=IP^-1 得到密文。

解密仍执行相同的 IP、Feistel、最后交换与 FP，只把子密钥顺序从 K1..K16 改成 K16..K1；并非把 IP/FP 任意调换。

对于明文 0123456789abcdef、key 133457799bbcdff1，IP 后 L0=cc00ccff、R0=f0aaf0aa；第一轮后 L1=f0aaf0aa、R1=ef4a6544；密文应为 85e813540f0ab405。只做往返测试会掩盖“加解密同样写错”问题，所以这些已知答案与中间态分别被断言。

### 1.5 分组模式与 padding

ECB 和 CBC 的链式公式与 AES 相同，DES 的 block_size 换成 8。标准单块接口只接受 8 字节，不自动补齐。可独立调用 PKCS​#7；对于 8 字节块它与 PKCS#5 的补齐字节规则一致。C 命令行的 PKCS7 为显式开关，默认 NONE。

下面包括 IP、FP、E、P、PC1、PC2、轮移位表和八个 S 盒的全部内容，代码中没有“此处略去表格”，没有调用外部加密函数。

## 0x02 逆向识别指纹

- 8 字节 block、16 轮、8 个 S 盒、PC-1/PC-2 与固定置换表是标准指纹。
- 密文长度通常是 8 的倍数；ECB/CBC 的 IV 与 padding 直接影响结果。
- 弱密钥、重复 key、key 只取 8 字节、字符串补零是 CTF 常见入口。

## 0x03 CTF 遇到时怎么处理

1. 确认 key 是 8 字节原始值、十六进制解码值还是 hash 截断值。
2. 确认 ECB/CBC/CFB/OFB、IV、padding；用下方纯 Python / C 实现做多组合验证。
3. 若调用 OpenSSL/CryptoAPI，先从参数和返回 buffer 追踪，不要一开始钻 DES 轮函数。
4. 出现已知明文时，检查是否存在弱 key、固定 IV 或 ECB 重复块。

## 0x04 魔改增强：不要猜，直接做差分

- 把 DES 换成 3DES、只做一轮/逆序轮、替换 S 盒或固定子密钥。
- 将 key 派生、IV 派生、padding 校验藏在校验函数中，是常见的“算法没变，输入变了”。
- 部分题目把 DES 当作代码保护外壳，真正 flag 比较在解密后；优先定位明文落点。

## 0x05 纯 Python 完整实现

本实现仅在命令行解析时使用标准库 argparse；加密核心完全由本文代码执行。没有 Crypto、cryptography、OpenSSL 子进程或其他加密库。以下代码可整块保存成 des_pure.py 独立运行，不需要 pip install。

```python
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
```

### Python 运行与固定答案

```powershell
python -X utf8 "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.py" enc 133457799bbcdff1 0123456789abcdef
python -X utf8 "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.py" dec 133457799bbcdff1 85e813540f0ab405
```

```text
加密输出：85e813540f0ab405
解密输出：0123456789abcdef
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
static const uint8_t IP[64] = {
    58,50,42,34,26,18,10,2,60,52,44,36,28,20,12,4,
    62,54,46,38,30,22,14,6,64,56,48,40,32,24,16,8,
    57,49,41,33,25,17,9,1,59,51,43,35,27,19,11,3,
    61,53,45,37,29,21,13,5,63,55,47,39,31,23,15,7
};
static const uint8_t FP[64] = {
    40,8,48,16,56,24,64,32,39,7,47,15,55,23,63,31,
    38,6,46,14,54,22,62,30,37,5,45,13,53,21,61,29,
    36,4,44,12,52,20,60,28,35,3,43,11,51,19,59,27,
    34,2,42,10,50,18,58,26,33,1,41,9,49,17,57,25
};
static const uint8_t E[48] = {
    32,1,2,3,4,5,4,5,6,7,8,9,8,9,10,11,
    12,13,12,13,14,15,16,17,16,17,18,19,20,21,20,21,
    22,23,24,25,24,25,26,27,28,29,28,29,30,31,32,1
};
static const uint8_t P[32] = {
    16,7,20,21,29,12,28,17,1,15,23,26,5,18,31,10,
    2,8,24,14,32,27,3,9,19,13,30,6,22,11,4,25
};
static const uint8_t PC1[56] = {
    57,49,41,33,25,17,9,1,58,50,42,34,26,18,10,2,
    59,51,43,35,27,19,11,3,60,52,44,36,63,55,47,39,
    31,23,15,7,62,54,46,38,30,22,14,6,61,53,45,37,
    29,21,13,5,28,20,12,4
};
static const uint8_t PC2[48] = {
    14,17,11,24,1,5,3,28,15,6,21,10,23,19,12,4,
    26,8,16,7,27,20,13,2,41,52,31,37,47,55,30,40,
    51,45,33,48,44,49,39,56,34,53,46,42,50,36,29,32
};
static const uint8_t SHIFTS[16] = {
    1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1
};
static const uint8_t SBOX[8][4][16] = {
    {
        {14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7},
        {0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8},
        {4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0},
        {15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13}
    },
    {
        {15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10},
        {3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5},
        {0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15},
        {13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9}
    },
    {
        {10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8},
        {13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1},
        {13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7},
        {1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12}
    },
    {
        {7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15},
        {13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9},
        {10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4},
        {3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14}
    },
    {
        {2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9},
        {14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6},
        {4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14},
        {11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3}
    },
    {
        {12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11},
        {10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8},
        {9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6},
        {4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13}
    },
    {
        {4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1},
        {13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6},
        {1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2},
        {6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12}
    },
    {
        {13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7},
        {1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2},
        {7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8},
        {2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11}
    }
};

typedef struct { uint64_t subkeys[16]; } des_ctx;

static uint64_t permute(uint64_t x, const uint8_t *table,
                        unsigned count, unsigned width) {
    uint64_t out = 0;
    unsigned i;
    for (i = 0; i < count; ++i)
        out = (out << 1) | ((x >> (width - table[i])) & UINT64_C(1));
    return out;
}

static uint64_t load64_be(const uint8_t p[8]) {
    uint64_t v = 0;
    unsigned i;
    for (i = 0; i < 8; ++i) v = (v << 8) | p[i];
    return v;
}

static void store64_be(uint8_t p[8], uint64_t v) {
    unsigned i;
    for (i = 8; i > 0; --i) { p[i - 1] = (uint8_t)v; v >>= 8; }
}

static uint32_t rol28(uint32_t x, unsigned n) {
    return ((x << n) | (x >> (28 - n))) & UINT32_C(0x0fffffff);
}

int des_init(des_ctx *ctx, const uint8_t *key, size_t key_len) {
    uint64_t k;
    uint32_t c, d;
    unsigned i;
    if (!ctx || !key || key_len != 8) return -1;
    k = permute(load64_be(key), PC1, 56, 64);
    c = (uint32_t)(k >> 28);
    d = (uint32_t)k & UINT32_C(0x0fffffff);
    for (i = 0; i < 16; ++i) {
        c = rol28(c, SHIFTS[i]); d = rol28(d, SHIFTS[i]);
        ctx->subkeys[i] = permute(((uint64_t)c << 28) | d, PC2, 48, 56);
    }
    return 0;
}

static uint32_t feistel(uint32_t r, uint64_t key) {
    uint64_t x = permute(r, E, 48, 32) ^ key;
    uint32_t out = 0;
    unsigned i;
    for (i = 0; i < 8; ++i) {
        unsigned six = (unsigned)((x >> (42 - 6*i)) & UINT64_C(0x3f));
        unsigned row = ((six & 0x20u) >> 4) | (six & 1u);
        unsigned col = (six >> 1) & 15u;
        out = (out << 4) | SBOX[i][row][col];
    }
    return (uint32_t)permute(out, P, 32, 32);
}

static void des_block(const des_ctx *ctx, const uint8_t in[8],
                       uint8_t out[8], int decrypt) {
    uint64_t x = permute(load64_be(in), IP, 64, 64);
    uint32_t l = (uint32_t)(x >> 32), r = (uint32_t)x;
    unsigned i;
    for (i = 0; i < 16; ++i) {
        uint32_t next = l ^ feistel(r, ctx->subkeys[decrypt ? 15 - i : i]);
        l = r; r = next;
    }
    x = permute(((uint64_t)r << 32) | l, FP, 64, 64);
    store64_be(out, x);
}

void des_encrypt_block(const des_ctx *ctx, const uint8_t in[8], uint8_t out[8]) {
    des_block(ctx, in, out, 0);
}

void des_decrypt_block(const des_ctx *ctx, const uint8_t in[8], uint8_t out[8]) {
    des_block(ctx, in, out, 1);
}

/* iv == NULL selects ECB; a 8-byte IV selects CBC. No implicit padding.
 * Separate buffers or exactly in == out are supported. No partial overlap.
 */
int des_crypt_blocks(const des_ctx *ctx, int decrypt,
                       const uint8_t *in, uint8_t *out, size_t len,
                       const uint8_t *iv) {
    uint8_t prev[8] = {0}, t[8], block[8];
    size_t i;
    unsigned j;
    if (!ctx || (!in && len) || (!out && len) || len % 8) return -1;
    if (iv) memcpy(prev, iv, 8);
    for (i = 0; i < len; i += 8) {
        memcpy(block, in + i, 8);
        if (decrypt) {
            des_decrypt_block(ctx, block, t);
            if (iv) for (j = 0; j < 8; ++j) t[j] ^= prev[j];
            memcpy(prev, block, 8);
        } else {
            if (iv) for (j = 0; j < 8; ++j) block[j] ^= prev[j];
            des_encrypt_block(ctx, block, t);
            memcpy(prev, t, 8);
        }
        memcpy(out + i, t, 8);
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
    des_ctx ctx;
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
    if (des_init(&ctx, key, key_len)) { fprintf(stderr, "invalid key length\n"); goto done; }
    if (cbc) {
        if (argc < 6) { fprintf(stderr, "CBC requires an IV\n"); goto done; }
        iv = parse_hex(argv[5], &iv_len);
        if (!iv || iv_len != 8) { fprintf(stderr, "invalid IV length\n"); goto done; }
    } else if (argc > 5 && strcmp(argv[5], "-")) {
        fprintf(stderr, "ECB uses no IV; use - as placeholder\n"); goto done;
    }
    if (padding && !decrypt) {
        size_t pad = 8 - len % 8;
        uint8_t *grown;
        if (len > SIZE_MAX - pad) { fprintf(stderr, "size overflow\n"); goto done; }
        grown = (uint8_t *)realloc(data, len + pad);
        if (!grown) { fprintf(stderr, "allocation failure\n"); goto done; }
        data = grown; memset(data + len, (int)pad, pad); len += pad;
    }
    if (len % 8 || (padding && decrypt && !len)) {
        fprintf(stderr, "invalid data length\n"); goto done;
    }
    out = (uint8_t *)malloc(len ? len : 1);
    if (!out) { fprintf(stderr, "allocation failure\n"); goto done; }
    if (des_crypt_blocks(&ctx, decrypt, data, out, len, iv)) {
        fprintf(stderr, "cipher error\n"); goto done;
    }
    if (padding && decrypt) {
        size_t pad = out[len - 1];
        if (!pad || pad > 8) { fprintf(stderr, "invalid PKCS#7 padding\n"); goto done; }
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
gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.c" -o "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.exe"
& "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.exe" enc 133457799bbcdff1 0123456789abcdef
& "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.exe" dec 133457799bbcdff1 85e813540f0ab405
```

```text
加密输出：85e813540f0ab405
解密输出：0123456789abcdef
```

C 的 des_init 初始化上下文，des_encrypt_block / des_decrypt_block 是单块接口；des_crypt_blocks 的 iv=NULL 选择 ECB，非NULL选择 CBC。调用者给 IV 分配完整块长并按整块长度提供数据。传入 CIPHER_NO_MAIN 宏可禁用命令行入口，用于自己的 C 程序；原地 in==out 已通过单独测试。

### CBC 与 PKCS#7 的使用例子

Python 在需要时使用 --pkcs7，不使用时要求输入整块。C 第4到6个参数依次为模式、IV和padding；ECB 使用 '-' 作为没有IV的占位。字符串数据的十六进制例子 666c61677b64656d6f7d 对应 flag{demo}。

```powershell
python -X utf8 "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.py" enc 133457799bbcdff1 666c61677b64656d6f7d --mode CBC --iv 0001020304050607 --pkcs7
& "C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.exe" enc 133457799bbcdff1 666c61677b64656d6f7d CBC 0001020304050607 PKCS7
```

解密把 enc 换成 dec，数据参数换为上一步的密文，key/IV/mode/padding 保持一致。

## 0x06 常见坑点

- DES key 长度不是任意字符串长度；不足 8 字节时题目可能自行补零。
- 库默认 padding 不同，Crypto.Util.Padding.pad 与手工 PKCS#5/7 要区分。
- 不要因为密文可打印就判断不是 DES，编码层可能在外面。

## 0x07 复盘模板

```text
样本：sample
算法假设：DES
输入长度：...
密钥来源：...
字节序：...
常量/轮数：...
已确认：...
未确认：...
最终校验点：...
FLAG：...
```

## 0x07.1 魔改定位：别把所有差异都叫 S 盒变了

- PC1/PC2 修改：先检查 subkeys。若 K1 就不符，先修 key 位序和调度；不要改 f 去补偿错误。
- 轮旋转、轮数或子密钥倒序：将 SHIFTS、subkeys 长度与轮循环同时记录。C subkeys[16] 是标准16轮容量，扩轮需扩数组与反序索引。
- S 盒修改：把 f 的48位输入、8个 six 与32位输出记录下来。Feistel 即使使用不同甚至非双射 f，也可按逆序子密钥恢复，只要结构保持。
- IP/FP 修改：FP 必须对应 IP 的逆；如果题目移除二者，两端也一起去掉。只做 encrypt/decrypt 往返仍可能隐藏不符合标准的位序。
- 最后交换修改：确认拼接的是 R16||L16 还是 L16||R16；这是常见的一字节不差但整块不对的原因。
- 奇偶位与弱密钥：PC1 丢弃的位不影响密文；不要把64位 key 空间与56位有效 key 混同。测试脚本还覆盖一个弱密钥的双重加密还原性质。

记录第一轮和全部子密钥：

```python
from des_pure import DES
trace = []
d = DES(bytes.fromhex("133457799bbcdff1"))
d.encrypt_block(bytes.fromhex("0123456789abcdef"), trace)
for round_no, left, right, key in trace:
    print(round_no, f"{left:08x}", f"{right:08x}",
          "IP" if key is None else f"{key:012x}")
for i, key in enumerate(d.subkeys, 1):
    print("subkey", i, f"{key:012x}")
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

FIPS 46-3（NIST 归档）：DES 位编号、IP/FP、E/P、PC-1/PC-2、移位表与八个 S 盒。  
SP 800-38A Appendix F.2：AES CBC 多块测试向量与模式定义。源码是本文独立实现；测试脚本只使用 Python 标准库和本机 C 编译器。

完整 Python 文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.py  
完整 C 文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\des_pure.c  
综合测试文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\test_crypto.py  
原地测试文件：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\test_inplace.c  
本次测试日志：C:\Users\Lenovo\.codex\visualizations\2026\10\09\01a120a9-292a-7d12-9579-ff3fb0d8b9ce\aes-des-pure\test-output.txt

Python 支持 --mode ECB/CBC、--iv、--pkcs7；C 支持 ECB/CBC 与 NONE/PKCS7。这些实现的表与控制流可直接用于 CTF 逐轮取证。
