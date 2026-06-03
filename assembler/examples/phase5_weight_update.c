#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 5 — Gradient descent weight update (Q8 fixed-point)
     *
     * Update rule (Q8):
     *   error[i] = y[i] - t[i]                 (Q8)
     *   grad[i][j] = SAR(IMUL(error[i], x[j]), 8)   (Q8 × Q8 → Q8)
     *   W[i][j] -= SAR(grad[i][j], LR_SHIFT)        (lr = 1/2^LR_SHIFT)
     *
     * LR_SHIFT = 4 means lr = 1/16 in Q8 space = 1/4096 in real space.
     * Tune LR_SHIFT to control convergence speed vs stability.
     *
     * Memory layout:
     *   mem[0..15]  = W[4][4]  (Q8 weights, updated in place)
     *   mem[16..19] = x[4]    (Q8 inputs)
     *   mem[20..23] = y[4]    (Q8 predictions from Phase 4)
     *   mem[24..27] = t[4]    (Q8 targets)
     */

    /* Compute error[i] = y[i] - t[i] */
    axel_const(&gpu, R1, 20);
    axel_add(&gpu, R1, R1, THREAD_IDX);
    axel_ldr(&gpu, R2, R1, 0);              /* R2 = y[i]                      */

    axel_const(&gpu, R1, 24);
    axel_add(&gpu, R1, R1, THREAD_IDX);
    axel_ldr(&gpu, R3, R1, 0);              /* R3 = t[i]                      */

    axel_sub(&gpu, R4, R2, R3);             /* R4 = error[i]  (Q8)            */

    /* Load x[0..3] */
    axel_const(&gpu, R5, 16);
    axel_ldr(&gpu, R6, R5, 0);              /* R6 = x[0]                      */
    axel_ldr(&gpu, R7, R5, 1);
    axel_ldr(&gpu, R8, R5, 2);
    axel_ldr(&gpu, R9, R5, 3);

    /* W row base = threadIdx * 4 */
    axel_const(&gpu, R10, 4);
    axel_mul(&gpu, R10, THREAD_IDX, R10);

    /* Load current weights */
    axel_ldr(&gpu, R11, R10, 0);
    axel_ldr(&gpu, R12, R10, 1);
    axel_ldr(&gpu, R13, R10, 2);
    axel_ldr(&gpu, R14, R10, 3);

    /* Q8 scale-down shift (>>8) + lr shift (>>4) combined = >>12 */
    axel_const(&gpu, R15, 12);              /* total shift = Q8 + lr          */

    /* W[i][0] -= SAR(error * x[0], 12) */
    axel_imul(&gpu, R16, R4, R6);
    axel_sar(&gpu, R16, R16, R15);
    axel_sub(&gpu, R11, R11, R16);

    /* W[i][1] -= SAR(error * x[1], 12) */
    axel_imul(&gpu, R16, R4, R7);
    axel_sar(&gpu, R16, R16, R15);
    axel_sub(&gpu, R12, R12, R16);

    /* W[i][2] -= SAR(error * x[2], 12) */
    axel_imul(&gpu, R16, R4, R8);
    axel_sar(&gpu, R16, R16, R15);
    axel_sub(&gpu, R13, R13, R16);

    /* W[i][3] -= SAR(error * x[3], 12) */
    axel_imul(&gpu, R16, R4, R9);
    axel_sar(&gpu, R16, R16, R15);
    axel_sub(&gpu, R14, R14, R16);

    /* Write updated weights back */
    axel_str(&gpu, R11, R10, 0);
    axel_str(&gpu, R12, R10, 1);
    axel_str(&gpu, R13, R10, 2);
    axel_str(&gpu, R14, R10, 3);
    axel_ret(&gpu);

    axel_compile(&gpu, "hex/phase5_weight_update.hex");
    axel_compile_bin(&gpu, "bin/phase5_weight_update.axelbin");

    printf("Phase 5 — Weight update (Q8): %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}