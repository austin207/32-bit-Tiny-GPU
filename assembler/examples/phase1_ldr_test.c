#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 1 — LDR end-to-end test
     *
     * Pre-loaded memory (set in testbench INITIAL_MEMORY):
     *   mem[0..3] = {10, 20, 30, 40}
     *
     * Each thread i:
     *   R1 = mem[threadIdx]       (LDR from mem[i])
     *   R2 = R1 + R1              (double the value)
     *   mem[threadIdx + 4] = R2   (STR to mem[i+4])
     *
     * Expected output:
     *   mem[4]=20  mem[5]=40  mem[6]=60  mem[7]=80
     */

    axel_ldr(&gpu, R1, THREAD_IDX, 0);   /* R1 = mem[threadIdx]         */
    axel_add(&gpu, R2, R1, R1);           /* R2 = 2 * R1                 */
    axel_str(&gpu, R2, THREAD_IDX, 4);   /* mem[threadIdx + 4] = R2     */
    axel_ret(&gpu);

    axel_compile(&gpu, "phase1_ldr_test.hex");

    printf("Phase 1 — LDR test: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}