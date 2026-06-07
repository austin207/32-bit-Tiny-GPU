#ifndef GPU_ASM_H
#define GPU_ASM_H

#include <stdint.h>

#define OP_NOP 0x00
#define OP_ADD 0x01
#define OP_SUB 0x02
#define OP_MUL 0x03
#define OP_DIV 0x04
#define OP_MOD 0x05
#define OP_SHL 0x06
#define OP_SHR 0x07
#define OP_AND 0x08
#define OP_OR 0x09
#define OP_XOR 0x0A
#define OP_NOT 0x0B
#define OP_FMA 0x0C
#define OP_CMP 0x0D
#define OP_BRnzp 0x0E
#define OP_LDR 0x0F
#define OP_STR 0x10
#define OP_CONST 0x11
#define OP_RET 0x12
#define OP_IMUL 0x13
#define OP_SAR 0x14
#define OP_SYNC 0x15
#define OP_DOT 0x16
#define OP_RELU 0x17
#define OP_CLAMP 0x18
#define OP_MAX 0x19
#define OP_MIN  0x1A
#define OP_EXP8 0x1B

typedef struct {
    uint32_t instructions[256];
    int count;
} GPUProgram;

void gpu_program_init(GPUProgram *prog);
void gpu_program_write(GPUProgram *prog, const char *filename);

void emit_add(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_sub(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_mul(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_imul(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_div(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_mod(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_shl(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_shr(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_sar(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_and(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_or(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_xor(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_not(GPUProgram *prog, uint8_t rd, uint8_t rs);
void emit_cmp(GPUProgram *prog, uint8_t rs1, uint8_t rs2);
void emit_fma(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3);
void emit_dot(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_relu(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_clamp(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_max(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_min(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2);
void emit_exp8(GPUProgram *prog, uint8_t rd, uint8_t rs1);
void emit_ldr(GPUProgram *prog, uint8_t rd, uint8_t rs, uint16_t imm);
void emit_str(GPUProgram *prog, uint8_t rd, uint8_t rs, uint16_t imm);
void emit_const(GPUProgram *prog, uint8_t rd, uint16_t imm);
void emit_brnzp(GPUProgram *prog, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset);
void emit_nop(GPUProgram *prog);
void emit_ret(GPUProgram *prog);
void emit_sync(GPUProgram *prog);
#endif // GPU_ASM_H