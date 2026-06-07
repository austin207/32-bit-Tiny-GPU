/*
 * phase13_digit_hidden.c
 *
 * Two-layer digit classifier — hidden layer pass.
 * Part 1 of 2: computes h = CLAMP(RELU(SAR(W_h * x, 8)))
 *
 * Architecture : 16-in -> 4-hidden -> 4-out
 * This file    : hidden layer only (4 neurons, 1 block x 4 threads)
 * Second pass  : phase14_digit_output.c reads h from data memory
 *
 * Memory layout (shared between both passes):
 *
 *   W_h weights (4 rows x 4 packed INT8x4 words = 16 words):
 *     mem[0..3]   W_h[0][0..3]   neuron 0 weights
 *     mem[4..7]   W_h[1][0..3]   neuron 1 weights
 *     mem[8..11]  W_h[2][0..3]   neuron 2 weights
 *     mem[12..15] W_h[3][0..3]   neuron 3 weights
 *
 *   Input x (4 packed INT8x4 words = 16 elements):
 *     mem[16..19] x[0..3]
 *
 *   Hidden outputs (written by this kernel, read by phase14):
 *     mem[20..23] h[0..3]   INT32 values in INT8 range after CLAMP
 *
 *   (W_o and y at mem[24..43] — untouched by this kernel)
 *
 * Kernel (per thread i = THREAD_IDX):
 *   R7  = THREAD_IDX * 4          weight_base for this neuron
 *   R8  = 16                       x_base
 *   R3  = 0 initially              DOT4 accumulator
 *   4x: LDR R1, R7, k; LDR R2, R8, k; DOT4 R3, R1, R2
 *   R4  = CLAMP(RELU(SAR(R3, 8)))
 *   mem[20 + THREAD_IDX] = R4
 *
 * Weight values (INT8, packed):
 *   W_h[0] = [32, 16,  8,  4, 32, 16,  8,  4, 32, 16,  8,  4, 32, 16,  8,  4]
 *   W_h[1] = [16, 32, 16,  8, 16, 32, 16,  8, 16, 32, 16,  8, 16, 32, 16,  8]
 *   W_h[2] = [-16, 8, 32, 16,-16,  8, 32, 16,-16,  8, 32, 16,-16,  8, 32, 16]
 *   W_h[3] = [  8,-16,  8, 32,  8,-16,  8, 32,  8,-16,  8, 32,  8,-16,  8, 32]
 *
 * Input x (INT8, packed):
 *   x = [64, 32, 16, 8] repeated 4x
 *
 * Golden reference (Python):
 *   x_flat = [64,32,16,8]*4
 *   W_h = [[32,16,8,4]*4, [16,32,16,8]*4, [-16,8,32,16]*4, [8,-16,8,32]*4]
 *   h[i] = clamp(relu(sum(W_h[i][k]*x_flat[k] for k in range(16)) >> 8), -128, 127)
 *
 * dot values:
 *   neuron 0: 4*(32*64+16*32+8*16+4*8) = 4*2720 = 10880 -> SAR8=42
 *   neuron 1: 4*(16*64+32*32+16*16+8*8) = 4*2368 = 9472  -> SAR8=37
 *   neuron 2: 4*(-16*64+8*32+32*16+16*8) = 4*-128 = -512  -> SAR8=-2 -> RELU->0
 *   neuron 3: 4*(8*64-16*32+8*16+32*8)  = 4*384  = 1536  -> SAR8=6
 *
 * Expected h[0..3] at mem[20..23] = [42, 37, 0, 6]
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);  /* 1 block, 4 threads */

    /* W_h[0] = [32,16,8,4] x4 packed */
    axel_set_data(&gpu, 0,  0x04081020); /* W_h[0][0..3] */
    axel_set_data(&gpu, 1,  0x04081020); /* W_h[0][4..7] */
    axel_set_data(&gpu, 2,  0x04081020); /* W_h[0][8..11] */
    axel_set_data(&gpu, 3,  0x04081020); /* W_h[0][12..15] */

    /* W_h[1] = [16,32,16,8] x4 packed */
    axel_set_data(&gpu, 4,  0x08102010); /* W_h[1][0..3] */
    axel_set_data(&gpu, 5,  0x08102010); /* W_h[1][4..7] */
    axel_set_data(&gpu, 6,  0x08102010); /* W_h[1][8..11] */
    axel_set_data(&gpu, 7,  0x08102010); /* W_h[1][12..15] */

    /* W_h[2] = [-16,8,32,16] x4 packed  (-16 = 0xF0) */
    axel_set_data(&gpu, 8,  0x102008F0); /* W_h[2][0..3] */
    axel_set_data(&gpu, 9,  0x102008F0); /* W_h[2][4..7] */
    axel_set_data(&gpu, 10, 0x102008F0); /* W_h[2][8..11] */
    axel_set_data(&gpu, 11, 0x102008F0); /* W_h[2][12..15] */

    /* W_h[3] = [8,-16,8,32] x4 packed  (-16 = 0xF0) */
    axel_set_data(&gpu, 12, 0x2008F008); /* W_h[3][0..3] */
    axel_set_data(&gpu, 13, 0x2008F008); /* W_h[3][4..7] */
    axel_set_data(&gpu, 14, 0x2008F008); /* W_h[3][8..11] */
    axel_set_data(&gpu, 15, 0x2008F008); /* W_h[3][12..15] */

    /* x = [64,32,16,8] x4  (0x40,0x20,0x10,0x08) */
    axel_set_data(&gpu, 16, 0x08102040); /* x[0..3] */
    axel_set_data(&gpu, 17, 0x08102040); /* x[4..7] */
    axel_set_data(&gpu, 18, 0x08102040); /* x[8..11] */
    axel_set_data(&gpu, 19, 0x08102040); /* x[12..15] */

    /* h output slots (written by kernel) */
    axel_set_data(&gpu, 20, 0);
    axel_set_data(&gpu, 21, 0);
    axel_set_data(&gpu, 22, 0);
    axel_set_data(&gpu, 23, 0);

    /* Kernel: 4 DOT4 batches per thread */
    axel_const(&gpu, R6,          4);              /* R6  = 4 */
    axel_mul  (&gpu, R7, THREAD_IDX, R6);          /* R7  = THREAD_IDX * 4 (weight base) */
    axel_const(&gpu, R8,         16);              /* R8  = 16 (x base) */

    axel_ldr  (&gpu, R1, R7, 0);   axel_ldr(&gpu, R2, R8, 0);   axel_dot(&gpu, R3, R1, R2);
    axel_ldr  (&gpu, R1, R7, 1);   axel_ldr(&gpu, R2, R8, 1);   axel_dot(&gpu, R3, R1, R2);
    axel_ldr  (&gpu, R1, R7, 2);   axel_ldr(&gpu, R2, R8, 2);   axel_dot(&gpu, R3, R1, R2);
    axel_ldr  (&gpu, R1, R7, 3);   axel_ldr(&gpu, R2, R8, 3);   axel_dot(&gpu, R3, R1, R2);

    axel_const(&gpu, R5,          8);              /* R5  = 8 (shift) */
    axel_sar  (&gpu, R4, R3, R5);                  /* R4  = R3 >> 8 */
    axel_relu (&gpu, R4, R4, R1);                  /* R4  = relu(R4) */
    axel_clamp(&gpu, R4, R4, R1);                  /* R4  = clamp(R4) */

    axel_const(&gpu, R9,         20);              /* R9  = 20 (h base) */
    axel_add  (&gpu, R10, R9, THREAD_IDX);         /* R10 = 20 + THREAD_IDX */
    axel_str  (&gpu, R4, R10, 0);                  /* mem[20+i] = h[i] */
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase13_digit_hidden.hex");
    axel_compile_bin(&gpu, "bin/phase13_digit_hidden.axelbin");

    printf("phase13_digit_hidden: 16-in -> 4-hidden, 4x DOT4 per thread\n");
    printf("expected h[0..3] at mem[20..23] = [42, 37, 0, 6]\n");

    return 0;
}