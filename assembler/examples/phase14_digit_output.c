/*
 * phase14_digit_output.c
 *
 * Two-layer digit classifier — output layer pass.
 * Part 2 of 2: computes y = CLAMP(RELU(SAR(W_o * h, 8)))
 *
 * Reads h[0..3] from data memory written by phase13_digit_hidden.
 * Uses scalar IMUL + ADD (not DOT4) because h values are INT32 scalars,
 * not packed INT8x4. This demonstrates both compute modes in one pipeline.
 *
 * Memory layout (shared with phase13):
 *   mem[0..19]  W_h and x  (untouched by this kernel)
 *   mem[20..23] h[0..3]    INT32 values written by phase13
 *
 *   W_o weights (4 rows x 4 INT32 scalar words = 16 words):
 *     mem[24..27] W_o[0][0..3]
 *     mem[28..31] W_o[1][0..3]
 *     mem[32..35] W_o[2][0..3]
 *     mem[36..39] W_o[3][0..3]
 *
 *   Output scores (written by this kernel):
 *     mem[40..43] y[0..3]
 *
 * Kernel (per thread j = THREAD_IDX):
 *   R9  = W_o[j] base = 24 + THREAD_IDX * 4
 *   R10 = 20 (h base)
 *   R2  = h[0]*W_o[j][0]           IMUL, accumulate into R2
 *   R2 += h[1]*W_o[j][1]
 *   R2 += h[2]*W_o[j][2]
 *   R2 += h[3]*W_o[j][3]
 *   R4  = CLAMP(RELU(SAR(R2, 8)))
 *   mem[40 + THREAD_IDX] = R4
 *
 * W_o values (INT32 scalars, all positive):
 *   W_o[0] = [30, 20, 10,  5]
 *   W_o[1] = [ 5, 30, 20, 10]
 *   W_o[2] = [10,  5, 30, 20]
 *   W_o[3] = [20, 10,  5, 30]
 *
 * Golden reference (after h = [42, 37, 0, 6] from phase13):
 *   y[0] = SAR8(30*42 + 20*37 + 10*0 + 5*6)  = SAR8(2030) = 7
 *   y[1] = SAR8( 5*42 + 30*37 + 20*0 + 10*6) = SAR8(1380) = 5
 *   y[2] = SAR8(10*42 +  5*37 + 30*0 + 20*6) = SAR8( 725) = 2
 *   y[3] = SAR8(20*42 + 10*37 +  5*0 + 30*6) = SAR8(1390) = 5
 *
 * Expected y[0..3] at mem[40..43] = [7, 5, 2, 5]
 * ARGMAX = class 0  (y[0] = 7 is highest)
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);  /* 1 block, 4 threads */

    /*
     * Only set W_o and y slots here.
     * h[20..23] is written by phase13 at runtime.
     * Set zeros as placeholders so data_words covers mem[24..43].
     */
    for (int i = 20; i < 24; i++) axel_set_data(&gpu, i, 0); /* h placeholders */

    /* W_o[0] = [30, 20, 10, 5] */
    axel_set_data(&gpu, 24, 30);
    axel_set_data(&gpu, 25, 20);
    axel_set_data(&gpu, 26, 10);
    axel_set_data(&gpu, 27,  5);

    /* W_o[1] = [5, 30, 20, 10] */
    axel_set_data(&gpu, 28,  5);
    axel_set_data(&gpu, 29, 30);
    axel_set_data(&gpu, 30, 20);
    axel_set_data(&gpu, 31, 10);

    /* W_o[2] = [10, 5, 30, 20] */
    axel_set_data(&gpu, 32, 10);
    axel_set_data(&gpu, 33,  5);
    axel_set_data(&gpu, 34, 30);
    axel_set_data(&gpu, 35, 20);

    /* W_o[3] = [20, 10, 5, 30] */
    axel_set_data(&gpu, 36, 20);
    axel_set_data(&gpu, 37, 10);
    axel_set_data(&gpu, 38,  5);
    axel_set_data(&gpu, 39, 30);

    /* Output slots */
    axel_set_data(&gpu, 40, 0);
    axel_set_data(&gpu, 41, 0);
    axel_set_data(&gpu, 42, 0);
    axel_set_data(&gpu, 43, 0);

    /*
     * Kernel: scalar IMUL + ADD accumulation
     * W_o base for this neuron = 24 + THREAD_IDX * 4
     */
    axel_const(&gpu, R6,          4);              /* R6  = 4 */
    axel_mul  (&gpu, R7, THREAD_IDX, R6);          /* R7  = THREAD_IDX * 4 */
    axel_const(&gpu, R8,         24);              /* R8  = 24 (W_o base) */
    axel_add  (&gpu, R9, R8, R7);                  /* R9  = W_o[neuron] base */
    axel_const(&gpu, R10,        20);              /* R10 = 20 (h base) */

    /* term 0: R2 = h[0] * W_o[j][0] */
    axel_ldr  (&gpu, R1,  R10, 0);                 /* R1  = h[0] */
    axel_ldr  (&gpu, R11, R9,  0);                 /* R11 = W_o[j][0] */
    axel_imul (&gpu, R2,  R1,  R11);               /* R2  = h[0] * W_o[0] */

    /* term 1: accumulate h[1] * W_o[j][1] */
    axel_ldr  (&gpu, R1,  R10, 1);                 /* R1  = h[1] */
    axel_ldr  (&gpu, R11, R9,  1);                 /* R11 = W_o[j][1] */
    axel_imul (&gpu, R3,  R1,  R11);               /* R3  = h[1] * W_o[1] */
    axel_add  (&gpu, R2,  R2,  R3);                /* R2 += R3 */

    /* term 2: accumulate h[2] * W_o[j][2] */
    axel_ldr  (&gpu, R1,  R10, 2);                 /* R1  = h[2] */
    axel_ldr  (&gpu, R11, R9,  2);                 /* R11 = W_o[j][2] */
    axel_imul (&gpu, R3,  R1,  R11);               /* R3  = h[2] * W_o[2] */
    axel_add  (&gpu, R2,  R2,  R3);                /* R2 += R3 */

    /* term 3: accumulate h[3] * W_o[j][3] */
    axel_ldr  (&gpu, R1,  R10, 3);                 /* R1  = h[3] */
    axel_ldr  (&gpu, R11, R9,  3);                 /* R11 = W_o[j][3] */
    axel_imul (&gpu, R3,  R1,  R11);               /* R3  = h[3] * W_o[3] */
    axel_add  (&gpu, R2,  R2,  R3);                /* R2 = full dot product */

    axel_const(&gpu, R5,          8);              /* R5  = 8 */
    axel_sar  (&gpu, R4, R2, R5);                  /* R4  = R2 >> 8 */
    axel_relu (&gpu, R4, R4, R1);                  /* R4  = relu(R4) */
    axel_clamp(&gpu, R4, R4, R1);                  /* R4  = clamp(R4) */

    axel_const(&gpu, R12,        40);              /* R12 = 40 (y base) */
    axel_add  (&gpu, R13, R12, THREAD_IDX);        /* R13 = 40 + THREAD_IDX */
    axel_str  (&gpu, R4, R13, 0);                  /* mem[40 + j] = y[j] */
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase14_digit_output.hex");
    axel_compile_bin(&gpu, "bin/phase14_digit_output.axelbin");

    printf("phase14_digit_output: 4-hidden -> 4-out, scalar IMUL+ADD per thread\n");
    printf("expected y[0..3] at mem[40..43] = [7, 5, 2, 5]  (argmax = class 0)\n");

    return 0;
}