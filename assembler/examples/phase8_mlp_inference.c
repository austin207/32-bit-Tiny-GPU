#include <stdio.h>
#include "axel.h"

/*
 * phase8_mlp_inference.c
 *
 * First real neural-network workload on the GPU.
 * Computes one layer of a quantized MLP: y = CLAMP(RELU(SAR(W * x, 8)))
 *
 * 4 threads run in parallel, one per output neuron. No branches, no divergence.
 *
 * Memory layout:
 *   mem[0] = W_row_0  packed INT8x4 = [ 127,  64, -64,   0]
 *   mem[1] = W_row_1  packed INT8x4 = [   0, 127,  64, -64]
 *   mem[2] = W_row_2  packed INT8x4 = [-127,   0, 127,  64]
 *   mem[3] = W_row_3  packed INT8x4 = [  64,-127,   0, 127]
 *   mem[4..7] = x replicated (same value at all 4 slots)
 *               packed INT8x4 = [85, 42, 127, 17]
 *   mem[8..11] = y[0..3]  INT32 output (written by kernel)
 *
 * WHY x IS REPLICATED:
 *   In multi-thread SIMT mode (blockDim > 1), LDR base registers must be
 *   R29 (THREAD_IDX), R30 (BLOCK_IDX), or R31 (BLOCK_DIM). Using a
 *   general-purpose register (R0-R28) as a base address in LDR produces
 *   incorrect memory addresses. This is a known hardware constraint.
 *   Replicating x at mem[4..7] allows all threads to load x via
 *   LDR R2, THREAD_IDX, 4 (which uses THREAD_IDX as the base). Each
 *   thread reads mem[thread_idx + 4], all of which hold the same x value.
 *
 * Kernel (per thread i, THREAD_IDX = i):
 *   R1 = W_row_i          LDR THREAD_IDX + 0
 *   R2 = x                LDR THREAD_IDX + 4  (replicated, all same value)
 *   R3 = DOT4(R3, R1, R2) INT32 dot product
 *   R5 = 8                CONST shift amount
 *   R4 = SAR(R3, R5)      arithmetic right shift requantization
 *   R4 = RELU(R4)         zero negative values
 *   R4 = CLAMP(R4)        clamp to INT8 range [-128, 127]
 *   mem[THREAD_IDX + 8] = R4
 *
 * Expected output (verified against Python golden reference in Colab):
 *   y[0] = 20  (dot=5355,  sar8=20)  -> mem[8]
 *   y[1] = 48  (dot=12374, sar8=48)  -> mem[9]
 *   y[2] = 25  (dot=6422,  sar8=25)  -> mem[10]
 *   y[3] = 8   (dot=2265,  sar8=8)   -> mem[11]
 */

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);  // 1 block, 4 threads

    // ── Weight rows (one per thread, THREAD_IDX-addressed) ────────────────────
    axel_set_data(&gpu, 0, 0x00C0407F);  // W_row_0 = [ 127,  64, -64,   0]
    axel_set_data(&gpu, 1, 0xC0407F00);  // W_row_1 = [   0, 127,  64, -64]
    axel_set_data(&gpu, 2, 0x407F0081);  // W_row_2 = [-127,   0, 127,  64]
    axel_set_data(&gpu, 3, 0x7F008140);  // W_row_3 = [  64,-127,   0, 127]

    // ── Input vector x — replicated 4x so thread i loads via THREAD_IDX+4 ────
    axel_set_data(&gpu, 4, 0x117F2A55);  // x for thread 0
    axel_set_data(&gpu, 5, 0x117F2A55);  // x for thread 1
    axel_set_data(&gpu, 6, 0x117F2A55);  // x for thread 2
    axel_set_data(&gpu, 7, 0x117F2A55);  // x for thread 3

    // ── Output slots ──────────────────────────────────────────────────────────
    axel_set_data(&gpu, 8,  0x00000000); // y[0]
    axel_set_data(&gpu, 9,  0x00000000); // y[1]
    axel_set_data(&gpu, 10, 0x00000000); // y[2]
    axel_set_data(&gpu, 11, 0x00000000); // y[3]

    // ── Kernel ────────────────────────────────────────────────────────────────
    axel_ldr  (&gpu, R1, THREAD_IDX, 0);  // R1 = mem[i+0] = W_row_i
    axel_ldr  (&gpu, R2, THREAD_IDX, 4);  // R2 = mem[i+4] = x (same for all i)
    axel_dot  (&gpu, R3, R1,         R2); // R3 = dot(W_row_i, x)
    axel_const(&gpu, R5,              8); // R5 = 8 (shift amount)
    axel_sar  (&gpu, R4, R3,         R5); // R4 = R3 >>> 8
    axel_relu (&gpu, R4, R4,         R1); // R4 = max(0, R4)
    axel_clamp(&gpu, R4, R4,         R1); // R4 = clamp(R4, -128, 127)
    axel_str  (&gpu, R4, THREAD_IDX,  8); // mem[i+8] = y[i]
    axel_ret  (&gpu);

    // ── Emit ──────────────────────────────────────────────────────────────────
    axel_compile    (&gpu, "hex/phase8_mlp_inference.hex");
    axel_compile_bin(&gpu, "bin/phase8_mlp_inference.axelbin");

    printf("phase8_mlp_inference: 4x4 Q8 MLP layer, 4 parallel threads\n");
    printf("expected y[0..3] at mem[8..11] = [20, 48, 25, 8]\n");

    return 0;
}