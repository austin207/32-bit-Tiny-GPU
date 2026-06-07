#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);  /* 1 block, 4 threads */

    /*
     * Phase 17 — Q8 4x4 Matvec (DOT4 accelerated)
     *
     * Thread i computes:
     *   y[i] = DOT4(A_row[i], x)    INT32 result, no requantize
     *
     * Memory layout:
     *   mem[0..3] = A[4][4] packed INT8x4 row-major (A_row[i] at mem[i])
     *   mem[4]    = x[4]    packed INT8x4
     *   mem[5..8] = y[4]    INT32 output
     *
     * NOTE: LDR/STR imm field is NOT used by RTL. Always imm=0.
     *       All non-trivial addresses computed via CONST + ADD.
     *
     * Test:
     *   A_row[0]=[1,2,0,0]  A_row[1]=[0,3,4,0]
     *   A_row[2]=[0,0,5,6]  A_row[3]=[7,0,0,8]
     *   x=[1,1,1,1]
     *   Expected y = [3, 7, 11, 15]
     *
     * Registers:
     *   R29 = THREAD_IDX (0..3)
     *   R1  = A_row[thread_idx]  (mem[R29])
     *   R2  = 4  (x address)
     *   R3  = x packed
     *   R4  = DOT4 accumulator
     *   R5  = 5  (output base)
     *   R6  = 5 + thread_idx  (output address)
     */

    /* R1 = mem[R29 + 0] = A_row[thread_idx] */
    axel_ldr(&gpu, R1, THREAD_IDX, 0);

    /* R2 = 4, R3 = mem[4] = x */
    axel_const(&gpu, R2, 4);
    axel_ldr(&gpu, R3, R2, 0);

    /* R4 = 0; R4 += DOT4(R1, R3) */
    axel_const(&gpu, R4, 0);
    axel_dot(&gpu, R4, R1, R3);

    /* R6 = 5 + thread_idx; mem[R6] = R4 */
    axel_const(&gpu, R5, 5);
    axel_add(&gpu, R6, THREAD_IDX, R5);
    axel_str(&gpu, R4, R6, 0);

    axel_ret(&gpu);

    /* Embed initial data */
    axel_set_data(&gpu, 0, 0x00000201);  // [1,2,0,0]
    axel_set_data(&gpu, 1, 0x00040300);  // [0,3,4,0]
    axel_set_data(&gpu, 2, 0x06050000);  // [0,0,5,6]
    axel_set_data(&gpu, 3, 0x08000007);  // [7,0,0,8]
    axel_set_data(&gpu, 4, 0x01010101);  // [1,1,1,1]

    printf("Phase 17 — Q8 4x4 matvec (DOT4): %d instructions\n",
           gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);

    axel_compile(&gpu, "hex/phase17_q8_matvec_4x4.hex");
    axel_compile_bin(&gpu, "bin/phase17_q8_matvec_4x4.axelbin");

    return 0;
}