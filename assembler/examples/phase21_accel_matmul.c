#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 4, 4);  /* 4 blocks × 4 threads */

    /*
     * Phase 21 — Memory-mapped matmul accelerator
     *
     * All 16 threads (4 blocks × 4 threads) execute the same kernel:
     *   1. Write ctrl regs via STR to 0x1F0–0x1F7
     *   2. Write START=1 to 0x1F7  → accelerator launches
     *   3. Poll DONE at 0x1F8      → spin while DONE=0
     *   4. RET when DONE=1
     *
     * RTL intercepts addr >= 0x1F0 in top_level_gpu and routes to
     * matmul_accelerator ctrl port (not external data_mem).
     * All cores write identical param values; priority arbiter takes first.
     *
     * Accelerator computes: C = A × B  (4×4, K=16, 4 DOT4 chunks)
     * Same matrix data and expected C as phase20.
     *
     * Memory layout:
     *   mem[0..15]  = A rows (4 chunks × 4 rows)
     *   mem[16..31] = B^T cols (4 chunks × 4 cols)
     *   mem[32..47] = C output [4][4] INT32 (written by accelerator)
     *
     * PC layout:
     *   PC  0: CONST R1, 0x1F0        ctrl reg base addr
     *   PC  1: CONST R2, 0
     *   PC  2: STR   R2, R1, 0        A_BASE  = 0
     *   PC  3: CONST R2, 16
     *   PC  4: STR   R2, R1, 1        B_BASE  = 16
     *   PC  5: CONST R2, 32
     *   PC  6: STR   R2, R1, 2        C_BASE  = 32
     *   PC  7: CONST R2, 4
     *   PC  8: STR   R2, R1, 3        M       = 4
     *   PC  9: STR   R2, R1, 4        N       = 4  (R2 still 4)
     *   PC 10: CONST R2, 16
     *   PC 11: STR   R2, R1, 5        K       = 16
     *   PC 12: CONST R2, 0
     *   PC 13: STR   R2, R1, 6        SCALE   = 0
     *   PC 14: CONST R2, 1
     *   PC 15: STR   R2, R1, 7        START   = 1  <- launches accelerator
     *   PC 16: LDR   R3, R0, 0x1F8   R3 = DONE (poll loop start)
     *   PC 17: CMP   R3, R0           NZP = sign(R3)
     *   PC 18: BRnzp Z, 0, -3         if DONE=0 (Z) → branch to PC 16
     *   PC 19: RET                     DONE=1, all threads exit
     *
     * No SIMT divergence: all 16 threads see same DONE value.
     * sync_offset=0 (no reconvergence needed).
     */

    /* ── Setup: write ctrl registers ──────────────────────────────────── */
    axel_const(&gpu, R1, 0x1F0);          /* R1 = ctrl reg base           */

    axel_const(&gpu, R2, 0);
    axel_str  (&gpu, R2, R1, 0);          /* A_BASE  = 0                  */

    axel_const(&gpu, R2, 16);
    axel_str  (&gpu, R2, R1, 1);          /* B_BASE  = 16                 */

    axel_const(&gpu, R2, 32);
    axel_str  (&gpu, R2, R1, 2);          /* C_BASE  = 32                 */

    axel_const(&gpu, R2, 4);
    axel_str  (&gpu, R2, R1, 3);          /* M       = 4                  */
    axel_str  (&gpu, R2, R1, 4);          /* N       = 4  (R2 still 4)    */

    axel_const(&gpu, R2, 16);
    axel_str  (&gpu, R2, R1, 5);          /* K       = 16                 */

    axel_const(&gpu, R2, 0);
    axel_str  (&gpu, R2, R1, 6);          /* SCALE   = 0                  */

    axel_const(&gpu, R2, 1);
    axel_str  (&gpu, R2, R1, 7);          /* START   = 1 → launch         */

    /* ── Poll loop: spin while DONE=0 ──────────────────────────────────── */
    /* PC 16 */ axel_ldr  (&gpu, R3, R0, 0x1F8);  /* R3 = DONE register   */
    /* PC 17 */ axel_cmp  (&gpu, R3, R0);          /* CMP R3, 0            */
    /* PC 18 */ axel_brnzp(&gpu, AXEL_Z, 0, -2);   /* if Z (DONE=0) → PC 16, under real target=branch_pc+offset semantics */
    /* PC 19 */ axel_ret  (&gpu);                   /* DONE=1, exit         */

    /* ── Matrix data (same as phase20) ─────────────────────────────────── */
    /* A rows: row i at mem[i*4 .. i*4+3], 4 identical DOT4 chunks        */
    int i;
    for (i = 0; i < 4; i++) axel_set_data(&gpu,  0+i, 0x01010101); /* row0 [1,1,1,1] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu,  4+i, 0x02020202); /* row1 [2,2,2,2] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu,  8+i, 0x00040300); /* row2 [0,3,4,0] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 12+i, 0x04030201); /* row3 [1,2,3,4] */

    /* B^T cols: col k at mem[16+k*4 .. 16+k*4+3], 4 identical chunks     */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 16+i, 0x01010101); /* col0 [1,1,1,1] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 20+i, 0x02020202); /* col1 [2,2,2,2] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 24+i, 0x00010001); /* col2 [1,0,1,0] */
    for (i = 0; i < 4; i++) axel_set_data(&gpu, 28+i, 0x01000100); /* col3 [0,1,0,1] */

    printf("Phase 21 — accel matmul: %d instructions\n", gpu.program.count);
    for (i = 0; i < gpu.program.count; i++)
        printf("  [%2d] 0x%08X\n", i, gpu.program.instructions[i]);

    axel_compile    (&gpu, "hex/phase21_accel_matmul.hex");
    axel_compile_bin(&gpu, "bin/phase21_accel_matmul.axelbin");

    return 0;
}