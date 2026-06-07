#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 4, 4);  /* 4 blocks x 4 threads */

    /*
     * Phase 19 - Q8 4x8 Matmul using two DOT4 chunks
     *
     * Shape:
     *   A = 4x8
     *   B = 8x4
     *   C = 4x4
     *
     * Thread mapping:
     *   row = BLOCK_IDX
     *   col = THREAD_IDX
     *
     * Each thread computes:
     *   C[row][col] =
     *       DOT4(A[row][0..3], B_col[col][0..3]) +
     *       DOT4(A[row][4..7], B_col[col][4..7])
     *
     * Memory layout:
     *   mem[0..7]    = A rows, two packed INT8x4 chunks per row
     *                  A[row][chunk] at mem[row*2 + chunk]
     *
     *   mem[8..15]   = B columns, two packed INT8x4 chunks per column
     *                  B_col[col][chunk] at mem[8 + col*2 + chunk]
     *
     *   mem[16..31]  = C[4][4] INT32 output
     *
     * Expected C:
     *   [ 3, 9, 11,  4]
     *   [ 5, 4,  8, 11]
     *   [ 6, 5, 11,  7]
     *   [10, 8, 11,  7]
     *
     * NOTE:
     *   Use imm=0 for LDR/STR.
     *   Compute all non-trivial addresses explicitly.
     */

    /*
     * Constants:
     *   R1 = 2
     *   R4 = 1
     *   R8 = 8
     *   R17 = 16
     */
    axel_const(&gpu, R1, 2);

    /* A base = row * 2 */
    axel_mul(&gpu, R2, BLOCK_IDX, R1);

    /* R3 = A0 = mem[row*2] */
    axel_ldr(&gpu, R3, R2, 0);

    /* R6 = A1 = mem[row*2 + 1] */
    axel_const(&gpu, R4, 1);
    axel_add(&gpu, R5, R2, R4);
    axel_ldr(&gpu, R6, R5, 0);

    /* B base = 8 + col*2 */
    axel_mul(&gpu, R7, THREAD_IDX, R1);
    axel_const(&gpu, R8, 8);
    axel_add(&gpu, R9, R7, R8);

    /* R10 = B0 = mem[8 + col*2] */
    axel_ldr(&gpu, R10, R9, 0);

    /* R13 = B1 = mem[8 + col*2 + 1] */
    axel_add(&gpu, R12, R9, R4);
    axel_ldr(&gpu, R13, R12, 0);

    /* Accumulate two DOT4 chunks */
    axel_const(&gpu, R14, 0);
    axel_dot(&gpu, R14, R3, R10);
    axel_dot(&gpu, R14, R6, R13);

    /* Output address = 16 + row*4 + col */
    axel_mul(&gpu, R15, BLOCK_IDX, BLOCK_DIM);
    axel_add(&gpu, R16, R15, THREAD_IDX);
    axel_const(&gpu, R17, 16);
    axel_add(&gpu, R18, R16, R17);

    /* mem[out] = acc */
    axel_str(&gpu, R14, R18, 0);

    axel_ret(&gpu);

    /*
     * A rows:
     * row0 = [1,2,0,0, 3,0,1,0]
     * row1 = [0,1,2,0, 0,3,0,1]
     * row2 = [2,0,1,1, 1,1,0,2]
     * row3 = [0,2,0,3, 2,0,2,0]
     */

    axel_set_data(&gpu, 0, 0x00000201);  /* row0 chunk0 [1,2,0,0] */
    axel_set_data(&gpu, 1, 0x00010003);  /* row0 chunk1 [3,0,1,0] */

    axel_set_data(&gpu, 2, 0x00020100);  /* row1 chunk0 [0,1,2,0] */
    axel_set_data(&gpu, 3, 0x01000300);  /* row1 chunk1 [0,3,0,1] */

    axel_set_data(&gpu, 4, 0x01010002);  /* row2 chunk0 [2,0,1,1] */
    axel_set_data(&gpu, 5, 0x02000101);  /* row2 chunk1 [1,1,0,2] */

    axel_set_data(&gpu, 6, 0x03000200);  /* row3 chunk0 [0,2,0,3] */
    axel_set_data(&gpu, 7, 0x00020002);  /* row3 chunk1 [2,0,2,0] */

    /*
     * B columns, transposed:
     * col0 = [1,0,1,2, 0,1,2,0]
     * col1 = [0,1,1,0, 2,0,1,1]
     * col2 = [2,3,0,1, 1,1,0,2]
     * col3 = [1,1,2,1, 0,2,1,0]
     */

    axel_set_data(&gpu, 8,  0x02010001);  /* col0 chunk0 [1,0,1,2] */
    axel_set_data(&gpu, 9,  0x00020100);  /* col0 chunk1 [0,1,2,0] */

    axel_set_data(&gpu, 10, 0x00010100);  /* col1 chunk0 [0,1,1,0] */
    axel_set_data(&gpu, 11, 0x01010002);  /* col1 chunk1 [2,0,1,1] */

    axel_set_data(&gpu, 12, 0x01000302);  /* col2 chunk0 [2,3,0,1] */
    axel_set_data(&gpu, 13, 0x02000101);  /* col2 chunk1 [1,1,0,2] */

    axel_set_data(&gpu, 14, 0x01020101);  /* col3 chunk0 [1,1,2,1] */
    axel_set_data(&gpu, 15, 0x00010200);  /* col3 chunk1 [0,2,1,0] */

    printf("Phase 19 - Q8 4x8 matmul, two DOT4 chunks: %d instructions\n",
           gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);

    axel_compile(&gpu, "hex/phase19_q8_matmul_4x8.hex");
    axel_compile_bin(&gpu, "bin/phase19_q8_matmul_4x8.axelbin");

    return 0;
}