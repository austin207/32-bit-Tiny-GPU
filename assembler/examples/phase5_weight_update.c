#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 5 — Gradient descent weight update
     *
     * Runs after Phase 4. Thread i updates the entire i-th row of W.
     *
     * Update rule:
     *   error[i] = y[i] - t[i]
     *   W[i][j] -= (error[i] * x[j]) >> 4      (lr = 1/16)
     *
     * Memory layout:
     *   mem[0..15]  = W[4][4]  weights (read + updated in place)
     *   mem[16..19] = x[4]    same input as forward pass
     *   mem[20..23] = y[4]    predictions from Phase 4
     *   mem[24..27] = t[4]    target values  (pre-loaded)
     *
     * After this kernel, mem[0..15] holds the updated weights.
     */

    /* Compute error[i] = y[i] - t[i] */
    axel_const(&gpu, R1, 20);               /* R1 = 20  (Y_BASE)              */
    axel_add(&gpu, R1, R1, THREAD_IDX);     /* R1 = Y_BASE + i                */
    axel_ldr(&gpu, R2, R1, 0);              /* R2 = y[i]                      */

    axel_const(&gpu, R1, 24);               /* R1 = 24  (T_BASE)              */
    axel_add(&gpu, R1, R1, THREAD_IDX);     /* R1 = T_BASE + i                */
    axel_ldr(&gpu, R3, R1, 0);              /* R3 = t[i]                      */

    axel_sub(&gpu, R4, R2, R3);             /* R4 = error[i]                  */

    /* Load x[0..3] */
    axel_const(&gpu, R5, 16);               /* R5 = 16  (X_BASE)              */
    axel_ldr(&gpu, R6, R5, 0);              /* R6 = x[0]                      */
    axel_ldr(&gpu, R7, R5, 1);              /* R7 = x[1]                      */
    axel_ldr(&gpu, R8, R5, 2);              /* R8 = x[2]                      */
    axel_ldr(&gpu, R9, R5, 3);              /* R9 = x[3]                      */

    /* W row base = threadIdx * 4 */
    axel_const(&gpu, R10, 4);               /* R10 = 4                        */
    axel_mul(&gpu, R10, THREAD_IDX, R10);   /* R10 = i*4                      */

    /* Load current weights */
    axel_ldr(&gpu, R11, R10, 0);            /* R11 = W[i][0]                  */
    axel_ldr(&gpu, R12, R10, 1);            /* R12 = W[i][1]                  */
    axel_ldr(&gpu, R13, R10, 2);            /* R13 = W[i][2]                  */
    axel_ldr(&gpu, R14, R10, 3);            /* R14 = W[i][3]                  */

    axel_const(&gpu, R15, 4);               /* R15 = 4  (shift for lr=1/16)   */

    /* W[i][0] */
    axel_imul(&gpu, R16, R4, R6);
    axel_sar(&gpu, R16, R16, R15);   // ← change this to axel_sar
    axel_sub(&gpu, R11, R11, R16);

    /* W[i][1] */
    axel_imul(&gpu, R16, R4, R7);
    axel_sar(&gpu, R16, R16, R15);   // ← change this to axel_sar
    axel_sub(&gpu, R12, R12, R16);

    /* W[i][2] */
    axel_imul(&gpu, R16, R4, R8);
    axel_sar(&gpu, R16, R16, R15);   // ← change this to axel_sar
    axel_sub(&gpu, R13, R13, R16);

    /* W[i][3] */
    axel_imul(&gpu, R16, R4, R9);
    axel_sar(&gpu, R16, R16, R15);   // ← change this to axel_sar
    axel_sub(&gpu, R14, R14, R16);

    /* Write updated weights back */
    axel_str(&gpu, R11, R10, 0);
    axel_str(&gpu, R12, R10, 1);
    axel_str(&gpu, R13, R10, 2);
    axel_str(&gpu, R14, R10, 3);
    axel_ret(&gpu);

    axel_compile(&gpu, "phase5_weight_update.hex");

    printf("Phase 5 — Weight update: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}