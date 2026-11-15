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
