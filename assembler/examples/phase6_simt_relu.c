#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    /*
     * Phase 6 — SIMT ReLU: first kernel requiring real branch divergence
     *
     * Data memory embedded in .axelbin (set by axel_set_data):
     *   mem[0] =  5           (thread 0: positive)
     *   mem[1] =  0xFFFFFFFD  (thread 1: -3, negative)
     *   mem[2] =  8           (thread 2: positive)
     *   mem[3] =  0xFFFFFFFF  (thread 3: -1, negative)
     *
     * GPU writes:
     *   mem[4] =  5   (thread 0 kept value)
     *   mem[5] =  0   (thread 1 zeroed)
     *   mem[6] =  8   (thread 2 kept value)
     *   mem[7] =  0   (thread 3 zeroed)
     *
     * Divergence: threads 0,2 positive → take branch (skip zeroing)
     *             threads 1,3 negative → don't take branch (zero R1)
     *
     * PC layout:
     *   PC 0: LDR  R1, THREAD_IDX, 0
     *   PC 1: CMP  R1, R0
     *   PC 2: BRnzp P, sync_offset=2, branch_offset=2
     *   PC 3: CONST R1, 0       <- not-taken path (negative inputs)
     *   PC 4: SYNC              <- reconvergence point
     *   PC 5: STR  R1, THREAD_IDX, 4
     *   PC 6: RET
     */

    /* ── Instructions ───────────────────────────────────────────────────── */
    axel_ldr  (&gpu, R1, THREAD_IDX, 0);   /* R1 = mem[threadIdx]         */
    axel_cmp  (&gpu, R1, R0);              /* compare R1 with R0 (0)      */
    axel_brnzp(&gpu, AXEL_P, 2, 2);       /* if P (negative): jump +2    */
    axel_const(&gpu, R1, 0);              /* not-taken: R1 = 0           */
    axel_sync (&gpu);                      /* reconvergence point         */
    axel_str  (&gpu, R1, THREAD_IDX, 4);  /* mem[threadIdx+4] = R1       */
    axel_ret  (&gpu);

    /* ── Data memory — embedded into .axelbin ───────────────────────────── */
    /* Testbench previously set these manually. Now they travel with the   */
    /* binary so any loader (cocotb, FPGA wrapper, future runtime) gets    */
    /* the correct initial memory state without extra configuration.       */
    axel_set_data(&gpu, 0,  5);            /* thread 0 input: +5          */
    axel_set_data(&gpu, 1, (uint32_t)-3);  /* thread 1 input: -3          */
    axel_set_data(&gpu, 2,  8);            /* thread 2 input: +8          */
    axel_set_data(&gpu, 3, (uint32_t)-1);  /* thread 3 input: -1          */

    /* ── Emit both formats ──────────────────────────────────────────────── */
    axel_compile    (&gpu, "hex/phase6_simt_relu.hex");     /* legacy hex      */
    axel_compile_bin(&gpu, "bin/phase6_simt_relu.axelbin"); /* axelbin binary  */

    printf("Phase 6 — SIMT ReLU: %d instructions, %d data words\n",
           gpu.program.count, gpu.data_mem_size);

    printf("Instructions:\n");
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);

    printf("Data segment:\n");
    for (int i = 0; i < gpu.data_mem_size; i++) {
        int32_t signed_val = (int32_t)gpu.data_mem[i];
        printf("  [%d] 0x%08X  (%d)\n", i, gpu.data_mem[i], signed_val);
    }

    return 0;
}