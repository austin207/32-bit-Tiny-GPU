/*
 * phase11_mlp_8in.c
 *
 * Config C — 8-in → 4-out MLP layer.
 *
 * First kernel to use double-DOT4 accumulation.
 * Each thread issues two DOT4 instructions, accumulating an 8-element
 * dot product into R3. DOT4 uses rs3=rd as accumulator, so second call
 * adds onto the first result.
 *
 * Memory layout:
 *   mem[0] = W_row_0_low   INT8x4 = [64,  32, -32,   0]  elements 0-3
 *   mem[1] = W_row_0_high  INT8x4 = [32, -16,   8,  -4]  elements 4-7
 *   mem[2] = W_row_1_low   INT8x4 = [ 0,  64,  32, -32]
 *   mem[3] = W_row_1_high  INT8x4 = [-16, 32, -16,   8]
 *   mem[4] = W_row_2_low   INT8x4 = [-32,  0,  64,  32]
 *   mem[5] = W_row_2_high  INT8x4 = [  8,-16,  32, -16]
 *   mem[6] = W_row_3_low   INT8x4 = [32, -32,   0,  64]
 *   mem[7] = W_row_3_high  INT8x4 = [-4,   8, -16,  32]
 *   mem[8] = x_low   INT8x4 = [85, 42, 127, 17]
 *   mem[9] = x_high  INT8x4 = [60, -30, 10, -5]
 *   mem[10..13] = y[0..3] INT32 output
 *
 * Kernel (per thread i = THREAD_IDX):
 *   R6  = 1
 *   R7  = THREAD_IDX << 1          (R7 = i * 2, base of weight row)
 *   R1  = mem[R7 + 0]              W_row_i_low
 *   R2  = mem[R7 + 1]              W_row_i_high
 *   R10 = 8
 *   R8  = mem[R10 + 0]             x_low  from mem[8]
 *   R9  = mem[R10 + 1]             x_high from mem[9]
 *   R3  = DOT4(R3, R1, R8)         R3  = 0 + dot(W_low, x_low)
 *   R3  = DOT4(R3, R2, R9)         R3 += dot(W_high, x_high)
 *   R5  = 8
 *   R4  = SAR(R3, R5)
 *   R4  = RELU(R4)
 *   R4  = CLAMP(R4)
 *   mem[THREAD_IDX + 10] = R4
 *   RET
 *
 * Golden reference (Python):
 *   x  = [85, 42, 127, 17, 60, -30, 10, -5]
 *   W  = [[64,32,-32,0,32,-16,8,-4],
 *          [0,64,32,-32,-16,32,-16,8],
 *          [-32,0,64,32,8,-16,32,-16],
 *          [32,-32,0,64,-4,8,-16,32]]
 *   y[i] = clamp(relu(dot(W[i], x) >> 8), -128, 127)
 *   dot values: [5220, 4088, 7312, 1664]
 *   sar8:       [20,   15,   28,   6]
 *
 * Expected output at mem[10..13]:
 *   y[0] = 20   y[1] = 15   y[2] = 28   y[3] = 6
 */

#include <stdio.h>
#include "axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);  /* 1 block, 4 threads */

    /* Weight row halves: paired layout, thread i owns mem[2i] and mem[2i+1] */
    axel_set_data(&gpu, 0, 0x00E02040);  /* W_row_0_low  = [ 64,  32, -32,   0] */
    axel_set_data(&gpu, 1, 0xFC08F020);  /* W_row_0_high = [ 32, -16,   8,  -4] */
    axel_set_data(&gpu, 2, 0xE0204000);  /* W_row_1_low  = [  0,  64,  32, -32] */
    axel_set_data(&gpu, 3, 0x08F020F0);  /* W_row_1_high = [-16,  32, -16,   8] */
    axel_set_data(&gpu, 4, 0x204000E0);  /* W_row_2_low  = [-32,   0,  64,  32] */
    axel_set_data(&gpu, 5, 0xF020F008);  /* W_row_2_high = [  8, -16,  32, -16] */
    axel_set_data(&gpu, 6, 0x4000E020);  /* W_row_3_low  = [ 32, -32,   0,  64] */
    axel_set_data(&gpu, 7, 0x20F008FC);  /* W_row_3_high = [ -4,   8, -16,  32] */

    /* x split into low and high halves */
    axel_set_data(&gpu, 8, 0x117F2A55);  /* x_low  = [85, 42, 127, 17] */
    axel_set_data(&gpu, 9, 0xFB0AE23C);  /* x_high = [60,-30,  10, -5] */

    /* Output slots */
    for (int i = 10; i < 14; i++)
        axel_set_data(&gpu, i, 0);

    /* Kernel: 2x DOT4 accumulation for 8-element dot product */
    axel_const(&gpu, R6,            1);           /* R6  = 1 (shift amount for *2) */
    axel_shl  (&gpu, R7, THREAD_IDX, R6);         /* R7  = THREAD_IDX * 2 */
    axel_ldr  (&gpu, R1, R7,         0);          /* R1  = W_row_i_low  mem[2i] */
    axel_ldr  (&gpu, R2, R7,         1);          /* R2  = W_row_i_high mem[2i+1] */
    axel_const(&gpu, R10,           8);           /* R10 = 8 (base of x) */
    axel_ldr  (&gpu, R8, R10,        0);          /* R8  = x_low  mem[8] */
    axel_ldr  (&gpu, R9, R10,        1);          /* R9  = x_high mem[9] */
    axel_dot  (&gpu, R3, R1,        R8);          /* R3  = dot(W_low,  x_low) */
    axel_dot  (&gpu, R3, R2,        R9);          /* R3 += dot(W_high, x_high) */
    axel_const(&gpu, R5,            8);           /* R5  = 8 */
    axel_sar  (&gpu, R4, R3,        R5);          /* R4  = R3 >> 8 */
    axel_relu (&gpu, R4, R4,        R1);          /* R4  = relu(R4) */
    axel_clamp(&gpu, R4, R4,        R1);          /* R4  = clamp(R4) */
    axel_str  (&gpu, R4, THREAD_IDX, 10);         /* mem[THREAD_IDX+10] = R4 */
    axel_ret  (&gpu);

    axel_compile    (&gpu, "hex/phase11_mlp_8in.hex");
    axel_compile_bin(&gpu, "bin/phase11_mlp_8in.axelbin");

    printf("phase11_mlp_8in: 8-in -> 4-out, 2x DOT4 accumulation per thread\n");
    printf("expected y[0..3] at mem[10..13] = [20, 15, 28, 6]\n");

    return 0;
}