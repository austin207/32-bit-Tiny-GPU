#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 4, 4);  /* 4 blocks x 4 threads */

    /*
     * Phase 18 - Q8 4x4 Matmul (DOT4 accelerated)
     *
     * Thread mapping:
     *   row = BLOCK_IDX
     *   col = THREAD_IDX
     *
     * Each thread computes:
     *   C[row][col] = DOT4(A_row[row], B_col[col])
     *
     * Memory layout:
     *   mem[0..3]   = A rows packed INT8x4
     *   mem[4..7]   = B columns packed INT8x4, B already transposed
     *   mem[8..23]  = C[4][4] INT32 output
     *
     * A:
     *   [1,2,0,0]
     *   [0,3,4,0]
     *   [0,0,5,6]
     *   [7,0,0,8]
     *
     * B:
     *   [1,0,2,1]
     *   [0,1,3,1]
     *   [1,1,0,2]
     *   [2,0,1,1]
     *
     * B stored transposed as columns:
     *   B_col0 = [1,0,1,2]
     *   B_col1 = [0,1,1,0]
     *   B_col2 = [2,3,0,1]
     *   B_col3 = [1,1,2,1]
     *
     * Expected C:
     *   [ 1, 2,  8,  3]
     *   [ 4, 7,  9, 11]
     *   [17, 5,  6, 16]
     *   [23, 0, 22, 15]
     *
     * Register plan:
     *   R1  = A_row
     *   R3  = B_col address
     *   R4  = B_col
     *   R5  = accumulator / output value
     *   R7  = row_offset = BLOCK_IDX * BLOCK_DIM
     *   R8  = flat_index = row_offset + THREAD_IDX
     *   R9  = output base = 8
     *   R10 = output address = 8 + row*4 + col
     *
     * NOTE:
     *   Use imm=0 for LDR/STR.
     *   Compute non-trivial addresses explicitly.
     */

    /* R1 = mem[BLOCK_IDX] = A_row[row] */
    axel_ldr(&gpu, R1, BLOCK_IDX, 0);

    /* R3 = THREAD_IDX + BLOCK_DIM = 4 + col */
    axel_add(&gpu, R3, THREAD_IDX, BLOCK_DIM);

    /* R4 = mem[4 + col] = B_col[col] */
    axel_ldr(&gpu, R4, R3, 0);

    /* R5 = 0; R5 += DOT4(A_row, B_col) */
    axel_const(&gpu, R5, 0);
    axel_dot(&gpu, R5, R1, R4);

    /* R7 = row * 4 */
    axel_mul(&gpu, R7, BLOCK_IDX, BLOCK_DIM);

    /* R8 = row*4 + col */
    axel_add(&gpu, R8, R7, THREAD_IDX);

    /* R10 = 8 + row*4 + col */
    axel_const(&gpu, R9, 8);
    axel_add(&gpu, R10, R8, R9);

    /* mem[R10] = R5 */
    axel_str(&gpu, R5, R10, 0);

    axel_ret(&gpu);

    /* A rows */
    axel_set_data(&gpu, 0, 0x00000201);  /* [1,2,0,0] */
    axel_set_data(&gpu, 1, 0x00040300);  /* [0,3,4,0] */
    axel_set_data(&gpu, 2, 0x06050000);  /* [0,0,5,6] */
    axel_set_data(&gpu, 3, 0x08000007);  /* [7,0,0,8] */

    /* B columns, transposed */
    axel_set_data(&gpu, 4, 0x02010001);  /* [1,0,1,2] */
    axel_set_data(&gpu, 5, 0x00010100);  /* [0,1,1,0] */
    axel_set_data(&gpu, 6, 0x01000302);  /* [2,3,0,1] */
    axel_set_data(&gpu, 7, 0x01020101);  /* [1,1,2,1] */

    printf("Phase 18 - Q8 4x4 matmul (DOT4): %d instructions\n",
           gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);

    axel_compile(&gpu, "hex/phase18_q8_matmul_4x4.hex");
    axel_compile_bin(&gpu, "bin/phase18_q8_matmul_4x4.axelbin");

    return 0;
}