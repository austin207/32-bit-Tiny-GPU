#include <stdio.h>
#include "axel.h"

/*
 * phase7_dot4_test.c
 *
 * First end-to-end test of the DOT4 instruction on the GPU pipeline.
 *
 * Memory layout:
 *   mem[0] = packed INT8x4 vec A = [1, 2, 3, 4]  (0x04030201)
 *   mem[1] = packed INT8x4 vec B = [1, 2, 3, 4]  (0x04030201)
 *   mem[2] = INT32 result (written by kernel)
 *
 * Kernel (1 block, 1 thread):
 *   R1 = mem[0]          load vec A
 *   R2 = mem[1]          load vec B
 *   R3 = DOT4(R3, R1, R2)  R3 starts as 0, accumulates dot product
 *   mem[2] = R3          store INT32 result
 *
 * Expected result: 1*1 + 2*2 + 3*3 + 4*4 = 30
 */

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 1);  // 1 block, 1 thread

    // ── Data memory ───────────────────────────────────────────────────────────
    // Pack INT8 values little-endian: lane0=bits[7:0], lane3=bits[31:24]
    // [1, 2, 3, 4] -> 0x04030201
    axel_set_data(&gpu, 0, 0x04030201);  // vec A = [1, 2, 3, 4]
    axel_set_data(&gpu, 1, 0x04030201);  // vec B = [1, 2, 3, 4]
    axel_set_data(&gpu, 2, 0x00000000);  // result slot, initialised to 0

    // ── Kernel ────────────────────────────────────────────────────────────────
    axel_ldr(&gpu, R1, THREAD_IDX, 0);  // R1 = mem[THREAD_IDX + 0] = vec A
    axel_ldr(&gpu, R2, THREAD_IDX, 1);  // R2 = mem[THREAD_IDX + 1] = vec B
    axel_dot(&gpu, R3, R1, R2);         // R3 = R3 + dot(R1, R2)  (R3 init=0)
    axel_str(&gpu, R3, THREAD_IDX, 2);  // mem[THREAD_IDX + 2] = R3
    axel_ret(&gpu);

    // ── Emit ──────────────────────────────────────────────────────────────────
    axel_compile(&gpu,     "hex/phase7_dot4_test.hex");
    axel_compile_bin(&gpu, "bin/phase7_dot4_test.axelbin");

    printf("phase7_dot4_test: A=[1,2,3,4]  B=[1,2,3,4]\n");
    printf("expected result:  1*1 + 2*2 + 3*3 + 4*4 = 30\n");

    return 0;
}