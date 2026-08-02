#include "emit.h"
#include <stdio.h>
#include <stdlib.h>

void ibuf_init(InstrBuf *b) { b->count = 0; }

static void push(InstrBuf *b, uint32_t word) {
    if (b->count >= AXELCC_MAX_INSTRUCTIONS) {
        fprintf(stderr, "emit: instruction buffer overflow (> %d)\n",
                AXELCC_MAX_INSTRUCTIONS);
        exit(1);
    }
    b->instructions[b->count++] = word;
}

void ibuf_patch(InstrBuf *b, int idx, uint32_t word) {
    b->instructions[idx] = word;
}

// ── Bit-pack helpers — identical to gpu_asm.h encoding ───────────────────────
// R-type:  [31:26]=op [25:21]=rd [20:16]=rs1 [15:11]=rs2 [10:6]=rs3 [5:0]=0
// I-type:  [31:26]=op [25:21]=rd [20:16]=rs1 [15:0]=imm
// B-type:  [31:26]=op [25:23]=nzp [22:12]=sync_off [11:0]=branch_off
// N-type:  [31:26]=op [25:0]=0

static uint32_t r_type(int op, int rd, int rs1, int rs2) {
    return ((uint32_t)op  << 26) | ((uint32_t)rd  << 21) |
           ((uint32_t)rs1 << 16) | ((uint32_t)rs2 << 11);
}
static uint32_t r4_type(int op, int rd, int rs1, int rs2, int rs3) {
    return ((uint32_t)op  << 26) | ((uint32_t)rd  << 21) |
           ((uint32_t)rs1 << 16) | ((uint32_t)rs2 << 11) |
           ((uint32_t)rs3 << 6);
}
static uint32_t i_type(int op, int rd, int rs, int imm) {
    return ((uint32_t)op << 26) | ((uint32_t)rd << 21) |
           ((uint32_t)rs << 16) | ((uint32_t)(imm & 0xFFFF));
}
static uint32_t n_type(int op) {
    return (uint32_t)op << 26;
}

void emit_add  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x01,rd,rs1,rs2)); }
void emit_sub  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x02,rd,rs1,rs2)); }
void emit_imul (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x13,rd,rs1,rs2)); }
void emit_div  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x04,rd,rs1,rs2)); }
void emit_mod  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x05,rd,rs1,rs2)); }
void emit_sar  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x14,rd,rs1,rs2)); }
void emit_shl  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x06,rd,rs1,rs2)); }
void emit_shr  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x07,rd,rs1,rs2)); }
void emit_and  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x08,rd,rs1,rs2)); }
void emit_or   (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x09,rd,rs1,rs2)); }
void emit_xor  (InstrBuf *b, int rd, int rs1, int rs2) { push(b, r_type(0x0A,rd,rs1,rs2)); }
void emit_fma  (InstrBuf *b, int rd, int rs1, int rs2, int rs3) { push(b, r4_type(0x0C,rd,rs1,rs2,rs3)); }
void emit_dot  (InstrBuf *b, int rd, int rs1, int rs2, int rs3) { push(b, r4_type(0x16,rd,rs1,rs2,rs3)); }
void emit_cmp  (InstrBuf *b, int rs1, int rs2) { push(b, r_type(0x0D,0,rs1,rs2)); }
void emit_ldr  (InstrBuf *b, int rd, int rs,  int imm) { push(b, i_type(0x0F,rd,rs,imm)); }
void emit_str  (InstrBuf *b, int rd, int rs,  int imm) { push(b, i_type(0x10,rd,rs,imm)); }
void emit_const(InstrBuf *b, int rd, int imm)          { push(b, i_type(0x11,rd,0,imm)); }
void emit_ret  (InstrBuf *b)                           { push(b, n_type(0x12)); }
void emit_nop  (InstrBuf *b)                           { push(b, n_type(0x00)); }
void emit_sync (InstrBuf *b)                           { push(b, n_type(0x15)); }
void emit_not  (InstrBuf *b, int rd, int rs) { push(b, r_type(0x0B,rd,rs,0)); }
void emit_exp8 (InstrBuf *b, int rd, int rs)           { push(b, r_type(0x1B,rd,rs,0)); }
void emit_relu (InstrBuf *b, int rd, int rs)           { push(b, r_type(0x17,rd,rs,0)); }

void emit_brnzp(InstrBuf *b, int nzp, int sync_off, int branch_off) {
    uint32_t word = ((uint32_t)0x0E        << 26)
                  | ((uint32_t)(nzp & 0x7) << 23)
                  | ((uint32_t)(sync_off   & 0x7FF) << 12)
                  | ((uint32_t)(branch_off & 0xFFF));
    push(b, word);
}