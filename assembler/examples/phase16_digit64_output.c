#include <stdio.h>
#include <stdint.h>
#include "axel.h"

/*
 * phase16_digit64_output.c
 *
 * True digit classifier output layer.
 *
 * Shape:
 *   16 hidden values -> 10 output classes
 *
 * Execution:
 *   3 blocks x 4 threads = 12 lanes
 *   classes 0..9 are real
 *   classes 10..11 are padding lanes, ignored
 *
 * Each thread computes:
 *   y[class] = CLAMP(RELU(SAR(sum(h[i] * W_o[class][i]), 8)))
 *
 * Uses scalar IMUL + ADD because h[0..15] are INT32 scalar values,
 * not packed INT8x4.
 *
 * Shared memory layout with phase15:
 *   mem[0..255]    = W_h
 *   mem[256..271]  = x
 *   mem[272..287]  = h[0..15] from phase15
 *
 * Phase16-specific:
 *   mem[288..479]  = W_o[12][16] INT32 scalar weights
 *                    10 real classes + 2 padding classes
 *   mem[480..491]  = y[0..11]
 *                    y[0..9] real scores, y[10..11] padding
 */

#define H_BASE       272
#define WO_BASE      288
#define Y_BASE       480
#define HIDDEN       16
#define CLASSES_REAL 10
#define CLASSES_PAD  12

static int32_t wo_value(int cls, int h) {
    if (cls == 0) {
        return 32;  // make class 0 intentionally strong
    }

    if (cls >= CLASSES_REAL) {
        return 0;   // padding classes
    }

    return ((cls * 7 + h * 3) % 15) - 7;  // [-7, 7]
}

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 3, 4);  // 3 blocks x 4 threads = 12 output lanes

    /*
     * Do not rely on h placeholders.
     * In the chained cocotb test, mem[272..287] comes from phase15.
     */

    // W_o: 12 rows x 16 scalar INT32 weights
    for (int cls = 0; cls < CLASSES_PAD; cls++) {
        for (int h = 0; h < HIDDEN; h++) {
            axel_set_data(
                &gpu,
                WO_BASE + cls * HIDDEN + h,
                (uint32_t)wo_value(cls, h)
            );
        }
    }

    // y output slots
    for (int cls = 0; cls < CLASSES_PAD; cls++) {
        axel_set_data(&gpu, Y_BASE + cls, 0);
    }

    /*
     * Kernel:
     *   class_id = BLOCK_IDX * 4 + THREAD_IDX
     *   W_o base = 288 + class_id * 16
     *   h base   = 272
     */
    axel_const(&gpu, R6, 4);                 // R6 = 4
    axel_mul  (&gpu, R7, BLOCK_IDX, R6);     // R7 = BLOCK_IDX * 4
    axel_add  (&gpu, R8, R7, THREAD_IDX);    // R8 = class_id

    axel_shl  (&gpu, R9, R8, R6);            // R9 = class_id * 16
    axel_const(&gpu, R10, WO_BASE);          // R10 = W_o base
    axel_add  (&gpu, R11, R10, R9);          // R11 = W_o[class_id] base

    axel_const(&gpu, R12, H_BASE);           // R12 = h base
    axel_const(&gpu, R2, 0);                 // R2 = accumulator

    for (int i = 0; i < HIDDEN; i++) {
        axel_ldr (&gpu, R1, R12, i);         // R1 = h[i]
        axel_ldr (&gpu, R3, R11, i);         // R3 = W_o[class_id][i]
        axel_imul(&gpu, R4, R1, R3);         // R4 = h[i] * W_o[class_id][i]
        axel_add (&gpu, R2, R2, R4);         // R2 += R4
    }

    axel_const(&gpu, R5, 8);
    axel_sar  (&gpu, R4, R2, R5);
    axel_relu (&gpu, R4, R4, R1);
    axel_clamp(&gpu, R4, R4, R1);

    axel_const(&gpu, R13, Y_BASE);
    axel_add  (&gpu, R14, R13, R8);          // y addr = 480 + class_id
    axel_str  (&gpu, R4, R14, 0);

    axel_ret(&gpu);

    axel_compile    (&gpu, "hex/phase16_digit64_output.hex");
    axel_compile_bin(&gpu, "bin/phase16_digit64_output.axelbin");

    printf("phase16_digit64_output: 16-hidden -> 10-output + 2 padded lanes\n");
    printf("output y[0..9] at mem[480..489], padding y[10..11] ignored\n");

    return 0;
}