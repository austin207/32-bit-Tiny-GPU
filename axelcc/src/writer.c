#include "writer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* ── .hex writer ─────────────────────────────────────────────────────────── */
/* One instruction per line, 8 lowercase hex digits. */
static int write_hex(const InstrBuf *buf, const char *path) {
    FILE *f = fopen(path, "w");
    if (!f) {
        perror(path);
        return 1;
    }

    for (int i = 0; i < buf->count; i++) {
        fprintf(f, "%08x\n", buf->instructions[i]);
    }

    fclose(f);
    return 0;
}

/* ── Little-endian writers ───────────────────────────────────────────────── */
static void write_u8(FILE *f, uint8_t v) {
    fwrite(&v, 1, 1, f);
}

static void write_u16le(FILE *f, uint16_t v) {
    uint8_t b[2] = {
        (uint8_t)(v & 0xFF),
        (uint8_t)((v >> 8) & 0xFF)
    };
    fwrite(b, 1, 2, f);
}

static void write_u32le(FILE *f, uint32_t v) {
    uint8_t b[4] = {
        (uint8_t)(v & 0xFF),
        (uint8_t)((v >> 8) & 0xFF),
        (uint8_t)((v >> 16) & 0xFF),
        (uint8_t)((v >> 24) & 0xFF)
    };
    fwrite(b, 1, 4, f);
}

/* ── .axelbin writer ─────────────────────────────────────────────────────── */
/*
 * Format expected by assembler/tools/axelbin.py:
 *
 * Header: 32 bytes
 *
 * Offset  Size  Field
 * 0       4     magic       "AXLB"
 * 4       1     version     0x01
 * 5       1     flags       0x00
 * 6       2     reserved    0x0000
 * 8       4     num_blocks
 * 12      4     blockDim
 * 16      4     text_words
 * 20      4     data_words
 * 24      4     entry_point
 * 28      4     reserved
 *
 * Then:
 *   text_words x uint32_t instructions
 *   data_words x uint32_t data words
 */
static int write_axelbin(const InstrBuf *buf, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        perror(path);
        return 1;
    }

    /* magic */
    fwrite("AXLB", 1, 4, f);

    /* version / flags / reserved */
    write_u8(f, 0x01);
    write_u8(f, 0x00);
    write_u16le(f, 0x0000);

    /* metadata */
    write_u32le(f, 0);                    /* num_blocks: testbench/host can override */
    write_u32le(f, 0);                    /* blockDim: testbench/host can override */
    write_u32le(f, (uint32_t)buf->count); /* text_words */
    write_u32le(f, 0);                    /* data_words */
    write_u32le(f, 0);                    /* entry_point */
    write_u32le(f, 0);                    /* reserved */

    /* text segment */
    for (int i = 0; i < buf->count; i++) {
        write_u32le(f, buf->instructions[i]);
    }

    /* no data segment for axelcc currently */

    fclose(f);
    return 0;
}

/* ── Entry point ──────────────────────────────────────────────────────────── */
int writer_write(const InstrBuf *buf, const char *outbase) {
    char path[512];
    int err = 0;

    snprintf(path, sizeof path, "%s.hex", outbase);
    err |= write_hex(buf, path);
    if (!err) {
        fprintf(stderr, "axelcc: wrote %s\n", path);
    }

    snprintf(path, sizeof path, "%s.axelbin", outbase);
    err |= write_axelbin(buf, path);
    if (!err) {
        fprintf(stderr, "axelcc: wrote %s\n", path);
    }

    return err;
}