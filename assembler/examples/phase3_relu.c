#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 3 — Branchless ReLU: y = max(0, x)
     *
     * Avoids BRnzp so there is no SIMD branch divergence across threads.
     * Uses bit manipulation on the sign bit instead:
     *
     *   sign = x >> 31              (0 if x>=0,  1 if x<0)
     *   mask = NOT(0 - sign)        (0xFFFFFFFF if x>=0,  0 if x<0)
     *   y    = x AND mask
     *
     * Pre-loaded memory (set in testbench INITIAL_MEMORY):
     *   mem[0] =  5           (positive  -> stays  5)
     *   mem[1] = -4 (0xFFFFFFFC)  (negative -> becomes 0)
     *   mem[2] =  10          (positive  -> stays 10)
     *   mem[3] = -8 (0xFFFFFFF8)  (negative -> becomes 0)
     *
     * GPU writes:
     *   mem[4..7] = {5, 0, 10, 0}
     */

    axel_ldr(&gpu, R1, THREAD_IDX, 0);  /* R1 = input[threadIdx]              */
    axel_const(&gpu, R2, 31);            /* R2 = 31  (shift amount)            */
    axel_shr(&gpu, R3, R1, R2);          /* R3 = R1 >> 31  (sign bit: 0 or 1) */
    axel_sub(&gpu, R4, R0, R3);          /* R4 = 0 - R3   (0 or 0xFFFFFFFF)   */
    axel_not(&gpu, R4, R4);               /* R4 = ~R4      (pass-through mask)  */
    axel_and(&gpu, R1, R1, R4);          /* R1 = R1 & R4  (ReLU result)        */
    axel_str(&gpu, R1, THREAD_IDX, 4);  /* mem[threadIdx + 4] = R1            */
    axel_ret(&gpu);

    axel_compile(&gpu, "hex/phase3_relu.hex");
    axel_compile_bin(&gpu, "bin/phase3_relu.axelbin");

    printf("Phase 3 — ReLU: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}