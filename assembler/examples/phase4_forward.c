#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 4 — Forward pass: Linear layer + ReLU  (Q8 fixed-point, SIMT)
     *
     * Q8 encoding: real value v is stored as round(v * 256)
     *   e.g. 1.0 → 256,  0.5 → 128,  -1.0 → 0xFFFFFF00 (two's complement)
     *
     * Computation per thread i:
     *   z[i] = sum_j( W[i][j] * x[j] ) >> 8      (Q8 × Q8 → Q8)
     *   y[i] = ReLU(z[i])
     *
     * Memory layout (pre-loaded by testbench):
     *   mem[0..15]  = W[4][4]  (Q8 weights, W[i][j] at addr i*4+j)
     *   mem[16..19] = x[4]    (Q8 inputs)
     *
     * GPU writes:
     *   mem[20..23] = y[4]    (Q8 outputs = ReLU(W*x) in Q8)
     *
     * ReLU is implemented via real branch divergence (SIMT):
     *   Threads with z[i] > 0 take the branch and skip zeroing.
     *   Threads with z[i] <= 0 do not take the branch and zero R11.
     *   All threads reconverge at SYNC before the store.
     *
     * PC layout of divergent region:
     *   PC 17: CMP  R11, R0              compare z[i] with 0
     *   PC 18: BRnzp P, sync=2, br=2    if positive: jump to PC 20 (SYNC)
     *   PC 19: CONST R11, 0             not-taken: z[i] = 0
     *   PC 20: SYNC                     reconvergence point
     *   PC 21: CONST R12, 20            Y_BASE
     */

    /* ── LOAD x[0..3] ────────────────────────────────────────────────── */
    axel_const(&gpu, R1, 16);               /* R1 = 16  (X_BASE)          */
    axel_ldr  (&gpu, R2, R1, 0);            /* R2 = x[0]                  */
    axel_ldr  (&gpu, R3, R1, 1);            /* R3 = x[1]                  */
    axel_ldr  (&gpu, R4, R1, 2);            /* R4 = x[2]                  */
    axel_ldr  (&gpu, R5, R1, 3);            /* R5 = x[3]                  */

    /* ── W ROW BASE = threadIdx * 4 ─────────────────────────────────── */
    axel_const(&gpu, R6, 4);
    axel_mul  (&gpu, R6, THREAD_IDX, R6);   /* R6 = threadIdx * 4         */

    /* ── LOAD W[i][0..3] ─────────────────────────────────────────────── */
    axel_ldr(&gpu, R7,  R6, 0);             /* R7  = W[i][0]              */
    axel_ldr(&gpu, R8,  R6, 1);             /* R8  = W[i][1]              */
    axel_ldr(&gpu, R9,  R6, 2);             /* R9  = W[i][2]              */
    axel_ldr(&gpu, R10, R6, 3);             /* R10 = W[i][3]              */

    /* ── DOT PRODUCT (Q8 × Q8 → Q16, then >>8 → Q8) ─────────────────── */
    axel_mul(&gpu, R11, R7,  R2);           /* R11  = W[i][0]*x[0] (Q16)  */
    axel_fma(&gpu, R11, R8,  R3, R11);      /* R11 += W[i][1]*x[1]        */
    axel_fma(&gpu, R11, R9,  R4, R11);      /* R11 += W[i][2]*x[2]        */
    axel_fma(&gpu, R11, R10, R5, R11);      /* R11 += W[i][3]*x[3]        */
    axel_const(&gpu, R12, 8);
    axel_sar  (&gpu, R11, R11, R12);        /* R11 >>= 8  → Q8 z[i]       */

    /* ── SIMT ReLU ───────────────────────────────────────────────────── */
    axel_cmp  (&gpu, R11, R0);             /* compare z[i] with 0         */
    axel_brnzp(&gpu, AXEL_P, 2, 2);       /* if P: jump to SYNC (PC +2)  */
    axel_const(&gpu, R11, 0);             /* not-taken: z[i] = 0         */
    axel_sync (&gpu);                      /* reconvergence point         */

    /* ── STORE y[i] ──────────────────────────────────────────────────── */
    axel_const(&gpu, R12, 20);              /* R12 = 20  (Y_BASE)         */
    axel_add  (&gpu, R12, R12, THREAD_IDX); /* R12 = Y_BASE + i           */
    axel_str  (&gpu, R11, R12, 0);          /* mem[Y_BASE + i] = y[i]     */
    axel_ret  (&gpu);

    axel_compile(&gpu, "hex/phase4_forward.hex");
    axel_compile_bin(&gpu, "bin/phase4_forward.axelbin");

    printf("Phase 4 — Forward pass (Q8, SIMT ReLU): %d instructions\n",
           gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}