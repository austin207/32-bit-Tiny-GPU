#ifndef AXEL_H
#define AXEL_H
#include "gpu_asm.h"

#define MAX_DATA_WORDS 256

// 

#define R0 0
#define R1 1
#define R2 2
#define R3 3
#define R4 4
#define R5 5
#define R6 6
#define R7 7
#define R8 8
#define R9 9
#define R10 10
#define R11 11
#define R12 12
#define R13 13
#define R14 14
#define R15 15
#define R16 16
#define R17 17
#define R18 18
#define R19 19
#define R20 20
#define R21 21
#define R22 22
#define R23 23
#define R24 24
#define R25 25
#define R26 26
#define R27 27
#define R28 28
#define THREAD_IDX 29
#define BLOCK_IDX 30
#define BLOCK_DIM 31

#define AXEL_N 0b100
#define AXEL_Z 0b010
#define AXEL_P 0b001
#define AXEL_NZ 0b110
#define AXEL_NP 0b101
#define AXEL_ZP 0b011
#define AXEL_ALL 0b111

typedef struct {
    GPUProgram program;
    int num_blocks;
    int threads_per_block;
    uint32_t data_mem[MAX_DATA_WORDS];
    int data_mem_size;
} AxelGPU;

void axel_init(AxelGPU *gpu, int num_blocks, int threads_per_block);
void axel_compile(AxelGPU *gpu, const char *filename);
void axel_add(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_sub(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_mul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_imul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_div(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_mod(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_shl(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_shr(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_sar(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_and(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_or(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_xor(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_not(AxelGPU *gpu, uint8_t rd, uint8_t rs);
void axel_cmp(AxelGPU *gpu, uint8_t rs1, uint8_t rs2);
void axel_fma(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3);
void axel_dot(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_relu(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_clamp(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_max(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_ldr(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm);
void axel_str(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm);
void axel_const(AxelGPU *gpu, uint8_t rd, uint16_t imm);
void axel_brnzp(AxelGPU *gpu, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset);
void axel_nop(AxelGPU *gpu);
void axel_ret(AxelGPU *gpu);
void axel_sync(AxelGPU *gpu);
void axel_set_data(AxelGPU *gpu, int addr, uint32_t value);
int axel_compile_bin(AxelGPU *gpu, const char *filename);

#endif