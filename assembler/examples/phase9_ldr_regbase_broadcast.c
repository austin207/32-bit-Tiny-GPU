/*
 * phase9_ldr_regbase_broadcast.c
 *
 * Verifies that all 4 SIMT threads can load from the SAME address using a
 * general-purpose register (R6) as the LDR base.
 *
 * This is the critical multi-thread case. All threads issue LDR to the
 * same address. The round-robin memory controller must serialize them,
 * return resp_valid to the correct in_flight thread each time, and the
 * lsu_done_latch must accumulate all 4 completions before the scheduler
 * exits WAIT.
 *
 * If this passes, the old comment in phase8_mlp_inference.c that restricts
 * LDR base to R29/R30/R31 is confirmed stale.
 *
 * Config: 1 block, 4 threads (blockDim = 4)
 *
 * Memory layout:
 *   mem[4]      = 0x12345678  (shared source, pre-loaded)
 *   mem[8..11]  = results     (thread 0..3 write here)
 *
 * Program (all 4 threads execute identically):
 *   CONST R6, 4              -> R6 = 4  (same in every thread)
 *   LDR   R1, R6, 0          -> R1 = mem[4] = 0x12345678  (all 4 threads)
 *   STR   R1, THREAD_IDX, 8  -> mem[THREAD_IDX + 8] = R1
 *   RET
 *
 * Expected output:
 *   mem[8]  = 0x12345678  (thread 0)
 *   mem[9]  = 0x12345678  (thread 1)
 *   mem[10] = 0x12345678  (thread 2)
 *   mem[11] = 0x12345678  (thread 3)
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    axel_set_data(&gpu, 4, 0x12345678);

    axel_const(&gpu, R6,             4);
    axel_ldr  (&gpu, R1, R6,         0);
    axel_str  (&gpu, R1, THREAD_IDX, 8);
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase9_ldr_regbase_broadcast.hex");
    axel_compile_bin(&gpu, "bin/phase9_ldr_regbase_broadcast.axelbin");

    printf("phase9_ldr_regbase_broadcast: %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++)
        printf("  [%d] 0x%08X\n", i, gpu.program.instructions[i]);
    printf("Expected: mem[8..11] = 0x12345678 (all 4 threads)\n");

    return 0;
}