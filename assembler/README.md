# AXEL Assembler

## Overview

`assembler/` contains the C-based assembler layer for the Tiny GPU.

It converts human-readable AXEL C kernel calls into 32-bit encoded instruction words and writes them into `.hex` files. These `.hex` files are then loaded by the cocotb program memory model and fetched by the GPU during simulation.

The assembler has two layers:

```text
AXEL API layer
  assembler/include/axel.h
  assembler/src/axel.c

Low-level instruction emitter layer
  assembler/include/gpu_asm.h
  assembler/src/gpu_asm.c
```

The AXEL layer gives readable functions such as:

```c
axel_add(...)
axel_ldr(...)
axel_brnzp(...)
axel_sync(...)
axel_ret(...)
```

The low-level `gpu_asm` layer performs the actual bit encoding.

---

## Software architecture

![Software Layer Architecture](../assets/Architecture-images/software_layer_architecture.png)

---

## Source files

```text
assembler/
├── include/
│   ├── axel.h
│   └── gpu_asm.h
├── src/
│   ├── axel.c
│   └── gpu_asm.c
├── examples/
│   ├── phase1_ldr_test.c
│   ├── phase2_matmul.c
│   ├── phase3_relu.c
│   ├── phase4_forward.c
│   ├── phase5_weight_update.c
│   └── phase6_simt_relu.c
├── builds/
│   ├── phase1
│   ├── phase2
│   ├── phase3
│   ├── phase4
│   ├── phase5
│   ├── phase6
│   ├── phase4_forward.hex
│   ├── phase5_weight_update.hex
│   ├── phase6_simt_relu.hex
│   └── weights.json
└── Makefile
```

---

## Main components

| File                | Purpose                                                                 |
| ------------------- | ----------------------------------------------------------------------- |
| `include/gpu_asm.h` | Defines opcodes, `GPUProgram`, and low-level `emit_*` prototypes        |
| `src/gpu_asm.c`     | Implements instruction encoders and `.hex` writer                       |
| `include/axel.h`    | Defines register aliases, NZP masks, `AxelGPU`, and high-level AXEL API |
| `src/axel.c`        | Implements high-level AXEL wrappers around low-level emitters           |
| `examples/*.c`      | Example kernels that generate `.hex` programs                           |
| `builds/*.hex`      | Generated GPU instruction files                                         |

---

## Build flow

The assembler build flow is:

```text
AXEL C example
      │
      ▼
AXEL API calls
      │
      ▼
low-level emit_* functions
      │
      ▼
32-bit instruction words
      │
      ▼
.hex file
      │
      ▼
cocotb program memory model
      │
      ▼
GPU fetcher
```

---

## Building all programs

From the repository root:

```bash
make test
```

The root test flow first builds assembler programs and then runs RTL tests.

To build only assembler programs:

```bash
cd assembler
make
```

This compiles the example C programs and emits the generated `.hex` files into `assembler/builds/`.

---

## AXEL high-level API

The high-level AXEL API is declared in:

```text
assembler/include/axel.h
```

and implemented in:

```text
assembler/src/axel.c
```

AXEL wraps the low-level emitters so kernels can be written in a cleaner style.

Example:

```c
AxelGPU gpu;
axel_init(&gpu, 1, 4);

axel_ldr(&gpu, R1, THREAD_IDX, 0);
axel_add(&gpu, R2, R1, R1);
axel_str(&gpu, R2, THREAD_IDX, 4);
axel_ret(&gpu);

axel_compile(&gpu, "output.hex");
```

This generates a `.hex` program containing encoded Tiny GPU instructions.

---

## `AxelGPU` structure

```c
typedef struct {
    GPUProgram program;
    int num_blocks;
    int threads_per_block;
} AxelGPU;
```

| Field               | Meaning                                   |
| ------------------- | ----------------------------------------- |
| `program`           | Internal instruction buffer               |
| `num_blocks`        | Number of blocks intended for the kernel  |
| `threads_per_block` | Threads per block intended for the kernel |

Current note:

```text
num_blocks and threads_per_block are stored in the AXEL object,
but kernel launch configuration is still written separately through DCR in the cocotb testbench.
```

---

## Initialization

```c
void axel_init(AxelGPU *gpu, int num_blocks, int threads_per_block);
```

Implementation:

```c
void axel_init(AxelGPU *gpu, int num_blocks, int threads_per_block) {
    gpu_program_init(&gpu->program);
    gpu->num_blocks = num_blocks;
    gpu->threads_per_block = threads_per_block;
}
```

This resets the program instruction count to zero and stores launch metadata.

---

## Compilation

```c
void axel_compile(AxelGPU *gpu, const char *filename);
```

Implementation:

```c
void axel_compile(AxelGPU *gpu, const char *filename) {
    gpu_program_write(&gpu->program, filename);
}
```

This writes the encoded instruction words to a `.hex` file.

Each line is one 32-bit instruction word in uppercase hexadecimal:

```text
3C3D0000
34010000
38802002
44200000
54000000
403D0004
48000000
```

---

## Register aliases

AXEL defines readable register aliases in `axel.h`.

```c
#define R0 0
#define R1 1
#define R2 2
...
#define R28 28
#define THREAD_IDX 29
#define BLOCK_IDX 30
#define BLOCK_DIM 31
```

---

## Register map

| Register | Alias         | Meaning                           |
| -------: | ------------- | --------------------------------- |
|     `R0` | `R0`          | Hardwired zero                    |
| `R1-R28` | `R1` to `R28` | General-purpose registers         |
|    `R29` | `THREAD_IDX`  | Hardware-injected thread index    |
|    `R30` | `BLOCK_IDX`   | Hardware-injected block index     |
|    `R31` | `BLOCK_DIM`   | Hardware-injected block dimension |

Special FPGA helper:

```text
When blockDim == 1, R29 returns blockIdx instead of threadIdx.
```

This allows the single-thread FPGA build to execute multiple blocks sequentially while preserving the same effective thread indexing as the multi-thread simulation.

---

## NZP condition masks

AXEL defines branch condition masks:

```c
#define AXEL_N   0b100
#define AXEL_Z   0b010
#define AXEL_P   0b001
#define AXEL_NZ  0b110
#define AXEL_NP  0b101
#define AXEL_ZP  0b011
#define AXEL_ALL 0b111
```

| Mask       | Binary | Meaning              |
| ---------- | -----: | -------------------- |
| `AXEL_N`   |  `100` | Negative             |
| `AXEL_Z`   |  `010` | Zero                 |
| `AXEL_P`   |  `001` | Positive             |
| `AXEL_NZ`  |  `110` | Negative or zero     |
| `AXEL_NP`  |  `101` | Negative or positive |
| `AXEL_ZP`  |  `011` | Zero or positive     |
| `AXEL_ALL` |  `111` | Any NZP result       |

These masks are used by:

```c
axel_brnzp(&gpu, AXEL_P, sync_offset, branch_offset);
```

---

## Opcode definitions

The opcode constants are defined in:

```text
assembler/include/gpu_asm.h
```

Current opcode table:

|     Opcode |    Hex | Mnemonic | Description              |
| ---------: | -----: | -------- | ------------------------ |
|   `OP_NOP` | `0x00` | `NOP`    | No operation             |
|   `OP_ADD` | `0x01` | `ADD`    | Add                      |
|   `OP_SUB` | `0x02` | `SUB`    | Subtract                 |
|   `OP_MUL` | `0x03` | `MUL`    | Multiply                 |
|   `OP_DIV` | `0x04` | `DIV`    | Divide                   |
|   `OP_MOD` | `0x05` | `MOD`    | Modulo                   |
|   `OP_SHL` | `0x06` | `SHL`    | Logical left shift       |
|   `OP_SHR` | `0x07` | `SHR`    | Logical right shift      |
|   `OP_AND` | `0x08` | `AND`    | Bitwise AND              |
|    `OP_OR` | `0x09` | `OR`     | Bitwise OR               |
|   `OP_XOR` | `0x0A` | `XOR`    | Bitwise XOR              |
|   `OP_NOT` | `0x0B` | `NOT`    | Bitwise NOT              |
|   `OP_FMA` | `0x0C` | `FMA`    | Multiply accumulate      |
|   `OP_CMP` | `0x0D` | `CMP`    | Compare and set NZP      |
| `OP_BRnzp` | `0x0E` | `BRnzp`  | Branch on NZP            |
|   `OP_LDR` | `0x0F` | `LDR`    | Load                     |
|   `OP_STR` | `0x10` | `STR`    | Store                    |
| `OP_CONST` | `0x11` | `CONST`  | Load 16-bit immediate    |
|   `OP_RET` | `0x12` | `RET`    | End block                |
|  `OP_IMUL` | `0x13` | `IMUL`   | Signed multiply          |
|   `OP_SAR` | `0x14` | `SAR`    | Arithmetic right shift   |
|  `OP_SYNC` | `0x15` | `SYNC`   | SIMT reconvergence point |

---

## Instruction buffer

The low-level program object is:

```c
typedef struct {
    uint32_t instructions[256];
    int count;
} GPUProgram;
```

This means each generated program currently supports up to:

```text
256 instructions
```

Current limitation:

```text
There is no bounds check in the emit functions.
If more than 256 instructions are emitted, the instruction array can overflow.
```

Future improvement:

```text
Add bounds checking in every emit function or inside a shared append helper.
```

---

## Instruction formats

The assembler supports four instruction formats:

```text
R-type  -> register/register ALU operations
I-type  -> load/store/constant immediate
B-type  -> BRnzp branch with sync and branch offsets
N-type  -> no-operand control instructions
```

Detailed ISA documentation:

```text
../docs/isa.md
```

---

## R-type encoding

Used by ALU-style instructions.

```text
31          26 25       21 20       16 15       11 10        6 5       0
+-------------+-----------+-----------+-----------+-----------+---------+
| opcode[5:0] | rd[4:0]   | rs1[4:0]  | rs2[4:0]  | rs3[4:0]  | unused  |
+-------------+-----------+-----------+-----------+-----------+---------+
```

Implementation:

```c
uint32_t encode_r(uint8_t op, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) rd << 21)  |
            ((uint32_t) rs1 << 16) |
            ((uint32_t) rs2 << 11) |
            ((uint32_t) rs3 << 6);
}
```

Used by:

```text
ADD
SUB
MUL
DIV
MOD
SHL
SHR
AND
OR
XOR
NOT
FMA
CMP
IMUL
SAR
```

---

## I-type encoding

Used by load/store and constants.

```text
31          26 25       21 20       16 15                              0
+-------------+-----------+-----------+---------------------------------+
| opcode[5:0] | rd[4:0]   | rs[4:0]   | imm[15:0]                       |
+-------------+-----------+-----------+---------------------------------+
```

Implementation:

```c
uint32_t encode_i(uint8_t op, uint8_t rd, uint8_t rs, uint16_t imm) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) rd << 21)  |
            ((uint32_t) rs << 16)  |
            (uint32_t) imm;
}
```

Used by:

```text
LDR
STR
CONST
```

Address behavior for `LDR` and `STR`:

```text
address = register[rs] + sign_extend(imm)
```

Current `CONST` behavior:

```text
rd = zero_extend(imm16)
```

---

## B-type encoding

Used by SIMT branch instruction `BRnzp`.

```text
31          26 25       23 22                    12 11                0
+-------------+-----------+------------------------+-------------------+
| opcode[5:0] | nzp[2:0]  | sync_offset[10:0]      | branch_offset[11:0] |
+-------------+-----------+------------------------+-------------------+
```

Implementation:

```c
uint32_t encode_b(uint8_t op, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset) {
    return  ((uint32_t) op << 26)           |
            ((uint32_t) nzp << 23)          |
            ((sync_offset  & 0x7FF) << 12)  |
            (branch_offset & 0xFFF);
}
```

Field behavior:

| Field           |   Width | Meaning                            |
| --------------- | ------: | ---------------------------------- |
| `nzp`           |  3 bits | Branch condition mask              |
| `sync_offset`   | 11 bits | Offset to SYNC/reconvergence point |
| `branch_offset` | 12 bits | Offset to taken path               |

Important limitation:

```text
sync_offset is masked to 11 bits.
branch_offset is masked to 12 bits.
Both are currently treated as unsigned forward offsets.
```

---

## N-type encoding

Used by no-operand control instructions.

```text
31          26 25                                                0
+-------------+---------------------------------------------------+
| opcode[5:0] | unused                                            |
+-------------+---------------------------------------------------+
```

Implementation:

```c
uint32_t encode_n(uint8_t op) {
    return (uint32_t) op << 26;
}
```

Used by:

```text
NOP
RET
SYNC
```

---

## Low-level emit functions

The low-level emit functions append encoded instruction words into `GPUProgram`.

Examples:

```c
void emit_add(GPUProgram *prog, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    prog->instructions[prog->count++] = encode_r(OP_ADD, rd, rs1, rs2, 0);
}
```

```c
void emit_ldr(GPUProgram *prog, uint8_t rd, uint8_t rs, uint16_t imm) {
    prog->instructions[prog->count++] = encode_i(OP_LDR, rd, rs, imm); 
}
```

```c
void emit_brnzp(GPUProgram *prog, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset) {
    prog->instructions[prog->count++] = encode_b(OP_BRnzp, nzp, sync_offset, branch_offset);
}
```

```c
void emit_sync(GPUProgram *prog) {
    prog->instructions[prog->count++] = encode_n(OP_SYNC);
}
```

---

## High-level AXEL wrappers

The high-level `axel_*` functions call the matching low-level `emit_*` functions.

Example:

```c
void axel_add(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2) {
    emit_add(&gpu->program, rd, rs1, rs2);
}
```

```c
void axel_brnzp(AxelGPU *gpu, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset) {
    emit_brnzp(&gpu->program, nzp, sync_offset, branch_offset);
}
```

The high-level layer keeps user code readable and hides direct access to `GPUProgram`.

---

## Supported AXEL functions

### Arithmetic

```c
void axel_add(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_sub(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_mul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_imul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_div(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_mod(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
```

### Shift

```c
void axel_shl(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_shr(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_sar(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
```

### Logic

```c
void axel_and(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_or(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_xor(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_not(AxelGPU *gpu, uint8_t rd, uint8_t rs);
```

### Compare and FMA

```c
void axel_cmp(AxelGPU *gpu, uint8_t rs1, uint8_t rs2);
void axel_fma(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3);
```

### Memory

```c
void axel_ldr(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm);
void axel_str(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm);
```

### Immediate

```c
void axel_const(AxelGPU *gpu, uint8_t rd, uint16_t imm);
```

### Control

```c
void axel_brnzp(AxelGPU *gpu, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset);
void axel_nop(AxelGPU *gpu);
void axel_ret(AxelGPU *gpu);
void axel_sync(AxelGPU *gpu);
```

---

## Program writer

The writer function is:

```c
void gpu_program_write(GPUProgram *prog, const char *filename);
```

Implementation:

```c
void gpu_program_write(GPUProgram *prog, const char *filename) {
    FILE *f = fopen(filename, "w");
    if (f == NULL) return;

    for (int i = 0; i < prog->count; i++) {
        fprintf(f, "%08X\n", prog->instructions[i]);
    }

    fclose(f);
}
```

Output format:

```text
one 32-bit instruction per line
8 uppercase hex digits
no 0x prefix
```

Example:

```text
3C3D0000
34010000
38802002
44200000
54000000
403D0004
48000000
```

Current limitation:

```text
If fopen fails, the function silently returns.
```

Future improvement:

```text
Print an error or return a status code from gpu_program_write.
```

---

## Example: simple load/store kernel

```c
#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    axel_ldr(&gpu, R1, THREAD_IDX, 0);   // R1 = mem[threadIdx]
    axel_add(&gpu, R2, R1, R1);          // R2 = 2 * R1
    axel_str(&gpu, R2, THREAD_IDX, 4);   // mem[threadIdx + 4] = R2
    axel_ret(&gpu);

    axel_compile(&gpu, "simple.hex");
    return 0;
}
```

Per-thread behavior:

```text
R1 = Memory[THREAD_IDX + 0]
R2 = R1 + R1
Memory[THREAD_IDX + 4] = R2
RET
```

---

## Example: SIMT ReLU kernel

```c
#include <stdio.h>
#include "../include/axel.h"

int main() {
    AxelGPU gpu;
    axel_init(&gpu, 1, 4);

    axel_ldr  (&gpu, R1, THREAD_IDX, 0);  // R1 = input[threadIdx]
    axel_cmp  (&gpu, R1, R0);             // compare R1 with 0
    axel_brnzp(&gpu, AXEL_P, 2, 2);       // if positive: jump to SYNC
    axel_const(&gpu, R1, 0);              // not-taken path: R1 = 0
    axel_sync (&gpu);                     // reconvergence point
    axel_str  (&gpu, R1, THREAD_IDX, 4);  // store result
    axel_ret  (&gpu);

    axel_compile(&gpu, "phase6_simt_relu.hex");
    return 0;
}
```

Program layout:

```text
PC0: LDR   R1, THREAD_IDX, 0
PC1: CMP   R1, R0
PC2: BR P, sync_offset=2, branch_offset=2
PC3: CONST R1, 0
PC4: SYNC
PC5: STR   R1, THREAD_IDX, 4
PC6: RET
```

Generated output:

```text
3C3D0000
34010000
38802002
44200000
54000000
403D0004
48000000
```

Expected SIMT behavior:

```text
positive lanes -> branch taken -> keep value
negative lanes -> branch not taken -> zero value
SYNC -> reconverge
STR -> store final values
```

---

## Example: Q8 forward-pass pattern

A Q8 linear layer uses this pattern:

```text
load x[0..3]
compute row_base = threadIdx * 4
load W[threadIdx][0..3]
perform dot product
scale Q16 back to Q8 using SAR >> 8
apply ReLU using CMP/BRnzp/SYNC
store y[threadIdx]
```

Important instructions for signed Q8 work:

```text
IMUL -> signed multiply
SAR  -> arithmetic right shift
```

---

## Q8 fixed-point convention

The neural-network examples use Q8 fixed-point arithmetic.

```text
real_value = q8_value / 256
q8_value   = round(real_value * 256)
```

Examples:

| Real value |       Q8 raw |
| ---------: | -----------: |
|      `1.0` |        `256` |
|      `2.0` |        `512` |
|      `0.5` |        `128` |
|     `-1.0` | `0xFFFFFF00` |

Q8 multiply rule:

```text
Q8 * Q8 = Q16
```

To scale back:

```text
SAR result, result, 8
```

Use `SAR` instead of `SHR` when the value may be negative.

---

## Current example programs

| Phase | Source file                       | Purpose                             |
| ----: | --------------------------------- | ----------------------------------- |
|     1 | `examples/phase1_ldr_test.c`      | LDR/STR smoke test                  |
|     2 | `examples/phase2_matmul.c`        | Matrix-vector multiply              |
|     3 | `examples/phase3_relu.c`          | ReLU baseline                       |
|     4 | `examples/phase4_forward.c`       | Q8 forward pass with SIMT ReLU      |
|     5 | `examples/phase5_weight_update.c` | Q8 weight update                    |
|     6 | `examples/phase6_simt_relu.c`     | Real SIMT divergent ReLU regression |

---

## Generated files

Generated outputs are written to:

```text
assembler/builds/
```

Common generated files:

```text
phase1
phase2
phase3
phase4
phase5
phase6
phase4_forward.hex
phase5_weight_update.hex
phase6_simt_relu.hex
weights.json
```

Important note:

```text
weights.json is generated by the training/top-level GPU test.
It may be gitignored and may not exist on a fresh clone.
```

---

## Relationship to cocotb tests

The top-level GPU test loads generated `.hex` files:

```text
Src/Top_level_GPU/test_top_level_gpu.py
```

Important paths used by the testbench:

```python
FORWARD_HEX  = "../../assembler/builds/phase4_forward.hex"
BACKWARD_HEX = "../../assembler/builds/phase5_weight_update.hex"
WEIGHTS_FILE = "../../assembler/builds/weights.json"
```

SIMT ReLU loads:

```python
relu_hex = "../../assembler/builds/phase6_simt_relu.hex"
```

So before running top-level tests, make sure the assembler outputs have been generated.

The root `make test` flow already builds assembler programs first.

---

## Important design rules

### 1. Keep opcodes synchronized

Opcode definitions must match across:

```text
assembler/include/gpu_asm.h
Src/decoder/decoder.sv
Src/alu/alu.sv
docs/isa.md
```

If a new opcode is added, update all of them.

---

### 2. Keep branch encoding synchronized

`BRnzp` encoding must match across:

```text
assembler/src/gpu_asm.c
Src/decoder/decoder.sv
Src/pc/pc.sv
Src/core/core.sv
docs/isa.md
```

Current branch encoding:

```text
[25:23] = nzp_mask
[22:12] = sync_offset
[11:0]  = branch_offset
```

---

### 3. Keep AXEL API and emitters synchronized

If you add a new instruction, update:

```text
assembler/include/gpu_asm.h
assembler/src/gpu_asm.c
assembler/include/axel.h
assembler/src/axel.c
docs/isa.md
```

---

### 4. Use `IMUL` and `SAR` for signed Q8 math

For signed fixed-point gradients:

```text
use IMUL, not MUL
use SAR, not SHR
```

---

### 5. Use `SYNC` after divergent branch regions

A divergent SIMT branch should have a reconvergence point.

Example:

```c
axel_cmp(&gpu, R1, R0);
axel_brnzp(&gpu, AXEL_P, 2, 2);
axel_const(&gpu, R1, 0);
axel_sync(&gpu);
```

---

## Current limitations

```text
- Maximum program length is 256 instructions.
- Emit functions do not bounds-check the instruction buffer.
- gpu_program_write silently returns if fopen fails.
- CONST only supports a 16-bit zero-extended immediate.
- Branch offsets are masked, not range-checked.
- Branch offsets are currently forward unsigned offsets.
- No label system yet.
- No automatic branch-offset calculation.
- No parser for assembly text yet.
- AXEL kernels are written as C function calls, not textual assembly.
```

---

## Future improvements

Useful future upgrades:

```text
- Add labels and automatic branch-offset resolution.
- Add bounds checking for GPUProgram instructions.
- Return error/status codes from gpu_program_write.
- Add LUI or 32-bit immediate loading support.
- Add ADDI/ANDI/ORI immediate instructions.
- Add a Python AXEL assembler/runtime.
- Add textual assembly parser.
- Add better build output checking in assembler Makefile.
- Add unit tests for instruction encoders.
- Add disassembler for debugging generated .hex files.
```

---

## Summary

The AXEL assembler converts readable C-style kernel construction into Tiny GPU machine code.

The core idea is:

```text
AXEL API call
    -> emit_* function
    -> encode_* function
    -> 32-bit instruction word
    -> .hex file
    -> GPU program memory
```

The most important files are:

```text
include/axel.h
include/gpu_asm.h
src/axel.c
src/gpu_asm.c
examples/
builds/
```

The most important synchronization rule is:

```text
Any ISA change must update assembler, RTL decoder/ALU/control logic, tests, and docs together.
```
