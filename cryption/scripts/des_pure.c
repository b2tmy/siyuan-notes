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
