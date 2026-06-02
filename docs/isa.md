# Tiny GPU ISA

## Overview

The Tiny GPU uses a custom 32-bit fixed-width instruction set.

The ISA is designed for a small SIMT-style GPU with:

```text
32-bit instruction words
6-bit opcode field
32-bit integer datapath
32 architectural registers per thread
per-thread PC
per-thread NZP condition flags
load/store memory operations
SIMT branch divergence through BRnzp + SYNC
Q8 fixed-point arithmetic support
```

The ISA is emitted by the AXEL C assembler and consumed by the RTL decoder inside each GPU core.

## Instruction encoding diagram

![Instruction Encoding](../assets/Architecture-images/instruction_encoding.png)

## Instruction width

All instructions are exactly:

```text
32 bits
```

The top 6 bits always contain the opcode:

```text
instruction[31:26] = opcode
```

## Instruction formats

The ISA currently uses four main instruction formats:

```text
R-type  -> register/register ALU operations
I-type  -> immediate, load, store
B-type  -> SIMT branch / BRnzp
N-type  -> no-operand control instructions
```

## R-type format

R-type instructions are used for ALU-style operations.

```text
31          26 25       21 20       16 15       11 10        6 5       0
+-------------+-----------+-----------+-----------+-----------+---------+
| opcode[5:0] | rd[4:0]   | rs1[4:0]  | rs2[4:0]  | rs3[4:0]  | unused  |
+-------------+-----------+-----------+-----------+-----------+---------+
```

Field mapping:

|      Bits | Field    | Meaning                               |
| --------: | -------- | ------------------------------------- |
| `[31:26]` | `opcode` | Instruction opcode                    |
| `[25:21]` | `rd`     | Destination register                  |
| `[20:16]` | `rs1`    | Source register 1                     |
| `[15:11]` | `rs2`    | Source register 2                     |
|  `[10:6]` | `rs3`    | Source register 3, mainly used by FMA |
|   `[5:0]` | unused   | Currently emitted as zero             |

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

## I-type format

I-type instructions are used for load/store and immediate constants.

```text
31          26 25       21 20       16 15                              0
+-------------+-----------+-----------+---------------------------------+
| opcode[5:0] | rd[4:0]   | rs[4:0]   | imm[15:0]                       |
+-------------+-----------+-----------+---------------------------------+
```

Field mapping:

|      Bits | Field    | Meaning                                                          |
| --------: | -------- | ---------------------------------------------------------------- |
| `[31:26]` | `opcode` | Instruction opcode                                               |
| `[25:21]` | `rd`     | Destination register for LDR/CONST, source data register for STR |
| `[20:16]` | `rs`     | Base register for LDR/STR                                        |
|  `[15:0]` | `imm`    | 16-bit immediate                                                 |

Used by:

```text
LDR
STR
CONST
```

For `LDR` and `STR`, the effective memory address is:

```text
address = register[rs] + sign_extend(imm)
```

For `CONST`, the immediate is zero-extended in the current core writeback path:

```text
rd = zero_extend(imm)
```

## B-type format

B-type instructions are used by `BRnzp`.

```text
31          26 25       23 22                    12 11                0
+-------------+-----------+------------------------+-------------------+
| opcode[5:0] | nzp[2:0]  | sync_offset[10:0]      | branch_offset[11:0] |
+-------------+-----------+------------------------+-------------------+
```

Field mapping:

|      Bits | Field           | Meaning                                      |
| --------: | --------------- | -------------------------------------------- |
| `[31:26]` | `opcode`        | Branch opcode                                |
| `[25:23]` | `nzp_mask`      | Branch condition mask                        |
| `[22:12]` | `sync_offset`   | Forward distance to SYNC/reconvergence point |
|  `[11:0]` | `branch_offset` | Forward branch offset for taken path         |

Used by:

```text
BRnzp
```

Both offsets are currently treated as unsigned forward offsets by the RTL.

## N-type format

N-type instructions contain only an opcode.

```text
31          26 25                                                0
+-------------+---------------------------------------------------+
| opcode[5:0] | unused                                            |
+-------------+---------------------------------------------------+
```

Used by:

```text
NOP
RET
SYNC
```

## Opcode table

| Opcode binary |    Hex | Mnemonic | Type | Description                                         |
| ------------: | -----: | -------- | ---- | --------------------------------------------------- |
|      `000000` | `0x00` | `NOP`    | N    | No operation                                        |
|      `000001` | `0x01` | `ADD`    | R    | `Rd = Rs1 + Rs2`                                    |
|      `000010` | `0x02` | `SUB`    | R    | `Rd = Rs1 - Rs2`                                    |
|      `000011` | `0x03` | `MUL`    | R    | `Rd = Rs1 * Rs2`, unsigned/default multiply         |
|      `000100` | `0x04` | `DIV`    | R    | `Rd = Rs1 / Rs2`                                    |
|      `000101` | `0x05` | `MOD`    | R    | `Rd = Rs1 % Rs2`                                    |
|      `000110` | `0x06` | `SHL`    | R    | `Rd = Rs1 << Rs2`                                   |
|      `000111` | `0x07` | `SHR`    | R    | `Rd = Rs1 >> Rs2`, logical right shift              |
|      `001000` | `0x08` | `AND`    | R    | `Rd = Rs1 & Rs2`                                    |
|      `001001` | `0x09` | `OR`     | R    | `Rd = Rs1 \| Rs2`                                   |
|      `001010` | `0x0A` | `XOR`    | R    | `Rd = Rs1 ^ Rs2`                                    |
|      `001011` | `0x0B` | `NOT`    | R    | `Rd = ~Rs1`                                         |
|      `001100` | `0x0C` | `FMA`    | R    | `Rd = (Rs1 * Rs2) + Rs3`                            |
|      `001101` | `0x0D` | `CMP`    | R    | Set NZP flags from signed comparison of `Rs1 - Rs2` |
|      `001110` | `0x0E` | `BRnzp`  | B    | Branch if stored NZP matches mask                   |
|      `001111` | `0x0F` | `LDR`    | I    | `Rd = Memory[Rs + imm]`                             |
|      `010000` | `0x10` | `STR`    | I    | `Memory[Rs + imm] = Rd`                             |
|      `010001` | `0x11` | `CONST`  | I    | `Rd = zero_extend(imm)`                             |
|      `010010` | `0x12` | `RET`    | N    | End current block execution                         |
|      `010011` | `0x13` | `IMUL`   | R    | `Rd = signed(Rs1) * signed(Rs2)`                    |
|      `010100` | `0x14` | `SAR`    | R    | `Rd = signed(Rs1) >>> Rs2`                          |
|      `010101` | `0x15` | `SYNC`   | N    | SIMT reconvergence point                            |

## Opcode definitions in assembler

The opcode constants are defined in:

```text
assembler/include/gpu_asm.h
```

Current opcode definitions:

```c
#define OP_NOP   0x00
#define OP_ADD   0x01
#define OP_SUB   0x02
#define OP_MUL   0x03
#define OP_DIV   0x04
#define OP_MOD   0x05
#define OP_SHL   0x06
#define OP_SHR   0x07
#define OP_AND   0x08
#define OP_OR    0x09
#define OP_XOR   0x0A
#define OP_NOT   0x0B
#define OP_FMA   0x0C
#define OP_CMP   0x0D
#define OP_BRnzp 0x0E
#define OP_LDR   0x0F
#define OP_STR   0x10
#define OP_CONST 0x11
#define OP_RET   0x12
#define OP_IMUL  0x13
#define OP_SAR   0x14
#define OP_SYNC  0x15
```

## Register file

Each thread has its own 32-register file.

| Register | Alias         | Type              | Description                             |
| -------: | ------------- | ----------------- | --------------------------------------- |
|     `R0` | `R0`          | hardwired         | Always reads as `0`; writes are ignored |
| `R1-R28` | `R1` to `R28` | general-purpose   | Writable 32-bit registers               |
|    `R29` | `THREAD_IDX`  | hardware-injected | Thread index inside the block           |
|    `R30` | `BLOCK_IDX`   | hardware-injected | Current block index                     |
|    `R31` | `BLOCK_DIM`   | hardware-injected | Threads per block                       |

## Register aliases in AXEL

Defined in:

```text
assembler/include/axel.h
```

Important aliases:

```c
#define R0  0
#define R1  1
...
#define R28 28

#define THREAD_IDX 29
#define BLOCK_IDX  30
#define BLOCK_DIM  31
```

## Special register behavior

## R0

`R0` is hardwired to zero.

```text
read R0  -> 0
write R0 -> ignored
```

## R29 / THREAD_IDX

Normally:

```text
R29 = threadIdx
```

In single-thread FPGA mode:

```text
if blockDim == 1:
    R29 = blockIdx
```

This helper allows the FPGA configuration with one thread per block to emulate multi-thread behavior by using sequential blocks as effective thread IDs.

## R30 / BLOCK_IDX

```text
R30 = blockIdx
```

## R31 / BLOCK_DIM

```text
R31 = blockDim
```

## NZP condition flags

`CMP` generates a 3-bit NZP flag.

Encoding:

| Flag |    Value | Meaning                 |
| ---- | -------: | ----------------------- |
| `N`  | `3'b100` | Negative / less-than    |
| `Z`  | `3'b010` | Zero / equal            |
| `P`  | `3'b001` | Positive / greater-than |

Assembler condition masks:

```c
#define AXEL_N   0b100
#define AXEL_Z   0b010
#define AXEL_P   0b001
#define AXEL_NZ  0b110
#define AXEL_NP  0b101
#define AXEL_ZP  0b011
#define AXEL_ALL 0b111
```

## CMP instruction

`CMP` compares two registers as signed 32-bit values.

Semantic behavior:

```text
diff = signed(Rs1) - signed(Rs2)

if diff == 0:
    NZP = Z
else if diff > 0:
    NZP = P
else:
    NZP = N
```

`CMP` does not write a general-purpose register.

It only updates the per-thread NZP flag stored in the PC module.

## BRnzp instruction

`BRnzp` branches based on the stored NZP flag.

Branch condition:

```text
taken = (stored_nzp & nzp_mask) != 0
```

If taken:

```text
PC = PC + branch_offset
```

If not taken:

```text
PC = PC + 1
```

For SIMT divergence, each thread evaluates the branch independently using its own stored NZP flag.

## Branch mask examples

| Mnemonic-style condition |     Mask | Meaning                         |
| ------------------------ | -------: | ------------------------------- |
| `BRn`                    | `3'b100` | Branch if negative              |
| `BRz`                    | `3'b010` | Branch if zero                  |
| `BRp`                    | `3'b001` | Branch if positive              |
| `BRnz`                   | `3'b110` | Branch if negative or zero      |
| `BRnp`                   | `3'b101` | Branch if negative or positive  |
| `BRzp`                   | `3'b011` | Branch if zero or positive      |
| `BRnzp` / `BRall`        | `3'b111` | Branch for any valid NZP result |

## SIMT branch divergence

The GPU uses a SIMT execution model.

Each thread lane has:

```text
own register file
own PC
own NZP flag
own ALU
own LSU
```

The scheduler controls which lanes are active using:

```text
active_mask
```

For a branch instruction, each active thread computes:

```text
taken_mask[i] =
    branch_en &&
    active_mask[i] &&
    ((nzp_stored[i] & nzp_mask) != 0)
```

Divergence occurs when:

```text
some active threads take the branch
some active threads do not take the branch
```

In RTL:

```text
divergence_detected =
    branch_en &&
    (taken_mask != active_mask) &&
    (taken_mask != 0)
```

## SIMT reconvergence

When divergence is detected:

```text
taken group runs first
not-taken active group is saved
warp_stack stores saved_mask and sync_pc
```

Saved mask:

```text
saved_mask = ~taken_mask & active_mask
```

Reconvergence PC:

```text
sync_pc = active_pc + sync_offset
```

At `SYNC`, the scheduler pops/restores the saved mask.

## SYNC instruction

`SYNC` marks a compiler/assembler-emitted reconvergence point.

It does not write registers and does not access memory.

It tells the scheduler/core:

```text
restore active_mask from warp_stack
```

In the current hardware flow:

```text
BRnzp causes divergence
warp_stack saves not-taken mask
taken group executes first
SYNC restores saved group
execution continues/reconverges according to scheduler/core mask logic
```

## Load/store instructions

## LDR

Format:

```text
LDR Rd, Rs, imm
```

Semantic behavior:

```text
Rd = Memory[Rs + sign_extend(imm)]
```

Control behavior:

```text
mem_read_en = 1
write_back_en = 1
```

The LSU issues a read request and the loaded data is written back to `Rd`.

## STR

Format:

```text
STR Rd, Rs, imm
```

Semantic behavior:

```text
Memory[Rs + sign_extend(imm)] = Rd
```

Control behavior:

```text
mem_write_en = 1
write_back_en = 0
```

The value from `Rd` is sent as store data.

## Memory addressing

The ISA uses word-addressed memory in the current simulation model.

Effective address:

```text
address = base_register + sign_extend(imm16)
```

Examples:

```text
LDR R1, THREAD_IDX, 0
```

For thread `i`:

```text
R1 = Memory[i + 0]
```

```text
STR R1, THREAD_IDX, 4
```

For thread `i`:

```text
Memory[i + 4] = R1
```

## CONST instruction

Format:

```text
CONST Rd, imm
```

Semantic behavior:

```text
Rd = zero_extend(imm16)
```

Example:

```text
CONST R1, 16
```

Result:

```text
R1 = 16
```

Note: the current `CONST` instruction is limited to unsigned 16-bit immediate values through zero extension.

## Arithmetic instructions

## ADD

```text
ADD Rd, Rs1, Rs2
Rd = Rs1 + Rs2
```

## SUB

```text
SUB Rd, Rs1, Rs2
Rd = Rs1 - Rs2
```

## MUL

```text
MUL Rd, Rs1, Rs2
Rd = Rs1 * Rs2
```

Default/unsigned-style multiplication.

## IMUL

```text
IMUL Rd, Rs1, Rs2
Rd = signed(Rs1) * signed(Rs2)
```

Used for signed Q8 fixed-point gradient computation.

## DIV

```text
DIV Rd, Rs1, Rs2
Rd = Rs1 / Rs2
```

Current limitation:

```text
No divide-by-zero guard.
```

For FPGA/ASIC synthesis targets, DIV may be disabled or replaced by zero in combined synthesis files because a combinational divider is expensive.

## MOD

```text
MOD Rd, Rs1, Rs2
Rd = Rs1 % Rs2
```

Current limitation:

```text
No modulo-by-zero guard.
```

For FPGA/ASIC synthesis targets, MOD may be disabled or replaced by zero in combined synthesis files.

## Shift instructions

## SHL

```text
SHL Rd, Rs1, Rs2
Rd = Rs1 << Rs2
```

Logical left shift.

## SHR

```text
SHR Rd, Rs1, Rs2
Rd = Rs1 >> Rs2
```

Logical right shift.

This fills vacated high bits with zero.

## SAR

```text
SAR Rd, Rs1, Rs2
Rd = signed(Rs1) >>> Rs2
```

Arithmetic right shift.

This preserves the sign bit and is required for signed fixed-point values.

## Logic instructions

## AND

```text
AND Rd, Rs1, Rs2
Rd = Rs1 & Rs2
```

## OR

```text
OR Rd, Rs1, Rs2
Rd = Rs1 | Rs2
```

## XOR

```text
XOR Rd, Rs1, Rs2
Rd = Rs1 ^ Rs2
```

## NOT

```text
NOT Rd, Rs1
Rd = ~Rs1
```

`NOT` uses only `Rs1`; the other source fields are unused.

## FMA instruction

Format:

```text
FMA Rd, Rs1, Rs2, Rs3
```

Semantic behavior:

```text
Rd = (Rs1 * Rs2) + Rs3
```

This is a single ALU operation in the current RTL.

For Q8 fixed-point arithmetic:

```text
Q8 * Q8 = Q16
```

So a scale-down instruction is usually needed after multiply/FMA:

```text
SAR result, result, shift_amount
```

For example:

```text
SAR R11, R11, R12
```

where `R12 = 8`.

## Control instructions

## NOP

```text
NOP
```

No operation.

All decoder control outputs remain zero.

## RET

```text
RET
```

Ends execution of the current block.

Scheduler behavior:

```text
block_done = 1
state returns to IDLE
```

`RET` does not write a register and does not advance PC.

## SYNC

```text
SYNC
```

SIMT reconvergence marker.

Scheduler behavior:

```text
enter SYNC_POP
restore active_mask from saved mask
```

`SYNC` does not write a register and does not access memory.

## Encoding functions

The assembler encodes instructions using helper functions in:

```text
assembler/src/gpu_asm.c
```

## R-type encoding

```c
uint32_t encode_r(uint8_t op, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) rd << 21)  |
            ((uint32_t) rs1 << 16) |
            ((uint32_t) rs2 << 11) |
            ((uint32_t) rs3 << 6);
}
```

## I-type encoding

```c
uint32_t encode_i(uint8_t op, uint8_t rd, uint8_t rs, uint16_t imm) {
    return  ((uint32_t) op << 26)  |
            ((uint32_t) rd << 21)  |
            ((uint32_t) rs << 16)  |
            (uint32_t) imm;
}
```

## B-type encoding

```c
uint32_t encode_b(uint8_t op, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset) {
    return  ((uint32_t) op << 26)           |
            ((uint32_t) nzp << 23)          |
            ((sync_offset  & 0x7FF) << 12)  |
            (branch_offset & 0xFFF);
}
```

## N-type encoding

```c
uint32_t encode_n(uint8_t op) {
    return (uint32_t) op << 26;
}
```

## AXEL API

The higher-level assembler wrapper is defined in:

```text
assembler/include/axel.h
assembler/src/axel.c
```

AXEL exposes functions such as:

```c
void axel_add(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_sub(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_mul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_imul(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_fma(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2, uint8_t rs3);
void axel_sar(AxelGPU *gpu, uint8_t rd, uint8_t rs1, uint8_t rs2);
void axel_cmp(AxelGPU *gpu, uint8_t rs1, uint8_t rs2);
void axel_brnzp(AxelGPU *gpu, uint8_t nzp, uint32_t sync_offset, uint32_t branch_offset);
void axel_ldr(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm);
void axel_str(AxelGPU *gpu, uint8_t rd, uint8_t rs, uint16_t imm);
void axel_const(AxelGPU *gpu, uint8_t rd, uint16_t imm);
void axel_sync(AxelGPU *gpu);
void axel_ret(AxelGPU *gpu);
```

## Example: simple load/store kernel

AXEL source:

```c
AxelGPU gpu;
axel_init(&gpu, 1, 4);

axel_ldr(&gpu, R1, THREAD_IDX, 0);   // R1 = mem[threadIdx]
axel_add(&gpu, R2, R1, R1);          // R2 = 2 * R1
axel_str(&gpu, R2, THREAD_IDX, 4);   // mem[threadIdx + 4] = R2
axel_ret(&gpu);

axel_compile(&gpu, "output.hex");
```

Meaning per thread:

```text
R1 = Memory[threadIdx]
R2 = R1 + R1
Memory[threadIdx + 4] = R2
RET
```

## Example: SIMT ReLU kernel

AXEL source:

```c
axel_ldr  (&gpu, R1, THREAD_IDX, 0);  // R1 = input[threadIdx]
axel_cmp  (&gpu, R1, R0);             // compare R1 with 0
axel_brnzp(&gpu, AXEL_P, 2, 2);       // if positive: jump to SYNC
axel_const(&gpu, R1, 0);              // not-taken path: R1 = 0
axel_sync (&gpu);                     // reconvergence point
axel_str  (&gpu, R1, THREAD_IDX, 4);  // store result
axel_ret  (&gpu);
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

Input memory:

```text
mem[0] =  5
mem[1] = -3
mem[2] =  8
mem[3] = -1
```

Expected output:

```text
mem[4] = 5
mem[5] = 0
mem[6] = 8
mem[7] = 0
```

Thread behavior:

```text
T0: +5 -> positive -> branch taken -> keep value
T1: -3 -> negative -> not taken -> zero
T2: +8 -> positive -> branch taken -> keep value
T3: -1 -> negative -> not taken -> zero
```

## Example encoded instructions

For the current Phase 6 SIMT ReLU program:

```text
[0] 0x3C3D0000  LDR   R1, THREAD_IDX, 0
[1] 0x34010000  CMP   R1, R0
[2] 0x38802002  BR P, sync_offset=2, branch_offset=2
[3] 0x44200000  CONST R1, 0
[4] 0x54000000  SYNC
[5] 0x403D0004  STR   R1, THREAD_IDX, 4
[6] 0x48000000  RET
```

## Q8 fixed-point usage

The ISA is integer-based, but neural-network examples use Q8 fixed-point arithmetic.

Encoding:

```text
q8_value = round(real_value * 256)
real_value = q8_value / 256
```

Examples:

| Real value |       Q8 raw |
| ---------: | -----------: |
|      `1.0` |        `256` |
|      `2.0` |        `512` |
|      `3.0` |        `768` |
|      `4.0` |       `1024` |
|      `0.5` |        `128` |
|     `-1.0` | `0xFFFFFF00` |

## Q8 multiply rule

Multiplying two Q8 values produces a Q16 intermediate:

```text
Q8 * Q8 = Q16
```

To convert back to Q8:

```text
SAR result, result, 8
```

Use `SAR`, not `SHR`, when the value may be signed.

## Why IMUL exists

`MUL` treats operands as unsigned/default values.

Signed Q8 errors use two's-complement negative numbers.

Example:

```text
-0.25 in Q8 = 0xFFFFFFC0
```

Unsigned `MUL` would interpret that as a large positive number.

`IMUL` fixes this:

```text
IMUL Rd, Rs1, Rs2
Rd = signed(Rs1) * signed(Rs2)
```

## Why SAR exists

`SHR` is logical right shift:

```text
0s shifted into the top bits
```

For negative values, that corrupts the sign.

`SAR` is arithmetic right shift:

```text
sign bit is preserved
```

So signed Q8 scale-down should use:

```text
SAR
```

not:

```text
SHR
```

## Neural-network memory map

The training/inference examples use this memory layout:

| Address | Contents                 |
| ------: | ------------------------ |
|  `0-15` | `W[4][4]`, Q8 weights    |
| `16-19` | `x[4]`, Q8 input vector  |
| `20-23` | `y[4]`, Q8 output vector |
| `24-27` | `t[4]`, Q8 target vector |

Indexing convention:

```text
W[i][j] is stored at address i * 4 + j
```

## Phase programs

| Phase | Source file                                 | Purpose                               |
| ----: | ------------------------------------------- | ------------------------------------- |
|     1 | `assembler/examples/phase1_ldr_test.c`      | LDR/STR smoke test                    |
|     2 | `assembler/examples/phase2_matmul.c`        | 4×4 matrix-vector multiply            |
|     3 | `assembler/examples/phase3_relu.c`          | ReLU baseline                         |
|     4 | `assembler/examples/phase4_forward.c`       | Linear layer + SIMT ReLU forward pass |
|     5 | `assembler/examples/phase5_weight_update.c` | Q8 gradient/weight update             |
|     6 | `assembler/examples/phase6_simt_relu.c`     | Real SIMT branch divergence ReLU      |

Generated outputs are stored in:

```text
assembler/builds/
```

Important generated files:

```text
phase4_forward.hex
phase5_weight_update.hex
phase6_simt_relu.hex
weights.json
```

## Decoder control behavior

The decoder maps opcodes into control signals.

| Instruction class | Control signals                        |
| ----------------- | -------------------------------------- |
| ALU ops           | `write_back_en = 1`                    |
| `CMP`             | `nzp_en = 1`                           |
| `BRnzp`           | `branch_en = 1`                        |
| `LDR`             | `mem_read_en = 1`, `write_back_en = 1` |
| `STR`             | `mem_write_en = 1`                     |
| `CONST`           | `write_back_en = 1`                    |
| `RET`             | `ret = 1`                              |
| `SYNC`            | `sync_en = 1`                          |
| `NOP`             | all control outputs remain `0`         |

Important rule:

```text
scheduler write_back_en alone does not mean a register writes
```

Actual register writeback in the core requires:

```text
scheduler write_back_en
decoder write_back_en
active_mask[i]
```

## Instruction execution notes

## No hazard detection

The current design does not implement a full hazard detection or forwarding unit.

Programs should be written assuming the current scheduler timing and tested behavior.

## No negative branch offsets

The current branch offset field is treated as unsigned by the RTL.

Therefore, branch programs should use forward offsets.

## Divide/modulo limitations

`DIV` and `MOD` exist in the ISA and simulator RTL, but they are expensive for synthesis and may be disabled in synthesis-target combined Verilog.

Avoid relying on them for FPGA/ASIC demos unless the synthesis target explicitly supports them.

## CONST immediate limitation

`CONST` currently zero-extends a 16-bit immediate.

It cannot directly load a full 32-bit constant in one instruction.

To create larger constants, future ISA extensions may need:

```text
LUI / upper immediate
ORI immediate
load literal
```

## Store source register convention

`STR Rd, Rs, imm` uses:

```text
Rd as store data source
Rs as base address
imm as offset
```

So:

```text
STR R1, THREAD_IDX, 4
```

means:

```text
Memory[THREAD_IDX + 4] = R1
```

## Known ISA limitations

```text
- Fixed 32-bit instruction width
- 6-bit opcode field
- CONST only loads 16-bit zero-extended immediates
- Branch offsets are unsigned forward offsets in current RTL
- No full jump/call instruction
- No stack pointer or subroutine call convention
- No byte/halfword memory access
- No floating-point operations
- No vector register file
- No explicit memory barriers
- DIV/MOD are not synthesis-friendly in current form
```

## Future ISA extension ideas

Potential extensions:

```text
LUI        -> load upper immediate
ADDI       -> add immediate
ANDI/ORI   -> logic immediate
JMP        -> unconditional jump
JAL/JR     -> call/return support
LDI32      -> load 32-bit literal
SLT        -> set-less-than
MIN/MAX    -> activation/helper instructions
CLAMP      -> fixed-point neural-network helper
MULHI      -> high-word multiply
LOADV/STRV -> vectorized memory helper
```

For SIMT control:

```text
SSY-style explicit set-sync instruction
better nested divergence metadata
hardware-assisted reconvergence checks using top_sync_pc
```

## Summary

The Tiny GPU ISA is a small 32-bit custom instruction set designed for an educational SIMT GPU.

It supports:

```text
integer arithmetic
logic operations
signed multiply
arithmetic shift
load/store memory access
hardware-injected thread/block registers
NZP condition flags
SIMT branch divergence
SYNC-based reconvergence
Q8 fixed-point neural-network kernels
```

The most important ISA rules are:

```text
R0 is always zero
R29/R30/R31 are hardware-injected
CMP updates NZP, not a register
BRnzp uses stored NZP
LDR writes a register
STR writes memory
SYNC restores SIMT execution mask
RET ends the block
SAR/IMUL are required for signed Q8 math
```
