#include <stdio.h>
#include <stdint.h>
#include "axel.h"

/*
 * phase15_digit64_hidden.c
 *
 * True digit classifier hidden layer.
 *
 * Shape:
 *   64 input values -> 16 hidden neurons
 *
 * Execution:
 *   4 blocks x 4 threads = 16 hidden neurons
 *   hidden_id = BLOCK_IDX * 4 + THREAD_IDX
 *
 * Each thread computes one hidden neuron:
 *   h[j] = CLAMP(RELU(SAR(dot(W_h[j], x), 8)))
 *
 * Since DOT4 handles 4 INT8 lanes, each 64-element dot product uses:
 *   64 / 4 = 16 DOT4 instructions per thread
 *
 * Memory layout:
 *   mem[0..255]    = W_h[16][16 packed INT8x4 words]
 *   mem[256..271]  = x[64] packed as 16 INT8x4 words
 *   mem[272..287]  = h[0..15] output INT32 values
 */

#define WH_BASE   0
#define X_BASE    256
#define H_BASE    272
#define HIDDEN    16
#define CHUNKS    16

static uint32_t pack4(int a, int b, int c, int d) {
    return ((uint32_t)(uint8_t)a)       |
           ((uint32_t)(uint8_t)b << 8)  |
           ((uint32_t)(uint8_t)c << 16) |
           ((uint32_t)(uint8_t)d << 24);
}

static int x_value(int idx) {
    return ((idx * 5 + 11) % 63) - 31;   // [-31, 31]
}

static int wh_value(int hidden, int idx) {
    return ((hidden * 11 + idx * 7) % 31) - 15;  // [-15, 15]
}

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 4, 4);  // 4 blocks x 4 threads = 16 hidden neurons

    // W_h: 16 rows, each row has 64 INT8 weights = 16 packed words
    for (int h = 0; h < HIDDEN; h++) {
        for (int k = 0; k < CHUNKS; k++) {
            int idx = k * 4;
            uint32_t packed = pack4(
                wh_value(h, idx + 0),
                wh_value(h, idx + 1),
                wh_value(h, idx + 2),
                wh_value(h, idx + 3)
            );
            axel_set_data(&gpu, WH_BASE + h * CHUNKS + k, packed);
        }
    }

    // x: 64 INT8 inputs = 16 packed words
    for (int k = 0; k < CHUNKS; k++) {
        int idx = k * 4;
        uint32_t packed = pack4(
            x_value(idx + 0),
            x_value(idx + 1),
            x_value(idx + 2),
            x_value(idx + 3)
        );
        axel_set_data(&gpu, X_BASE + k, packed);
    }

    // h output slots
    for (int i = 0; i < HIDDEN; i++) {
        axel_set_data(&gpu, H_BASE + i, 0);
    }

    /*
     * Kernel:
     *   hidden_id = BLOCK_IDX * 4 + THREAD_IDX
     *   W base    = hidden_id * 16
     *   X base    = 256
     */
    axel_const(&gpu, R6, 4);                  // R6 = 4
    axel_mul  (&gpu, R7, BLOCK_IDX, R6);      // R7 = BLOCK_IDX * 4
    axel_add  (&gpu, R8, R7, THREAD_IDX);     // R8 = hidden_id

    axel_shl  (&gpu, R9, R8, R6);             // R9 = hidden_id << 4 = hidden_id * 16
    axel_const(&gpu, R10, X_BASE);            // R10 = x base

    axel_const(&gpu, R3, 0);                  // R3 = accumulator

    for (int k = 0; k < CHUNKS; k++) {
        axel_ldr(&gpu, R1, R9,  k);           // R1 = W_h[hidden_id][k]
        axel_ldr(&gpu, R2, R10, k);           // R2 = x[k]
        axel_dot(&gpu, R3, R1, R2);           // R3 += DOT4(R1, R2)
    }

    axel_const(&gpu, R5, 8);                  // SAR shift = 8
    axel_sar  (&gpu, R4, R3, R5);
    axel_relu (&gpu, R4, R4, R1);
    axel_clamp(&gpu, R4, R4, R1);

    axel_const(&gpu, R11, H_BASE);            // h base
    axel_add  (&gpu, R12, R11, R8);           // h addr = 272 + hidden_id
    axel_str  (&gpu, R4, R12, 0);

    axel_ret(&gpu);

    axel_compile    (&gpu, "hex/phase15_digit64_hidden.hex");
    axel_compile_bin(&gpu, "bin/phase15_digit64_hidden.axelbin");

    printf("phase15_digit64_hidden: 64-in -> 16-hidden, 16x DOT4 per thread\n");
    printf("output h[0..15] at mem[272..287]\n");

    return 0;
}