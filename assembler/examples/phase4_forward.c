#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 4 — Forward pass: Linear layer + ReLU
     *
     * Combines Phase 2 (matmul) and Phase 3 (branchless ReLU) into one kernel.
     *
     * Pre-loaded memory (set in testbench INITIAL_MEMORY):
     *   mem[0..15]  = W[4][4]  weights
     *   mem[16..19] = x[4]    input vector
     *
     * GPU writes:
     *   mem[20..23] = y[4] = ReLU(W * x)
     *
     * Thread i:
     *   z[i] = dot(W[i], x)   via MUL + FMA
     *   y[i] = ReLU(z[i])     via bit-manipulation mask
     */

    /* ── MATMUL ──────────────────────────────────────── */
    axel_const(&gpu, R1, 16);               /* R1 = 16  (X_BASE)              */
    axel_ldr(&gpu, R2, R1, 0);              /* R2 = x[0]                      */
    axel_ldr(&gpu, R3, R1, 1);              /* R3 = x[1]                      */
    axel_ldr(&gpu, R4, R1, 2);              /* R4 = x[2]                      */
    axel_ldr(&gpu, R5, R1, 3);              /* R5 = x[3]                      */

    axel_const(&gpu, R6, 4);
    axel_mul(&gpu, R6, THREAD_IDX, R6);     /* R6 = threadIdx * 4             */

    axel_ldr(&gpu, R7,  R6, 0);             /* R7  = W[i][0]                  */
    axel_ldr(&gpu, R8,  R6, 1);             /* R8  = W[i][1]                  */
    axel_ldr(&gpu, R9,  R6, 2);             /* R9  = W[i][2]                  */
    axel_ldr(&gpu, R10, R6, 3);             /* R10 = W[i][3]                  */

    axel_mul(&gpu, R11, R7,  R2);           /* R11  = W[i][0]*x[0]            */
    axel_fma(&gpu, R11, R8,  R3, R11);      /* R11 += W[i][1]*x[1]            */
    axel_fma(&gpu, R11, R9,  R4, R11);      /* R11 += W[i][2]*x[2]            */
    axel_fma(&gpu, R11, R10, R5, R11);      /* R11 += W[i][3]*x[3]            */

    /* ── BRANCHLESS ReLU ─────────────────────────────── */
    axel_const(&gpu, R12, 31);              /* R12 = 31                       */
    axel_shr(&gpu, R13, R11, R12);          /* R13 = sign bit of z[i]         */
    axel_sub(&gpu, R14, R0,  R13);          /* R14 = 0 - sign                 */
    axel_not(&gpu, R14, R14);               /* R14 = pass-through mask        */
    axel_and(&gpu, R11, R11, R14);          /* R11 = ReLU(z[i])               */

    /* ── STORE ───────────────────────────────────────── */
    axel_const(&gpu, R15, 20);              /* R15 = 20  (Y_BASE)             */
    axel_add(&gpu, R15, R15, THREAD_IDX);   /* R15 = Y_BASE + i               */
    axel_str(&gpu, R11, R15, 0);            /* mem[Y_BASE + i] = y[i]         */
    axel_ret(&gpu);

    axel_compile(&gpu, "phase4_forward.hex");

    printf("Phase 4 — Forward pass: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}