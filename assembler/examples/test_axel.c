#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 4, 4);  // 4 blocks, 4 threads

    // Simple vector addition kernel
    // Each thread computes: R3 = threadIdx + blockIdx
    axel_add(&gpu, R3, THREAD_IDX, BLOCK_IDX);
    axel_str(&gpu, THREAD_IDX, R3, 0);
    axel_ret(&gpu);

    axel_compile(&gpu, "vector_add.hex");

    printf("AXEL — Austin's eXecution Engine Layer\n");
    printf("Compiled %d instructions\n", gpu.program.count);
    for (int i = 0; i < gpu.program.count; i++) {
        printf("[%d] 0x%08X\n", i, gpu.program.instructions[i]);
    }
    return 0;
}