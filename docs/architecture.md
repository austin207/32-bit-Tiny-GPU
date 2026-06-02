# Tiny GPU Architecture

## Overview

This project implements a small SIMT-style GPU in SystemVerilog with cocotb-based verification.

The design is organized around a top-level GPU module that receives kernel launch configuration through a Device Control Register, dispatches blocks to cores, and executes instructions across multiple thread lanes per core.

Current default configuration:

```text
NUM_CORES        = 4
THREADS_PER_CORE = 4
TOTAL_THREADS    = 16
```

The architecture is intentionally simple and educational, but it now includes enough GPU-like behavior to run small AXEL assembler programs, memory operations, SIMT branch divergence, SYNC reconvergence, ReLU kernels, and Q8 fixed-point forward/update workloads.

## Architecture diagrams

## GPU architecture

![GPU Architecture](../assets/Architecture-images/gpu_architecture.png)

Diagram note:

The current architecture image shows the main top-level structure: DCR, dispatcher, cores, per-thread execution units, and memory interface.

This image should be updated later to include `warp_stack` inside each core. In the current RTL, `warp_stack` is part of `core.sv` and is used for SIMT divergence/reconvergence.

Also note that the current RTL instantiates `mem_controller` inside each core, not as one single shared top-level memory controller. If the diagram shows one global memory controller below all cores, treat that as a conceptual memory interface view rather than the exact RTL hierarchy.

## Instruction encoding

![Instruction Encoding](../assets/Architecture-images/instruction_encoding.png)

## Software layer architecture

![Software Layer Architecture](../assets/Architecture-images/software_layer_architecture.png)

## Repository structure

Relevant project layout:

```text
gpu-project/
  assembler/
    include/
      axel.h
      gpu_asm.h
    src/
      axel.c
      gpu_asm.c
    examples/
      phase1_ldr_test.c
      phase2_matmul.c
      phase3_relu.c
      phase4_forward.c
      phase5_weight_update.c
      phase6_simt_relu.c
    builds/
      phase4_forward.hex
      phase5_weight_update.hex
      phase6_simt_relu.hex
      weights.json

  Src/
    Top_level_GPU/
      top_level_gpu.sv
      test_top_level_gpu.py
      inference.py
    core/
      core.sv
      test_core.py
    device_control_register/
      dcr.sv
      test_dcr.py
    dispatcher/
      dispatcher.sv
      test_dispatcher.py
    scheduler/
      scheduler.sv
      test_scheduler.py
    fetcher/
      fetcher.sv
      test_fetcher.py
    decoder/
      decoder.sv
      test_decoder.py
    alu/
      alu.sv
      test_alu.py
    lsu/
      lsu.sv
      test_lsu.py
    pc/
      pc.sv
      test_pc.py
    registers/
      register_file.sv
      test_registers.py
    memory_controller/
      mem_controller.sv
      test_mem_controller.py
    warp_stack/
      warp_stack.sv
      test_warp_stack.py

  docs/
    architecture.md
    isa.md
    memory_map.md
    debug_log.md

  assets/
    Architecture-images/
      gpu_architecture.png
      instruction_encoding.png
      software_layer_architecture.png
    Images-Components/
      ALU-page-00001.jpg
      Core-page-00001.jpg
      DCR-page-00001.jpg
      Decoder-page-00001.jpg
      Dispatcher-page-00001.jpg
      Fetcher-page-00001.jpg
      GPU-page-00001.jpg
      LSU-page-00001.jpg
      Memory Controller-page-00001.jpg
      PC-page-00001.jpg
      Register File-page-00001.jpg
      Scheduler-page-00001.jpg
```

## Top-level hardware hierarchy

The top-level GPU module is:

```text
Src/Top_level_GPU/top_level_gpu.sv
```

Its main hierarchy is:

```text
gpu
├── dcr
├── dispatcher
└── core_gen[i]
    └── core
        ├── fetcher
        ├── decoder
        ├── scheduler
        ├── warp_stack
        ├── mem_controller
        └── thread_gen[j]
            ├── registers
            ├── alu
            ├── lsu
            └── pc
```

Default generated structure:

```text
gpu
├── core_gen[0]
│   └── 4 thread lanes
├── core_gen[1]
│   └── 4 thread lanes
├── core_gen[2]
│   └── 4 thread lanes
└── core_gen[3]
    └── 4 thread lanes
```

So the default design has:

```text
4 cores × 4 threads/core = 16 total thread lanes
```

## Main module responsibilities

| Module           | Responsibility                                                         |
| ---------------- | ---------------------------------------------------------------------- |
| `gpu`            | Top-level integration of DCR, dispatcher, cores, and memory interfaces |
| `dcr`            | Stores launch configuration and emits one-cycle start pulse            |
| `dispatcher`     | Assigns block indices to available cores and asserts `kernel_done`     |
| `core`           | Main SIMT execution engine                                             |
| `scheduler`      | Core instruction sequencing FSM                                        |
| `fetcher`        | Requests instructions from program memory                              |
| `decoder`        | Extracts instruction fields and control signals                        |
| `registers`      | Per-thread register file with hardware-injected special registers      |
| `alu`            | Arithmetic, logic, comparison, FMA, shift, and multiply operations     |
| `pc`             | Per-thread program counter and NZP storage                             |
| `lsu`            | Per-thread load/store request FSM                                      |
| `mem_controller` | Per-core memory request arbiter across thread LSUs                     |
| `warp_stack`     | Stores divergence/reconvergence masks for SIMT control flow            |

## Launch control path

Kernel launch starts from host/testbench writes into the DCR.

```text
host / cocotb testbench
        │
        ▼
DCR writes
        │
        ▼
dcr
        │
        ├── num_blocks
        ├── blockDim
        └── start
              │
              ▼
        dispatcher
              │
              ├── core_start[i]
              ├── blockIdx_out[i]
              └── kernel_done
```

Launch sequence:

```text
1. Write num_blocks to DCR address 0b00.
2. Write blockDim to DCR address 0b01.
3. Write DCR address 0b10 to generate start pulse.
4. Dispatcher receives start as dispatch_en.
5. Dispatcher assigns blockIdx values to free cores.
6. Cores execute assigned blocks.
7. Cores assert block_done after RET.
8. Dispatcher asserts kernel_done when all blocks are complete.
```

## DCR register map

| Address | Name         | Meaning                     |
| ------: | ------------ | --------------------------- |
| `2'b00` | `num_blocks` | Number of blocks to launch  |
| `2'b01` | `blockDim`   | Number of threads per block |
| `2'b10` | `start`      | One-cycle start pulse       |
| `2'b11` | reserved     | Unused                      |

Important rule:

```text
num_blocks and blockDim are persistent registers.
start is a one-cycle pulse.
```

## Dispatcher behavior

The dispatcher assigns blocks to cores.

Current behavior:

```text
one new block assignment per clock
core_start[i] remains high while core i is active
kernel_done is sticky until reset
```

Example with `NUM_CORES = 4` and `num_blocks = 4`:

```text
cycle 1 -> core 0 gets block 0
cycle 2 -> core 1 gets block 1
cycle 3 -> core 2 gets block 2
cycle 4 -> core 3 gets block 3
```

Example with `NUM_CORES = 4` and `num_blocks = 6`:

```text
first wave:
  core 0 -> block 0
  core 1 -> block 1
  core 2 -> block 2
  core 3 -> block 3

after core 0 completes:
  core 0 -> block 4

after core 1 completes:
  core 1 -> block 5
```

## Core architecture

Each core is a SIMT execution unit.

One core contains:

```text
fetcher
decoder
scheduler
warp_stack
mem_controller
THREADS_PER_CORE × thread lane
```

Each thread lane contains:

```text
register file
ALU
LSU
PC
```

Core-level flow:

```text
active_pc
   │
   ▼
fetcher
   │
   ▼
instruction latch
   │
   ▼
decoder
   │
   ▼
scheduler
   │
   ├── ALU execution
   ├── LSU/memory operation
   ├── register writeback
   ├── PC update
   └── divergence/SYNC handling
```

## Instruction lifecycle

A normal non-memory instruction follows:

```text
FETCH
  -> DECODE
  -> EXECUTE
  -> UPDATE
  -> FETCH
```

A memory instruction follows:

```text
FETCH
  -> DECODE
  -> REQUEST
  -> WAIT
  -> EXECUTE
  -> UPDATE
  -> FETCH
```

A `RET` instruction follows:

```text
FETCH
  -> DECODE
  -> EXECUTE
  -> UPDATE
  -> block_done
  -> IDLE
```

A divergent branch follows:

```text
FETCH
  -> DECODE
  -> EXECUTE
  -> UPDATE
  -> DIVERGE
  -> FETCH
```

A `SYNC` instruction follows:

```text
FETCH
  -> DECODE
  -> EXECUTE
  -> UPDATE
  -> SYNC_POP
  -> FETCH
```

## Scheduler FSM

The scheduler states are:

| State      |  Encoding | Meaning                                  |
| ---------- | --------: | ---------------------------------------- |
| `IDLE`     | `4'b0000` | Wait for `core_start`                    |
| `FETCH`    | `4'b0001` | Enable fetcher                           |
| `DECODE`   | `4'b0010` | Decide memory or non-memory path         |
| `REQUEST`  | `4'b0011` | Pulse LSU enable                         |
| `WAIT`     | `4'b0100` | Wait for all active LSUs to finish       |
| `EXECUTE`  | `4'b0101` | Pulse execute enable                     |
| `UPDATE`   | `4'b0110` | Writeback / PC update / block completion |
| `DIVERGE`  | `4'b0111` | Apply taken branch mask                  |
| `SYNC_POP` | `4'b1000` | Restore saved active mask                |

The scheduler emits:

```text
fetcher_en
lsu_en
execute_en
write_back_en
pc_en
active_mask
block_done
current_state
```

## Register architecture

Each thread lane has one private register file.

Logical register map:

| Register | Meaning                                         |
| -------: | ----------------------------------------------- |
|     `R0` | Hardwired zero                                  |
| `R1-R28` | Writable general-purpose registers              |
|    `R29` | `threadIdx`, or `blockIdx` when `blockDim == 1` |
|    `R30` | `blockIdx`                                      |
|    `R31` | `blockDim`                                      |

Important FPGA helper:

```text
When blockDim == 1, R29 returns blockIdx instead of threadIdx.
```

This allows single-thread-per-block FPGA execution to numerically match multi-thread simulation behavior.

## ALU architecture

Each thread lane has one ALU.

Supported ALU/control operations include:

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

`CMP` generates NZP flags:

```text
N = 3'b100
Z = 3'b010
P = 3'b001
```

The PC stores NZP flags and uses them for branch decisions.

## PC and branch behavior

Each thread lane has its own PC and NZP register.

PC behavior:

```text
normal instruction -> pc_out = pc_out + 1
taken branch       -> pc_out = pc_out + branch_offset
block start        -> pc_out = 0
```

Branch condition:

```text
branch_taken = branch_en && ((stored_nzp & nzp_mask) != 0)
```

CMP and branch are separate instructions:

```text
CMP stores NZP.
BRNZP uses the stored NZP.
```

## Memory architecture

The current RTL uses a per-core memory controller.

Path:

```text
thread LSU requests
        │
        ▼
per-core mem_controller
        │
        ▼
top-level data memory interface
        │
        ▼
cocotb data memory model / external memory
```

Inside each core:

```text
THREADS_PER_CORE LSU lanes
        │
        ▼
mem_controller
        │
        ▼
single core data-memory request interface
```

The memory controller:

```text
buffers one-cycle LSU request pulses
selects one request using round-robin arbitration
issues one external request at a time
routes response back to the correct thread
```

Read/write convention:

```text
1 = read
0 = write
```

## Program memory interface

Each core has a program memory request lane.

```text
prog_mem_req_valid[i]
prog_mem_req_addr[i]
prog_mem_resp_valid[i]
prog_mem_resp_data[i]
```

In the current top-level RTL, `prog_mem_resp_data` is unpacked:

```systemverilog
input logic [31:0] prog_mem_resp_data [NUM_CORES-1:0]
```

So cocotb can drive it per core:

```python
dut.prog_mem_resp_data[i].value = instr
```

## Data memory interface

Each core has a data memory request lane.

```text
data_mem_req_valid[i]
data_mem_req_addr[i]
data_mem_req_rw[i]
data_mem_req_data[i]
data_mem_resp_valid[i]
data_mem_resp_data[i]
```

Important bus-shape rule:

`data_mem_resp_data` is packed:

```systemverilog
input logic [NUM_CORES-1:0][31:0] data_mem_resp_data
```

So cocotb must drive the whole bus as one packed integer:

```python
packed = 0
for c in range(NUM_CORES):
    packed |= (resp_data_per_core[c] & 0xFFFFFFFF) << (c * 32)

dut.data_mem_resp_data.value = packed
```

Do not drive it per index from cocotb.

## Packed vs unpacked bus rule

The project currently has both packed and unpacked array ports.

Important examples:

```text
prog_mem_resp_data -> unpacked
data_mem_resp_data -> packed
blockIdx_out       -> packed internally
lsu_resp_data      -> packed internally
mem_controller.resp_data -> packed
```

The most important fixed bug was caused by a packed/unpacked mismatch in the memory response path.

Bad behavior before the fix:

```text
mc_resp_data=5
mc_out_data0=5
lsu0_resp_v=1
lsu0_resp_data=0
lsu0_read_data=0
```

Correct behavior after the fix:

```text
mc_resp_data=5
lsu0_resp_v=1
lsu0_resp_data=5
lsu0_read_data=5
```

This is why packed response-data buses must stay aligned between:

```text
top_level_gpu.sv
core.sv
mem_controller.sv
test_top_level_gpu.py
inference.py
```

## SIMT execution model

The core executes one instruction stream across multiple thread lanes.

Each lane has:

```text
own register file
own PC
own NZP flag
own ALU
own LSU
```

The scheduler controls an `active_mask`.

```text
active_mask[i] = 1 -> thread i participates
active_mask[i] = 0 -> thread i is inactive
```

The core gates important per-thread actions with `active_mask`:

```text
LSU enable
register write enable
PC enable
```

This prevents inactive lanes from issuing memory requests, writing registers, or advancing PC.

## Divergence and reconvergence

SIMT branch divergence occurs when only some active threads take a branch.

Branch decision per thread:

```text
taken_mask[i] =
    branch_en &&
    active_mask[i] &&
    ((nzp_stored[i] & nzp_mask) != 0)
```

Divergence condition:

```text
divergence_detected =
    branch_en &&
    (taken_mask != active_mask) &&
    (taken_mask != 0)
```

If divergence occurs:

```text
taken path becomes active first
not-taken active path is saved
warp_stack stores saved mask and sync PC
```

The warp stack stores:

```text
sync_pc
saved_mask
```

At `SYNC`, the scheduler restores:

```text
active_mask = saved_mask
```

## Warp stack note

The current architecture diagram should be updated to include `warp_stack`.

Suggested diagram placement:

```text
Inside each core:
  place Warp Stack near Scheduler and PC
```

Suggested connection labels:

```text
Scheduler -> Warp Stack:
  push / pop

Branch logic -> Warp Stack:
  sync_pc
  saved_mask

Warp Stack -> Scheduler:
  saved_mask

Warp Stack -> PC / reconvergence logic:
  sync_pc
```

Suggested block label:

```text
Warp Stack
SIMT reconvergence
```

## SIMT ReLU example

The SIMT ReLU program is the key branch-divergence regression.

Program:

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

Meaning:

```text
T0: +5 -> branch taken -> keep 5
T1: -3 -> not taken -> zero
T2: +8 -> branch taken -> keep 8
T3: -1 -> not taken -> zero
```

This verifies:

```text
LDR read path
register writeback
CMP NZP generation
BRNZP branch decision
divergence handling
SYNC path
STR write path
kernel completion
```

## AXEL assembler flow

The software side generates hex programs for the GPU.

Flow:

```text
C AXEL example
      │
      ▼
AXEL assembler helpers
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

Relevant files:

```text
assembler/include/axel.h
assembler/include/gpu_asm.h
assembler/src/axel.c
assembler/src/gpu_asm.c
assembler/examples/*.c
assembler/builds/*.hex
```

Generated example programs:

```text
phase1_ldr_test.hex
phase2_matmul.hex
phase3_relu.hex
phase4_forward.hex
phase5_weight_update.hex
phase6_simt_relu.hex
```

## Q8 fixed-point convention

Several programs use Q8 fixed-point values.

Convention:

```text
real_value = q8_value / 256
q8_value   = round(real_value * 256)
```

Examples:

```text
1.0  -> 256
2.0  -> 512
0.5  -> 128
-1.0 -> 0xFFFFFF00
```

The forward/update tests use:

```text
X = [256, 512, 768, 1024]
T = [512, 1024, 1536, 2048]
```

which correspond to:

```text
X = [1.0, 2.0, 3.0, 4.0]
T = [2.0, 4.0, 6.0, 8.0]
```

## Verification strategy

The project uses cocotb unit tests for each RTL module and integration tests at the core/top-level GPU level.

Current unit/integration coverage includes:

| Area              | Tests                                                   |
| ----------------- | ------------------------------------------------------- |
| ALU               | ADD, SUB, CMP, NOT                                      |
| Registers         | reset, write/read, R0 zero, hardware-injected registers |
| PC                | reset, increment, NZP store, branch taken/not taken     |
| Fetcher           | basic fetch, multicycle response, reset during fetch    |
| LSU               | read, write, reset during read                          |
| Memory controller | single read, single write, round-robin                  |
| Scheduler         | basic flow, memory flow, RET, divergence                |
| Warp stack        | push, pop, full/overflow                                |
| Dispatcher        | single block, multiple cores, more blocks than cores    |
| DCR               | num_blocks write, blockDim write, start pulse           |
| Core              | basic fetch/execute/RET                                 |
| Top-level GPU     | AXEL program, SIMT ReLU                                 |
| Inference         | forward-only inference using saved weights              |

Run all tests from repo root:

```bash
make test
```

Run top-level GPU tests:

```bash
cd Src/Top_level_GPU
make
```

Run inference:

```bash
cd Src/Top_level_GPU
make infer
```

## Current known limitations

## Architecture image needs update

The current `gpu_architecture.png` should be updated to include `warp_stack`.

Also verify whether the diagram should show memory controller as:

```text
per-core mem_controller
```

instead of a single shared global memory controller.

The current RTL uses per-core memory controllers.

## Dispatcher assigns one block per cycle

The dispatcher currently assigns only one new block per clock cycle.

This is simple and test-covered, but not maximum throughput.

## `kernel_done` is sticky

`kernel_done` remains high until reset.

Repeated kernel launches should reset the GPU first unless dispatcher behavior is extended.

## Warp stack is partially parameterized

`warp_stack` has parameters, but the current internal storage is effectively hardcoded for:

```text
THREADS_PER_CORE = 4
STACK_DEPTH = 4
```

Future work should parameterize entry width and stack pointer width.

## Program memory model returns RET for missing addresses

The cocotb program memory model returns:

```text
RET = 0x48000000
```

for missing instruction addresses.

This prevents tests from hanging on invalid fetches, but it can also hide bad PC behavior if not checked carefully.

## No real external memory yet

The current memory system is modeled in cocotb.

RTL exposes request/response ports, but no physical SRAM/BRAM/external memory controller is integrated at top level yet.

## Important design rules

Do not change packed response-data buses casually.

The following must remain aligned:

```text
data_mem_resp_data
lsu_resp_data
mem_controller.resp_data
cocotb memory model packing
```

Do not use scheduler `write_back_en` alone.

Register writes must be gated by:

```text
scheduler write_back_en
decoder write_back_en
active_mask
```

Do not let inactive lanes update state.

Inactive lanes must not:

```text
issue LSU requests
write registers
advance PC
```

Do not debug branch divergence before proving LDR works.

If loaded register values are wrong, CMP and branch behavior become misleading.

Do not remove the instruction latch inside `core.sv`.

Decoder outputs must remain stable across multicycle instruction execution.

## Last known status

```text
Status: passing

Verified with:
  cd ~/gpu-project
  make test

Key regression:
  test_simt_relu passes with:
    mem[4] = 5
    mem[5] = 0
    mem[6] = 8
    mem[7] = 0

Important fixed bug:
  Packed/unpacked response-data mismatch between memory controller and LSU response path.
```

## Design summary

The Tiny GPU is a multi-core SIMT-style educational GPU.

At the top level:

```text
DCR configures launch
dispatcher assigns blocks
cores execute instructions
program memory supplies instructions
data memory supplies/accepts data
kernel_done marks completion
```

Inside each core:

```text
fetcher fetches instructions
decoder extracts control fields
scheduler sequences execution
thread lanes execute in SIMT style
memory controller serializes LSU requests
warp stack supports divergence/reconvergence
```

The most important architectural concepts are:

```text
per-core SIMT execution
per-thread register/ALU/LSU/PC lanes
active_mask-controlled execution
per-core memory arbitration
packed response-data bus alignment
DCR-driven kernel launch
dispatcher-driven block scheduling
```
