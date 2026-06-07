/*
 * phase9_ldr_regbase_single.c
 *
 * Verifies that a general-purpose register (R6) can serve as an LDR base
 * address in single-thread mode.
 *
 * After the lsu_done_latch fix in core.sv, the old claim that LDR base
 * must be R29/R30/R31 should be obsolete. This test confirms that.
 *
 * Config: 1 block, 1 thread (blockDim = 1, THREAD_IDX = 0)
 *
 * Memory layout:
 *   mem[4]  = 0x12345678  (source, pre-loaded)
 *   mem[8]  = result      (written by kernel)
 *
 * Program:
 *   CONST R6, 4          -> R6 = 4
 *   LDR   R1, R6, 0      -> R1 = mem[R6 + 0] = mem[4] = 0x12345678
 *   STR   R1, THREAD_IDX, 8 -> mem[THREAD_IDX + 8] = R1
 *   RET
 *
 * Expected output:
 *   mem[8] = 0x12345678
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 1);

    axel_set_data(&gpu, 4, 0x12345678);

    axel_const(&gpu, R6,         4);
    axel_ldr  (&gpu, R1, R6,     0);
    axel_str  (&gpu, R1, THREAD_IDX, 8);
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase9_ldr_regbase_single.hex");
    axel_compile_bin(&gpu, "bin/phase9_ldr_regbase_single.axelbin");

    printf("phase9_ldr_regbase_single: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    printf("Expected: mem[8] = 0x12345678\n");

    return 0;
}