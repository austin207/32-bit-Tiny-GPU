# 32-Bit Tiny GPU

A fully parameterized 32-bit GPU architecture implemented in SystemVerilog, built from scratch with a custom ISA, AXEL C assembler, cocotb-based verification, and an end-to-end neural network training and inference pipeline running on the simulated hardware. Synthesized and flashed to a Sipeed Tang Nano 20K FPGA.

---

## What This Is

This project implements a complete GPU stack entirely from scratch:

- Custom 32-bit ISA (21 instructions, 4 formats)
- SystemVerilog RTL with 12 modules, fully parameterized
- AXEL C assembler library that emits `.hex` kernels
- cocotb/Icarus Verilog simulation and verification suite
- A 4×4 linear layer neural network that trains on the GPU and runs inference
- Synthesized FPGA build targeting Sipeed Tang Nano 20K (GW2AR-18C QN88)

The GPU trains a matrix multiplication kernel over 20 epochs in Q8 fixed-point arithmetic, converges to within 2.5% of the target, and runs inference with a single `make infer`.

---

## Architecture Overview

![ISA Diagram](assets/Architecture-images/gpu_architecture.png)

**N** = NUM_CORES (default: 4)  
**T** = THREADS_PER_CORE (default: 4)  
**Total threads** = N × T (default: 16)

---

## Instruction Set Architecture (ISA)

32-bit fixed-width instructions. 6-bit opcode field. Four instruction formats:

![ISA Diagram](assets/Architecture-images/instruction_encoding.png)

### Opcode Table

| Opcode | Hex  | Instruction | Type | Description                              |
|--------|------|-------------|------|------------------------------------------|
| 000000 | 0x00 | NOP         | N    | No operation                             |
| 000001 | 0x01 | ADD         | R    | Rd = Rs1 + Rs2                           |
| 000010 | 0x02 | SUB         | R    | Rd = Rs1 − Rs2                           |
| 000011 | 0x03 | MUL         | R    | Rd = Rs1 × Rs2 (unsigned)                |
| 000100 | 0x04 | DIV         | R    | Rd = Rs1 / Rs2                           |
| 000101 | 0x05 | MOD         | R    | Rd = Rs1 % Rs2                           |
| 000110 | 0x06 | SHL         | R    | Rd = Rs1 << Rs2                          |
| 000111 | 0x07 | SHR         | R    | Rd = Rs1 >> Rs2 (logical)                |
| 001000 | 0x08 | AND         | R    | Rd = Rs1 & Rs2                           |
| 001001 | 0x09 | OR          | R    | Rd = Rs1 \| Rs2                          |
| 001010 | 0x0A | XOR         | R    | Rd = Rs1 ^ Rs2                           |
| 001011 | 0x0B | NOT         | R    | Rd = ~Rs1                                |
| 001100 | 0x0C | FMA         | R    | Rd = (Rs1 × Rs2) + Rs3                   |
| 001101 | 0x0D | CMP         | R    | Set NZP flags from Rs1 − Rs2             |
| 001110 | 0x0E | BRnzp       | B    | Branch if NZP condition met              |
| 001111 | 0x0F | LDR         | I    | Rd = Memory[Rs + imm]                    |
| 010000 | 0x10 | STR         | I    | Memory[Rs + imm] = Rd                    |
| 010001 | 0x11 | CONST       | I    | Rd = zero_extend(imm)                    |
| 010010 | 0x12 | RET         | N    | End thread block execution               |
| 010011 | 0x13 | IMUL        | R    | Rd = $signed(Rs1) × $signed(Rs2)         |
| 010100 | 0x14 | SAR         | R    | Rd = $signed(Rs1) >>> Rs2 (arithmetic)   |

IMUL and SAR were added to support Q8 fixed-point gradient computation. SHR fills with zeros, which corrupts the sign of negative gradients; SAR preserves it.

**BRnzp branch offset encoding**: the 23-bit `branch_offset` field is added directly to the PC as an unsigned value. Forward branches use the offset as-is. Backward branches must encode the offset as a two's complement negative number in 23 bits (e.g. a jump of −3 is encoded as `0x7FFFFD`).

---

## Register File

32 registers, 32-bit wide each.

| Register  | Purpose    | Description                                         |
|-----------|-----------|-----------------------------------------------------|
| R0        | Hardwired  | Always reads as 0; writes ignored                  |
| R1–R28    | General    | General purpose computation registers              |
| R29       | threadIdx  | Read-only; hardware-injected thread index in block |
| R30       | blockIdx   | Read-only; hardware-injected block index in grid   |
| R31       | blockDim   | Read-only; hardware-injected block dimension       |

---

## Module Breakdown

### 1. Register File (`register_file.sv`)
![Register File Diagram](assets/Images-Components/Register-page-00001.jpg)

32×32-bit register storage with one synchronous write port and three asynchronous read ports. The triple read allows FMA to read three source registers (Rs1, Rs2, Rs3) in a single cycle without stalling.

On reset, only R1–R28 are cleared. R0 has no physical storage — all three read ports return hardwired zero when R0 is addressed, and writes to R0 are silently ignored by the write-enable guard (`w_addr >= 1 && w_addr <= 28`).

R29, R30, and R31 are not stored in the register array either — they are driven directly from hardware-injected inputs:
- **R29 (threadIdx)**: returns `threadIdx` input normally, but returns `blockIdx` when `blockDim == 1`. This is the FPGA single-thread patch: with one thread per block, `blockIdx` serves as the effective thread index so each sequential block computes the correct output row without changing the kernel.
- **R30 (blockIdx)**: always returns the `blockIdx` input.
- **R31 (blockDim)**: always returns the `blockDim` input.

The `(* syn_dont_touch = 1 *)` attribute prevents synthesis tools from merging or eliminating register file instances.

### 2. ALU (`alu.sv`)
![ALU Diagram](assets/Images-Components/ALU-page-00001.jpg)

Purely combinational execution unit — no clock, no state. Takes three 32-bit operands and a 6-bit `op_select` (the raw opcode), outputs a 32-bit `result` and a 3-bit `nzp_flag`. Both default to zero if the opcode is not an ALU operation, so the ALU is always active but safe to ignore on non-ALU instructions.

Operations by category:

- **Arithmetic**: ADD, SUB, MUL (unsigned 32-bit), DIV, MOD
- **Shift**: SHL (logical left), SHR (logical right, zero-fills), SAR (arithmetic right, sign-extends — required for signed Q8 values)
- **Logic**: AND, OR, XOR, NOT (unary, only uses operand1)
- **Multiply-accumulate**: FMA — `result = (operand1 × operand2) + operand3`, single-cycle, no intermediate scaling. In Q8 usage, multiplying two Q8 values produces a Q16 result; the scale-down (SAR >>8) must be applied as a separate instruction after FMA.
- **Signed multiply**: IMUL — `$signed(operand1) × $signed(operand2)`, used for gradient computation where errors are signed Q8 values that MUL would misinterpret as large positive numbers
- **Compare**: CMP — computes `$signed(operand1) - $signed(operand2)`, writes nothing to `result`, only sets `nzp_flag`: N=`3'b100` (negative), Z=`3'b010` (zero), P=`3'b001` (positive)

NZP flag is only meaningful when the opcode is CMP; for all other operations it remains zero.

The `(* syn_dont_touch = 1 *)` attribute prevents synthesis tools from eliminating ALU instances it deems unreachable.

### 3. Program Counter (`pc.sv`)
![PC Diagram](assets/Images-Components/PC-page-00001.jpg)

Stores the current instruction address and an internal NZP condition register. Both are updated synchronously on the rising clock edge.

Two separate reset paths exist: `rst` (global reset, clears PC and NZP to zero) and `block_rst` (block-level reset, also clears both to zero). `block_rst` fires when the scheduler is in IDLE and `core_start` pulses, ensuring each new thread block begins fetching from instruction 0 rather than continuing from the previous block's RET address.

The NZP register is written only when `nzp_en` is asserted (set by the decoder on CMP instructions). The PC advances only when `pc_en` is asserted (set by the scheduler on the UPDATE→FETCH transition).

Crucially, the `nzp_en` and `pc_en` checks are written as two **independent `if` blocks** inside the same `always_ff`, not `else if`. This means both can fire in the same clock cycle — necessary when a CMP and BRnzp instruction sequence needs the NZP to be written and consumed correctly across pipeline stages.

Branch logic: if `branch_en` is asserted and `(nzp_reg & nzp_mask) != 0`, the PC takes a relative jump: `pc_out <= pc_out + branch_offset`. Otherwise it increments by 1. The 23-bit `branch_offset` is added directly (unsigned addition) so negative offsets must be encoded as two's complement in the 23-bit field.

### 4. Decoder (`decoder.sv`)
![Decoder Diagram](assets/Images-Components/Decoder-page-00001.jpg)

Purely combinational instruction decode — no clock, no state. All field extractions are done with continuous `assign` statements directly from bit ranges of the 32-bit instruction word:

- `opcode` = bits [31:26]
- `rd_addr` = bits [25:21]
- `rs1_addr` = bits [20:16]
- `rs2_addr` = bits [15:11]
- `rs3_addr` = bits [10:6]
- `imm` = bits [15:0] (overlaps rs2/rs3 fields in I-format)
- `nzp_mask` = bits [25:23] (B-format, overlaps rd field)
- `branch_offset` = bits [22:0] (B-format)

Control signal generation uses a case on `opcode` inside `always_comb`. All control signals default to zero; only the relevant ones are set per opcode group:

| Opcode group | Signals asserted |
|---|---|
| ALU ops (0x01–0x0C, 0x13, 0x14) | `write_back_en` |
| CMP (0x0D) | `nzp_en` |
| BRnzp (0x0E) | `branch_en` |
| LDR (0x0F) | `mem_read_en`, `write_back_en` |
| STR (0x10) | `mem_write_en` |
| CONST (0x11) | `write_back_en` |
| RET (0x12) | `ret` |
| NOP (0x00) | _(none)_ |

The decoder does not gate control signals based on pipeline state — that is the scheduler's job. It purely translates the instruction word into control intent.

### 5. Fetcher (`fetcher.sv`)
![Fetcher Diagram](assets/Images-Components/Fetcher-page-00001.jpg)

2-state FSM (IDLE / WAITING) that issues a single instruction fetch request to program memory and waits for the response. Uses a valid/ready handshake: the fetcher asserts `req_valid` with the PC address, then waits in WAITING until `resp_valid` comes back from memory.

In IDLE: when `core_en` is asserted by the scheduler, the fetcher latches the current PC value into `req_addr`, asserts `req_valid`, and transitions to WAITING.

In WAITING: the fetcher holds until `resp_valid` goes high. On that cycle it latches `resp_data` into `instruction`, pulses `done` for one cycle, and returns to IDLE. `req_valid` and `done` are both cleared to zero at the start of each cycle (default assignment), so they are naturally single-cycle pulses.

One fetcher exists per core and is shared across all threads in that core. Since execution is SIMD, all threads run the same instruction, so a single fetch is sufficient.

### 6. LSU — Load Store Unit (`lsu.sv`)
![LSU Diagram](assets/Images-Components/LSU-page-00001.jpg)

2-state FSM (IDLE / WAITING) that handles one memory transaction per instruction — either a load (LDR) or a store (STR). One LSU exists per thread, so all threads in a core can access memory independently in parallel.

In IDLE: when `core_en` is asserted by the scheduler:
- **LDR path**: sets `is_read=1`, asserts `req_valid`, sets `read_write_switch=1` (signals memory this is a read), latches the computed address into `req_addr`, transitions to WAITING.
- **STR path**: sets `is_read=0`, asserts `req_valid`, sets `read_write_switch=0` (signals a write), latches the computed address and the store data (`mem_write_data`) into `req_addr` and `write_data`, transitions to WAITING.

In WAITING: waits for `resp_valid`. On a read, latches `resp_data` into `mem_read_data`. On a write, nothing is captured (the data was already sent). Either way, `done` is pulsed and the FSM returns to IDLE.

`is_read` is explicitly set to `0` in the STR path (not just left undefined from prior state), preventing stale-read bugs if a write follows a read.

The store data (`mem_write_data`) is wired in the core to `reg_data3[i]`, which reads from the Rd register address via `r_addr3`. STR semantics: `Memory[Rs + imm] = Rd`, so Rd is both the address-base field in the instruction and the source of the data being written.

### 7. Memory Controller (`mem_controller.sv`)
![Memory Controller Diagram](assets/Images-Components/Memory%20Controller-page-00001.jpg)

Parameterized combinational pass-through with `TOTAL_THREADS = NUM_CORES × THREADS_PER_CORE` independent channels. Each channel is a direct wire mapping: LSU request signals (`req_avail`, `req_addr`, `read_write_switch`, `req_data`) pass straight through to the memory request interface, and memory response signals (`mem_resp_valid`, `mem_resp_data`) pass straight back to the LSU.

There is no arbitration, no clock, and no state. Every thread gets its own dedicated memory port — bandwidth scales linearly with thread count at the cost of requiring the memory to support TOTAL_THREADS simultaneous accesses.

The module has no `clk` or `rst` ports; round-robin arbitration is the planned upgrade path. Note: this module is tested standalone but is not instantiated in the top-level GPU — the top-level wires core data memory ports directly, making the pass-through implicit at the top level.

### 8. Scheduler (`scheduler.sv`)
![Scheduler Diagram](assets/Images-Components/Scheduler-page-00001.jpg)

7-state FSM that sequences the pipeline for one core. All output enables (`fetcher_en`, `lsu_en`, `execute_en`, `write_back_en`, `pc_en`, `block_done`) default to zero every cycle and are asserted only in specific states, making them naturally single-cycle pulses unless explicitly held.

```
IDLE    (000) — Wait for core_start; on assertion, assert fetcher_en and go to FETCH
FETCH   (001) — Hold fetcher_en=1; on fetcher_done, clear fetcher_en and go to DECODE
DECODE  (010) — Combinational route: if mem_read_en or mem_write_en → REQUEST, else → EXECUTE
REQUEST (011) — Pulse lsu_en=1 for one cycle, go to WAIT
WAIT    (100) — Stall until all_done (&lsu_done); go to EXECUTE
EXECUTE (101) — Pulse execute_en=1 for one cycle, go to UPDATE
UPDATE  (110) — Assert write_back_en=1; if ret: assert block_done=1, go to IDLE
                else: assert pc_en=1, go to FETCH
```

Key behaviours:
- **DECODE is zero-cycle**: no clock edge is consumed — the state transition is decided combinationally based on the decoded instruction already sitting in the registers. The FSM moves to REQUEST or EXECUTE on the very next edge.
- **`all_done`** is a bitwise AND reduction of `lsu_done` across all threads (`&lsu_done`). The FSM stays in WAIT until every thread's LSU has completed.
- **`pc_en` and `write_back_en` are both asserted together in UPDATE** (when not RET): register writeback and PC advance happen on the same clock edge.
- The scheduler broadcasts the same enables to all threads simultaneously — this is what enforces SIMD lockstep execution.

### 9. Core (`core.sv`)
![Core Diagram](assets/Images-Components/Core-page-00001.jpg)

The core is the main processing unit. It instantiates one each of Scheduler, Fetcher, Decoder, and PC (all shared across threads), and `THREADS_PER_CORE` instances each of ALU, LSU, and Register File (one per thread).

**Shared resources**: The single Fetcher uses the shared PC (`pc_shared`) to fetch the same instruction for all threads. The Decoder decodes that one instruction into control signals broadcast to all threads. The Scheduler drives all threads with the same enable signals each cycle. This is the SIMD execution model — all threads execute identical instructions, differing only in their data (threadIdx, register values, memory addresses).

**Per-thread datapath** (inside generate loop):
- Memory address: `mem_addr[i] = reg_data1[i] + sign_extend(imm)` — each thread computes its own address from its own Rs1 value plus the shared immediate.
- Write-back mux: `lsu_read_data[i]` on LDR, `{16'b0, imm}` on CONST (zero-extended), `alu_result[i]` otherwise.
- STR source: `r_addr3` is wired to `rd_addr` when `mem_write_en` is set, so the register named as Rd in the STR instruction is read as the store data (not written to).

**Branch decision**: The shared PC uses `nzp_result[0]` — thread 0's NZP flag — as the representative condition for the whole core. Since all threads run the same instructions, divergent branches are not supported; thread 0 is the tie-breaker.

**`pc_block_rst`**: asserted when `current_state == IDLE && core_start`. This resets the PC to 0 at the start of every new block dispatch, so block N+1 starts fetching from instruction 0.

**`thread_keep_alive`**: XOR of all per-thread `write_data` signals, chained through a generate loop and exposed as a primary output. Connecting this to an LED or top-level output forces synthesis tools to trace the entire thread datapath backward from the output, preventing dead-code elimination of threads 1–(N-1).

All per-thread signal arrays carry `(* syn_keep=1 *)` to prevent intermediate signal elimination by the Gowin synthesizer.

### 10. Dispatcher (`dispatcher.sv`)
![Dispatcher Diagram](assets/Images-Components/Dispatcher-page-00001.jpg)

Assigns thread blocks to idle cores and tracks when all blocks have completed. Operates entirely in a single `always_ff` block using a mix of blocking and non-blocking assignments.

**State tracked**:
- `next_block`: the index of the next unassigned block (starts at 0, increments each time a block is dispatched).
- `active_blocks`: count of blocks currently executing across all cores.

**Each clock cycle** (when `dispatch_en` is asserted):
1. Loops over all cores. For any core where `block_done[i]` is high: clears `core_start[i]` and decrements a local blocking variable `delta`.
2. Finds the first idle core (`core_start[i] == 0 && block_done[i] == 0`) where `next_block < num_blocks`. Assigns it the next block: sets `core_start[i]`, writes `blockIdx_out[i] = next_block`, increments `next_block` and `delta`.
3. `active_blocks <= active_blocks + delta` — the NBA update applies the net change atomically at the end of the always_ff evaluation.

**`kernel_done`** is asserted when `next_block == num_blocks` (all blocks dispatched) **and** `active_blocks + delta == 0` (all blocks finished). The `delta` term is included so kernel_done can fire on the same cycle the last block completes.

`assigned` and `delta` use blocking assignments because they are loop-local accumulators — they must take effect immediately within the iteration to correctly avoid double-assigning a core in the same cycle.

### 11. DCR — Device Control Register (`dcr.sv`)
![DCR Diagram](assets/Images-Components/DCR-page-00001.jpg)

Minimal host-facing configuration interface with three registers, written synchronously via a 2-bit address bus. The host (testbench or FPGA boot FSM) writes these registers before asserting `start` to launch a kernel.

| Address | Register | Description |
|---------|----------|-------------|
| `2'b00` (0x00) | `num_blocks` | Total number of thread blocks to dispatch |
| `2'b01` (0x01) | `blockDim` | Threads per block (injected into R31 of every thread) |
| `2'b10` (0x02) | `start` | Single-cycle pulse that triggers the dispatcher |

`start` is special: it is cleared to `0` at the top of every `always_ff` evaluation and only set to `1` when address `2'b10` is written. This makes it a self-clearing single-cycle pulse regardless of how long the host holds `dcr_write_en` high — unless the host continuously re-writes address `2'b10` every cycle, as the FPGA boot FSM does to keep `dispatch_en` asserted across all 4 sequential blocks.

### 12. Top-Level GPU (`top_level_gpu.sv`)
![GPU Diagram](assets/Images-Components/GPU-page-00001.jpg)

The top-level wires together the DCR, Dispatcher, and `NUM_CORES` Core instances into a complete GPU. It is the only module that sees both program memory and data memory interfaces simultaneously.

**Memory architecture**:
- Each core has its own independent program memory channel (`prog_mem_req_valid[i]`, `prog_mem_req_addr[i]`, etc.) — all cores can fetch different instructions simultaneously if running different blocks.
- Data memory is a flat array of `TOTAL_THREADS` channels (`data_mem_req_valid[TOTAL_THREADS-1:0]`, etc.) — each thread across all cores has its own dedicated data memory port.

**Generate loop**: For each core, a set of intermediate local wires is declared inside the generate block. This works around an Icarus Verilog limitation where unpacked array part-selects (e.g. `data_mem_req_addr[i*T+j]`) are not directly addressable via VPI in simulation. The intermediate wires are then connected to the top-level flat arrays with explicit `assign` statements.

**`thread_keep_alive`**: XOR of all per-core `thread_keep_alive` signals, again chained through a generate loop. The final XOR is the top-level `thread_keep_alive` output, which in the FPGA wrapper is OR'd into an LED output to anchor the entire thread datapath in synthesis.

---

## Parameters

| Parameter         | Default | Description                         |
|------------------|---------|-------------------------------------|
| NUM_CORES         | 4       | Number of parallel cores            |
| THREADS_PER_CORE  | 4       | Threads per core (SIMD width)       |
| TOTAL_THREADS     | 16      | NUM_CORES × THREADS_PER_CORE        |

To scale to 4 cores × 16 threads each:

```systemverilog
gpu #(
    .NUM_CORES(4),
    .THREADS_PER_CORE(16)
) gpu_inst ( ... );
```

---

## AXEL Assembler

![AXEL Architecture Diagram](assets/Architecture-images/software_layer_architecture.png)

AXEL is a C library that emits `.hex` kernel files for the GPU. It provides two layers: `gpu_asm` (low-level `emit_*` functions) and `axel` (higher-level kernel API with register name aliases).

### Build

```bash
cd assembler
make phase4    # compiles and emits builds/phase4_forward.hex
make phase5    # compiles and emits builds/phase5_weight_update.hex
make           # builds all phases
```

### Register aliases

```c
R0–R28        // general purpose
THREAD_IDX    // R29 — hardware-injected thread index
BLOCK_IDX     // R30 — hardware-injected block index
BLOCK_DIM     // R31 — hardware-injected block dimension
```

### Example kernel

```c
AxelGPU gpu;
axel_init(&gpu, 1, 4);

axel_ldr(&gpu, R1, THREAD_IDX, 0);   // R1 = mem[threadIdx]
axel_add(&gpu, R2, R1, R1);           // R2 = 2 * R1
axel_str(&gpu, R2, THREAD_IDX, 4);   // mem[threadIdx + 4] = R2
axel_ret(&gpu);

axel_compile(&gpu, "output.hex");
```

---

## Neural Network — End-to-End Training and Inference

The GPU trains a 4×4 linear layer with ReLU activation in Q8 fixed-point arithmetic using gradient descent.

### Q8 Fixed-Point Encoding

All values are stored as integers where `real_value = stored_int / 256`.

| Real value | Q8 raw |
|-----------|--------|
| 1.0       | 256    |
| 2.0       | 512    |
| −0.5      | 0xFFFFFF80 |

Q8 multiply produces Q16, which is scaled down by SAR >>8 back to Q8. The gradient step combines Q8 scale-down and learning rate into a single SAR >>12 (lr = 1/16 in Q8 space).

### Memory Layout

| Address   | Contents                        |
|-----------|---------------------------------|
| 0–15      | W[4][4] — weights (Q8), W[i][j] at addr i×4+j |
| 16–19     | x[4] — input vector (Q8)        |
| 20–23     | y[4] — forward pass output (Q8) |
| 24–27     | t[4] — target vector (Q8)       |

### Kernel Phases

| Phase | File                     | Instructions | What it does                         |
|-------|--------------------------|-------------|--------------------------------------|
| 1     | `phase1_ldr_test.c`      | 4           | LDR/STR end-to-end smoke test        |
| 2     | `phase2_matmul.c`        | 19          | 4×4 matrix-vector multiply           |
| 3     | `phase3_relu.c`          | 8           | Branchless ReLU via bit masking      |
| 4     | `phase4_forward.c`       | 26          | Linear layer + ReLU in Q8            |
| 5     | `phase5_weight_update.c` | 36          | Gradient descent weight update in Q8 |

### Training Results

```
x (real) = [1.0, 2.0, 3.0, 4.0]
t (real) = [2.0, 4.0, 6.0, 8.0]  (target: W ≈ 2×I)

Epoch  1 | y=[1.0, 1.99, 3.0, 3.99] | err=[-1.0, -2.0, -3.0, -4.0]
Epoch 10 | y=[1.76, 3.55, 5.34, 7.14] | err=[-0.24, -0.45, -0.66, -0.86]
Epoch 20 | y=[1.95, 3.94, 5.94, 7.94] | err=[-0.05, -0.06, -0.06, -0.06]

Final W diagonal ≈ [1.06, 1.14, 1.29, 1.50]
```

Residual ~0.05 error is the Q8 quantization floor (1/256 ≈ 0.004 per gradient step). The network converges and stays there.

### Inference

```bash
cd Src/Top_level_GPU
make infer
```

Output:

```
=============================================
  Input  (Q8 raw) : [256, 512, 768, 1024]
  Input  (real)   : [1.0, 2.0, 3.0, 4.0]
=============================================
  Output (Q8 raw) : [499, 1010, 1523, 2035]
  Output (real)   : [1.9492, 3.9453, 5.9492, 7.9492]
=============================================
```

Trained weights persist in `assembler/builds/weights.json` between runs. The training loop loads them automatically on next `make`. Note: `weights.json` is gitignored and must be regenerated by running `make` in `Src/Top_level_GPU/` on a fresh clone.

---

## FPGA — Sipeed Tang Nano 20K

The GPU has been synthesized and flashed to a Sipeed Tang Nano 20K (GW2AR-18C QN88, 20K LUTs).

### FPGA Configuration

The FPGA build uses a reduced configuration for area reasons:

| Parameter         | Simulation | FPGA        |
|------------------|------------|-------------|
| NUM_CORES         | 4          | 1           |
| THREADS_PER_CORE  | 4          | 1           |
| num_blocks        | 1          | 4           |
| Execution model   | Parallel   | Sequential  |

With a single thread, R29 returns `blockIdx` when `blockDim == 1` (patched in `gpu_combined.v`), so each of the 4 sequential blocks computes one output neuron: `y[blockIdx]`. The result is numerically identical to the 4×4 simulation.

### FPGA-Specific Modifications (`gpu_combined.v`)

The `fpga/gpu_combined.v` file differs from the original `.sv` sources in the following ways:

- **Shared PC**: A single `pc` instance replaces the per-thread generate loop. All threads are SIMD and share one program counter; branch decision uses `nzp_result[0]` as representative.
- **R29 patch**: `registers.sv` read ports return `blockIdx` when `blockDim == 1`, enabling single-thread blocks to use `blockIdx` as their thread index.
- **`thread_keep_alive` port**: An XOR reduction of all thread `write_data` signals, added as a primary output to prevent synthesis tools from sweeping thread logic as dead code.
- **`(* syn_keep=1 *)`**: Applied to per-thread signal arrays to prevent incorrect dead logic elimination by Gowin synthesizer.
- **`$dumpfile`/`$dumpvars` removed**: Simulation-only; breaks synthesis.

### Pin Assignments (Tang Nano 20K)

| Signal    | Pin | Notes                              |
|-----------|-----|------------------------------------|
| clk       | 52  | 27 MHz onboard oscillator          |
| led[0]    | 10  | kernel_done indicator (active-LOW) |
| led[1]    | 11  | Heartbeat blink (active-LOW)       |
| led[2]    | 13  |                                    |
| led[3]    | 14  |                                    |
| led[4]    | 15  |                                    |
| led[5]    | 16  |                                    |
| uart_tx   | 69  | 115200 8N1 → BL616 USB-UART bridge |

### UART Output

After flashing, open the higher-numbered COM port at 115200 baud. Output:

```
GPU DONE
T:XXXXXXXX   (clk_slow cycles to kernel_done)
Y: YYYYYYYY YYYYYYYY YYYYYYYY YYYYYYYY  (Q8 hex, divide by 256 for real value)
```

### Toolchain

```
WSL (Ubuntu)               Windows
────────────────────────   ──────────────────────────
sv2v → gpu_combined.v      Gowin EDA Education Edition
iverilog + cocotb → test   Zadig (WinUSB driver, one-time)
```

Gowin EDA project settings: Device = GW2AR-18C QN88, Verilog Language = SystemVerilog 2017.

---

## Silicon — Sky130A ASIC Synthesis

The full 4-core 4-thread GPU has been synthesized through the complete RTL-to-GDSII flow using OpenLane 2.3.10 targeting the SkyWater Sky130A open-source 130nm PDK.

### Layout

![GPU Layout](assets/gds/gpu_layout.png)

The layout above shows the complete chip with all metal layers visible (poly, li1, met1 through met5). The four parallel compute cores are visible as distinct regions in the dense logic area.

### Results

| Metric | Value |
|--------|-------|
| Standard cells | 204,938 |
| Chip area | 1.977 mm² |
| Flip-flops | 16,138 |
| Clock target | 40 MHz (25ns period) |
| Worst setup slack | +8.01ns (timing met) |
| Max achievable frequency | ~59 MHz |
| Total negative slack | 0 ps |
| LVS result | Passed (171,278 devices, 171,969 nets matched) |
| PDK | SkyWater Sky130A (130nm) |
| Tool | OpenLane 2.3.10 / OpenROAD |

### The Road to GDS — Three Days of Decisions

Getting a 204k-cell GPU through the full open-source ASIC flow was not straightforward. This section documents every failure, root cause, and fix in the order they were discovered.

**RTL preparation**

Before synthesis, two changes were made to `gpu_combined.v`. The DIV and MOD operators synthesize to deep combinational dividers that prevent timing closure — both were replaced with `32'b0` and documented as multi-cycle paths planned for a future iterative divider implementation. All `$dumpfile` and `$dumpvars` calls were already removed from the FPGA combined file. Everything else synthesized cleanly with zero linter errors.

**OpenLane 1 — synthesis passed, routing did not**

The first runs used OpenLane 1 (image `ff5509f`). Synthesis completed successfully in every run, producing consistent results: 204,938 cells, 1.977mm², +8.01ns slack. The problem was entirely in physical implementation.

Placement failed first with `GPL-0302` (density too low). Increasing `PL_TARGET_DENSITY` from 0.35 to 0.55 and `FP_CORE_UTIL` to 50 fixed placement, and runs 1 through 12 passed cleanly including clock tree synthesis.

Global routing then failed with `GRT-0119` (congestion too high). The root cause was the placement resizer: it was inserting 44,920 timing repair buffers post-placement, bloating the design from 204k to 293k cells before the router saw it. Disabling all four resizer passes (`GLB_RESIZER_DESIGN_OPTIMIZATIONS`, `GLB_RESIZER_TIMING_OPTIMIZATIONS`, `PL_RESIZER_DESIGN_OPTIMIZATIONS`, `PL_RESIZER_TIMING_OPTIMIZATIONS`) stopped the bloat. Dropping `GRT_ADJUSTMENT` from the default 0.30 to 0.10 gave the router 90% of available metal tracks instead of 70%.

After those fixes, global routing passed with 0/0/0 overflow on all layers, 169,343 nets routed, 28.58% total track usage. But the OpenROAD process then crashed with a segmentation fault at address `0x0000000000D3C6C7` — the same address in every run, indicating a deterministic code bug in the FastRoute implementation in that specific OpenROAD binary. No configuration change can fix a code bug.

**WSL2 hardware instability**

Several runs on Windows WSL2 ended in hard system hangs. The cause was a combination of factors: WSL2 defaulting to 15GB RAM on a 32GB machine (insufficient for TritonRoute peak usage), NVIDIA overlay process conflicts, and AMD integrated GPU driver crashes (`amdkmdag.sys`) under sustained memory pressure. WSL2 memory was increased to 24GB via `.wslconfig`, NVIDIA overlay was disabled, and Docker cores were reduced to avoid peak memory spikes. The system still crashed. WSL2 was abandoned.

**OpenLane 2 on native Ubuntu**

Switching to native Ubuntu dualboot eliminated all hardware instability immediately. With no WSL2 overhead, the full 32GB was available directly to Docker.

OpenLane 1 was frozen at `ff5509f` with no newer image. The successor is OpenLane 2 (`efabless/openlane2:2.3.10`), which uses a significantly newer OpenROAD binary. The segfault at the same address never appeared again.

The resizer issue resurfaced in OpenLane 2 in a different form: the default flow inserted 36,465 timing repair buffers and 8,455 hold buffers post-CTS, again bloating cell count to 293k before global routing. With the design already having +8.01ns slack at synthesis, these optimizations were unnecessary and actively harmful. All resizers were disabled.

Global routing passed cleanly in OpenLane 2 with the same 0/0/0 overflow result as before. The run then crashed during the post-routing antenna violation report generation inside the OpenROAD script. The fix was disabling the antenna checker (`GRT_ANTENNA_ITERS: 0`) and resuming directly from the saved global routing state into detailed routing.

Detailed routing (TritonRoute) ran for approximately 5 hours on 1 thread to avoid memory pressure, then completed. DRC showed 5 Magic and 1 KLayout violation — minor metal spacing issues from the open-source router, not functional failures. LVS passed perfectly with all 171,278 devices and 171,969 nets matched. GDS was generated.

**Final working OpenLane 2 config**

```json
{
    "DESIGN_NAME": "gpu",
    "VERILOG_FILES": "dir::src/*.v",
    "CLOCK_PORT": "clk",
    "CLOCK_NET": "clk",
    "CLOCK_PERIOD": 25,
    "FP_CORE_UTIL": 25,
    "PL_TARGET_DENSITY_PCT": 35,
    "SYNTH_STRATEGY": "AREA 0",
    "MAX_FANOUT_CONSTRAINT": 8,
    "RUN_POST_GPL_DESIGN_REPAIR": false,
    "RUN_POST_CTS_RESIZER_TIMING": false,
    "GRT_RESIZER_DESIGN_OPTIMIZATIONS": false,
    "GRT_RESIZER_TIMING_OPTIMIZATIONS": false,
    "GRT_ADJUSTMENT": 0.1,
    "DRT_THREADS": 1,
    "PDK": "sky130A",
    "STD_CELL_LIBRARY": "sky130_fd_sc_hd"
}
```

**Key lessons**

The single most impactful discovery was that the OpenLane resizer, when left enabled on a design with substantial positive slack, produces a net negative result: it adds tens of thousands of buffers that congest routing without meaningfully improving timing. Disabling all resizers and routing the synthesized netlist directly was the correct approach for this design.

The second lesson: OpenLane 1 is frozen. For any new design targeting Sky130, OpenLane 2 with Docker is the correct starting point. The newer OpenROAD binary eliminated the deterministic segfault that blocked every OpenLane 1 routing attempt.

The third lesson: open-source ASIC flows are not designed for 200k+ cell designs on consumer hardware. The flow completed, but required careful management of memory limits, parallelism, and step-by-step resumption. Professional tools handle this scale routinely. The synthesis and GDS results are real Sky130 numbers regardless of the tooling path taken to produce them.

## Project Structure

```
gpu-project/
├── README.md
├── .gitignore
├── assembler/
│   ├── Makefile
│   ├── include/
│   │   ├── axel.h
│   │   └── gpu_asm.h
│   ├── src/
│   │   ├── axel.c
│   │   └── gpu_asm.c
│   ├── examples/
│   │   ├── phase1_ldr_test.c
│   │   ├── phase2_matmul.c
│   │   ├── phase3_relu.c
│   │   ├── phase4_forward.c
│   │   └── phase5_weight_update.c
│   └── builds/
│       ├── phase4_forward.hex
│       ├── phase5_weight_update.hex
│       └── weights.json              ← gitignored; regenerated by make
├── fpga/
│   ├── gpu_combined.v                ← sv2v output + FPGA modifications
│   ├── gpu_fpga_top.sv               ← FPGA wrapper (BRAM, DCR sequencer, UART)
│   ├── prog_mem.hex                  ← phase4_forward kernel (BRAM init)
│   ├── data_mem.hex                  ← trained weights + x/t vectors (BRAM init)
│   └── constraints/
│       └── gpu_top.cst               ← pin assignments for Tang Nano 20K
└── Src/
    ├── alu/
    ├── registers/
    ├── pc/
    ├── decoder/
    ├── fetcher/
    ├── lsu/
    ├── memory_controller/
    ├── scheduler/
    ├── core/
    ├── dispatcher/
    ├── device_control_register/
    └── Top_level_GPU/
        ├── top_level_gpu.sv
        ├── test_top_level_gpu.py
        ├── inference.py
        └── Makefile
```

---

## Prerequisites

- [Icarus Verilog](https://steveicarus.github.io/iverilog/) v12.0+
- Python 3.10+
- [cocotb](https://www.cocotb.org/) v2.0+
- GCC (for assembler)
- GTKWave (optional, for waveform viewing)
- [sv2v](https://github.com/zachjs/sv2v) (for FPGA synthesis)
- Gowin EDA Education Edition (for Tang Nano 20K synthesis and flashing)

### Install cocotb

```bash
python3 -m venv cocotb-env
source cocotb-env/bin/activate
pip install cocotb
```

---

## Running Tests

Each module has its own Makefile:

```bash
source ~/cocotb-env/bin/activate
cd Src/<module_name>
make
```

### Test Results

| Module              | Tests | Status  |
|---------------------|-------|---------|
| Register File       | 4     | ✅ PASS |
| ALU                 | 6     | ✅ PASS |
| Program Counter     | 5     | ✅ PASS |
| Decoder             | 4     | ✅ PASS |
| Fetcher             | 3     | ✅ PASS |
| LSU                 | 3     | ✅ PASS |
| Memory Controller   | 3     | ✅ PASS |
| Scheduler           | 3     | ✅ PASS |
| Core                | 1     | ✅ PASS |
| Dispatcher          | 3     | ✅ PASS |
| DCR                 | 3     | ✅ PASS |
| Top-Level GPU       | 1     | ✅ PASS |

---

## Design Decisions

**Why separate NZP register in the PC module?**
The NZP flag is only consumed by BRnzp for PC updates. Keeping it co-located with the PC avoids routing flag state across module boundaries. Independent `if` blocks (not `else if`) in pc.sv ensure NZP can be written and PC can advance in the same cycle.

**Why 1:1 memory controller mapping?**
Simplicity for the initial implementation. The memory controller is designed for round-robin arbitration as a future upgrade — `clk` and `rst` are already stubbed out with comments.

**Why is the memory controller not instantiated in the top-level GPU?**
The current `mem_controller.sv` is a combinational pass-through — every output is a direct `assign` of its corresponding input. Inserting it into the top-level hierarchy would add a module boundary with no functional effect. It is developed and tested standalone so the round-robin arbitration upgrade can be dropped in without touching the top-level wiring. Once arbitration logic exists, the module connects between the cores and the external memory ports.

**Why `write_back_en_sched` vs `write_back_en_dec`?**
The decoder's `write_back_en` indicates whether the instruction type requires a writeback. The scheduler's version is the actual enable signal gated by pipeline timing, allowing the scheduler to control writeback independently of instruction type.

**Why blocking assignments for `assigned` and `delta` in the dispatcher?**
These are loop-local accumulators within a single `always_ff` evaluation. Blocking assignments ensure they take effect immediately within the loop iteration, preventing NBA race conditions when assigning multiple cores in one cycle.

**Why IMUL instead of MUL for gradient computation?**
MUL treats operands as unsigned. Gradient errors are signed Q8 values — a negative error like `−0.25` (0xFFFFFFC0 in two's complement) would be interpreted as a large positive number by MUL, giving completely wrong weight updates. IMUL uses `$signed` casting on both operands.

**Why SAR instead of SHR?**
SHR fills vacated bits with 0. On a negative product (negative gradient), SHR would produce a large positive number instead of a small negative one. SAR sign-extends, preserving the sign across the scale-down.

**Why branchless ReLU?**
The GPU is SIMD — all threads in a core execute the same instruction. If threads branch differently (some positive, some negative), only thread 0's outcome drives the PC, corrupting all other threads. The branchless bit-mask approach computes `max(0, x)` arithmetically, with no branch divergence.

**Why a shared PC for the FPGA build?**
With THREADS_PER_CORE=1, there is no parallelism benefit from per-thread PCs. Synthesis tools treated the three non-thread-0 PCs as dead logic and swept them, corrupting addresses. A single shared PC with `nzp_result[0]` as branch input is architecturally correct for SIMD and eliminates the sweep problem.

---

## Known Limitations

- Icarus Verilog does not support unpacked array part-selects — intermediate wires used as workaround in the top-level generate block
- Memory controller is a pass-through with no arbitration — round-robin planned
- `memory_controller.sv` is not instantiated in `top_level_gpu.sv` — cores wire directly to memory ports (equivalent to pass-through at current implementation stage)
- Fetcher is shared per core and uses thread 0's PC only (SIMD intentional; multi-PC fetch not supported)
- No hazard detection or pipeline stalling between back-to-back instructions
- Decoder generates ~32 "constant selects in always_*" warnings from Icarus (cosmetic — simulation correct; fix: move static field assignments to `assign` statements outside `always_comb`)
- FPGA build uses NUM_CORES=1, THREADS_PER_CORE=1 — runs 4 blocks sequentially, not in parallel

---

## Future Work

- Round-robin arbitration in Memory Controller
- Decoder warning fix (move static field decodes to `assign`)
- Higher Q-scale (Q10 = 1024 base) for ~0.001 precision floor vs current ~0.004
- Python AXEL runtime: write kernels in clean Python syntax, emit `.hex` directly
- Scale FPGA build to NUM_CORES=4, THREADS_PER_CORE=4 (full parallel configuration)
- UVM-based verification environment

---

## Author

**Austin Antony**  
B.Tech Applied Electronics and Instrumentation Engineering  
Rajagiri School of Engineering and Technology (2023–2027)  
CTO & Co-founder, Virtusco