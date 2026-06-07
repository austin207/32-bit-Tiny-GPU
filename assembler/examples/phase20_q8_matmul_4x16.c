#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 4, 4);  /* 4 blocks, 4 threads */

    /*
     * Phase 20 — Q8 4x16 Tiled Matmul (4 DOT4 chunks per output)
     *
     * A = 4x16, B = 16x4 (stored as B^T = 4x16), C = 4x4
     *
     * Thread mapping:
     *   row = BLOCK_IDX  (0..3)
     *   col = THREAD_IDX (0..3)
     *
     * Each thread:
     *   C[row][col] = DOT4(chunk0) + DOT4(chunk1) + DOT4(chunk2) + DOT4(chunk3)
     *
     * Memory layout (all LDR/STR use imm=0, addresses explicit):
     *   mem[0..15]  = A rows, 4 chunks/row:  A[row][chunk] at mem[row*4 + chunk]
     *   mem[16..31] = B^T cols, 4 chunks/col: B_col[col][chunk] at mem[16 + col*4 + chunk]
     *   mem[32..47] = C[4][4] INT32 output:   C[row][col] at mem[32 + row*4 + col]
     *
     * Test data (each A row and B col repeated 4 chunks):
     *   A_row[0] = [1,1,1,1] x4   B_col[0] = [1,1,1,1] x4
     *   A_row[1] = [2,2,2,2] x4   B_col[1] = [2,2,2,2] x4
     *   A_row[2] = [0,3,4,0] x4   B_col[2] = [1,0,1,0] x4
     *   A_row[3] = [1,2,3,4] x4   B_col[3] = [0,1,0,1] x4
     *
     * Expected C:
     *   row0: [16, 32,  8,  8]
     *   row1: [32, 64, 16, 16]
     *   row2: [28, 56, 16, 12]
     *   row3: [40, 80, 16, 24]
     *
     * Registers:
     *   R1  = 4 (chunk stride)
     *   R2  = A_base  = BLOCK_IDX * 4
     *   R3  = col * 4 (temp)
     *   R4  = 16 (B block offset)
     *   R5  = B_base  = 16 + THREAD_IDX * 4
     *   R6  = A chunk data (reused)
     *   R7  = B chunk data (reused)
     *   R8  = INT32 accumulator
     *   R9  = chunk offset (1, 2, 3)
     *   R10 = A_base + chunk_offset
     *   R11 = B_base + chunk_offset
     *   R12 = 32 (C block offset)
     *   R13 = output address
     */

    /* ── Setup ─────────────────────────────────────────────────────── */
    axel_const(&gpu, R1,  4);
    axel_mul  (&gpu, R2,  BLOCK_IDX,  R1);  /* R2 = BLOCK_IDX * 4  = A_base */
    axel_mul  (&gpu, R3,  THREAD_IDX, R1);  /* R3 = THREAD_IDX * 4 */
    axel_const(&gpu, R4,  16);
    axel_add  (&gpu, R5,  R3, R4);          /* R5 = 16 + THREAD_IDX*4 = B_base */

    /* ── Chunk 0 ────────────────────────────────────────────────────── */
    axel_const(&gpu, R8, 0);                /* accumulator = 0 */
    axel_ldr  (&gpu, R6,  R2,  0);          /* R6 = A[row][0..3] */
    axel_ldr  (&gpu, R7,  R5,  0);          /* R7 = B_col[col][0..3] */
    axel_dot  (&gpu, R8,  R6,  R7);         /* R8 += DOT4 */

    /* ── Chunk 1 ────────────────────────────────────────────────────── */
    axel_const(&gpu, R9, 1);
    axel_add  (&gpu, R10, R2,  R9);         /* R10 = A_base + 1 */
    axel_add  (&gpu, R11, R5,  R9);         /* R11 = B_base + 1 */
    axel_ldr  (&gpu, R6,  R10, 0);
    axel_ldr  (&gpu, R7,  R11, 0);
    axel_dot  (&gpu, R8,  R6,  R7);

    /* ── Chunk 2 ────────────────────────────────────────────────────── */
    axel_const(&gpu, R9, 2);
    axel_add  (&gpu, R10, R2,  R9);
    axel_add  (&gpu, R11, R5,  R9);
    axel_ldr  (&gpu, R6,  R10, 0);
    axel_ldr  (&gpu, R7,  R11, 0);
    axel_dot  (&gpu, R8,  R6,  R7);

    /* ── Chunk 3 ────────────────────────────────────────────────────── */
    axel_const(&gpu, R9, 3);
    axel_add  (&gpu, R10, R2,  R9);
    axel_add  (&gpu, R11, R5,  R9);
    axel_ldr  (&gpu, R6,  R10, 0);
    axel_ldr  (&gpu, R7,  R11, 0);
    axel_dot  (&gpu, R8,  R6,  R7);

    /* ── Store C[row][col] at mem[32 + row*4 + col] ─────────────────── */
    axel_const(&gpu, R12, 32);
    axel_add  (&gpu, R13, R2,  R12);        /* R13 = BLOCK_IDX*4 + 32 */
    axel_add  (&gpu, R13, R13, THREAD_IDX); /* R13 += col */
    axel_str  (&gpu, R8,  R13, 0);          /* mem[R13] = R8 */

    axel_ret(&gpu);

    /* ── Test data ───────────────────────────────────────────────────── */
    /* A rows: row i at mem[i*4 .. i*4+3], 4 identical chunks */
    int i;
    for (i = 0; i < 4; i++) axel_set_data(&gpu,  0+i, 0x01010101); /* row0 [1,1,1,1] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu,  4+i, 0x02020202); /* row1 [2,2,2,2] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu,  8+i, 0x00040300); /* row2 [0,3,4,0] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 12+i, 0x04030201); /* row3 [1,2,3,4] */

    /* B^T cols: col k at mem[16+k*4 .. 16+k*4+3], 4 identical chunks */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 16+i, 0x01010101); /* col0 [1,1,1,1] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 20+i, 0x02020202); /* col1 [2,2,2,2] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 24+i, 0x00010001); /* col2 [1,0,1,0] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 28+i, 0x01000100); /* col3 [0,1,0,1] */

    printf("Phase 20 — Q8 4x16 tiled matmul (4 DOT4 chunks): %d instructions\n",
           gpu.program.count);
    for (i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);

    axel_compile    (&gpu, "hex/phase20_q8_matmul_4x16.hex");
    axel_compile_bin(&gpu, "bin/phase20_q8_matmul_4x16.axelbin");

    return 0;
}