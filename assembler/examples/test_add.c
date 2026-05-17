#include <stdio.h>
#include "../include/gpu_asm.h"

int main() {
    GPUProgram prog;
    gpu_program_init(&prog);

    // Simple program: R1 = 10, R2 = 20, R3 = R1 + R2, RET
    emit_const(&prog, 1, 10);   // R1 = 10
    emit_const(&prog, 2, 20);   // R2 = 20
    emit_add(&prog, 3, 1, 2);   // R3 = R1 + R2
    emit_ret(&prog);

    gpu_program_write(&prog, "test_add.hex");

    printf("Compiled %d instructions\n", prog.count);
    for (int i = 0; i < prog.count; i++) {
        printf("[%d] 0x%08X\n", i, prog.instructions[i]);
    }
    return 0;
}