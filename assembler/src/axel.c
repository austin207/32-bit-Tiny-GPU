#include "axel.h"

void axel_init(AxelGPU *gpu, int num_blocks, int threads_per_block) {
    gpu_program_init(&gpu->program);
    gpu->num_blocks = num_blocks;
    gpu->threads_per_block = threads_per_block;
}

void axel_compile(AxelGPU *gpu, const char *filename) {
    gpu_program_write(&gpu->program, filename);
}

void axel_add(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_add(&gpu->program, rd, rs1, rs2);
}

void axel_sub(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_sub(&gpu->program, rd, rs1, rs2);
}

void axel_mul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_mul(&gpu->program, rd, rs1, rs2);
}

void axel_div(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_div(&gpu->program, rd, rs1, rs2);
}

void axel_mod(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_mod(&gpu->program, rd, rs1, rs2);
}

void axel_shl(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_shl(&gpu->program, rd, rs1, rs2);
}

void axel_shr(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_shr(&gpu->program, rd, rs1, rs2);
}

void axel_and(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_and(&gpu->program, rd, rs1, rs2);
}

void axel_or(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_or(&gpu->program, rd, rs1, rs2);
}

void axel_xor(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_xor(&gpu->program, rd, rs1, rs2);
}

void axel_not(AxelGPU *gpu, uint8_t rd, uint8_t rs) {
    emit_not(&gpu->program, rd, rs);
}

void axel_cmp(AxelGPU *gpu, uint8_t rs1, uint8_t rs2) {
    emit_cmp(&gpu->program, rs1, rs2);
}

void axel_fma(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3) {
    emit_fma(&gpu->program, rd, rs1, rs2, rs3);
}

void axel_ldr(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm) {
    emit_ldr(&gpu->program, rd, rs, imm);
}

void axel_str(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm) {
    emit_str(&gpu->program, rd, rs, imm);
}

void axel_const(AxelGPU *gpu, uint8_t rd, uint16_t imm) {
    emit_const(&gpu->program, rd, imm);
}

void axel_brnzp(AxelGPU *gpu, uint8_t nzp, uint32_t pc_offset) {
    emit_brnzp(&gpu->program, nzp, pc_offset);
}

void axel_nop(AxelGPU *gpu) {
    emit_nop(&gpu->program);
}

void axel_ret(AxelGPU *gpu) {
    emit_ret(&gpu->program);
}

