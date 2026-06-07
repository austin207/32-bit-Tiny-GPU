/*
 * phase10_mlp_8out.c
 *
 * Config B — 4-in → 8-out MLP layer.
 *
 * First kernel to use multi-block dispatch for correctness.
 * Block 0 computes neurons 0-3, Block 1 computes neurons 4-7.
 * neuron_id = BLOCK_IDX * 4 + THREAD_IDX  (GPU scaling pattern)
 *
 * Also demonstrates GP-register base addressing (R9) for loading x —
 * confirmed working after lsu_done_latch fix (phase9 broadcast test).
 *
 * Memory layout:
 *   mem[0]     = W_row_0  packed INT8x4 = [ 100,  50, -50,   0]
 *   mem[1]     = W_row_1  packed INT8x4 = [   0, 100,  50, -50]
 *   mem[2]     = W_row_2  packed INT8x4 = [ -50,   0, 100,  50]
 *   mem[3]     = W_row_3  packed INT8x4 = [  50, -50,   0, 100]
 *   mem[4]     = W_row_4  packed INT8x4 = [  80, -80,  40, -40]
 *   mem[5]     = W_row_5  packed INT8x4 = [ -40,  80, -80,  40]
 *   mem[6]     = W_row_6  packed INT8x4 = [  40, -40,  80, -80]
 *   mem[7]     = W_row_7  packed INT8x4 = [ -80,  40, -40,  80]
 *   mem[8]     = x packed INT8x4 = [85, 42, 127, 17]  (single copy, GP-reg load)
 *   mem[12..19] = y[0..7] INT32 output
 *
 * Kernel (per thread, neuron_id = BLOCK_IDX*4 + THREAD_IDX):
 *   R6 = 4
 *   R7 = BLOCK_IDX * R6          MUL: R7 = BLOCK_IDX * 4
 *   R8 = R7 + THREAD_IDX         ADD: R8 = neuron_id
 *   R1 = mem[R8 + 0]             LDR: W_row[neuron_id]
 *   R9 = 8
 *   R2 = mem[R9 + 0]             LDR: x  (GP-reg base, not THREAD_IDX)
 *   R3 = DOT4(R3, R1, R2)
 *   R5 = 8
 *   R4 = SAR(R3, R5)
 *   R4 = RELU(R4)
 *   R4 = CLAMP(R4)
 *   mem[R8 + 12] = R4            STR: y[neuron_id]
 *   RET
 *
 * Golden reference (Python, Q8 scale = 256):
 *   x = [85, 42, 127, 17]
 *   W = [[100,50,-50,0],[0,100,50,-50],[-50,0,100,50],[50,-50,0,100],
 *        [80,-80,40,-40],[-40,80,-80,40],[40,-40,80,-80],[-80,40,-40,80]]
 *   y[i] = clamp(relu(dot(W[i], x) >> 8), -128, 127)
 *
 * Expected output at mem[12..19]:
 *   y[0] = 16   y[1] = 37   y[2] = 36   y[3] = 15
 *   y[4] = 30   y[5] = 0    y[6] = 41   y[7] = 0
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 2, 4);  /* 2 blocks, 4 threads per block */

    /* Weight rows 0-3 for block 0 */
    axel_set_data(&gpu, 0, 0x00CE3264);  /* W_row_0 = [ 100,  50, -50,   0] */
    axel_set_data(&gpu, 1, 0xCE326400);  /* W_row_1 = [   0, 100,  50, -50] */
    axel_set_data(&gpu, 2, 0x326400CE);  /* W_row_2 = [ -50,   0, 100,  50] */
    axel_set_data(&gpu, 3, 0x6400CE32);  /* W_row_3 = [  50, -50,   0, 100] */

    /* Weight rows 4-7 for block 1 */
    axel_set_data(&gpu, 4, 0xD828B050);  /* W_row_4 = [  80, -80,  40, -40] */
    axel_set_data(&gpu, 5, 0x28B050D8);  /* W_row_5 = [ -40,  80, -80,  40] */
    axel_set_data(&gpu, 6, 0xB050D828);  /* W_row_6 = [  40, -40,  80, -80] */
    axel_set_data(&gpu, 7, 0x50D828B0);  /* W_row_7 = [ -80,  40, -40,  80] */

    /* x — single copy, loaded via R9 (GP-reg base) */
    axel_set_data(&gpu, 8, 0x117F2A55);  /* x = [85, 42, 127, 17] */

    /* Output slots */
    for (int i = 12; i < 20; i++)
        axel_set_data(&gpu, i, 0);

    /* Kernel: neuron_id = BLOCK_IDX * 4 + THREAD_IDX */
    axel_const(&gpu, R6,          4);              /* R6  = 4 (blockDim) */
    axel_mul  (&gpu, R7, BLOCK_IDX, R6);           /* R7  = BLOCK_IDX * 4 */
    axel_add  (&gpu, R8, R7,     THREAD_IDX);      /* R8  = neuron_id */
    axel_ldr  (&gpu, R1, R8,          0);          /* R1  = W_row[neuron_id] */
    axel_const(&gpu, R9,          8);              /* R9  = 8 (base of x) */
    axel_ldr  (&gpu, R2, R9,          0);          /* R2  = x (GP-reg base) */
    axel_dot  (&gpu, R3, R1,         R2);          /* R3  = dot(W_row_i, x) */
    axel_const(&gpu, R5,          8);              /* R5  = 8 (SAR shift) */
    axel_sar  (&gpu, R4, R3,         R5);          /* R4  = R3 >> 8 */
    axel_relu (&gpu, R4, R4,         R1);          /* R4  = relu(R4) */
    axel_clamp(&gpu, R4, R4,         R1);          /* R4  = clamp(R4) */
    axel_str  (&gpu, R4, R8,         12);          /* mem[neuron_id+12] = R4 */
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase10_mlp_8out.hex");
    axel_compile_bin(&gpu, "bin/phase10_mlp_8out.axelbin");

    printf("phase10_mlp_8out: 4-in -> 8-out, 2 blocks x 4 threads\n");
    printf("expected y[0..7] at mem[12..19] = [16, 37, 36, 15, 30, 0, 41, 0]\n");

    return 0;
}