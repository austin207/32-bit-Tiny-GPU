#include "axel.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>

void axel_init(AxelGPU *gpu, int num_blocks, int threads_per_block) {
    gpu_program_init(&gpu->program);
    gpu->num_blocks = num_blocks;
    gpu->threads_per_block = threads_per_block;
    memset(gpu->data_mem, 0, sizeof(gpu->data_mem));
    gpu->data_mem_size = 0;
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

void axel_sar(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_sar(&gpu->program, rd, rs1, rs2);
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

void axel_imul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_imul(&gpu->program, rd, rs1, rs2);
}

void axel_cmp(AxelGPU *gpu, uint8_t rs1, uint8_t rs2) {
    emit_cmp(&gpu->program, rs1, rs2);
}

void axel_fma(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3) {
    emit_fma(&gpu->program, rd, rs1, rs2, rs3);
}

void axel_dot(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_dot(&gpu->program, rd, rs1, rs2);
}

void axel_relu(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_relu(&gpu->program, rd, rs1, rs2);
}

void axel_clamp(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_clamp(&gpu->program, rd, rs1, rs2);
}

void axel_max(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_max(&gpu->program, rd, rs1, rs2);
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

void axel_brnzp(AxelGPU *gpu, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset) {
    emit_brnzp(&gpu->program, nzp, sync_offset, branch_offset);
}

void axel_nop(AxelGPU *gpu) {
    emit_nop(&gpu->program);
}

void axel_ret(AxelGPU *gpu) {
    emit_ret(&gpu->program);
}

void axel_sync(AxelGPU *gpu) {
    emit_sync(&gpu->program);
}

void axel_set_data(AxelGPU *gpu, int addr, uint32_t value) {
    if (addr < 0 || addr >= MAX_DATA_WORDS) return;
    gpu->data_mem[addr] = value;
    if (addr + 1 > gpu->data_mem_size)
        gpu->data_mem_size = addr + 1;
}

int axel_compile_bin(AxelGPU *gpu, const char *filename) {
    FILE *f = fopen(filename, "wb");
    if (!f) {
        fprintf(stderr, "axel_compile_bin: cannot open %s\n", filename);
        return -1;
    }

    // ── Header ────────────────────────────────────────────────────────────────
    const char magic[4] = {'A', 'X', 'L', 'B'};
    uint8_t  version   = 0x01;
    uint8_t  flags     = 0x00;
    uint16_t res16     = 0x0000;
    uint32_t num_blocks   = (uint32_t)gpu->num_blocks;
    uint32_t blockDim     = (uint32_t)gpu->threads_per_block;
    uint32_t text_words   = (uint32_t)gpu->program.count;
    uint32_t data_words   = (uint32_t)gpu->data_mem_size;
    uint32_t entry_point  = 0x00000000;
    uint32_t res32        = 0x00000000;

    fwrite(magic,        1, 4, f);
    fwrite(&version,     1, 1, f);
    fwrite(&flags,       1, 1, f);
    fwrite(&res16,       2, 1, f);
    fwrite(&num_blocks,  4, 1, f);
    fwrite(&blockDim,    4, 1, f);
    fwrite(&text_words,  4, 1, f);
    fwrite(&data_words,  4, 1, f);
    fwrite(&entry_point, 4, 1, f);
    fwrite(&res32,       4, 1, f);

    // ── Text segment ─────────────────────────────────────────────────────────
    fwrite(gpu->program.instructions, 4, text_words, f);

    // ── Data segment ─────────────────────────────────────────────────────────
    if (data_words > 0)
        fwrite(gpu->data_mem, 4, data_words, f);

    fclose(f);
    printf("axelbin: wrote %s (%u instructions, %u data words)\n",
           filename, text_words, data_words);
    return 0;
}