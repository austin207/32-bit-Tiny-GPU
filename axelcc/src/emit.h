#ifndef EMIT_H
#define EMIT_H
#include <stdint.h>

// Instruction buffer — mirrors GPUProgram from gpu_asm.h
#define AXELCC_MAX_INSTRUCTIONS 256

typedef struct {
    uint32_t instructions[AXELCC_MAX_INSTRUCTIONS];
    int      count;
} InstrBuf;

void ibuf_init(InstrBuf *buf);

// Instruction emitters (bit-pack exactly as gpu_asm.h does)
void emit_add  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_sub  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_imul (InstrBuf *b, int rd, int rs1, int rs2);
void emit_sar  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_shl  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_shr  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_and  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_or   (InstrBuf *b, int rd, int rs1, int rs2);
void emit_xor  (InstrBuf *b, int rd, int rs1, int rs2);
void emit_fma  (InstrBuf *b, int rd, int rs1, int rs2, int rs3);
void emit_cmp  (InstrBuf *b, int rs1, int rs2);
void emit_ldr  (InstrBuf *b, int rd, int rs, int imm);
void emit_str  (InstrBuf *b, int rd, int rs, int imm);
void emit_const(InstrBuf *b, int rd, int imm);
void emit_brnzp(InstrBuf *b, int nzp, int sync_offset, int branch_offset);
void emit_sync (InstrBuf *b);
void emit_ret  (InstrBuf *b);
void emit_nop  (InstrBuf *b);
void emit_not  (InstrBuf *b, int rd, int rs);
void emit_exp8 (InstrBuf *b, int rd, int rs);

// Patch: overwrite instruction at index with new value
void ibuf_patch(InstrBuf *b, int idx, uint32_t word);

#endif // EMIT_H