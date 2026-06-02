# Tiny GPU Memory Map

## Overview

This document defines the memory layout used by the Tiny GPU simulation, AXEL programs, neural-network training kernels, inference kernels, and SIMT ReLU regression tests.

The current memory model is word-addressed.

```text
1 address = 1 × 32-bit word
```

All instruction/data values are 32-bit values.

The project currently separates:

```text
program memory -> instruction words loaded from .hex files
data memory    -> runtime data, weights, inputs, outputs, targets
```

The cocotb testbench models both memories.

## Memory spaces

| Memory space   |  Width | Addressing                | Purpose                                       |
| -------------- | -----: | ------------------------- | --------------------------------------------- |
| Program memory | 32-bit | word-addressed PC index   | Stores encoded instructions                   |
| Data memory    | 32-bit | word-addressed data index | Stores weights, vectors, outputs, test inputs |

## Program memory

Program memory stores 32-bit encoded ISA instructions.

Each program counter value maps directly to one instruction word:

```text
instruction = program_memory[PC]
```

Example:

```text
PC0 -> first instruction
PC1 -> second instruction
PC2 -> third instruction
```

The fetcher sends:

```text
prog_mem_req_addr = PC value
```

The program memory model returns:

```text
prog_mem_resp_data = instruction word
```

## Program memory files

AXEL assembler output files are stored in:

```text
assembler/builds/
```

Common generated files:

| File                       | Purpose                    |
| -------------------------- | -------------------------- |
| `phase1_ldr_test.hex`      | LDR/STR smoke test         |
| `phase2_matmul.hex`        | 4×4 matrix-vector multiply |
| `phase3_relu.hex`          | ReLU baseline              |
| `phase4_forward.hex`       | Q8 forward pass with ReLU  |
| `phase5_weight_update.hex` | Q8 weight update           |
| `phase6_simt_relu.hex`     | SIMT ReLU divergence test  |

## Program memory fallback behavior

The top-level program memory model returns `RET` for missing instruction addresses.

```text
RET = 0x48000000
```

This prevents a bad or out-of-range PC from hanging the simulation forever.

Important note:

```text
Fallback RET is useful for simulation safety, but it can hide PC bugs if the test does not check exact instruction flow.
```

## Phase 6 SIMT ReLU program memory

The Phase 6 SIMT ReLU program currently contains 7 instructions.

|  PC | Encoded instruction | Meaning                                |
| --: | ------------------: | -------------------------------------- |
| `0` |        `0x3C3D0000` | `LDR R1, THREAD_IDX, 0`                |
| `1` |        `0x34010000` | `CMP R1, R0`                           |
| `2` |        `0x38802002` | `BR P, sync_offset=2, branch_offset=2` |
| `3` |        `0x44200000` | `CONST R1, 0`                          |
| `4` |        `0x54000000` | `SYNC`                                 |
| `5` |        `0x403D0004` | `STR R1, THREAD_IDX, 4`                |
| `6` |        `0x48000000` | `RET`                                  |

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

## Data memory

Data memory stores runtime values.

The top-level cocotb tests use a Python dictionary:

```python
data_memory = {}
```

Data memory request convention:

```text
data_mem_req_rw = 1 -> read
data_mem_req_rw = 0 -> write
```

For reads:

```text
response_data = data_memory.get(address, 0)
```

For writes:

```text
data_memory[address] = write_data
```

Missing addresses return zero in the cocotb model.

## Neural-network memory map

The Q8 neural-network forward/update tests use this fixed memory map:

| Address range | Name      |     Size | Format | Description                |
| ------------: | --------- | -------: | ------ | -------------------------- |
|        `0-15` | `W[4][4]` | 16 words | Q8     | Weight matrix              |
|       `16-19` | `x[4]`    |  4 words | Q8     | Input vector               |
|       `20-23` | `y[4]`    |  4 words | Q8     | Forward-pass output vector |
|       `24-27` | `t[4]`    |  4 words | Q8     | Target vector              |

## Weight matrix layout

The 4×4 weight matrix is stored row-major.

```text
W[i][j] -> address = i * 4 + j
```

Address table:

| Address | Matrix element |
| ------: | -------------- |
|     `0` | `W[0][0]`      |
|     `1` | `W[0][1]`      |
|     `2` | `W[0][2]`      |
|     `3` | `W[0][3]`      |
|     `4` | `W[1][0]`      |
|     `5` | `W[1][1]`      |
|     `6` | `W[1][2]`      |
|     `7` | `W[1][3]`      |
|     `8` | `W[2][0]`      |
|     `9` | `W[2][1]`      |
|    `10` | `W[2][2]`      |
|    `11` | `W[2][3]`      |
|    `12` | `W[3][0]`      |
|    `13` | `W[3][1]`      |
|    `14` | `W[3][2]`      |
|    `15` | `W[3][3]`      |

## Input vector layout

| Address | Element |
| ------: | ------- |
|    `16` | `x[0]`  |
|    `17` | `x[1]`  |
|    `18` | `x[2]`  |
|    `19` | `x[3]`  |

Current default input vector:

```text
X = [256, 512, 768, 1024]
```

Q8 real values:

```text
X = [1.0, 2.0, 3.0, 4.0]
```

## Output vector layout

| Address | Element |
| ------: | ------- |
|    `20` | `y[0]`  |
|    `21` | `y[1]`  |
|    `22` | `y[2]`  |
|    `23` | `y[3]`  |

The forward-pass kernel writes outputs here.

## Target vector layout

| Address | Element |
| ------: | ------- |
|    `24` | `t[0]`  |
|    `25` | `t[1]`  |
|    `26` | `t[2]`  |
|    `27` | `t[3]`  |

Current default target vector:

```text
T = [512, 1024, 1536, 2048]
```

Q8 real values:

```text
T = [2.0, 4.0, 6.0, 8.0]
```

## Q8 fixed-point format

The neural-network examples use Q8 fixed-point arithmetic.

```text
real_value = raw_value / 256
raw_value  = round(real_value * 256)
```

Examples:

| Real value | Q8 raw decimal |   Q8 raw hex |
| ---------: | -------------: | -----------: |
|      `1.0` |          `256` | `0x00000100` |
|      `2.0` |          `512` | `0x00000200` |
|      `3.0` |          `768` | `0x00000300` |
|      `4.0` |         `1024` | `0x00000400` |
|      `0.5` |          `128` | `0x00000080` |
|     `-1.0` |         `-256` | `0xFFFFFF00` |

## Q8 multiply scaling

Multiplying two Q8 values produces a Q16 intermediate.

```text
Q8 * Q8 = Q16
```

To scale back to Q8:

```text
SAR value, value, 8
```

Use `SAR` for signed values.

Do not use `SHR` for signed Q8 values because it zero-fills and corrupts negative numbers.

## Initial training weights

The default initial weight matrix is identity in Q8:

```text
W_INIT = [
    [256, 0,   0,   0],
    [0,   256, 0,   0],
    [0,   0,   256, 0],
    [0,   0,   0,   256],
]
```

Real-value equivalent:

```text
W_INIT = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]
```

## Saved weights file

Training saves weights to:

```text
assembler/builds/weights.json
```

Only weight addresses `0-15` are saved.

Example structure:

```json
{
  "0": 256,
  "1": 0,
  "2": 0,
  "3": 0
}
```

The file is used by inference and later training runs.

Important note:

```text
weights.json is generated by simulation and may be gitignored.
On a fresh clone, run the training/top-level test before running inference.
```

## Phase 4 forward-pass memory usage

Phase 4 reads:

```text
W[0..15]
x[16..19]
```

It writes:

```text
y[20..23]
```

Conceptual computation per output thread `i`:

```text
z[i] = sum_j(W[i][j] * x[j]) >> 8
y[i] = ReLU(z[i])
```

Address behavior:

```text
row_base = threadIdx * 4
W[i][j] = Memory[row_base + j]
x[j]    = Memory[16 + j]
y[i]    = Memory[20 + threadIdx]
```

## Phase 5 weight-update memory usage

Phase 5 reads:

```text
W[0..15]
x[16..19]
y[20..23]
t[24..27]
```

It writes updated weights back into:

```text
W[0..15]
```

Conceptual update:

```text
error[i] = y[i] - t[i]
W[i][j] = W[i][j] - scaled_gradient(error[i], x[j])
```

The Q8 scale-down and learning rate are handled using signed multiply and arithmetic shift.

Important instructions:

```text
IMUL -> signed Q8 multiply
SAR  -> signed scale-down
```

## Phase 6 SIMT ReLU memory map

Phase 6 uses a smaller test-specific memory layout.

Initial memory:

| Address |        Value | Meaning                  |
| ------: | -----------: | ------------------------ |
|     `0` |          `5` | Thread 0 input, positive |
|     `1` | `0xFFFFFFFD` | Thread 1 input, `-3`     |
|     `2` |          `8` | Thread 2 input, positive |
|     `3` | `0xFFFFFFFF` | Thread 3 input, `-1`     |

Expected output memory:

| Address | Expected value | Meaning                       |
| ------: | -------------: | ----------------------------- |
|     `4` |            `5` | Thread 0 keeps positive value |
|     `5` |            `0` | Thread 1 zeros negative value |
|     `6` |            `8` | Thread 2 keeps positive value |
|     `7` |            `0` | Thread 3 zeros negative value |

The kernel code performs:

```text
R1 = Memory[THREAD_IDX + 0]
if R1 > 0:
    keep R1
else:
    R1 = 0
Memory[THREAD_IDX + 4] = R1
```

## Memory access examples

## Load input by thread index

Instruction:

```text
LDR R1, THREAD_IDX, 0
```

For each thread:

| Thread | `THREAD_IDX` | Address | Loaded value |
| -----: | -----------: | ------: | ------------ |
|     T0 |          `0` |     `0` | `Memory[0]`  |
|     T1 |          `1` |     `1` | `Memory[1]`  |
|     T2 |          `2` |     `2` | `Memory[2]`  |
|     T3 |          `3` |     `3` | `Memory[3]`  |

## Store output by thread index

Instruction:

```text
STR R1, THREAD_IDX, 4
```

For each thread:

| Thread | `THREAD_IDX` | Address | Stored value |
| -----: | -----------: | ------: | ------------ |
|     T0 |          `0` |     `4` | `R1`         |
|     T1 |          `1` |     `5` | `R1`         |
|     T2 |          `2` |     `6` | `R1`         |
|     T3 |          `3` |     `7` | `R1`         |

## FPGA single-thread mode memory behavior

For the FPGA-reduced configuration:

```text
NUM_CORES = 1
THREADS_PER_CORE = 1
blockDim = 1
num_blocks = 4
```

The register file helper makes:

```text
R29 / THREAD_IDX = blockIdx
```

when:

```text
blockDim == 1
```

This means four sequential blocks behave like four thread indices:

|   Block | `blockIdx` | Effective `THREAD_IDX` |
| ------: | ---------: | ---------------------: |
| Block 0 |        `0` |                    `0` |
| Block 1 |        `1` |                    `1` |
| Block 2 |        `2` |                    `2` |
| Block 3 |        `3` |                    `3` |

This allows single-thread FPGA execution to match the 4-thread simulation result numerically.

## Top-level data memory response bus

The current top-level RTL uses a packed response-data bus:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

Cocotb must drive the whole packed bus as one integer.

Correct:

```python
packed = 0

for c in range(NUM_CORES):
    packed |= (resp_data_per_core[c] & 0xFFFFFFFF) << (c * 32)

dut.data_mem_resp_data.value = packed
```

Incorrect:

```python
dut.data_mem_resp_data[i].value = value
```

## Program memory response bus

Program memory response data is currently unpacked at top level:

```systemverilog
input logic [31:0] prog_mem_resp_data [NUM_CORES-1:0]
```

Cocotb can drive it per core:

```python
dut.prog_mem_resp_data[i].value = instruction
```

## Memory controller response-data bus

Inside the current core memory path, memory-controller response data is packed:

```systemverilog
output logic [THREADS_PER_CORE-1:0][31:0] resp_data
```

This must match the core’s internal LSU response-data bus.

Important fixed bug:

```text
mem_controller.resp_data and core.lsu_resp_data must use the same packed shape.
```

If they do not match, the memory controller can receive correct data while the LSU sees zero.

## Important memory-path rule

Keep these bus shapes aligned:

```text
top_level_gpu.sv:
  data_mem_resp_data = packed [NUM_CORES-1:0][31:0]

core.sv:
  lsu_resp_data = packed [THREADS_PER_CORE-1:0][31:0]

mem_controller.sv:
  resp_data = packed [THREADS_PER_CORE-1:0][31:0]

test_top_level_gpu.py:
  drives data_mem_resp_data as one packed integer

inference.py:
  must follow the same packed response-data convention
```

## Known memory limitations

```text
- Data memory is modeled in cocotb, not implemented as final RTL SRAM/BRAM at top level.
- Memory is word-addressed only.
- No byte or halfword loads/stores.
- No memory protection.
- No cache.
- No memory barriers.
- Current data memory model returns 0 for missing addresses.
- Program memory model returns RET for missing instruction addresses.
- DIV/MOD are not recommended for synthesis demos.
```

## Summary

The Tiny GPU memory map is intentionally simple:

```text
Program memory:
  PC-indexed 32-bit instruction words

Data memory:
  address 0-15  -> W[4][4]
  address 16-19 -> x[4]
  address 20-23 -> y[4]
  address 24-27 -> t[4]
```

The most important practical rules are:

```text
Use word addresses, not byte addresses.
Use Q8 fixed-point for neural-network examples.
Use SAR/IMUL for signed Q8 math.
Keep packed memory response buses aligned across RTL and cocotb.
Drive data_mem_resp_data as one packed integer in cocotb.
```
