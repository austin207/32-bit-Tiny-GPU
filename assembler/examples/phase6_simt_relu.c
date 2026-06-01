#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 6 — SIMT ReLU: first kernel requiring real branch divergence
     *
     * Memory pre-loaded by testbench:
     *   mem[0] =  5          (thread 0: positive)
     *   mem[1] =  0xFFFFFFFD (thread 1: -3, negative)
     *   mem[2] =  8          (thread 2: positive)
     *   mem[3] =  0xFFFFFFFF (thread 3: -1, negative)
     *
     * GPU writes:
     *   mem[4] =  5  (thread 0 kept value)
     *   mem[5] =  0  (thread 1 zeroed)
     *   mem[6] =  8  (thread 2 kept value)
     *   mem[7] =  0  (thread 3 zeroed)
     *
     * Divergence: threads 0,2 positive → take branch (skip zeroing)
     *             threads 1,3 negative → don't take branch (zero R1)
     *
     * PC layout:
     *   PC 0: LDR  R1, THREAD_IDX, 0
     *   PC 1: CMP  R1, R0
     *   PC 2: BRnzp P, sync_offset=2, branch_offset=2
     *   PC 3: CONST R1, 0       <- not-taken path
     *   PC 4: SYNC              <- reconvergence point
     *   PC 5: STR  R1, THREAD_IDX, 4
     *   PC 6: RET
     */

    axel_ldr  (&gpu, R1, THREAD_IDX, 0);    /* R1 = mem[threadIdx]         */
    axel_cmp  (&gpu, R1, R0);               /* compare R1 with 0           */
    axel_brnzp(&gpu, AXEL_P, 2, 2);        /* if P: jump +2 to SYNC       */
    axel_const(&gpu, R1, 0);               /* else: R1 = 0                */
    axel_sync (&gpu);                       /* reconvergence point         */
    axel_str  (&gpu, R1, THREAD_IDX, 4);   /* mem[threadIdx+4] = R1       */
    axel_ret  (&gpu);

    axel_compile(&gpu, "phase6_simt_relu.hex");

    printf("Phase 6 — SIMT ReLU: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    return 0;
}