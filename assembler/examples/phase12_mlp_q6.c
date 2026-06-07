/*
 * phase12_mlp_q6.c
 *
 * Config D — 4-in → 4-out MLP layer, Q6 quantization (SAR 6).
 *
 * Same shape as phase8 but different scale factor.
 * Phase8 used SAR 8 (scale = 256, real = q / 256).
 * This uses SAR 6  (scale = 64,  real = q / 64).
 *
 * Demonstrates that the GPU correctly handles different quantization
 * granularities by simply changing the shift constant.
 *
 * Memory layout:
 *   mem[0] = W_row_0  INT8x4 = [ 50,  25, -25,  10]
 *   mem[1] = W_row_1  INT8x4 = [ 10,  50,  25, -25]
 *   mem[2] = W_row_2  INT8x4 = [-25,  10,  50,  25]
 *   mem[3] = W_row_3  INT8x4 = [ 25, -25,  10,  50]
 *   mem[4..7] = x replicated (same as phase8 pattern for compatibility)
 *               INT8x4 = [85, 42, 127, 17]
 *   mem[8..11] = y[0..3] INT32 output
 *
 * Kernel (identical to phase8 except R5 = 6 instead of 8):
 *   R1 = W_row_i          LDR THREAD_IDX + 0
 *   R2 = x                LDR THREAD_IDX + 4
 *   R3 = DOT4(R3, R1, R2)
 *   R5 = 6                CONST shift (Q6, not Q8)
 *   R4 = SAR(R3, R5)
 *   R4 = RELU(R4)
 *   R4 = CLAMP(R4)
 *   mem[THREAD_IDX + 8] = R4
 *   RET
 *
 * Golden reference (Python, Q6 scale = 64):
 *   x = [85, 42, 127, 17]
 *   W = [[50,25,-25,10],[10,50,25,-25],[-25,10,50,25],[25,-25,10,50]]
 *   y[i] = clamp(relu(dot(W[i], x) >> 6), -128, 127)
 *   dot values: [2295, 5700, 5070, 3195]
 *   sar6:       [35,   89,   79,   49]
 *
 * Expected output at mem[8..11]:
 *   y[0] = 35   y[1] = 89   y[2] = 79   y[3] = 49
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);  /* 1 block, 4 threads */

    /* Weight rows */
    axel_set_data(&gpu, 0, 0x0AE71932);  /* W_row_0 = [ 50,  25, -25,  10] */
    axel_set_data(&gpu, 1, 0xE719320A);  /* W_row_1 = [ 10,  50,  25, -25] */
    axel_set_data(&gpu, 2, 0x19320AE7);  /* W_row_2 = [-25,  10,  50,  25] */
    axel_set_data(&gpu, 3, 0x320AE719);  /* W_row_3 = [ 25, -25,  10,  50] */

    /* x replicated (same layout as phase8 for structural comparison) */
    axel_set_data(&gpu, 4, 0x117F2A55);
    axel_set_data(&gpu, 5, 0x117F2A55);
    axel_set_data(&gpu, 6, 0x117F2A55);
    axel_set_data(&gpu, 7, 0x117F2A55);

    /* Output slots */
    for (int i = 8; i < 12; i++)
        axel_set_data(&gpu, i, 0);

    /* Kernel: identical to phase8 except SAR shift = 6 */
    axel_ldr  (&gpu, R1, THREAD_IDX, 0);   /* R1 = W_row_i */
    axel_ldr  (&gpu, R2, THREAD_IDX, 4);   /* R2 = x */
    axel_dot  (&gpu, R3, R1,         R2);  /* R3 = dot(W_row_i, x) */
    axel_const(&gpu, R5,              6);  /* R5 = 6  (Q6, not Q8) */
    axel_sar  (&gpu, R4, R3,         R5);  /* R4 = R3 >> 6 */
    axel_relu (&gpu, R4, R4,         R1);  /* R4 = relu(R4) */
    axel_clamp(&gpu, R4, R4,         R1);  /* R4 = clamp(R4) */
    axel_str  (&gpu, R4, THREAD_IDX,  8);  /* mem[THREAD_IDX+8] = y[i] */
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase12_mlp_q6.hex");
    axel_compile_bin(&gpu, "bin/phase12_mlp_q6.axelbin");

    printf("phase12_mlp_q6: 4-in -> 4-out, Q6 scale (SAR 6)\n");
    printf("expected y[0..3] at mem[8..11] = [35, 89, 79, 49]\n");

    return 0;
}