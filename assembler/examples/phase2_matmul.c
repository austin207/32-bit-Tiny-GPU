#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 2 — 4×4 matrix-vector multiply
     *
     * Pre-loaded memory (set in testbench INITIAL_MEMORY):
     *   mem[0..15]  = W[4][4]  row-major:  W[i][j] at addr i*4+j
     *   mem[16..19] = x[4]    input vector
     *
     * GPU writes:
     *   mem[20..23] = y[4]    where y[i] = dot(W[i], x)
     *
     * Thread i computes y[i] using 1 MUL + 3 FMA (fully unrolled loop):
     *   y[i] = W[i][0]*x[0] + W[i][1]*x[1] + W[i][2]*x[2] + W[i][3]*x[3]
     */

    /* Load x[0..3] from addresses 16..19 */
    axel_const(&gpu, R1, 16);               /* R1 = 16  (X_BASE)               */
    axel_ldr(&gpu, R2, R1, 0);              /* R2 = x[0]                        */
    axel_ldr(&gpu, R3, R1, 1);              /* R3 = x[1]                        */
    axel_ldr(&gpu, R4, R1, 2);              /* R4 = x[2]                        */
    axel_ldr(&gpu, R5, R1, 3);              /* R5 = x[3]                        */

    /* W row base address: threadIdx * 4 */
    axel_const(&gpu, R6, 4);                /* R6 = 4                           */
    axel_mul(&gpu, R6, THREAD_IDX, R6);     /* R6 = threadIdx * 4               */

    /* Load W[i][0..3] from addresses R6+0 .. R6+3 */
    axel_ldr(&gpu, R7,  R6, 0);             /* R7  = W[i][0]                    */
    axel_ldr(&gpu, R8,  R6, 1);             /* R8  = W[i][1]                    */
    axel_ldr(&gpu, R9,  R6, 2);             /* R9  = W[i][2]                    */
    axel_ldr(&gpu, R10, R6, 3);             /* R10 = W[i][3]                    */

    /* Dot product using MUL + FMA */
    axel_mul(&gpu, R11, R7,  R2);           /* R11  = W[i][0]*x[0]              */
    axel_fma(&gpu, R11, R8,  R3, R11);      /* R11 += W[i][1]*x[1]              */
    axel_fma(&gpu, R11, R9,  R4, R11);      /* R11 += W[i][2]*x[2]              */
    axel_fma(&gpu, R11, R10, R5, R11);      /* R11 += W[i][3]*x[3]              */

    /* Store y[i] at address 20 + threadIdx */
    axel_const(&gpu, R12, 20);              /* R12 = 20  (Y_BASE)               */
    axel_add(&gpu, R12, R12, THREAD_IDX);   /* R12 = Y_BASE + i                 */
    axel_str(&gpu, R11, R12, 0);            /* mem[Y_BASE + i] = y[i]           */
    axel_ret(&gpu);

    axel_compile(&gpu, "hex/phase2_matmul.hex");
    axel_compile_bin(&gpu, "bin/phase2_matmul.axelbin");

    printf("Phase 2 — matmul: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}