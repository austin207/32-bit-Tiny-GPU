#include <stdio.h>
#include <stdint.h>
#include "gpu_asm.h"

uint32_t encode_r(uint8_t op, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) rd << 21)  |
            ((uint32_t) rs1 << 16) |
            ((uint32_t) rs2 << 11) |
            ((uint32_t) rs3 << 6);
}

uint32_t encode_i(uint8_t op, uint8_t rd, uint8_t rs, uint16_t imm) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) rd << 21)  |
            ((uint32_t) rs << 16)  |
            (uint32_t) imm;
}

uint32_t encode_b(uint8_t op, uint8_t nzp, uint32_t pc_offset) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) nzp << 23) |
            (pc_offset & 0x7FFFFF);
}

uint32_t encode_n(uint8_t op) {
    return (uint32_t) op << 26;
}

void emit_add(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_ADD, rd, rs1, rs2, 0);
}

void emit_sub(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_SUB, rd, rs1, rs2, 0); 
}

void emit_mul(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_MUL, rd, rs1, rs2, 0); 
}

void emit_div(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_DIV, rd, rs1, rs2, 0); 
}

void emit_mod(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_MOD, rd, rs1, rs2, 0); 
}

void emit_shl(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_SHL, rd, rs1, rs2, 0); 
}

void emit_shr(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_SHR, rd, rs1, rs2, 0); 
}

void emit_sar(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_SAR, rd, rs1, rs2, 0);
}

void emit_and(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_AND, rd, rs1, rs2, 0); 
}

void emit_or(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_OR, rd, rs1, rs2, 0); 
}

void emit_xor(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_XOR, rd, rs1, rs2, 0); 
}

void emit_not(GPUProgram *prog, uint8_t rd, uint8_t rs) {
    prog->instructions[prog->count++] = encode_r(OP_NOT, rd, rs, 0, 0); 
}

void emit_cmp(GPUProgram *prog, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_CMP, 0, rs1, rs2, 0); 
}

void emit_fma(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3) {
    prog->instructions[prog->count++] = encode_r(OP_FMA, rd, rs1, rs2, rs3); 
}

void emit_imul(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_IMUL, rd, rs1, rs2, 0);
}

void emit_ldr(GPUProgram *prog, uint8_t rd, uint8_t rs, uint16_t imm) {
    prog->instructions[prog->count++] = encode_i(OP_LDR, rd, rs, imm); 
}

void emit_str(GPUProgram *prog, uint8_t rd, uint8_t rs, uint16_t imm) {
    prog->instructions[prog->count++] = encode_i(OP_STR, rd, rs, imm);
}

void emit_const(GPUProgram *prog, uint8_t rd, uint16_t imm) {
    prog->instructions[prog->count++] = encode_i(OP_CONST, rd, 0, imm); 
}

void emit_brnzp(GPUProgram *prog, uint8_t nzp, uint32_t pc_offset) {
    prog->instructions[prog->count++] = encode_b(OP_BRnzp, nzp, pc_offset); 
}

void emit_nop(GPUProgram *prog) {
    prog->instructions[prog->count++] = encode_n(OP_NOP);
}

void emit_ret(GPUProgram *prog) {
    prog->instructions[prog->count++] = encode_n(OP_RET);
}

void gpu_program_init(GPUProgram *prog) {
    prog->count = 0;
}

void gpu_program_write(GPUProgram *prog, const char *filename) {
    FILE *f = fopen(filename, "w");
    if (f == NULL) return;

    for (int i = 0; i < prog->count; i++) {
        fprintf(f, "%08X\n", prog->instructions[i]);
    }

    fclose(f);
}